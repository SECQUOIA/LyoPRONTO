from __future__ import annotations

import numpy as np
import pytest

from examples.current_main_optimizer_comparison import (
    comparison_inputs,
    integrated_driving_force,
    run_case_comparison,
)
from lyopronto import functions
from tests.pyomo_solver import require_pyomo_solver


def test_comparison_inputs_preserve_historical_grid_conventions() -> None:
    data = comparison_inputs(18.0, 3.3e-4)

    assert data["product"]["A1"] == pytest.approx(18.0)
    assert data["product"]["T_pr_crit"] == pytest.approx(-25.0)
    assert data["ht"]["KC"] == pytest.approx(3.3e-4)
    assert data["scipy_pchamber"]["setpt"] == [0.1]
    assert data["pyomo_pchamber"]["min"] == pytest.approx(0.1)
    assert data["pyomo_pchamber"]["max"] == pytest.approx(0.1)
    assert data["nvial"] == 400


def test_integrated_driving_force_converts_legacy_pressure_to_torr() -> None:
    trajectory = np.zeros((3, 7), dtype=float)
    trajectory[:, 0] = [0.0, 1.0, 2.0]
    trajectory[:, 1] = -30.0
    trajectory[:, 4] = 100.0

    expected = 2.0 * (0.1 - float(functions.Vapor_pressure(-30.0)))
    assert integrated_driving_force(trajectory) == pytest.approx(expected)


@pytest.mark.parametrize(
    "trajectory",
    [
        np.zeros((2, 6), dtype=float),
        np.array([[0.0] * 7, [float("nan")] * 7]),
    ],
)
def test_integrated_driving_force_rejects_invalid_tables(trajectory: np.ndarray) -> None:
    with pytest.raises(ValueError, match="trajectory must"):
        integrated_driving_force(trajectory)


@pytest.mark.pyomo
def test_current_main_comparison_helper_solves_smoke_case() -> None:
    solver = require_pyomo_solver("ipopt")

    case = run_case_comparison(
        16.0,
        2.75e-4,
        scipy_dt=0.1,
        n_steps=8,
        final_dried_fraction=0.90,
        timing_repeats=1,
        solver=solver,
    )

    assert case.scipy_trajectory.shape[1] == 7
    assert case.pyomo_trajectory.shape == (9, 7)
    assert case.pyomo_trajectory[-1, 6] >= 90.0 - 1.0e-3
    assert case.max_constraint_violation < 1.0e-4
    assert np.isfinite(case.objective_gap_percent)
    assert case.speedup > 0.0


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
            "n_steps": 8,
            "final_dried_fraction": 0.90,
            "timing_repeats": 1,
            "mesh_steps": [4, 8],
            "constraint_tolerance": 1.0e-4,
            "save_results": False,
        },
    )
