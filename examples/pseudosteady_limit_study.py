"""Continuation from the paper's transient model toward the pseudosteady limit.

The paper-reference models in :mod:`lyopronto.pyomo_models.paper_ocp` discretize
a 1D *transient* PDE for the frozen region. LyoPRONTO's own primary-drying path
treats that region as pseudosteady, balancing shelf conduction against interface
conduction algebraically with no time derivative of the temperature field. This
study measures how much that formulation choice is worth for the paper's vial.

The frozen heat capacity ``Cp_f`` enters ``paper_ocp`` only through the
transient term: it sits in the denominators of the radiation and source terms
and inside the diffusivity ``alpha = k / (rho Cp)``. Scaling it by ``f``
therefore scales the whole temperature right-hand side by ``1/f``, which is
equivalent to solving

    f * dT/dt = RHS(T, S)

so ``f = 1`` is the paper's model and ``f -> 0`` approaches the pseudosteady
formulation. The interface mass balance, vapour-pressure correlation, cake
resistance, and shelf boundary condition are all independent of ``Cp_f``, so the
ladder varies the formulation and nothing else.

Two things make this useful beyond the physics question. Each rung is a
progressively stiffer NLP built from one physical parameter, and the lower rungs
sit past what the current solver stack handles, so the ladder doubles as a set
of solver-comparison instances with a recorded baseline. ``--solver-executable``
runs the same models under a different NLP binary without touching model code:
any solver following the AMPL ``<solver> <stub> -AMPL`` convention works, which
includes POUNCE.

Cold starts fail below ``f = 1``, so every rung warm starts from the previous
converged solution. A failure is recorded and ends that problem's ladder rather
than aborting the study, because where the ladder stops is itself the result.

Run from the repository root::

    python -m examples.pseudosteady_limit_study
    python -m examples.pseudosteady_limit_study --solver-executable /path/to/pounce
"""

from __future__ import annotations

import argparse
import dataclasses
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from lyopronto.pyomo_models import paper_ocp

#: Heat-capacity scale factors, descending toward the pseudosteady limit.
DEFAULT_LADDER: tuple[float, ...] = (1.0, 0.5, 0.2, 0.1, 0.05, 0.02, 0.01)

#: Paper problems covered by the study.
PROBLEMS: tuple[str, ...] = ("problem1", "problem2")

#: Iteration budget per rung. Deliberately generous: a rung that fails should
#: fail because the solver cannot make progress, not because it ran out of room.
DEFAULT_SOLVER_OPTIONS: dict[str, Any] = {"max_iter": 10000}


#: Constraint violation above which a rung is reported as accepted rather than
#: converged. IPOPT's ``acceptable_tol`` defaults to 1e-3 here, and a solve that
#: stops at that level exits ``Solved To Acceptable Level`` while Pyomo still
#: reports ``termination_condition: optimal``. Termination alone therefore
#: cannot distinguish the two, so the study records the violation itself.
FEASIBILITY_TOL = 1.0e-6


@dataclasses.dataclass(frozen=True)
class RungResult:
    """One solve at one heat-capacity scale."""

    problem: str
    factor: float
    conduction_time_s: float
    converged: bool
    endpoint_hr: float | None = None
    max_product_temperature_K: float | None = None
    termination_condition: str | None = None
    solver_status: str | None = None
    max_constraint_violation: float | None = None
    max_landau_cleared_violation: float | None = None
    solver_message: str | None = None
    failure: str | None = None

    @property
    def feasible(self) -> bool | None:
        """Whether the returned point satisfies the constraints to tolerance.

        ``None`` when no solution was returned. A rung can report a successful
        termination and still be infeasible at this tolerance; that gap is the
        reason this field exists.
        """
        if self.max_landau_cleared_violation is None:
            return None
        return self.max_landau_cleared_violation <= FEASIBILITY_TOL

    def as_dict(self) -> dict[str, Any]:
        record = dataclasses.asdict(self)
        record["feasible"] = self.feasible
        return record


def scaled_config(factor: float) -> paper_ocp.PaperPrimaryDryingConfig:
    """Return the paper config with the frozen heat capacity scaled by ``factor``.

    ``frozen_heat_capacity`` is a linear mixture of the solute and ice values, so
    scaling both components scales it exactly.
    """
    if not factor > 0.0:
        raise ValueError("heat-capacity scale factor must be positive")
    base = paper_ocp.PaperPrimaryDryingConfig()
    return dataclasses.replace(
        base,
        solute_heat_capacity=base.solute_heat_capacity * factor,
        ice_heat_capacity=base.ice_heat_capacity * factor,
    )


