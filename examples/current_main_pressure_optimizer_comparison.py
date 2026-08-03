"""Pressure comparison for the mannitol case in the LyoPRONTO paper.

The experiment compares equivalent chamber-pressure optimization problems:

* legacy SciPy maximizes sublimation rate at each dried-cake state and advances
  until complete drying;
* Pyomo.DAE optimizes the full pressure trajectory simultaneously and minimizes
  the free final drying time; and
* the Pyomo model is transcribed with either backward finite differences or
  LAGRANGE-RADAU orthogonal collocation.

Both paths use the paper's 30 degC shelf setpoint, product and equipment
limits, and seven-column trajectory contract. The 2 Torr numerical upper bound
is inactive and replaces the original input's effectively unbounded 1000 Torr
value. The published paper reports a 2.99 hr drying time for this case.
"""

from __future__ import annotations

from time import perf_counter
from typing import Any, Sequence, Union
import warnings

import numpy as np

from examples.current_main_comparison import (
    CaseComparison,
    SolverRun,
    collect_case_comparison,
    collect_discretization_sensitivity,
    matched_nfe_for_point_budget,
    solver_run_from_dae_result,
)
from lyopronto import opt_Pch


DEFAULT_A1_VALUES = (16.0, 18.0, 20.0)
DEFAULT_KC_VALUES = (2.75e-4, 3.30e-4, 4.00e-4)


def comparison_inputs(a1: float, kc: float) -> dict[str, Any]:
    """Return explicit legacy dictionaries for one historical grid point."""
    return {
        "vial": {"Av": 3.8, "Ap": 3.14, "Vfill": 2.0},
        "product": {
            "cSolid": 0.05,
            "R0": 1.4,
            "A1": float(a1),
            "A2": 0.0,
            "T_pr_crit": -5.0,
        },
        "ht": {"KC": float(kc), "KP": 8.93e-4, "KD": 0.46},
        "pchamber": {"min": 0.05, "max": 2.0},
        "tshelf": {
            "init": 30.0,
            "setpt": [30.0],
            "dt_setpt": [6000.0],
            "ramp_rate": 1.0,
        },
        "eq_cap": {"a": -0.182, "b": 11.7},
        "nvial": 398,
    }


def run_scipy_reference(a1: float, kc: float, *, dt: float = 0.01) -> SolverRun:
    """Run the sequential chamber-pressure optimizer to complete drying."""
    if dt <= 0.0:
        raise ValueError("dt must be positive")
    data = comparison_inputs(a1, kc)
    start = perf_counter()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        trajectory = opt_Pch.dry(
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
    warning_messages = [str(item.message) for item in caught]
    optimizer_failed = any("Optimization failed" in message for message in warning_messages)
    incomplete = any("Drying incomplete" in message for message in warning_messages)
    success = bool(
        trajectory.ndim == 2
        and trajectory.shape[1] == 7
        and trajectory.size
        and np.all(np.isfinite(trajectory))
        and trajectory[-1, 6] >= 100.0 - 1.0e-6
        and not optimizer_failed
        and not incomplete
    )
    objective = float(trajectory[-1, 0]) if trajectory.size else float("nan")
    return SolverRun(
        trajectory=np.asarray(trajectory, dtype=float),
        wall_time_s=float(wall_time_s),
        objective_time_hr=objective,
        success=success,
        solver_status="warning" if warning_messages else "n/a",
        termination_condition="completed" if success else "incomplete_or_failed",
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
    """Run one current-physics, free-final-time pressure optimization."""
    from lyopronto.pyomo_models import solve_dae_chamber_pressure_optimization

    data = comparison_inputs(a1, kc)
    start = perf_counter()
    result = solve_dae_chamber_pressure_optimization(
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
    """Run repeated equivalent pressure optimizations at a matched point budget."""
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
