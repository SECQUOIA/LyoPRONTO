"""Helpers for the current-main implementable-cycle optimizer tutorial.

The tutorial asks for the fastest cycle that honors stated initial controls
and pressure/shelf-temperature slew limits. It uses the equivalent
rate-unlimited pressure-and-temperature optimizations as validation:

* legacy SciPy maximizes sublimation rate at each dried-cake state and advances
  until complete drying;
* Pyomo.DAE optimizes both complete control trajectories simultaneously and
  minimizes the free final drying time; and
* the Pyomo model is transcribed with either backward finite differences or
  LAGRANGE-RADAU orthogonal collocation.

Both paths use the same pressure and shelf-temperature bounds, physics,
constraints, completion target, and seven-column trajectory contract. The
tutorial notebook owns the decision narrative and plots; this module keeps
the validation, penalty decomposition, and equipment-rate sweep importable
and testable.
"""

from __future__ import annotations

from dataclasses import dataclass
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


@dataclass(frozen=True)
class ImplementabilityAnalysis:
    """Counterfactuals that explain one implementable cycle's time penalty.

    ``anchored_unlimited`` fixes the operational starting controls but allows
    an immediate next-node jump. ``pressure_preconditioned`` starts chamber
    pressure at its lower bound while retaining the operational shelf start
    and both rate limits. ``implementable`` applies both operational starts
    and both rate limits. These counterfactuals expose the interaction between
    starting conditions and slew limits instead of assigning it silently.
    """

    idealized: SolverRun
    anchored_unlimited: SolverRun
    pressure_preconditioned: SolverRun
    implementable: SolverRun

    @property
    def anchor_only_penalty_hr(self) -> float:
        """Return the penalty from fixed starts when jumps remain unlimited [hr]."""
        return self.anchored_unlimited.objective_time_hr - self.idealized.objective_time_hr

    @property
    def rate_and_interaction_penalty_hr(self) -> float:
        """Return the incremental rate-limit and start/rate interaction cost [hr]."""
        return self.implementable.objective_time_hr - self.anchored_unlimited.objective_time_hr

    @property
    def pressure_start_penalty_hr(self) -> float:
        """Return the pressure-start cost conditional on both stated rates [hr]."""
        return (
            self.implementable.objective_time_hr
            - self.pressure_preconditioned.objective_time_hr
        )

    @property
    def preconditioned_penalty_hr(self) -> float:
        """Return the remaining rate and shelf-start penalty over idealized [hr]."""
        return self.pressure_preconditioned.objective_time_hr - self.idealized.objective_time_hr

    @property
    def total_penalty_hr(self) -> float:
        """Return the full implementability penalty over the idealized cycle [hr]."""
        return self.implementable.objective_time_hr - self.idealized.objective_time_hr

    @property
    def total_penalty_percent(self) -> float:
        """Return the full implementability penalty relative to idealized time [%]."""
        return 100.0 * self.total_penalty_hr / self.idealized.objective_time_hr


def comparison_inputs(a1: float, kc: float) -> dict[str, Any]:
    """Return explicit legacy dictionaries for one historical grid point."""
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
        "pchamber": {"min": 0.05, "max": 0.5},
        "tshelf": {"min": -45.0, "max": 120.0, "init": -35.0},
        "eq_cap": {"a": -0.182, "b": 11.7},
        "nvial": 400,
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


def _require_successful_run(run: SolverRun, label: str) -> None:
    """Raise when a tutorial scenario does not reach a usable optimum."""
    if not run.success:
        raise RuntimeError(
            f"{label} failed: {run.solver_status}/{run.termination_condition}"
        )