def conduction_time_s(config: paper_ocp.PaperPrimaryDryingConfig, n_z: int) -> float:
    """Return ``H^2 / alpha`` for the frozen layer at full thickness."""
    derived = paper_ocp.derive_primary_drying_parameters(config, n_z=n_z)
    return derived.product_height**2 / derived.frozen_diffusivity


def _solver_report(solution: Mapping[str, Any]) -> tuple[str | None, str | None]:
    metadata = solution.get("metadata", {})
    return metadata.get("termination_condition"), metadata.get("status")


def max_constraint_violation(model: Any) -> float:
    """Return the largest constraint violation of the loaded solution.

    Measured on the model itself rather than taken from the solver, so the
    number does not depend on what the solver chose to call success. Matches
    IPOPT's own reported ``Constraint violation`` where both are available.
    """
    import pyomo.environ as pyo  # imported here so the module stays import-light

    worst = 0.0
    for constraint in model.component_data_objects(pyo.Constraint, active=True):
        try:
            body = pyo.value(constraint.body)
        except (ValueError, TypeError):
            # An unset variable means no solution was loaded for this block.
            continue
        violation = 0.0
        if constraint.lower is not None:
            violation = max(violation, pyo.value(constraint.lower) - body)
        if constraint.upper is not None:
            violation = max(violation, body - pyo.value(constraint.upper))
        worst = max(worst, violation)
    return worst


def max_landau_cleared_violation(model: Any) -> float:
    """Return the largest ``temperature_ode`` residual with the Landau factor cleared.

    The frozen-region equations live on ``psi = (z - S)/(H - S)``, so their
    conduction term carries ``1/(H - S)^2``. As the front approaches the vial
    bottom that factor grows by four orders of magnitude, reaching about
    7.7e8 at the terminal cutoff, and an absolute residual of 1e-4 there is a
    relative residual near 1e-13.

    IPOPT's convergence test is absolute, so it reports these solves as
    ``Solved To Acceptable Level`` however well converged they are. Multiplying
    each residual by ``(H - S)^2`` measures it in the units where the conduction
    term is order one, which is the number that actually says whether the
    equation is satisfied.

    Note this is a reporting measure only. Multiplying the *constraints*
    through by the same factor makes IPOPT report ``Optimal Solution Found`` on
    a bit-identical solution whose residual on the original equation is no
    better, so it changes the label rather than the answer.
    """
    import pyomo.environ as pyo  # type: ignore[import-untyped]

    ode = getattr(model, "temperature_ode", None)
    if ode is None:
        return float("nan")
    height = model._paper_derived.product_height

    worst = 0.0
    for index in ode:
        constraint = ode[index]
        try:
            residual = abs(pyo.value(constraint.body))
            thickness = height - pyo.value(model.S[index[-1]])
        except (ValueError, TypeError):
            continue
        worst = max(worst, residual * thickness**2)
    return worst


def run_ladder(
    problem: str,
    *,
    discretization: paper_ocp.PaperDiscretization | None = None,
    ladder: Sequence[float] = DEFAULT_LADDER,
    solver: str = "ipopt",
    solver_executable: str | None = None,
    solver_options: Mapping[str, Any] | None = None,
) -> list[RungResult]:
    """Walk one problem down the ladder, warm starting each rung from the last."""
    if problem not in PROBLEMS:
        raise ValueError(f"unsupported paper problem: {problem!r}")
    discretization = discretization or paper_ocp.PaperDiscretization(
        n_z=20, nfe=36, ncp=3
    )
    options = dict(DEFAULT_SOLVER_OPTIONS)
    if solver_options:
        options.update(solver_options)
    solve = getattr(paper_ocp, f"solve_paper_{problem}")

    results: list[RungResult] = []
    warm_start: Mapping[str, Any] | None = None
    for factor in ladder:
        config = scaled_config(factor)
        tau = conduction_time_s(config, discretization.n_z)
        try:
            solution = solve(
                config=config,
                discretization=discretization,
                initialization=warm_start,
                solver=solver,
                solver_executable=solver_executable,
                solver_options=options,
                return_model=True,
            )
        except Exception as exc:  # noqa: BLE001 - a failed rung is a recorded result
            results.append(
                RungResult(
                    problem=problem,
                    factor=factor,
                    conduction_time_s=tau,
                    converged=False,
                    failure=f"{type(exc).__name__}: {exc}",
                )
            )
            break
        warm_start = solution
        termination, status = _solver_report(solution)
        results.append(
            RungResult(
                problem=problem,
                factor=factor,
                conduction_time_s=tau,
                converged=True,
                endpoint_hr=float(solution["states"]["time_hr"][-1]),
                max_product_temperature_K=float(
                    solution["metrics"]["max_product_temperature_K"]
                ),
                termination_condition=termination,
                solver_status=status,
                max_constraint_violation=max_constraint_violation(solution["model"]),
                max_landau_cleared_violation=max_landau_cleared_violation(
                    solution["model"]
                ),
            )
        )
    return results


