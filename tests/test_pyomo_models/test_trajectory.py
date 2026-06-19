from __future__ import annotations

from typing import Dict

import numpy as np
import pytest

from lyopronto import calc_knownRp, constant, functions
from tests.pyomo_solver import require_pyomo_solver

pyo = pytest.importorskip("pyomo.environ")

from lyopronto.pyomo_models.trajectory import (
    apply_trajectory_warmstart,
    create_trajectory_model,
    sample_ramp_profile,
    solve_trajectory,
    trajectory_initialization_from_scipy_output,
)

pytestmark = pytest.mark.pyomo


@pytest.fixture
def standard_trajectory_case() -> Dict[str, object]:
    vial = {"Av": 3.8, "Ap": 3.14, "Vfill": 2.0}
    product = {
        "cSolid": 0.05,
        "R0": 1.4,
        "A1": 16.0,
        "A2": 0.0,
        "T_pr_crit": 0.0,
    }
    ht = {"KC": 2.75e-4, "KP": 8.93e-4, "KD": 0.46}
    pchamber = {"setpt": [0.15], "dt_setpt": [1800.0], "ramp_rate": 0.5}
    tshelf = {"init": -35.0, "setpt": [20.0], "dt_setpt": [1800.0], "ramp_rate": 1.0}
    return {
        "vial": vial,
        "product": product,
        "ht": ht,
        "Pchamber": pchamber,
        "Tshelf": tshelf,
        "dt": 0.25,
        "n_steps": 26,
    }


def _time_points(case: Dict[str, object]) -> np.ndarray:
    return np.arange(case["n_steps"] + 1, dtype=float) * case["dt"]


def test_trajectory_model_constructs_with_backward_euler_grid(standard_trajectory_case):
    time_points = _time_points(standard_trajectory_case)

    model = create_trajectory_model(
        standard_trajectory_case["vial"],
        standard_trajectory_case["product"],
        standard_trajectory_case["ht"],
        n_steps=4,
        dt=0.5,
        final_dried_fraction=0.20,
        fixed_pch_profile=sample_ramp_profile(
            standard_trajectory_case["Pchamber"], np.arange(5, dtype=float) * 0.5
        ),
        fixed_tsh_profile=sample_ramp_profile(
            standard_trajectory_case["Tshelf"], np.arange(5, dtype=float) * 0.5
        ),
        pch_ramp_rate=standard_trajectory_case["Pchamber"]["ramp_rate"] * constant.hr_To_min,
        tsh_ramp_rate=standard_trajectory_case["Tshelf"]["ramp_rate"] * constant.hr_To_min,
    )

    assert model.discretization_method == "backward_euler"
    assert list(model.TIME) == [0, 1, 2, 3, 4]
    assert list(model.STEPS) == [1, 2, 3, 4]
    assert pyo.value(model.time[2]) == pytest.approx(1.0)
    assert pyo.value(model.final_dried_fraction) == pytest.approx(0.20)
    assert hasattr(model, "drying_front_dynamics")
    assert hasattr(model, "final_drying_target")
    assert hasattr(model, "fixed_chamber_pressure_profile")
    assert hasattr(model, "fixed_shelf_temperature_profile")
    assert hasattr(model, "chamber_pressure_ramp_up")
    assert hasattr(model, "shelf_temperature_ramp_down")
    assert pyo.value(model.fixed_Pch[0]) == pytest.approx(
        sample_ramp_profile(standard_trajectory_case["Pchamber"], time_points[:1])[0]
    )


def test_fixed_profiles_require_all_time_nodes(standard_trajectory_case):
    with pytest.raises(ValueError, match="fixed_pch_profile must have n_steps \\+ 1 values"):
        create_trajectory_model(
            standard_trajectory_case["vial"],
            standard_trajectory_case["product"],
            standard_trajectory_case["ht"],
            n_steps=3,
            dt=1.0,
            fixed_pch_profile=[0.15, 0.15],
        )


def test_warmstart_from_scipy_output_converts_legacy_units(standard_trajectory_case):
    lpr0 = 2.0
    ap = 4.0
    output = np.array(
        [
            [0.0, -30.0, -29.0, -25.0, 150.0, 1.0, 0.0],
            [1.0, -20.0, -19.0, -10.0, 200.0, 2.0, 50.0],
        ],
        dtype=float,
    )

    initialization = trajectory_initialization_from_scipy_output(
        output,
        lpr0=lpr0,
        ap=ap,
        ht=standard_trajectory_case["ht"],
        time_points=[0.0, 0.5, 1.0],
    )

    np.testing.assert_allclose(initialization["Lck"], [0.0, 0.5, 1.0])
    np.testing.assert_allclose(initialization["Pch"], [0.15, 0.175, 0.2])
    np.testing.assert_allclose(
        initialization["dmdt"],
        np.array([1.0, 1.5, 2.0]) * ap * constant.cm_To_m**2,
    )
    np.testing.assert_allclose(
        initialization["Psub"], functions.Vapor_pressure(np.array([-30, -25, -20]))
    )
    assert "Kv" in initialization