def run_implementability_analysis(
    a1: float,
    kc: float,
    *,
    point_budget: int = 97,
    ncp: int = 3,
    final_dried_fraction: float = 1.0,
    initial_pressure_torr: float = 0.15,
    initial_shelf_temperature_c: float = -35.0,
    pressure_ramp_rate_torr_hr: float = 0.05,
    shelf_temperature_ramp_rate_c_hr: float = 10.0,
    solver: Union[str, Any] = "ipopt",
) -> ImplementabilityAnalysis:
    """Solve and decompose one implementable-cycle time penalty.

    Parameters
    ----------
    a1
        Product-resistance coefficient [cm hr Torr/g].
    kc
        Vial heat-transfer coefficient parameter [cal/s/K/cm^2].
    point_budget
        Number of collocation transcription points [-].
    ncp
        Radau collocation points per finite element [-].
    final_dried_fraction
        Terminal dried fraction [0-1].
    initial_pressure_torr
        Operational initial chamber pressure [Torr].
    initial_shelf_temperature_c
        Operational initial shelf temperature [degC].
    pressure_ramp_rate_torr_hr
        Maximum adjacent-node chamber-pressure rate [Torr/hr].
    shelf_temperature_ramp_rate_c_hr
        Maximum adjacent-node shelf-temperature rate [degC/hr].
    solver
        Pyomo solver name or solver object [-].

    Returns
    -------
    ImplementabilityAnalysis
        Four optimized cycles that separate anchor-only, rate/anchor
        interaction, and conditional pressure-start effects [hr].
    """
    _, collocation_nfe = matched_nfe_for_point_budget(point_budget, ncp)
    common = {
        "discretization": "collocation",
        "nfe": collocation_nfe,
        "ncp": ncp,
        "final_dried_fraction": final_dried_fraction,
        "solver": solver,
    }
    idealized = run_pyomo_dae(a1, kc, **common)
    _require_successful_run(idealized, "rate-unlimited idealized cycle")

    anchored_unlimited = run_pyomo_dae(
        a1,
        kc,
        initial_pressure=initial_pressure_torr,
        initial_shelf_temperature=initial_shelf_temperature_c,
        **common,
    )
    _require_successful_run(anchored_unlimited, "anchored rate-unlimited cycle")

    rate_options = {
        "pressure_ramp_rate": pressure_ramp_rate_torr_hr,
        "shelf_temperature_ramp_rate": shelf_temperature_ramp_rate_c_hr,
    }
    pressure_floor_torr = float(comparison_inputs(a1, kc)["pchamber"]["min"])  # [Torr]
    pressure_preconditioned = run_pyomo_dae(
        a1,
        kc,
        initial_pressure=pressure_floor_torr,
        initial_shelf_temperature=initial_shelf_temperature_c,
        **rate_options,
        **common,
    )
    _require_successful_run(
        pressure_preconditioned,
        "rate-limited pressure-preconditioned cycle",
    )

    implementable = run_pyomo_dae(
        a1,
        kc,
        initial_pressure=initial_pressure_torr,
        initial_shelf_temperature=initial_shelf_temperature_c,
        **rate_options,
        **common,
    )
    _require_successful_run(implementable, "rate-limited operational-start cycle")
    return ImplementabilityAnalysis(
        idealized=idealized,
        anchored_unlimited=anchored_unlimited,
        pressure_preconditioned=pressure_preconditioned,
        implementable=implementable,
    )


def run_slew_rate_sweep(
    a1: float,
    kc: float,
    idealized_time_hr: float,
    *,
    pressure_ramp_rates_torr_hr: Sequence[float],
    shelf_temperature_ramp_rates_c_hr: Sequence[float],
    point_budget: int = 49,
    ncp: int = 3,
    final_dried_fraction: float = 1.0,
    initial_pressure_torr: float = 0.15,
    initial_shelf_temperature_c: float = -35.0,
    solver: Union[str, Any] = "ipopt",
) -> list[dict[str, float]]:
    """Return implementable-cycle time penalties over actuator-rate pairs.

    Each row contains the pressure rate [Torr/hr], shelf-temperature rate
    [degC/hr], optimized completion time [hr], and its increase over the
    supplied idealized reference [hr and %].
    """
    if not np.isfinite(idealized_time_hr) or idealized_time_hr <= 0.0:
        raise ValueError("idealized_time_hr must be finite and positive")
    pressure_rates = tuple(float(value) for value in pressure_ramp_rates_torr_hr)
    shelf_rates = tuple(float(value) for value in shelf_temperature_ramp_rates_c_hr)
    if not pressure_rates or any(value <= 0.0 for value in pressure_rates):
        raise ValueError("pressure_ramp_rates_torr_hr must contain positive values")
    if not shelf_rates or any(value <= 0.0 for value in shelf_rates):
        raise ValueError("shelf_temperature_ramp_rates_c_hr must contain positive values")

    _, collocation_nfe = matched_nfe_for_point_budget(point_budget, ncp)
    rows: list[dict[str, float]] = []
    for pressure_rate in pressure_rates:
        for shelf_rate in shelf_rates:
            run = run_pyomo_dae(
                a1,
                kc,
                discretization="collocation",
                nfe=collocation_nfe,
                ncp=ncp,
                final_dried_fraction=final_dried_fraction,
                initial_pressure=initial_pressure_torr,
                initial_shelf_temperature=initial_shelf_temperature_c,
                pressure_ramp_rate=pressure_rate,
                shelf_temperature_ramp_rate=shelf_rate,
                solver=solver,
            )
            _require_successful_run(
                run,
                f"slew sweep P={pressure_rate:g} Torr/hr, "
                f"Tsh={shelf_rate:g} degC/hr",
            )
            penalty_hr = run.objective_time_hr - idealized_time_hr  # [hr]
            rows.append(
                {
                    "pressure_ramp_rate_torr_hr": pressure_rate,
                    "shelf_temperature_ramp_rate_c_hr": shelf_rate,
                    "objective_time_hr": run.objective_time_hr,
                    "penalty_hr": penalty_hr,
                    "penalty_percent": 100.0 * penalty_hr / idealized_time_hr,
                }
            )
    return rows


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
    "ImplementabilityAnalysis",
    "SolverRun",
    "comparison_inputs",
    "matched_nfe_for_point_budget",
    "run_case_comparison",
    "run_discretization_sensitivity",
    "run_implementability_analysis",
    "run_pyomo_dae",
    "run_scipy_reference",
    "run_slew_rate_sweep",
    "trajectory_constraint_diagnostics",
]
