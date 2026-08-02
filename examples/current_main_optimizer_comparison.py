"""Helpers for the current-main SciPy/Pyomo.DAE comparison tutorial.

The experiment compares equivalent shelf-temperature optimization problems:

* legacy SciPy maximizes sublimation rate at each dried-cake state and advances
  until complete drying;
* Pyomo.DAE optimizes the full trajectory simultaneously and minimizes the
  free final drying time; and
* the Pyomo model is transcribed with either backward finite differences or
  LAGRANGE-RADAU orthogonal collocation.

Both paths use the current LyoPRONTO physics, controls, constraints, completion
target, and seven-column trajectory convention.  The tutorial notebook owns
the one-off parameter sweep and visualization; this module keeps its model
runs importable and testable.
"""

from __future__ import annotations

from time import perf_counter
from typing import Any, Sequence, Union

import numpy as np

from examples.current_main_comparison import (
    CaseComparison,
    SolverRun,
    collect_case_comparison,
    collect_discretization_sensitivity,
    matched_nfe_for_point_budget,
    solver_run_from_dae_result,
)
from lyopronto import opt_Tsh


DEFAULT_A1_VALUES = (16.0, 18.0, 20.0)
DEFAULT_KC_VALUES = (2.75e-4, 3.30e-4, 4.00e-4)


def comparison_inputs(a1: float, kc: float) -> dict[str, Any]:
    """Return the explicit legacy dictionaries for one grid point."""
    return {
        "vial": {"Av": 3.8, "Ap": 3.14, "Vfill": 2.0},
        "product": {
            "cSolid": 0.05,
            "R0": 1.4,
            "A1": float(a1),
            "A2": 0.0,
            "T_pr_crit": -25.0,
        },
        "ht": {"KC": float(kc), "KP": 8.93e-4, "KD": 0.46},
        "pchamber": {
            "setpt": [0.1],
            "dt_setpt": [1800.0],
            "ramp_rate": 0.5,
        },
        "tshelf": {"min": -45.0, "max": 120.0, "init": -35.0},
        "eq_cap": {"a": -0.182, "b": 11.7},
        "nvial": 400,
    }


def run_scipy_reference(a1: float, kc: float, *, dt: float = 0.01) -> SolverRun:
    """Run the legacy sequential shelf-temperature optimizer to completion."""
    data = comparison_inputs(a1, kc)
    start = perf_counter()
    trajectory = opt_Tsh.dry(
        data["vial"],
        dict(data["product"]),
        data["ht"],
        dict(data["pchamber"]),
        dict(data["tshelf"]),
        float(dt),
        data["eq_cap"],
        data["nvial"],
    )
    wall_time_s = perf_counter() - start
    success = bool(
        trajectory.ndim == 2
        and trajectory.shape[1] == 7
        and trajectory.size
        and np.all(np.isfinite(trajectory))
        and trajectory[-1, 6] >= 100.0 - 1.0e-6
    )
    objective = float(trajectory[-1, 0]) if trajectory.size else float("nan")
    return SolverRun(
        trajectory=np.asarray(trajectory, dtype=float),
        wall_time_s=float(wall_time_s),
        objective_time_hr=objective,
        success=success,
        solver_status="n/a",
        termination_condition="completed" if success else "incomplete",
        max_constraint_violation=0.0,
        n_time_points=int(trajectory.shape[0]),
        n_variables=None,
        n_constraints=None,
        solver_iterations=None,
    )


def run_pyomo_dae(
    a1: float,
    kc: float,
    *,
    discretization: str,
    nfe: int = 24,
    ncp: int = 3,
    final_dried_fraction: float = 1.0,
    initialize: np.ndarray | None = None,
    solver: Union[str, Any] = "ipopt",
) -> SolverRun:
    """Run one current-physics, free-final-time Pyomo.DAE optimization."""
    from lyopronto.pyomo_models import solve_dae_shelf_temperature_optimization

    data = comparison_inputs(a1, kc)
    start = perf_counter()
    result = solve_dae_shelf_temperature_optimization(
        data["vial"],
        data["product"],
        data["ht"],
        data["pchamber"],
        data["tshelf"],
        eq_cap=data["eq_cap"],
        nvial=data["nvial"],
        nfe=int(nfe),
        discretization=discretization,
        ncp=int(ncp),
        final_dried_fraction=float(final_dried_fraction),
        initialize=initialize,
        solver=solver,
    )
    wall_time_s = perf_counter() - start
    return solver_run_from_dae_result(result, wall_time_s=wall_time_s)


def run_case_comparison(
    a1: float,
    kc: float,
    *,
    scipy_dt: float = 0.01,
    finite_difference_nfe: int = 24,
    collocation_nfe: int = 8,
    ncp: int = 3,
    final_dried_fraction: float = 1.0,
    timing_repeats: int = 1,
    warmstart_from_scipy: bool = False,
    solver: Union[str, Any] = "ipopt",
) -> CaseComparison:
    """Run repeated equivalent optimizations at a matched DAE point budget."""
    return collect_case_comparison(
        a1,
        kc,
        run_scipy=run_scipy_reference,
        run_dae=run_pyomo_dae,
        scipy_dt=scipy_dt,
        finite_difference_nfe=finite_difference_nfe,
        collocation_nfe=collocation_nfe,
        ncp=ncp,
        final_dried_fraction=final_dried_fraction,
        timing_repeats=timing_repeats,
        warmstart_from_scipy=warmstart_from_scipy,
        solver=solver,
    )


def run_discretization_sensitivity(
    a1: float,
    kc: float,
    scipy_trajectory: np.ndarray,
    *,
    point_budgets: Sequence[int] = (25, 49, 73),
    ncp: int = 3,
    final_dried_fraction: float = 1.0,
    solver: Union[str, Any] = "ipopt",
) -> list[dict[str, Any]]:
    """Evaluate both DAE transformations at exactly matched point budgets."""
    return collect_discretization_sensitivity(
        a1,
        kc,
        scipy_trajectory,
        run_dae=run_pyomo_dae,
        point_budgets=point_budgets,
        ncp=ncp,
        final_dried_fraction=final_dried_fraction,
        solver=solver,
        extra_row_values=None,
    )


__all__ = [
    "CaseComparison",
    "DEFAULT_A1_VALUES",
    "DEFAULT_KC_VALUES",
    "SolverRun",
    "comparison_inputs",
    "matched_nfe_for_point_budget",
    "run_case_comparison",
    "run_discretization_sensitivity",
    "run_pyomo_dae",
    "run_scipy_reference",
]