def endpoint_shift_percent(results: Sequence[RungResult]) -> float | None:
    """Return the percentage change in endpoint from the first rung to the last."""
    converged = [r for r in results if r.converged and r.endpoint_hr is not None]
    if len(converged) < 2:
        return None
    first, last = converged[0], converged[-1]
    return (last.endpoint_hr - first.endpoint_hr) / first.endpoint_hr * 100.0


def run_study(
    *,
    problems: Sequence[str] = PROBLEMS,
    ladder: Sequence[float] = DEFAULT_LADDER,
    solver: str = "ipopt",
    solver_executable: str | None = None,
    discretization: paper_ocp.PaperDiscretization | None = None,
) -> dict[str, list[RungResult]]:
    """Run the ladder for each problem and return the per-problem results."""
    return {
        problem: run_ladder(
            problem,
            discretization=discretization,
            ladder=ladder,
            solver=solver,
            solver_executable=solver_executable,
        )
        for problem in problems
    }


def format_results(results: Mapping[str, Sequence[RungResult]]) -> str:
    """Render the study as a short text table."""
    lines: list[str] = []
    for problem, rungs in results.items():
        lines.append(problem)
        for rung in rungs:
            if rung.converged:
                if rung.feasible is None:
                    # No residual recorded: say so rather than implying a verdict.
                    residuals = "viol=n/a cleared=n/a (not measured)"
                else:
                    verdict = "feasible" if rung.feasible else "ACCEPTED ONLY"
                    residuals = (
                        f"viol={rung.max_constraint_violation:.2e} "
                        f"cleared={rung.max_landau_cleared_violation:.2e} ({verdict})"
                    )
                lines.append(
                    f"  f={rung.factor:<6g} tau={rung.conduction_time_s:8.3f} s  "
                    f"endpoint={rung.endpoint_hr:.4f} hr  "
                    f"maxT={rung.max_product_temperature_K:.4f} K  "
                    f"{rung.termination_condition}/{rung.solver_status}  "
                    f"{residuals}"
                )
            else:
                lines.append(
                    f"  f={rung.factor:<6g} tau={rung.conduction_time_s:8.3f} s  "
                    f"DID NOT CONVERGE: {rung.failure}"
                )
        shift = endpoint_shift_percent(rungs)
        if shift is not None:
            converged = [r for r in rungs if r.converged]
            lines.append(
                f"  endpoint moved {shift:+.3f}% from f={converged[0].factor:g} "
                f"to f={converged[-1].factor:g}"
            )
    return "\n".join(lines)


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--solver", default="ipopt", help="Pyomo solver name")
    parser.add_argument(
        "--solver-executable",
        default=None,
        help="Path to the solver binary; any AMPL-convention NLP solver works",
    )
    parser.add_argument(
        "--problem", action="append", choices=PROBLEMS, dest="problems"
    )
    parser.add_argument("--n-z", type=int, default=20)
    parser.add_argument("--nfe", type=int, default=36)
    parser.add_argument("--ncp", type=int, default=3)
    parser.add_argument("--output", type=Path, default=None, help="write JSON here")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    results = run_study(
        problems=args.problems or PROBLEMS,
        solver=args.solver,
        solver_executable=args.solver_executable,
        discretization=paper_ocp.PaperDiscretization(
            n_z=args.n_z, nfe=args.nfe, ncp=args.ncp
        ),
    )
    print(format_results(results))
    if args.output is not None:
        payload = {
            "solver": args.solver,
            "solver_executable": args.solver_executable,
            "discretization": {"n_z": args.n_z, "nfe": args.nfe, "ncp": args.ncp},
            "results": {
                problem: [rung.as_dict() for rung in rungs]
                for problem, rungs in results.items()
            },
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, indent=2))
        print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
