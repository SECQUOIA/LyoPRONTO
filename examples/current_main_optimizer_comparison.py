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

from dataclasses import dataclass
from time import perf_counter
from typing import Any, Sequence, Tuple, Union

import numpy as np

from lyopronto import opt_Tsh


DEFAULT_A1_VALUES = (16.0, 18.0, 20.0)
DEFAULT_KC_VALUES = (2.75e-4, 3.30e-4, 4.00e-4)


@dataclass
class SolverRun:
    """One timed optimizer execution and its normalized trajectory."""

    trajectory: np.ndarray
    wall_time_s: float
    objective_time_hr: float
    success: bool
    solver_status: str
    termination_condition: str
    max_constraint_violation: float
    n_time_points: int


@dataclass
class CaseComparison:
    """Repeated SciPy, finite-difference, and collocation measurements."""

    a1: float
    kc: float
    scipy_trajectory: np.ndarray
    finite_difference_trajectory: np.ndarray
    collocation_trajectory: np.ndarray
    scipy_wall_times_s: Tuple[float, ...]
    finite_difference_wall_times_s: Tuple[float, ...]
    collocation_wall_times_s: Tuple[float, ...]
    finite_difference_status: str
    finite_difference_termination: str
    collocation_status: str
    collocation_termination: str
    finite_difference_max_constraint_violation: float
    collocation_max_constraint_violation: float

    @property
    def scipy_objective_time_hr(self) -> float:
        """Return the SciPy completion-time objective."""
        return float(self.scipy_trajectory[-1, 0])

    @property
    def finite_difference_objective_time_hr(self) -> float:
        """Return the finite-difference Pyomo.DAE final-time objective."""
        return float(self.finite_difference_trajectory[-1, 0])

    @property
    def collocation_objective_time_hr(self) -> float:
        """Return the collocation Pyomo.DAE final-time objective."""
        return float(self.collocation_trajectory[-1, 0])

    @property
    def scipy_wall_median_s(self) -> float:
        """Return the median SciPy wall time."""
        return float(np.median(self.scipy_wall_times_s))

    @property
    def finite_difference_wall_median_s(self) -> float:
        """Return the median finite-difference wall time."""
        return float(np.median(self.finite_difference_wall_times_s))

    @property
    def collocation_wall_median_s(self) -> float:
        """Return the median collocation wall time."""
        return float(np.median(self.collocation_wall_times_s))

    @property
    def finite_difference_speedup(self) -> float:
        """Return SciPy/finite-difference median runtime."""
        return self.scipy_wall_median_s / self.finite_difference_wall_median_s

    @property
    def collocation_speedup(self) -> float:
        """Return SciPy/collocation median runtime."""
        return self.scipy_wall_median_s / self.collocation_wall_median_s

    @property
    def finite_difference_objective_gap_percent(self) -> float:
        """Return the finite-difference drying-time gap from SciPy."""
        return 100.0 * (
            self.finite_difference_objective_time_hr - self.scipy_objective_time_hr
        ) / self.scipy_objective_time_hr

    @property
    def collocation_objective_gap_percent(self) -> float:
        """Return the collocation drying-time gap from SciPy."""
        return 100.0 * (
            self.collocation_objective_time_hr - self.scipy_objective_time_hr
        ) / self.scipy_objective_time_hr


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
    trajectory = result.as_table()
    max_violation = max(
        (float(value) if value is not None else 0.0)
        for value in result.constraint_violations.values()
    )
    objective = (
        float(result.objective_time_hr)
        if result.objective_time_hr is not None
        else float("nan")
    )
    return SolverRun(
        trajectory=trajectory,
        wall_time_s=float(wall_time_s),
        objective_time_hr=objective,
        success=bool(result.success),
        solver_status=str(result.solver_status),
        termination_condition=str(result.termination_condition),
        max_constraint_violation=max_violation,
        n_time_points=int(result.discretization["n_time_points"]),
    )


def _require_success(run: SolverRun, label: str, a1: float, kc: float) -> None:
    if not run.success:
        raise RuntimeError(
            f"{label} failed for A1={a1}, KC={kc}: "
            f"{run.solver_status}/{run.termination_condition}"
        )


