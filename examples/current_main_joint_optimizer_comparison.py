"""Joint-control comparison for the mannitol case in the LyoPRONTO paper.

The module compares equivalent rate-unlimited pressure-and-temperature
optimizations:

* legacy SciPy maximizes sublimation rate at each dried-cake state and advances
  until complete drying;
* Pyomo.DAE optimizes both complete control trajectories simultaneously and
  minimizes the free final drying time; and
* the Pyomo model is transcribed with either backward finite differences or
  LAGRANGE-RADAU orthogonal collocation.

Both paths use the paper's mannitol inputs, pressure and shelf-temperature
bounds, physics, constraints, completion target, and seven-column trajectory
contract. The published paper reports a 1.96 hr drying time for this case.
The Pyomo wrapper also exposes its optional initial-control and rate limits for
one direct capability comparison in the notebook.
"""

from __future__ import annotations

from time import perf_counter
from typing import Any, Mapping, Sequence, Union

import numpy as np

from examples.current_main_comparison import (
    CaseComparison,
    SolverRun,
    collect_case_comparison,
    collect_discretization_sensitivity,
    matched_nfe_for_point_budget,
    solver_run_from_dae_result,
)
from lyopronto import constant, opt_Pch_Tsh


DEFAULT_A1_VALUES = (16.0, 18.0, 20.0)
DEFAULT_KC_VALUES = (2.75e-4, 3.30e-4, 4.00e-4)


def comparison_inputs(a1: float, kc: float) -> dict[str, Any]:
    """Return the paper's 5% mannitol inputs with selected A1 and KC values."""
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
        "pchamber": {"min": 0.05, "max": 0.5},
        "tshelf": {"min": -45.0, "max": 120.0, "init": -35.0},
        "eq_cap": {"a": -0.182, "b": 11.7},
        "nvial": 398,
    }


def run_scipy_reference(a1: float, kc: float, *, dt: float = 0.01) -> SolverRun:
    """Run the sequential joint-control optimizer to complete drying."""
    if dt <= 0.0:
        raise ValueError("dt must be positive")
    data = comparison_inputs(a1, kc)
    start = perf_counter()
    trajectory = opt_Pch_Tsh.dry(
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
    pressure_bounds: tuple[float, float] | None = None,
    initial_pressure: float | None = None,
    initial_shelf_temperature: float | None = None,
    pressure_ramp_rate: float | None = None,
    shelf_temperature_ramp_rate: float | None = None,
    solver: Union[str, Any] = "ipopt",
) -> SolverRun:
    """Run one current-physics, free-final-time joint optimization."""
    from lyopronto.pyomo_models import solve_dae_joint_optimization

    data = comparison_inputs(a1, kc)
    if pressure_bounds is not None:
        data["pchamber"] = {
            "min": float(pressure_bounds[0]),
            "max": float(pressure_bounds[1]),
        }
    start = perf_counter()
    result = solve_dae_joint_optimization(
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
        initial_pressure=initial_pressure,
        initial_shelf_temperature=initial_shelf_temperature,
        pressure_ramp_rate=pressure_ramp_rate,
        shelf_temperature_ramp_rate=shelf_temperature_ramp_rate,
        solver=solver,
    )
    wall_time_s = perf_counter() - start
    return solver_run_from_dae_result(result, wall_time_s=wall_time_s)


def trajectory_constraint_diagnostics(
    trajectory: np.ndarray,
    data: Mapping[str, Any],
) -> dict[str, float]:
    """Evaluate exported legacy-table constraints without trusting solver status.

    The trajectory columns use the package contract: time [hr], temperatures
    [degC], chamber pressure [mTorr], sublimation flux [kg/hr/m^2], and dried
    percentage [0-100]. Equipment margin is returned in kg/hr for the batch.
    """
    table = np.asarray(trajectory, dtype=float)
    if table.ndim != 2 or table.shape[1] != 7 or not np.all(np.isfinite(table)):
        raise ValueError("trajectory must be a finite two-dimensional, seven-column table")

    pressure_mtorr = table[:, 4]  # [mTorr]
    shelf_temperature = table[:, 3]  # [degC]
    vial_bottom_temperature = table[:, 2]  # [degC]
    total_sublimation_rate = (
        table[:, 5] * float(data["vial"]["Ap"]) * constant.cm_To_m**2
    )  # [kg/hr/vial]
    pressure_torr = pressure_mtorr / constant.Torr_to_mTorr  # [Torr]
    equipment_margin = (
        float(data["eq_cap"]["a"])
        + float(data["eq_cap"]["b"]) * pressure_torr
        - int(data["nvial"]) * total_sublimation_rate
    )  # [kg/hr]

    critical_temperature = float(data["product"]["T_pr_crit"])  # [degC]
    pressure_min_mtorr = float(data["pchamber"]["min"]) * constant.Torr_to_mTorr  # [mTorr]
    pressure_max_mtorr = float(data["pchamber"]["max"]) * constant.Torr_to_mTorr  # [mTorr]
    shelf_min = float(data["tshelf"]["min"])  # [degC]
    shelf_max = float(data["tshelf"]["max"])  # [degC]
    return {
        "final_dried_percent": float(table[-1, 6]),
        "product_temperature_violation_c": max(
            0.0, float(np.max(vial_bottom_temperature)) - critical_temperature
        ),
        "pressure_lower_violation_mtorr": max(
            0.0, pressure_min_mtorr - float(np.min(pressure_mtorr))
        ),
        "pressure_upper_violation_mtorr": max(
            0.0, float(np.max(pressure_mtorr)) - pressure_max_mtorr
        ),
        "shelf_lower_violation_c": max(0.0, shelf_min - float(np.min(shelf_temperature))),
        "shelf_upper_violation_c": max(0.0, float(np.max(shelf_temperature)) - shelf_max),
        "minimum_equipment_margin_kg_hr": float(np.min(equipment_margin)),
        "pressure_lower_bound_fraction": float(
            np.mean(np.isclose(pressure_mtorr, pressure_min_mtorr, atol=1.0e-3))
        ),
    }


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
    """Run repeated equivalent joint optimizations at a matched point budget."""
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


def _joint_sensitivity_row_values(run: SolverRun) -> dict[str, float]:
    """Return joint-only time [hr] and product-temperature [degC] details."""
    return {
        "first_positive_time_hr": float(run.trajectory[1, 0]),
        "initial_product_temperature_c": float(run.trajectory[0, 2]),
        "first_positive_product_temperature_c": float(run.trajectory[1, 2]),
    }


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
        extra_row_values=_joint_sensitivity_row_values,
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
    "trajectory_constraint_diagnostics",
]
