from __future__ import annotations

import numpy as np
import pytest

from examples.current_main_joint_optimizer_comparison import (
    ImplementabilityAnalysis,
    run_implementability_analysis,
    run_slew_rate_sweep,
    comparison_inputs,
    matched_nfe_for_point_budget,
    run_case_comparison,
    run_pyomo_dae,
    trajectory_constraint_diagnostics,
)
from tests.pyomo_solver import require_pyomo_solver


def test_joint_comparison_inputs_match_paper_mannitol_joint_case() -> None:
    data = comparison_inputs(18.0, 3.3e-4)

    assert data["product"]["A1"] == pytest.approx(18.0)
    assert data["product"]["T_pr_crit"] == pytest.approx(-5.0)
    assert data["ht"]["KC"] == pytest.approx(3.3e-4)
    assert data["pchamber"] == {"min": 0.05, "max": 0.5}
    assert data["tshelf"]["min"] == pytest.approx(-45.0)
    assert data["tshelf"]["max"] == pytest.approx(120.0)
    assert data["nvial"] == 398


def test_joint_case_comparison_rejects_unmatched_transcription_points() -> None:
    with pytest.raises(ValueError, match="same number of transcription points"):
        run_case_comparison(
            16.0,
            2.75e-4,
            finite_difference_nfe=24,
            collocation_nfe=24,
            ncp=3,
        )


def test_trajectory_constraint_diagnostics_cover_sequential_outputs() -> None:
    """Notebook acceptance diagnostics apply independently to SciPy tables."""
    data = comparison_inputs(16.0, 2.75e-4)
    table = np.array(
        [
            [0.0, -7.0, -5.0, 20.0, 50.0, 1.0, 0.0],
            [1.0, -6.0, -4.4, 20.0, 40.0, 1.0, 100.0],
        ]
    )

    diagnostics = trajectory_constraint_diagnostics(table, data)

    assert diagnostics["product_temperature_violation_c"] == pytest.approx(0.6)
    assert diagnostics["pressure_lower_violation_mtorr"] == pytest.approx(10.0)
    assert diagnostics["pressure_upper_violation_mtorr"] == pytest.approx(0.0)
    assert diagnostics["shelf_lower_violation_c"] == pytest.approx(0.0)
    assert diagnostics["shelf_upper_violation_c"] == pytest.approx(0.0)
    assert diagnostics["final_dried_percent"] == pytest.approx(100.0)


@pytest.mark.pyomo
@pytest.mark.parametrize("warmstart_from_scipy", [False, True])
def test_current_main_joint_comparison_helper_solves_smoke_case(
    warmstart_from_scipy,
) -> None:
    solver = require_pyomo_solver("ipopt")

    case = run_case_comparison(
        16.0,
        2.75e-4,
        scipy_dt=0.1,
        finite_difference_nfe=12,
        collocation_nfe=4,
        ncp=3,
        final_dried_fraction=1.0,
        timing_repeats=1,
        warmstart_from_scipy=warmstart_from_scipy,
        solver=solver,
    )

    assert case.scipy_trajectory.shape[1] == 7
    assert case.finite_difference_trajectory.shape == (13, 7)
    assert case.collocation_trajectory.shape == (13, 7)
    assert case.scipy_trajectory[-1, 6] >= 100.0 - 1.0e-6
    assert case.finite_difference_trajectory[-1, 6] >= 100.0 - 1.0e-3
    assert case.collocation_trajectory[-1, 6] >= 100.0 - 1.0e-3
    assert case.finite_difference_max_constraint_violation < 1.0e-4
    assert case.collocation_max_constraint_violation < 1.0e-4
    assert np.isfinite(case.finite_difference_objective_gap_percent)
    assert np.isfinite(case.collocation_objective_gap_percent)
    assert abs(case.finite_difference_objective_gap_percent) < 10.0
    assert abs(case.collocation_objective_gap_percent) < 5.0
    assert case.finite_difference_speedup > 0.0
    assert case.collocation_speedup > 0.0
    assert case.finite_difference_n_variables > 0
    assert case.finite_difference_n_constraints > 0
    assert case.collocation_n_variables > 0
    assert case.collocation_n_constraints > 0