def run_case_comparison(
    a1: float,
    kc: float,
    *,
    scipy_dt: float = 0.01,
    nfe: int = 24,
    ncp: int = 3,
    final_dried_fraction: float = 1.0,
    timing_repeats: int = 1,
    warmstart_from_scipy: bool = False,
    solver: Union[str, Any] = "ipopt",
) -> CaseComparison:
    """Run repeated equivalent SciPy, FD, and collocation optimizations."""
    if timing_repeats < 1:
        raise ValueError("timing_repeats must be at least one")

    scipy_runs = []
    finite_difference_runs = []
    collocation_runs = []
    for _ in range(int(timing_repeats)):
        scipy_run = run_scipy_reference(a1, kc, dt=scipy_dt)
        _require_success(scipy_run, "SciPy", a1, kc)
        initialization = scipy_run.trajectory if warmstart_from_scipy else None
        finite_difference_run = run_pyomo_dae(
            a1,
            kc,
            discretization="finite_difference",
            nfe=nfe,
            ncp=ncp,
            final_dried_fraction=final_dried_fraction,
            initialize=initialization,
            solver=solver,
        )
        collocation_run = run_pyomo_dae(
            a1,
            kc,
            discretization="collocation",
            nfe=nfe,
            ncp=ncp,
            final_dried_fraction=final_dried_fraction,
            initialize=initialization,
            solver=solver,
        )
        _require_success(finite_difference_run, "Pyomo.DAE finite difference", a1, kc)
        _require_success(collocation_run, "Pyomo.DAE collocation", a1, kc)
        scipy_runs.append(scipy_run)
        finite_difference_runs.append(finite_difference_run)
        collocation_runs.append(collocation_run)

    return CaseComparison(
        a1=float(a1),
        kc=float(kc),
        scipy_trajectory=scipy_runs[-1].trajectory,
        finite_difference_trajectory=finite_difference_runs[-1].trajectory,
        collocation_trajectory=collocation_runs[-1].trajectory,
        scipy_wall_times_s=tuple(run.wall_time_s for run in scipy_runs),
        finite_difference_wall_times_s=tuple(
            run.wall_time_s for run in finite_difference_runs
        ),
        collocation_wall_times_s=tuple(run.wall_time_s for run in collocation_runs),
        finite_difference_status=finite_difference_runs[-1].solver_status,
        finite_difference_termination=finite_difference_runs[-1].termination_condition,
        collocation_status=collocation_runs[-1].solver_status,
        collocation_termination=collocation_runs[-1].termination_condition,
        finite_difference_max_constraint_violation=max(
            run.max_constraint_violation for run in finite_difference_runs
        ),
        collocation_max_constraint_violation=max(
            run.max_constraint_violation for run in collocation_runs
        ),
    )


def run_discretization_sensitivity(
    a1: float,
    kc: float,
    scipy_trajectory: np.ndarray,
    *,
    nfe_values: Sequence[int] = (8, 16, 24),
    ncp: int = 3,
    final_dried_fraction: float = 1.0,
    solver: Union[str, Any] = "ipopt",
) -> list[dict[str, Any]]:
    """Evaluate objective convergence for both DAE transformations."""
    scipy_objective = float(np.asarray(scipy_trajectory)[-1, 0])
    rows: list[dict[str, Any]] = []
    for method in ("finite_difference", "collocation"):
        for nfe in nfe_values:
            run = run_pyomo_dae(
                a1,
                kc,
                discretization=method,
                nfe=int(nfe),
                ncp=ncp,
                final_dried_fraction=final_dried_fraction,
                solver=solver,
            )
            if not run.success:
                raise RuntimeError(f"Pyomo.DAE {method} solve failed for nfe={nfe}")
            rows.append(
                {
                    "method": method,
                    "nfe": int(nfe),
                    "ncp": None if method == "finite_difference" else int(ncp),
                    "n_time_points": run.n_time_points,
                    "objective_time_hr": run.objective_time_hr,
                    "objective_gap_percent": 100.0
                    * (run.objective_time_hr - scipy_objective)
                    / scipy_objective,
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
    "run_case_comparison",
    "run_discretization_sensitivity",
    "run_pyomo_dae",
    "run_scipy_reference",
]
