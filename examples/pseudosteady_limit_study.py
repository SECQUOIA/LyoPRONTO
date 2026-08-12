"""Continuation from the paper's transient model toward the pseudosteady limit.

The paper-reference models in :mod:`lyopronto.pyomo_models.paper_ocp` discretize
a 1D *transient* PDE for the frozen region. LyoPRONTO's own primary-drying path
treats that region as pseudosteady, balancing shelf conduction against interface
conduction algebraically with no time derivative of the temperature field. This
study measures how much that formulation choice is worth for the paper's vial.

Scaling the frozen heat capacity ``Cp_f`` by ``f`` scales the thermal inertia of
the frozen layer relative to conduction and the surface fluxes. In fixed
(physical) coordinates the energy balance

    rho_f Cp_f dT/dt|_z = k_f d2T/dz2 + Q

becomes ``f rho_f Cp_f dT/dt|_z = k_f d2T/dz2 + Q``, so ``f = 1`` is the paper's
model and ``f -> 0`` recovers the pseudosteady balance ``0 = k_f d2T/dz2 + Q``.
That limit is what the ladder walks toward.

The transformed right-hand side does **not** scale uniformly, and it is worth
being precise about why. ``paper_ocp`` solves on the Landau coordinate
``psi = (z - S)/(H - S)``, so ``temperature_rhs`` is

    diffusion + convection - side_loss + source

where ``diffusion``, ``side_loss`` and ``source`` carry ``1/(rho_f Cp_f)`` and
therefore scale by ``1/f``, while ``convection``, the moving-coordinate term
``-((psi - 1) dS/dt / (H - S)) dT/dpsi``, is kinematic and independent of
``Cp_f``. So

    f * rhs(scaled) = rhs(base) + (f - 1) * convection

rather than ``f * rhs(scaled) = rhs(base)``. Setting ``dS/dt = 0`` makes the
relation exact, which is what
``tests/test_pseudosteady_limit_study.py`` pins. For this vial the moving-front
term is small: with ``f = 0.25`` and a nonuniform profile the residual mismatch
is about 2.4e-4 against right-hand sides of order 40, so roughly 1e-5 relative.
The ``f -> 0`` limit is unaffected, because the ``1/f`` terms dominate and force
the pseudosteady balance regardless of the kinematic term.

Two things make this useful beyond the physics question. Each rung is a
progressively stiffer NLP built from one physical parameter, and the lower rungs
sit past what the current solver stack handles, so the ladder doubles as a set
of solver-comparison instances with a recorded baseline. ``--solver-executable``
runs the same models under a different NLP binary without touching model code:
any solver following the AMPL ``<solver> <stub> -AMPL`` convention works, which
includes POUNCE.

Cold starts fail below ``f = 1``, so every rung warm starts from the previous
solution. A rung that returns a non-success termination is recorded with its
solver status, termination condition, and message, and ends that problem's
ladder, because where the ladder stops is itself the result. A solver that
runs and returns a result Pyomo refuses to load is recorded the same way, with
`error` as its termination: that is a solver outcome, and on the paper mesh it
is how the IPOPT ladder actually ends. Configuration failures -- a missing or
invalid binary, a rejected option, a programming error -- happen before or
instead of a solve and are *not* caught: they propagate so a broken run
produces no baseline artifact at all.

A converged rung also reports *which* tolerance it met. The success gate
accepts a solve stopped at IPOPT's ``acceptable_tol`` alongside one that
reached ``tol``, and Pyomo labels both ``optimal``, so ``converged`` alone
cannot separate them. Every converged rung of the recorded IPOPT baseline is
acceptable-level, which is expected on this Landau-coordinate transcription
(see ``paper_ocp``) but is the opposite of what a bare ``optimal/ok converged``
line reads as. Each rung therefore carries ``convergence_quality`` and prints
it, so the ladder states its own convergence level instead of implying a
tighter one.

Run from the repository root::

    python -m examples.pseudosteady_limit_study
    python -m examples.pseudosteady_limit_study --solver-executable /path/to/pounce
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
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

#: Terminations that count as a usable result for this study.
SUCCESS_TERMINATIONS = frozenset({"optimal", "locallyoptimal", "feasible"})


@dataclasses.dataclass(frozen=True)
class RungResult:
    """One solve at one heat-capacity scale.

    ``max_constraint_violation`` is the largest violation over *every* active
    constraint, in each constraint's own units.

    ``ode_residual_times_thickness_squared_K_m2`` is a narrower diagnostic: the
    largest ``temperature_ode`` residual multiplied by ``(H - S)^2``, in K m^2.
    It exists because the Landau coordinate makes that equation's conduction
    term carry ``1/(H - S)^2``, so its absolute residual is dominated by the
    transform rather than by solution quality. It is deliberately *not* a
    feasibility verdict: it covers one constraint family, it is dimensionful, and
    the ``(H - S)^2`` factor falls to about 1.3e-9 at the default terminal
    cutoff, so comparing it against a fixed threshold would accept arbitrarily
    large residuals late in the horizon. Judge feasibility from
    ``max_constraint_violation``, and read this only as evidence about how much
    of that number is the coordinate transform.

    ``convergence_quality`` says *which* tolerance a converged rung met, which
    ``converged`` cannot: the success gate accepts a solve stopped at
    ``acceptable_tol`` alongside one that reached ``tol``, and Pyomo reports
    both as ``termination_condition: optimal``. Every converged rung of the
    recorded IPOPT baseline is acceptable-level, so a report carrying only
    ``converged`` states the opposite of what the ladder measured. Values come
    from :func:`lyopronto.pyomo_models.paper_ocp.classify_convergence_quality`.
    """

    problem: str
    factor: float
    conduction_time_s: float
    converged: bool
    endpoint_hr: float | None = None
    max_product_temperature_K: float | None = None
    termination_condition: str | None = None
    solver_status: str | None = None
    solver_message: str | None = None
    max_constraint_violation: float | None = None
    ode_residual_times_thickness_squared_K_m2: float | None = None
    convergence_quality: str = paper_ocp.CONVERGENCE_QUALITY_UNKNOWN

    def as_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


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


def max_constraint_violation(model: Any) -> float:
    """Return the largest violation over every active constraint *and* bound.

    Measured on the model rather than taken from the solver, so the number does
    not depend on what the solver chose to call success. Matches IPOPT's own
    reported ``Constraint violation`` where both are available.

    Variable bounds are included deliberately. An interface position driven past
    the product height, or a shelf temperature outside its window, is a
    feasibility failure that no ``Constraint`` object reports, so a
    constraints-only measure would pass it silently.
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

    for variable in model.component_data_objects(pyo.Var, active=True):
        value = variable.value
        if value is None:
            continue
        if variable.lb is not None:
            worst = max(worst, variable.lb - value)
        if variable.ub is not None:
            worst = max(worst, value - variable.ub)
    return worst