@pytest.mark.pyomo
def test_joint_pyomo_rate_limited_paper_extension_solves() -> None:
    """Pyomo adds coupled initial-control and rate limits to the paper case."""
    solver = require_pyomo_solver("ipopt")

    run = run_pyomo_dae(
        16.0,
        2.75e-4,
        discretization="collocation",
        nfe=8,
        ncp=3,
        initial_pressure=0.15,
        initial_shelf_temperature=30.0,
        pressure_ramp_rate=0.05,
        shelf_temperature_ramp_rate=30.0,
        solver=solver,
    )
    table = run.trajectory
    dt = np.diff(table[:, 0])  # [hr]

    assert run.success
    assert table.shape == (25, 7)
    assert table[-1, 6] >= 100.0 - 1.0e-3
    assert table[0, 4] == pytest.approx(150.0, abs=1.0e-3)  # [mTorr]
    assert table[0, 3] == pytest.approx(30.0, abs=1.0e-3)  # [degC]
    assert np.max(np.abs(np.diff(table[:, 4]) / 1000.0) / dt) <= 0.05 + 1.0e-5
    assert np.max(np.abs(np.diff(table[:, 3])) / dt) <= 30.0 + 1.0e-5


@pytest.mark.serial
@pytest.mark.notebook
@pytest.mark.pyomo
def test_current_main_joint_comparison_notebook_execution(repo_root) -> None:
    require_pyomo_solver("ipopt")
    papermill = pytest.importorskip("papermill")

    papermill.execute_notebook(
        repo_root / "docs/examples/current_main_joint_optimizer_comparison.ipynb",
        repo_root / "docs/examples/current_main_joint_optimizer_comparison_output.ipynb",
        parameters={
            "a1": 16.0,
            "kc": 2.75e-4,
            "scipy_dt": 0.1,
            "point_budget": 25,
            "ncp": 3,
            "final_dried_fraction": 1.0,
            "pressure_ramp_rate_torr_hr": 0.05,
            "shelf_temperature_ramp_rate_c_hr": 30.0,
            # Two budgets keep the mesh-sensitivity trend checkable while the
            # smoke run stays short.
            "sensitivity_point_budgets": [25, 49],
            "scipy_refinement_dt_values": [0.02, 0.01],
            "shelf_sweep_rates_c_hr": [30.0, 60.0],
        },
    )


def test_implementability_penalty_decomposition_is_additive() -> None:
    """Anchoring and slew increments sum to the total drying-time penalty [hr]."""
    from examples.current_main_comparison import SolverRun

    def run(objective_time_hr: float) -> SolverRun:
        return SolverRun(
            trajectory=np.zeros((2, 7)),
            wall_time_s=0.0,
            objective_time_hr=objective_time_hr,
            success=True,
            solver_status="ok",
            termination_condition="optimal",
            max_constraint_violation=0.0,
            n_time_points=2,
            n_variables=1,
            n_constraints=1,
            solver_iterations=1,
        )

    analysis = ImplementabilityAnalysis(
        idealized=run(10.0),
        anchored_unlimited=run(10.1),
        pressure_preconditioned=run(12.0),
        implementable=run(12.5),
    )

    assert analysis.anchor_only_penalty_hr == pytest.approx(0.1)
    assert analysis.rate_and_interaction_penalty_hr == pytest.approx(2.4)
    assert analysis.pressure_start_penalty_hr == pytest.approx(0.5)
    assert analysis.preconditioned_penalty_hr == pytest.approx(2.0)
    assert analysis.total_penalty_hr == pytest.approx(2.5)
    assert analysis.total_penalty_percent == pytest.approx(25.0)
    assert analysis.total_penalty_hr == pytest.approx(
        analysis.anchor_only_penalty_hr + analysis.rate_and_interaction_penalty_hr
    )
    assert analysis.total_penalty_hr == pytest.approx(
        analysis.preconditioned_penalty_hr + analysis.pressure_start_penalty_hr
    )