def test_apply_trajectory_warmstart_sets_indexed_variable_values(standard_trajectory_case):
    model = create_trajectory_model(
        standard_trajectory_case["vial"],
        standard_trajectory_case["product"],
        standard_trajectory_case["ht"],
        n_steps=2,
        dt=1.0,
        final_dried_fraction=0.10,
    )

    apply_trajectory_warmstart(
        model,
        {
            "Tsh": [-30.0, -20.0, -10.0],
            "Pch": {0: 0.10, 1: 0.12, 2: 0.14},
        },
    )

    assert pyo.value(model.Tsh[1]) == pytest.approx(-20.0)
    assert pyo.value(model.Pch[2]) == pytest.approx(0.14)


def test_unsolved_trajectory_returns_clear_diagnostics(standard_trajectory_case):
    class FailingSolver:
        options = {}

        def solve(self, model, tee=False):
            raise RuntimeError("solver executable missing")

    model = create_trajectory_model(
        standard_trajectory_case["vial"],
        standard_trajectory_case["product"],
        standard_trajectory_case["ht"],
        n_steps=2,
        dt=1.0,
        final_dried_fraction=0.10,
    )

    result = solve_trajectory(model, solver=FailingSolver())

    assert not result.success
    assert result.solver_status == "not_available"
    assert "solver executable missing" in result.message
    assert "Pyomo solve failed before returning results" in result.message
    assert "Lck" in result.values
    assert "drying_front_dynamics[1]" in result.constraint_violations


def test_trajectory_solves_and_matches_scipy_reference(standard_trajectory_case):
    solver = require_pyomo_solver("ipopt")
    vial = standard_trajectory_case["vial"]
    product = standard_trajectory_case["product"]
    ht = standard_trajectory_case["ht"]
    pchamber = standard_trajectory_case["Pchamber"]
    tshelf = standard_trajectory_case["Tshelf"]
    dt = standard_trajectory_case["dt"]
    n_steps = standard_trajectory_case["n_steps"]
    time_points = _time_points(standard_trajectory_case)
    reference = calc_knownRp.dry(vial, product, ht, pchamber, tshelf, dt)
    lpr0 = functions.Lpr0_FUN(vial["Vfill"], vial["Ap"], product["cSolid"])
    initialization = trajectory_initialization_from_scipy_output(
        reference,
        lpr0=lpr0,
        ap=vial["Ap"],
        ht=ht,
        time_points=time_points,
    )

    model = create_trajectory_model(
        vial,
        product,
        ht,
        n_steps=n_steps,
        dt=dt,
        final_dried_fraction=0.95,
        fixed_pch_profile=sample_ramp_profile(pchamber, time_points),
        fixed_tsh_profile=sample_ramp_profile(tshelf, time_points),
        pch_ramp_rate=pchamber["ramp_rate"] * constant.hr_To_min,
        tsh_ramp_rate=tshelf["ramp_rate"] * constant.hr_To_min,
        initialize=initialization,
    )

    result = solve_trajectory(model, solver=solver)

    assert result.success, result.message
    trajectory = result.as_table()
    assert trajectory.shape == (n_steps + 1, 7)
    assert trajectory[-1, 6] >= 95.0
    # The comparison tolerance documents the first-order backward-Euler
    # discretization error against the adaptive SciPy BDF trajectory.
    assert trajectory[-1, 6] == pytest.approx(reference[-1, 6], abs=1.5)
    assert trajectory[-1, 3] == pytest.approx(reference[-1, 3], abs=1.0e-8)
    assert trajectory[-1, 4] == pytest.approx(reference[-1, 4], abs=1.0e-8)
    assert np.max(trajectory[:, 2]) <= product["T_pr_crit"] + 1.0e-6
    assert result.values["Lck"][-1] >= 0.95 * lpr0
    assert max(violation or 0.0 for violation in result.constraint_violations.values()) < 1.0e-5


def test_trajectory_cold_start_solves_and_matches_scipy_reference(standard_trajectory_case):
    solver = require_pyomo_solver("ipopt")
    vial = standard_trajectory_case["vial"]
    product = standard_trajectory_case["product"]
    ht = standard_trajectory_case["ht"]
    pchamber = standard_trajectory_case["Pchamber"]
    tshelf = standard_trajectory_case["Tshelf"]
    dt = standard_trajectory_case["dt"]
    n_steps = standard_trajectory_case["n_steps"]
    time_points = _time_points(standard_trajectory_case)
    reference = calc_knownRp.dry(vial, product, ht, pchamber, tshelf, dt)
    lpr0 = functions.Lpr0_FUN(vial["Vfill"], vial["Ap"], product["cSolid"])
    model = create_trajectory_model(
        vial,
        product,
        ht,
        n_steps=n_steps,
        dt=dt,
        final_dried_fraction=0.95,
        fixed_pch_profile=sample_ramp_profile(pchamber, time_points),
        fixed_tsh_profile=sample_ramp_profile(tshelf, time_points),
        pch_ramp_rate=pchamber["ramp_rate"] * constant.hr_To_min,
        tsh_ramp_rate=tshelf["ramp_rate"] * constant.hr_To_min,
    )

    result = solve_trajectory(model, solver=solver)

    assert result.success, result.message
    trajectory = result.as_table()
    assert trajectory[-1, 6] >= 95.0
    assert trajectory[-1, 6] == pytest.approx(reference[-1, 6], abs=1.5)
    assert np.max(trajectory[:, 2]) <= product["T_pr_crit"] + 1.0e-6
    assert result.values["Lck"][-1] >= 0.95 * lpr0
    assert max(violation or 0.0 for violation in result.constraint_violations.values()) < 1.0e-5
