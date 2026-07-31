"""Helpers for the current-main SciPy/Pyomo comparison tutorial.

The historical comparison optimized free final time with two Pyomo.DAE
discretizations.  Current ``main`` instead exposes a fixed-horizon,
backward-Euler Pyomo validation prototype.  These helpers make the comparison
appropriate for that current formulation:

* run the legacy SciPy shelf-temperature optimizer to complete drying;
* use the SciPy completion time as a shared Pyomo horizon;
* compare an integrated form of the current driving-force objective; and
* retain the seven-column legacy trajectory convention for plotting.

The narrative and full parameter sweep live in
``docs/examples/current_main_optimizer_comparison.ipynb``.  Pyomo and IPOPT
are imported only when a Pyomo solve is requested, so non-Pyomo installations
can still import and test the analysis helpers.
"""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Any, Sequence, Tuple, Union

import numpy as np
from scipy.integrate import trapezoid

from lyopronto import constant, functions, opt_Tsh


DEFAULT_A1_VALUES = (16.0, 18.0, 20.0)
DEFAULT_KC_VALUES = (2.75e-4, 3.30e-4, 4.00e-4)


@dataclass
class SolverRun:
    """One timed solver execution and its normalized trajectory."""

    trajectory: np.ndarray
    wall_time_s: float
    success: bool
    solver_status: str
    termination_condition: str
    max_constraint_violation: float


@dataclass
class CaseComparison:
    """Repeated SciPy/Pyomo measurements for one ``A1``/``KC`` case."""

    a1: float
    kc: float
    scipy_trajectory: np.ndarray
    pyomo_trajectory: np.ndarray
    scipy_wall_times_s: Tuple[float, ...]
    pyomo_wall_times_s: Tuple[float, ...]
    pyomo_status: str
    pyomo_termination: str
    max_constraint_violation: float

    @property
    def horizon_hr(self) -> float:
        """Return the common comparison horizon in hours."""
        return float(self.scipy_trajectory[-1, 0])

    @property
    def scipy_wall_median_s(self) -> float:
        """Return the median SciPy wall time."""
        return float(np.median(self.scipy_wall_times_s))

    @property
    def pyomo_wall_median_s(self) -> float:
        """Return the median Pyomo wall time."""
        return float(np.median(self.pyomo_wall_times_s))

    @property
    def speedup(self) -> float:
        """Return the workflow-level median SciPy/Pyomo runtime ratio."""
        return self.scipy_wall_median_s / self.pyomo_wall_median_s

    @property
    def scipy_objective(self) -> float:
        """Return the integrated SciPy driving-force objective."""
        return integrated_driving_force(self.scipy_trajectory)

    @property
    def pyomo_objective(self) -> float:
        """Return the integrated Pyomo driving-force objective."""
        return integrated_driving_force(self.pyomo_trajectory)

    @property
    def objective_gap_percent(self) -> float:
        """Return the Pyomo objective gap relative to SciPy.

        The denominator uses the absolute SciPy objective because the driving
        force ``Pch - Psub`` is normally negative.  A positive gap means the
        Pyomo objective is higher (less negative) than the SciPy reference.
        """
        return 100.0 * (self.pyomo_objective - self.scipy_objective) / abs(
            self.scipy_objective
        )


def comparison_inputs(a1: float, kc: float) -> dict[str, Any]:
    """Return the explicit baseline dictionaries for one grid point."""
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
        "scipy_pchamber": {
            "setpt": [0.1],
            "dt_setpt": [1800.0],
            "ramp_rate": 0.5,
        },
        "scipy_tshelf": {"min": -45.0, "max": 120.0},
        "pyomo_pchamber": {
            "min": 0.1,
            "max": 0.1,
            "setpt": [0.1],
            "dt_setpt": [1800.0],
            "ramp_rate": 0.5,
        },
        "pyomo_tshelf": {
            "min": -45.0,
            "max": 120.0,
            "init": -35.0,
            "setpt": [20.0],
            "dt_setpt": [1800.0],
            "ramp_rate": 1.0,
        },
        "eq_cap": {"a": -0.182, "b": 11.7},
        "nvial": 400,
    }


def integrated_driving_force(trajectory: np.ndarray) -> float:
    """Integrate ``Pch - Psub`` over a seven-column legacy trajectory.

    Legacy output pressure (column 4) is mTorr, while vapor pressure is Torr.
    The returned value therefore has units of Torr-hour.
    """
    table = np.asarray(trajectory, dtype=float)
    if table.ndim != 2 or table.shape[1] != 7 or table.shape[0] < 2:
        raise ValueError("trajectory must be a two-dimensional, seven-column table")
    if not np.all(np.isfinite(table)):
        raise ValueError("trajectory must contain only finite values")

    time_hr = table[:, 0]
    pch_torr = table[:, 4] / constant.Torr_to_mTorr
    psub_torr = np.asarray(functions.Vapor_pressure(table[:, 1]), dtype=float)
    return float(trapezoid(pch_torr - psub_torr, time_hr))


def run_scipy_reference(a1: float, kc: float, *, dt: float = 0.01) -> SolverRun:
    """Run the legacy sequential shelf-temperature optimizer to completion."""
    data = comparison_inputs(a1, kc)
    start = perf_counter()
    trajectory = opt_Tsh.dry(
        data["vial"],
        dict(data["product"]),
        data["ht"],
        dict(data["scipy_pchamber"]),
        dict(data["scipy_tshelf"]),
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
        and trajectory[-1, 6] >= 99.0
    )
    return SolverRun(
        trajectory=np.asarray(trajectory, dtype=float),
        wall_time_s=float(wall_time_s),
        success=success,
        solver_status="n/a",
        termination_condition="completed" if success else "incomplete",
        max_constraint_violation=0.0,
    )


