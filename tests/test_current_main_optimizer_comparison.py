from __future__ import annotations

import numpy as np
import pytest

from examples.current_main_optimizer_comparison import (
    comparison_inputs,
    run_case_comparison,
)
from tests.pyomo_solver import require_pyomo_solver


def test_comparison_inputs_preserve_historical_grid_conventions() -> None:
    data = comparison_inputs(18.0, 3.3e-4)

    assert data["product"]["A1"] == pytest.approx(18.0)
    assert data["product"]["T_pr_crit"] == pytest.approx(-25.0)
    assert data["ht"]["KC"] == pytest.approx(3.3e-4)
    assert data["pchamber"]["setpt"] == [0.1]
    assert data["tshelf"]["min"] == pytest.approx(-45.0)
    assert data["tshelf"]["max"] == pytest.approx(120.0)
    assert data["nvial"] == 400


@pytest.mark.pyomo
@pytest.mark.parametrize("warmstart_from_scipy", [False, True])
def test_current_main_comparison_helper_solves_smoke_case(
    warmstart_from_scipy,
) -> None:
    solver = require_pyomo_solver("ipopt")

    case = run_case_comparison(
        16.0,
        2.75e-4,
        scipy_dt=0.1,
        nfe=8,
        ncp=3,
        final_dried_fraction=1.0,
        timing_repeats=1,
        warmstart_from_scipy=warmstart_from_scipy,
        solver=solver,
    )

    assert case.scipy_trajectory.shape[1] == 7
    assert case.finite_difference_trajectory.shape == (9, 7)
    assert case.collocation_trajectory.shape == (25, 7)
    assert case.finite_difference_trajectory[-1, 6] >= 100.0 - 1.0e-3
    assert case.collocation_trajectory[-1, 6] >= 100.0 - 1.0e-3
    assert case.finite_difference_max_constraint_violation < 1.0e-4
    assert case.collocation_max_constraint_violation < 1.0e-4
    assert np.isfinite(case.finite_difference_objective_gap_percent)
    assert np.isfinite(case.collocation_objective_gap_percent)
    assert abs(case.finite_difference_objective_gap_percent) < 15.0
    assert abs(case.collocation_objective_gap_percent) < 2.0
    assert case.finite_difference_speedup > 0.0
    assert case.collocation_speedup > 0.0


@pytest.mark.serial
@pytest.mark.notebook
@pytest.mark.pyomo
def test_current_main_comparison_notebook_execution(repo_root) -> None:
    require_pyomo_solver("ipopt")
    papermill = pytest.importorskip("papermill")

    papermill.execute_notebook(
        repo_root / "docs/examples/current_main_optimizer_comparison.ipynb",
        repo_root / "docs/examples/current_main_optimizer_comparison_output.ipynb",
        parameters={
            "a1_values": [16.0],
            "kc_values": [2.75e-4],
            "scipy_dt": 0.1,
            "nfe": 8,
            "ncp": 3,
            "final_dried_fraction": 1.0,
            "timing_repeats": 1,
            "sensitivity_nfe": [4, 8],
            "constraint_tolerance": 1.0e-4,
            "save_results": False,
        },
    )
