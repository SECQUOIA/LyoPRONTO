"""Compare paper, continuous-NLP, and GDP switching solutions.

This validation-only example solves the Srisuma--Braatz primary-drying cases
two ways with the same SI-unit physical equations:

* ``paper_ocp`` uses one simultaneous continuous NLP and classifies active
  constraints after the solve;
* ``paper_gdp`` uses free phase durations and GDP indicators to select the
  policy sequence during the solve.

Agreement independently checks the switching representation and policy
selection.  It does not independently validate the shared physical equations.
GDPopt RIC calls IPOPT for local nonlinear subproblems, so the result is not a
global optimality certificate.

Install the optional stack before running this module:

``python -m pip install -e ".[dev,pyomo]"``
``idaes get-extensions --extra petsc``
``sudo apt-get install glpk-utils``
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from examples.paper_optimal_control_replication import PAPER_REFERENCE, run_paper_case
from lyopronto.pyomo_models.paper_gdp import (
    PaperGDPDiscretization,
    paper_gdp_comparison_rows,
    solve_paper_problem1_gdp,
    solve_paper_problem2_gdp,
)


@dataclass(frozen=True)
class PaperGDPValidationRun:
    """One paper/continuous-NLP/GDP comparison for a paper problem."""

    problem: str
    continuous_solution: Mapping[str, Any]
    gdp_solution: Mapping[str, Any]
    comparison_rows: tuple[Mapping[str, Any], ...]


def run_paper_gdp_validation(
    problem: str,
    *,
    n_z: int = 5,
    nfe_per_phase: int = 6,
    ncp: int = 2,
    phase_duration_weights: Sequence[float] | None = None,
    init_algorithm: str = "set_covering",
) -> PaperGDPValidationRun:
    """Solve and compare one paper case on matched spatial/collocation grids.

    ``phase_duration_weights`` initializes only continuous phase durations; it
    never initializes GDP indicators.  ``init_algorithm="no_init"`` provides
    a second discrete-solver start that is independent of GDPopt's default
    set-covering initialization.
    """
    if problem not in {"problem1", "problem2"}:
        raise ValueError(f"unsupported paper problem: {problem!r}")
    n_phases = 2 if problem == "problem1" else 3
    continuous = run_paper_case(
        problem,
        n_z=n_z,
        nfe=n_phases * nfe_per_phase,
        ncp=ncp,
        initialization=None,
    )
    discretization = PaperGDPDiscretization(
        n_z=n_z,
        nfe_per_phase=nfe_per_phase,
        ncp=ncp,
    )
    solve = (
        solve_paper_problem1_gdp if problem == "problem1" else solve_paper_problem2_gdp
    )
    gdp_solution = solve(
        discretization=discretization,
        phase_duration_weights=phase_duration_weights,
        init_algorithm=init_algorithm,
    )
    rows = paper_gdp_comparison_rows(
        gdp_solution,
        continuous.solution,
        PAPER_REFERENCE[problem],
    )
    return PaperGDPValidationRun(
        problem=problem,
        continuous_solution=continuous.solution,
        gdp_solution=gdp_solution,
        comparison_rows=tuple(rows),
    )


def _print_run(run: PaperGDPValidationRun) -> None:
    print(f"\n{run.problem}")
    for row in run.comparison_rows:
        print(
            f"{row['quantity']}: paper={row['paper']}, "
            f"continuous NLP={row['continuous_nlp']}, GDP={row['gdp']}"
        )
    metadata = run.gdp_solution["metadata"]
    print(
        "GDP solver: "
        f"{metadata['solver_configuration']}; "
        f"global certificate={metadata['global_optimality_certified']}"
    )


if __name__ == "__main__":
    for problem_name in ("problem1", "problem2"):
        _print_run(run_paper_gdp_validation(problem_name))
