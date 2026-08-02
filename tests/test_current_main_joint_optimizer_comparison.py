from __future__ import annotations

import numpy as np
import pytest

from examples.current_main_joint_optimizer_comparison import (
    comparison_inputs,
    matched_nfe_for_point_budget,
    run_case_comparison,
    trajectory_constraint_diagnostics,
)
from tests.pyomo_solver import require_pyomo_solver


def test_joint_comparison_inputs_preserve_historical_grid_conventions() -> None:
    data = comparison_inputs(18.0, 3.3e-4)

    assert data["product"]["A1"] == pytest.approx(18.0)
    assert data["product"]["T_pr_crit"] == pytest.approx(-25.0)
    assert data["ht"]["KC"] == pytest.approx(3.3e-4)
    assert data["pchamber"] == {"min": 0.05, "max": 0.5}
    assert data["tshelf"]["min"] == pytest.approx(-45.0)
    assert data["tshelf"]["max"] == pytest.approx(120.0)
    assert data["nvial"] == 400


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
            [0.0, -30.0, -25.0, 20.0, 50.0, 1.0, 0.0],
            [1.0, -29.0, -24.4, 20.0, 40.0, 1.0, 100.0],
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
            "a1_values": [16.0],
            "kc_values": [2.75e-4],
            "scipy_dt": 0.1,
            "point_budget": 13,
            "ncp": 3,
            "final_dried_fraction": 1.0,
            "timing_repeats": 1,
            "sensitivity_point_budgets": [13, 25],
            "pressure_lower_bound_values_torr": [0.05, 0.10],
            "implementability_point_budget": 13,
            "scipy_dt_values": [0.2, 0.1],
            "constraint_tolerance": 1.0e-4,
            "save_results": False,
        },
    )


def test_shared_point_budget_helper_remains_available() -> None:
    assert matched_nfe_for_point_budget(25, ncp=3) == (24, 8)
