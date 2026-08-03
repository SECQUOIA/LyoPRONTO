from __future__ import annotations

import numpy as np
import pytest

from examples.current_main_pressure_optimizer_comparison import (
    comparison_inputs,
    matched_nfe_for_point_budget,
    run_case_comparison,
)
from tests.pyomo_solver import require_pyomo_solver


def test_pressure_comparison_inputs_match_paper_mannitol_pressure_case() -> None:
    data = comparison_inputs(18.0, 3.3e-4)

    assert data["product"]["A1"] == pytest.approx(18.0)
    assert data["product"]["T_pr_crit"] == pytest.approx(-5.0)
    assert data["ht"]["KC"] == pytest.approx(3.3e-4)
    assert data["pchamber"] == {"min": 0.05, "max": 2.0}
    assert data["tshelf"]["init"] == pytest.approx(30.0)
    assert data["tshelf"]["setpt"] == [30.0]
    assert data["nvial"] == 398


def test_pressure_case_comparison_rejects_unmatched_transcription_points() -> None:
    with pytest.raises(ValueError, match="same number of transcription points"):
        run_case_comparison(
            16.0,
            2.75e-4,
            finite_difference_nfe=24,
            collocation_nfe=24,
            ncp=3,
        )


@pytest.mark.pyomo
@pytest.mark.parametrize("warmstart_from_scipy", [False, True])
def test_current_main_pressure_comparison_helper_solves_smoke_case(
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
    assert abs(case.finite_difference_objective_gap_percent) < 5.0
    assert abs(case.collocation_objective_gap_percent) < 2.0
    assert case.finite_difference_speedup > 0.0
    assert case.collocation_speedup > 0.0
    assert case.finite_difference_n_variables > 0
    assert case.finite_difference_n_constraints > 0
    assert case.collocation_n_variables > 0
    assert case.collocation_n_constraints > 0


def test_shared_point_budget_helper_remains_available() -> None:
    assert matched_nfe_for_point_budget(25, ncp=3) == (24, 8)