def run_pyomo_at_horizon(
    a1: float,
    kc: float,
    horizon_hr: float,
    *,
    n_steps: int = 24,
    final_dried_fraction: float = 0.989,
    solver: Union[str, Any] = "ipopt",
) -> SolverRun:
    """Run the current fixed-horizon Pyomo shelf-temperature optimizer."""
    from lyopronto.pyomo_models import solve_primary_drying_optimization

    if horizon_hr <= 0.0:
        raise ValueError("horizon_hr must be positive")
    if n_steps < 1:
        raise ValueError("n_steps must be at least one")

    data = comparison_inputs(a1, kc)
    start = perf_counter()
    result = solve_primary_drying_optimization(
        data["vial"],
        data["product"],
        data["ht"],
        data["pyomo_pchamber"],
        data["pyomo_tshelf"],
        n_steps=int(n_steps),
        dt=float(horizon_hr) / int(n_steps),
        mode="shelf_temperature",
        final_dried_fraction=float(final_dried_fraction),
        eq_cap=data["eq_cap"],
        nvial=data["nvial"],
        solver=solver,
    )
    wall_time_s = perf_counter() - start
    trajectory = result.as_table()
    max_violation = max(
        (float(value) if value is not None else 0.0)
        for value in result.constraint_violations.values()
    )
    return SolverRun(
        trajectory=trajectory,
        wall_time_s=float(wall_time_s),
        success=bool(result.success),
        solver_status=str(result.solver_status),
        termination_condition=str(result.termination_condition),
        max_constraint_violation=max_violation,
    )


def run_case_comparison(
    a1: float,
    kc: float,
    *,
    scipy_dt: float = 0.01,
    n_steps: int = 24,
    final_dried_fraction: float = 0.989,
    timing_repeats: int = 1,
    solver: Union[str, Any] = "ipopt",
) -> CaseComparison:
    """Run repeated SciPy/Pyomo measurements for one grid point."""
    if timing_repeats < 1:
        raise ValueError("timing_repeats must be at least one")

    scipy_runs = []
    pyomo_runs = []
    for _ in range(int(timing_repeats)):
        scipy_run = run_scipy_reference(a1, kc, dt=scipy_dt)
        if not scipy_run.success:
            raise RuntimeError(f"SciPy did not complete drying for A1={a1}, KC={kc}")
        pyomo_run = run_pyomo_at_horizon(
            a1,
            kc,
            float(scipy_run.trajectory[-1, 0]),
            n_steps=n_steps,
            final_dried_fraction=final_dried_fraction,
            solver=solver,
        )
        if not pyomo_run.success:
            raise RuntimeError(
                "Pyomo did not solve successfully for "
                f"A1={a1}, KC={kc}: {pyomo_run.solver_status}/"
                f"{pyomo_run.termination_condition}"
            )
        scipy_runs.append(scipy_run)
        pyomo_runs.append(pyomo_run)

    return CaseComparison(
        a1=float(a1),
        kc=float(kc),
        scipy_trajectory=scipy_runs[-1].trajectory,
        pyomo_trajectory=pyomo_runs[-1].trajectory,
        scipy_wall_times_s=tuple(run.wall_time_s for run in scipy_runs),
        pyomo_wall_times_s=tuple(run.wall_time_s for run in pyomo_runs),
        pyomo_status=pyomo_runs[-1].solver_status,
        pyomo_termination=pyomo_runs[-1].termination_condition,
        max_constraint_violation=max(run.max_constraint_violation for run in pyomo_runs),
    )


def run_mesh_sensitivity(
    a1: float,
    kc: float,
    scipy_trajectory: np.ndarray,
    *,
    n_steps_values: Sequence[int] = (12, 24, 48),
    final_dried_fraction: float = 0.989,
    solver: Union[str, Any] = "ipopt",
) -> list[dict[str, float]]:
    """Evaluate current backward-Euler mesh sensitivity on one horizon."""
    horizon_hr = float(np.asarray(scipy_trajectory)[-1, 0])
    scipy_objective = integrated_driving_force(scipy_trajectory)
    rows = []
    for n_steps in n_steps_values:
        run = run_pyomo_at_horizon(
            a1,
            kc,
            horizon_hr,
            n_steps=int(n_steps),
            final_dried_fraction=final_dried_fraction,
            solver=solver,
        )
        if not run.success:
            raise RuntimeError(f"Pyomo mesh solve failed for n_steps={n_steps}")
        objective = integrated_driving_force(run.trajectory)
        rows.append(
            {
                "n_steps": float(n_steps),
                "objective": objective,
                "objective_gap_percent": 100.0
                * (objective - scipy_objective)
                / abs(scipy_objective),
                "final_percent_dried": float(run.trajectory[-1, 6]),
                "wall_time_s": run.wall_time_s,
                "max_constraint_violation": run.max_constraint_violation,
            }
        )
    return rows


__all__ = [
    "CaseComparison",
    "DEFAULT_A1_VALUES",
    "DEFAULT_KC_VALUES",
    "SolverRun",
    "comparison_inputs",
    "integrated_driving_force",
    "run_case_comparison",
    "run_mesh_sensitivity",
    "run_pyomo_at_horizon",
    "run_scipy_reference",
]
