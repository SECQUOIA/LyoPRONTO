"""Unit tests for formulation-independent current-main comparison orchestration."""

from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

import examples.current_main_joint_optimizer_comparison as joint_comparison
import examples.current_main_optimizer_comparison as shelf_comparison
import examples.current_main_pressure_optimizer_comparison as pressure_comparison
from examples.current_main_comparison import (
    CaseComparison,
    SolverRun,
    collect_case_comparison,
    collect_discretization_sensitivity,
    solver_run_from_dae_result,
)


def _trajectory(final_time_hr: float) -> np.ndarray:
    """Return a minimal legacy-shaped trajectory ending at ``final_time_hr`` [hr]."""
    return np.array(
        [
            [0.0, -30.0, -29.0, -20.0, 100.0, 0.01, 0.0],
            [final_time_hr, -28.0, -25.0, 10.0, 50.0, 0.02, 100.0],
        ]
    )


def _solver_run(
    final_time_hr: float,
    wall_time_s: float,
    *,
    n_time_points: int,
) -> SolverRun:
    """Return a successful normalized run with explicit time units."""
    return SolverRun(
        trajectory=_trajectory(final_time_hr),
        wall_time_s=wall_time_s,
        objective_time_hr=final_time_hr,
        success=True,
        solver_status="ok",
        termination_condition="optimal",
        max_constraint_violation=1.0e-8,
        n_time_points=n_time_points,
        n_variables=20,
        n_constraints=10,
        solver_iterations=4,
    )


def test_experiment_modules_preserve_shared_compatibility_imports() -> None:
    """Existing helper import paths expose the one shared result contract."""
    for module in (shelf_comparison, pressure_comparison, joint_comparison):
        assert module.SolverRun is SolverRun
        assert module.CaseComparison is CaseComparison
        assert module.matched_nfe_for_point_budget(25, ncp=3) == (24, 8)


def test_collect_case_comparison_owns_repeats_warmstarts_and_aggregation() -> None:
    """Shared orchestration preserves experiment callbacks and timing tuples."""
    scipy_runs = []
    dae_calls = []

    def run_scipy(a1: float, kc: float, *, dt: float) -> SolverRun:
        scipy_runs.append((a1, kc, dt))
        return _solver_run(10.0, float(len(scipy_runs)), n_time_points=1001)

    def run_dae(
        a1: float,
        kc: float,
        *,
        discretization: str,
        nfe: int,
        ncp: int,
        final_dried_fraction: float,
        initialize: np.ndarray,
        solver: Any,
    ) -> SolverRun:
        dae_calls.append(
            {
                "a1": a1,
                "kc": kc,
                "discretization": discretization,
                "nfe": nfe,
                "ncp": ncp,
                "final_dried_fraction": final_dried_fraction,
                "initialize": initialize,
                "solver": solver,
            }
        )
        final_time_hr = 10.5 if discretization == "finite_difference" else 10.1
        return _solver_run(
            final_time_hr,
            float(len(dae_calls)),
            n_time_points=nfe * (ncp if discretization == "collocation" else 1) + 1,
        )

    comparison = collect_case_comparison(
        16.0,
        2.75e-4,
        run_scipy=run_scipy,
        run_dae=run_dae,
        scipy_dt=0.02,
        finite_difference_nfe=6,
        collocation_nfe=2,
        ncp=3,
        final_dried_fraction=1.0,
        timing_repeats=2,
        warmstart_from_scipy=True,
        solver="ipopt",
    )

    assert isinstance(comparison, CaseComparison)
    assert scipy_runs == [(16.0, 2.75e-4, 0.02), (16.0, 2.75e-4, 0.02)]
    assert [call["discretization"] for call in dae_calls] == [
        "finite_difference",
        "collocation",
        "finite_difference",
        "collocation",
    ]
    assert all(call["initialize"] is not None for call in dae_calls)
    assert all(call["initialize"][-1, 6] == 100.0 for call in dae_calls)
    assert comparison.scipy_wall_times_s == (1.0, 2.0)
    assert comparison.finite_difference_wall_times_s == (1.0, 3.0)
    assert comparison.collocation_wall_times_s == (2.0, 4.0)
    assert comparison.finite_difference_objective_gap_percent == 5.0
    assert comparison.collocation_objective_gap_percent == pytest.approx(1.0)


