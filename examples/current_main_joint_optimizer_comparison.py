"""Helpers for the current-main joint-control optimizer tutorial.

The experiment compares equivalent pressure-and-temperature optimization
problems:

* legacy SciPy maximizes sublimation rate at each dried-cake state and advances
  until complete drying;
* Pyomo.DAE optimizes both complete control trajectories simultaneously and
  minimizes the free final drying time; and
* the Pyomo model is transcribed with either backward finite differences or
  LAGRANGE-RADAU orthogonal collocation.

Both paths use the same pressure and shelf-temperature bounds, physics,
constraints, completion target, and seven-column trajectory contract. The
tutorial notebook owns the one-off sweep and plots; this module keeps the
experiment runs importable and testable.
"""

from __future__ import annotations

from time import perf_counter
from typing import Any, Sequence, Union

import numpy as np

from examples.current_main_optimizer_comparison import (
    CaseComparison,
    SolverRun,
    matched_nfe_for_point_budget,
)
from lyopronto import opt_Pch_Tsh


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
    solver: Union[str, Any] = "ipopt",
) -> SolverRun:
    """Run one current-physics, free-final-time joint optimization."""
    from lyopronto.pyomo_models import solve_dae_joint_optimization

    data = comparison_inputs(a1, kc)
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
        n_variables=int(result.discretization["n_variables"]),
        n_constraints=int(result.discretization["n_constraints"]),
        solver_iterations=result.discretization["solver_iterations"],
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
    finite_difference_nfe: int = 24,
    collocation_nfe: int = 8,
    ncp: int = 3,
    final_dried_fraction: float = 1.0,
    timing_repeats: int = 1,
    warmstart_from_scipy: bool = False,
    solver: Union[str, Any] = "ipopt",
) -> CaseComparison:
    """Run repeated equivalent joint optimizations at a matched point budget."""
    if timing_repeats < 1:
        raise ValueError("timing_repeats must be at least one")
    finite_difference_points = int(finite_difference_nfe) + 1
    collocation_points = int(collocation_nfe) * int(ncp) + 1
    if finite_difference_points != collocation_points:
        raise ValueError(
            "finite_difference_nfe and collocation_nfe must create the same "
            "number of transcription points"
        )

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
            nfe=finite_difference_nfe,
            ncp=ncp,
            final_dried_fraction=final_dried_fraction,
            initialize=initialization,
            solver=solver,
        )
        collocation_run = run_pyomo_dae(
            a1,
            kc,
            discretization="collocation",
            nfe=collocation_nfe,
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
        finite_difference_n_variables=int(finite_difference_runs[-1].n_variables),
        finite_difference_n_constraints=int(finite_difference_runs[-1].n_constraints),
        finite_difference_solver_iterations=finite_difference_runs[-1].solver_iterations,
        collocation_n_variables=int(collocation_runs[-1].n_variables),
        collocation_n_constraints=int(collocation_runs[-1].n_constraints),
        collocation_solver_iterations=collocation_runs[-1].solver_iterations,
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
    scipy_objective = float(np.asarray(scipy_trajectory)[-1, 0])
    rows: list[dict[str, Any]] = []
    for point_budget in point_budgets:
        finite_difference_nfe, collocation_nfe = matched_nfe_for_point_budget(
            int(point_budget), ncp
        )
        for method, nfe in (
            ("finite_difference", finite_difference_nfe),
            ("collocation", collocation_nfe),
        ):
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
                    "point_budget": int(point_budget),
                    "nfe": int(nfe),
                    "ncp": None if method == "finite_difference" else int(ncp),
                    "n_time_points": run.n_time_points,
                    "objective_time_hr": run.objective_time_hr,
                    "objective_gap_percent": 100.0
                    * (run.objective_time_hr - scipy_objective)
                    / scipy_objective,
                    "final_percent_dried": float(run.trajectory[-1, 6]),
                    "wall_time_s": run.wall_time_s,
                    "n_variables": run.n_variables,
                    "n_constraints": run.n_constraints,
                    "solver_iterations": run.solver_iterations,
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
    "matched_nfe_for_point_budget",
    "run_case_comparison",
    "run_discretization_sensitivity",
    "run_pyomo_dae",
    "run_scipy_reference",
]