@pytest.mark.parametrize(
    ("pressure_rates", "shelf_rates", "message"),
    [
        ([], [30.0], "pressure_ramp_rates_torr_hr"),
        ([np.nan], [30.0], "pressure_ramp_rates_torr_hr"),
        ([0.05], [0.0], "shelf_temperature_ramp_rates_c_hr"),
        ([0.05], [np.inf], "shelf_temperature_ramp_rates_c_hr"),
    ],
)
def test_slew_rate_sweep_rejects_empty_or_nonpositive_rates(
    pressure_rates, shelf_rates, message
) -> None:
    with pytest.raises(ValueError, match=message):
        run_slew_rate_sweep(
            16.0,
            2.75e-4,
            10.0,
            pressure_ramp_rates_torr_hr=pressure_rates,
            shelf_temperature_ramp_rates_c_hr=shelf_rates,
        )


@pytest.mark.pyomo
def test_implementability_analysis_solves_and_decomposes_smoke_case() -> None:
    """The real optimizer runs preserve both penalty identities [hr]."""
    solver = require_pyomo_solver("ipopt")

    analysis = run_implementability_analysis(
        16.0,
        2.75e-4,
        point_budget=25,
        ncp=3,
        initial_pressure_torr=0.15,
        initial_shelf_temperature_c=-35.0,
        pressure_ramp_rate_torr_hr=0.05,
        shelf_temperature_ramp_rate_c_hr=10.0,
        solver=solver,
    )

    for run in (
        analysis.idealized,
        analysis.anchored_unlimited,
        analysis.pressure_preconditioned,
        analysis.implementable,
    ):
        assert run.success
        assert run.trajectory.shape == (25, 7)
        assert run.trajectory[-1, 6] >= 100.0 - 1.0e-3
    assert analysis.anchored_unlimited.objective_time_hr == pytest.approx(
        analysis.idealized.objective_time_hr, abs=1.0e-3
    )
    assert analysis.pressure_preconditioned.trajectory[0, 4] == pytest.approx(
        50.0, abs=1.0e-3
    )  # [mTorr]
    assert analysis.implementable.trajectory[0, 4] == pytest.approx(
        150.0, abs=1.0e-3
    )  # [mTorr]
    # The pressure-start term is signed and case-dependent: preconditioning to
    # the pressure floor is slower here, because a higher starting pressure
    # improves early vial heat transfer. Assert the invariants instead.
    assert analysis.pressure_preconditioned.success
    assert analysis.pressure_start_penalty_hr == pytest.approx(
        analysis.implementable.objective_time_hr
        - analysis.pressure_preconditioned.objective_time_hr
    )
    # Rate limits can never beat the unconstrained optimum.
    assert analysis.total_penalty_hr > 0.0
    assert (
        analysis.implementable.objective_time_hr
        >= analysis.idealized.objective_time_hr
    )
    assert analysis.idealized.shadow_prices["product_temperature_limit"] < 0.0
    assert analysis.total_penalty_hr == pytest.approx(
        analysis.anchor_only_penalty_hr + analysis.rate_and_interaction_penalty_hr
    )
    assert analysis.total_penalty_hr == pytest.approx(
        analysis.preconditioned_penalty_hr + analysis.pressure_start_penalty_hr
    )

    sweep_rows = run_slew_rate_sweep(
        16.0,
        2.75e-4,
        analysis.idealized.objective_time_hr,
        pressure_ramp_rates_torr_hr=[0.05],
        shelf_temperature_ramp_rates_c_hr=[30.0],
        point_budget=25,
        ncp=3,
        solver=solver,
    )
    assert len(sweep_rows) == 1
    assert sweep_rows[0]["objective_time_hr"] > analysis.idealized.objective_time_hr
    assert sweep_rows[0]["penalty_hr"] == pytest.approx(
        sweep_rows[0]["objective_time_hr"] - analysis.idealized.objective_time_hr
    )


def test_shared_point_budget_helper_remains_available() -> None:
    assert matched_nfe_for_point_budget(25, ncp=3) == (24, 8)