def test_collect_case_comparison_rejects_failure_before_running_dae() -> None:
    """The shared success gate stops orchestration with experiment context."""
    failed_scipy = _solver_run(10.0, 1.0, n_time_points=1001)
    failed_scipy.success = False
    failed_scipy.termination_condition = "incomplete"

    def run_scipy(a1: float, kc: float, *, dt: float) -> SolverRun:
        return failed_scipy

    def run_dae(*args, **kwargs) -> SolverRun:
        raise AssertionError("DAE should not run after a failed SciPy reference")

    with pytest.raises(RuntimeError, match=r"SciPy failed for A1=16.0, KC=0.000275"):
        collect_case_comparison(
            16.0,
            2.75e-4,
            run_scipy=run_scipy,
            run_dae=run_dae,
            scipy_dt=0.02,
            finite_difference_nfe=6,
            collocation_nfe=2,
            ncp=3,
            final_dried_fraction=1.0,
            timing_repeats=1,
            warmstart_from_scipy=False,
            solver="ipopt",
        )


def test_collect_discretization_sensitivity_supports_experiment_details() -> None:
    """The shared loop owns common rows while a callback adds joint-only fields."""
    calls = []

    def run_dae(
        a1: float,
        kc: float,
        *,
        discretization: str,
        nfe: int,
        ncp: int,
        final_dried_fraction: float,
        solver: Any,
    ) -> SolverRun:
        calls.append((a1, kc, discretization, nfe, ncp, final_dried_fraction, solver))
        objective_time_hr = 11.0 if discretization == "finite_difference" else 10.1
        return _solver_run(objective_time_hr, 0.25, n_time_points=7)

    rows = collect_discretization_sensitivity(
        18.0,
        3.30e-4,
        _trajectory(10.0),
        run_dae=run_dae,
        point_budgets=(7,),
        ncp=3,
        final_dried_fraction=1.0,
        solver="ipopt",
        extra_row_values=lambda run: {"final_pressure_mtorr": float(run.trajectory[-1, 4])},
    )

    assert [call[2:4] for call in calls] == [
        ("finite_difference", 6),
        ("collocation", 2),
    ]
    assert [row["objective_gap_percent"] for row in rows] == pytest.approx([10.0, 1.0])
    assert [row["final_pressure_mtorr"] for row in rows] == [50.0, 50.0]
    assert list(rows[0]) == [
        "method",
        "point_budget",
        "nfe",
        "ncp",
        "n_time_points",
        "objective_time_hr",
        "objective_gap_percent",
        "final_pressure_mtorr",
        "final_percent_dried",
        "wall_time_s",
        "n_variables",
        "n_constraints",
        "solver_iterations",
        "max_constraint_violation",
    ]


def test_solver_run_from_dae_result_normalizes_shared_metadata() -> None:
    """DAE result conversion keeps legacy-table and solver metadata units intact."""
    result = SimpleNamespace(
        as_table=lambda: _trajectory(12.0),
        constraint_violations={"temperature": 2.0e-7, "equipment": None},
        objective_time_hr=12.0,
        success=True,
        solver_status="ok",
        termination_condition="optimal",
        shadow_prices={"product_temperature_limit": -1.2},
        discretization={
            "n_time_points": 25,
            "n_variables": 100,
            "n_constraints": 80,
            "solver_iterations": 6,
        },
    )

    run = solver_run_from_dae_result(result, wall_time_s=0.5)

    assert run.wall_time_s == 0.5
    assert run.objective_time_hr == 12.0
    assert run.max_constraint_violation == 2.0e-7
    assert run.n_time_points == 25
    assert run.n_variables == 100
    assert run.n_constraints == 80
    assert run.solver_iterations == 6
    assert run.shadow_prices == {"product_temperature_limit": -1.2}