def ode_residual_times_thickness_squared(model: Any) -> float:
    """Return ``max |temperature_ode residual| * (H - S)^2``, in K m^2.

    See :class:`RungResult` for what this can and cannot be used for. It is a
    diagnostic for how much of the absolute residual is the Landau transform,
    not a feasibility test.
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


def _solver_report(
    solution: Mapping[str, Any],
) -> tuple[str | None, str | None, str | None, str]:
    """Return the rung's termination, status, message, and convergence quality.

    ``paper_ocp`` classifies the quality during extraction, so this reads its
    label rather than re-matching the solver text here.
    """
    metadata = solution.get("metadata", {})
    return (
        metadata.get("termination_condition"),
        metadata.get("status"),
        metadata.get("message"),
        metadata.get("convergence_quality", paper_ocp.CONVERGENCE_QUALITY_UNKNOWN),
    )


def _is_success(termination: str | None) -> bool:
    return str(termination).strip().lower() in SUCCESS_TERMINATIONS


def solver_provenance(
    solver: str, solver_executable: str | None
) -> dict[str, Any]:
    """Record which binary actually ran, and its version.

    The Pyomo interface name and the solver identity are different things: a
    POUNCE run is driven through the ``ipopt`` ASL interface, so the interface
    name alone would label both baselines as IPOPT. The executable path is
    reduced to its basename because the absolute path is host-specific.
    """
    import pyomo.environ as pyo  # type: ignore[import-untyped]

    opt = (
        pyo.SolverFactory(solver, executable=str(solver_executable))
        if solver_executable is not None
        else pyo.SolverFactory(solver)
    )
    resolved = None
    try:
        resolved = opt.executable()
    except Exception:  # noqa: BLE001 - provenance must not break the run
        resolved = solver_executable
    version = None
    try:
        raw = opt.version()
        if raw is not None:
            version = ".".join(str(part) for part in raw)
    except Exception:  # noqa: BLE001
        version = None
    return {
        "pyomo_interface": solver,
        "solver_name": os.path.basename(str(resolved)) if resolved else solver,
        "solver_version": version,
        "solver_executable_basename": (
            os.path.basename(str(solver_executable)) if solver_executable else None
        ),
    }


def run_ladder(
    problem: str,
    *,
    discretization: paper_ocp.PaperDiscretization | None = None,
    ladder: Sequence[float] = DEFAULT_LADDER,
    solver: str = "ipopt",
    solver_executable: str | None = None,
    solver_options: Mapping[str, Any] | None = None,
    nlp_scaling_method: str | None = None,
    on_rung: Any = None,
) -> list[RungResult]:
    """Walk one problem down the ladder, warm starting each rung from the last.

    Solves with ``require_success=False`` so a non-success termination is
    recorded with its solver metadata rather than raised past it. Configuration
    and execution failures are not caught and will abort the study.

    ``on_rung`` is called with each :class:`RungResult` as it completes. An
    aborting rung discards the in-memory list, so without it the rungs already
    solved are lost and the operator cannot see how far the ladder got.
    """
    if problem not in PROBLEMS:
        raise ValueError(f"unsupported paper problem: {problem!r}")
    discretization = discretization or paper_ocp.PaperDiscretization(
        n_z=20, nfe=36, ncp=3
    )
    options = dict(DEFAULT_SOLVER_OPTIONS)
    if nlp_scaling_method is not None:
        options["nlp_scaling_method"] = nlp_scaling_method
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
                require_success=False,
                return_model=True,
            )
        except ValueError as exc:
            # Narrow on purpose. Pyomo raises this when the solver *ran* and
            # returned a result it refuses to load, which is a solver outcome
            # and the kind of endpoint this ladder exists to record. Anything
            # else -- a missing binary, a rejected option, a programming error
            # -- happens before or instead of a solve and must still propagate
            # so a broken run emits no baseline.
            if "bad status" not in str(exc):
                raise
            results.append(
                RungResult(
                    problem=problem,
                    factor=factor,
                    conduction_time_s=tau,
                    converged=False,
                    termination_condition="error",
                    solver_status="error",
                    solver_message=str(exc),
                )
            )
            if on_rung is not None:
                on_rung(results[-1])
            break
        termination, status, message, quality = _solver_report(solution)
        converged = _is_success(termination)
        record = RungResult(
            problem=problem,
            factor=factor,
            conduction_time_s=tau,
            converged=converged,
            endpoint_hr=float(solution["states"]["time_hr"][-1]),
            max_product_temperature_K=float(
                solution["metrics"]["max_product_temperature_K"]
            ),
            termination_condition=termination,
            solver_status=status,
            solver_message=message,
            max_constraint_violation=max_constraint_violation(solution["model"]),
            ode_residual_times_thickness_squared_K_m2=(
                ode_residual_times_thickness_squared(solution["model"])
            ),
            convergence_quality=quality,
        )
        results.append(record)
        if on_rung is not None:
            on_rung(record)
        if not converged:
            break
        warm_start = solution
    return results


def endpoint_shift_percent(results: Sequence[RungResult]) -> float | None:
    """Return the percentage change in endpoint across the converged rungs."""
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
    nlp_scaling_method: str | None = None,
    on_rung: Any = None,
) -> dict[str, list[RungResult]]:
    """Run the ladder for each problem and return the per-problem results."""
    return {
        problem: run_ladder(
            problem,
            discretization=discretization,
            ladder=ladder,
            solver=solver,
            solver_executable=solver_executable,
            nlp_scaling_method=nlp_scaling_method,
            on_rung=on_rung,
        )
        for problem in problems
    }


def format_results(results: Mapping[str, Sequence[RungResult]]) -> str:
    """Render the study as a short text table."""
    lines: list[str] = []
    for problem, rungs in results.items():
        lines.append(problem)
        for rung in rungs:
            state = "ok " if rung.converged else "NOT CONVERGED"

            def _fmt(value: float | None, spec: str) -> str:
                return "n/a" if value is None else format(value, spec)

            lines.append(
                f"  f={rung.factor:<6g} tau={rung.conduction_time_s:8.3f} s  "
                f"endpoint={_fmt(rung.endpoint_hr, '.4f')} hr  "
                f"maxT={_fmt(rung.max_product_temperature_K, '.4f')} K  "
                f"{rung.termination_condition}/{rung.solver_status} {state} "
                f"quality={rung.convergence_quality} "
                f"viol={_fmt(rung.max_constraint_violation, '.2e')} "
                f"odeK_m2="
                f"{_fmt(rung.ode_residual_times_thickness_squared_K_m2, '.2e')}"
            )
            if not rung.converged and rung.solver_message:
                lines.append(f"      message: {rung.solver_message}")
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
    parser.add_argument("--solver", default="ipopt", help="Pyomo solver interface")
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
    parser.add_argument(
        "--nlp-scaling",
        default=None,
        help=(
            "nlp_scaling_method to pass to the solver. The best choice is "
            "instance-dependent here; see benchmarks/README.md"
        ),
    )
    parser.add_argument("--output", type=Path, default=None, help="write JSON here")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    provenance = solver_provenance(args.solver, args.solver_executable)
    print(
        f"solver: {provenance['solver_name']} {provenance['solver_version']} "
        f"(via the {provenance['pyomo_interface']} interface)",
        flush=True,
    )

    def report(rung: RungResult) -> None:
        state = "ok" if rung.converged else "NOT CONVERGED"
        endpoint = (
            "n/a" if rung.endpoint_hr is None else f"{rung.endpoint_hr:.4f} hr"
        )
        print(
            f"  [{rung.problem} f={rung.factor:g}] "
            f"{rung.termination_condition}/{rung.solver_status} {state} "
            f"quality={rung.convergence_quality} "
            f"endpoint={endpoint}",
            flush=True,
        )

    try:
        results = run_study(
            problems=args.problems or PROBLEMS,
            solver=args.solver,
            solver_executable=args.solver_executable,
            discretization=paper_ocp.PaperDiscretization(
                n_z=args.n_z, nfe=args.nfe, ncp=args.ncp
            ),
            nlp_scaling_method=args.nlp_scaling,
            on_rung=report,
        )
    except Exception:
        # A broken run writes no artifact, but the rungs streamed above stay on
        # screen so the failure can be located without rerunning the ladder.
        print("\nstudy aborted after the rungs above; no baseline written", flush=True)
        raise
    print(format_results(results))
    if args.output is not None:
        payload = {
            "solver": provenance,
            "nlp_scaling_method": args.nlp_scaling or "solver default (gradient-based)",
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
