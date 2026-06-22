from __future__ import annotations

import warnings
from typing import Dict

import numpy as np
import pytest

from lyopronto import constant, opt_Pch, opt_Pch_Tsh, opt_Tsh
from tests.pyomo_solver import require_pyomo_solver

pyo = pytest.importorskip("pyomo.environ")

from lyopronto.pyomo_models.optimization import (
    OptimizationMode,
    create_joint_optimization_model,
    create_pressure_optimization_model,
    create_primary_drying_optimization_model,
    create_shelf_temperature_optimization_model,
    solve_primary_drying_optimization,
)
from lyopronto.pyomo_models.trajectory import sample_ramp_profile

pytestmark = pytest.mark.pyomo


@pytest.fixture
def optimization_case() -> Dict[str, object]:
    return {
        "vial": {"Av": 3.8, "Ap": 3.14, "Vfill": 2.0},
        "product": {
            "cSolid": 0.05,
            "R0": 1.4,
            "A1": 16.0,
            "A2": 0.0,
            "T_pr_crit": -15.0,
        },
        "ht": {"KC": 2.75e-4, "KP": 8.93e-4, "KD": 0.46},
        "pchamber": {
            "min": 0.05,
            "max": 0.5,
            "setpt": np.array([0.15]),
            "dt_setpt": np.array([1800.0]),
            "ramp_rate": 0.5,
        },
        "tshelf": {
            "min": -45.0,
            "max": 50.0,
            "init": -35.0,
            "setpt": np.array([20.0]),
            "dt_setpt": np.array([1800.0]),
            "ramp_rate": 1.0,
        },
        "eq_cap": {"a": -0.182, "b": 11.7},
        "nvial": 398,
    }


def _time_points(n_steps: int, dt: float) -> np.ndarray:
    return np.arange(n_steps + 1, dtype=float) * dt


def _values(component) -> np.ndarray:
    return np.array([pyo.value(component[index]) for index in component.index_set()], dtype=float)


@pytest.mark.parametrize(
    ("mode", "optimized_controls", "fixed_controls"),
    [
        (OptimizationMode.PRESSURE, ("Pch",), ("Tsh",)),
        (OptimizationMode.SHELF_TEMPERATURE, ("Tsh",), ("Pch",)),
        (OptimizationMode.JOINT, ("Pch", "Tsh"), ()),
    ],
)
def test_primary_drying_optimization_modes_apply_expected_constraints(
    optimization_case,
    mode,
    optimized_controls,
    fixed_controls,
):
    n_steps = 4
    dt = 0.5
    time_points = _time_points(n_steps, dt)

    model = create_primary_drying_optimization_model(
        optimization_case["vial"],
        optimization_case["product"],
        optimization_case["ht"],
        optimization_case["pchamber"],
        optimization_case["tshelf"],
        n_steps=n_steps,
        dt=dt,
        mode=mode,
        final_dried_fraction=0.20,
        eq_cap=optimization_case["eq_cap"],
        nvial=optimization_case["nvial"],
    )

    assert model.optimization_mode == mode.value
    assert model.optimized_controls == optimized_controls
    assert model.fixed_controls == fixed_controls
    assert model.optimization_objective == "sum_Pch_minus_Psub"
    assert model.obj.active
    assert np.isfinite(pyo.value(model.obj.expr))
    assert pyo.value(model.final_dried_fraction) == pytest.approx(0.20)
    assert hasattr(model, "equipment_capability")

    if mode is OptimizationMode.PRESSURE:
        expected_tsh = sample_ramp_profile(optimization_case["tshelf"], time_points)
        assert not hasattr(model, "fixed_chamber_pressure_profile")
        assert hasattr(model, "fixed_shelf_temperature_profile")
        np.testing.assert_allclose(_values(model.fixed_Tsh), expected_tsh)
        assert model.Pch[0].bounds == (0.05, 0.5)
        assert model.Tsh[0].bounds == (float(np.min(expected_tsh)), float(np.max(expected_tsh)))
    elif mode is OptimizationMode.SHELF_TEMPERATURE:
        expected_pch = sample_ramp_profile(optimization_case["pchamber"], time_points)
        assert hasattr(model, "fixed_chamber_pressure_profile")
        assert not hasattr(model, "fixed_shelf_temperature_profile")
        np.testing.assert_allclose(_values(model.fixed_Pch), expected_pch)
        assert model.Pch[0].bounds == (float(np.min(expected_pch)), float(np.max(expected_pch)))
        assert model.Tsh[0].bounds == (-45.0, 50.0)
    else:
        assert not hasattr(model, "fixed_chamber_pressure_profile")
        assert not hasattr(model, "fixed_shelf_temperature_profile")
        assert model.Pch[0].bounds == (0.05, 0.5)
        assert model.Tsh[0].bounds == (-45.0, 50.0)


def test_named_mode_builders_return_tagged_models(optimization_case):
    common = {
        "n_steps": 2,
        "dt": 0.5,
        "final_dried_fraction": 0.10,
        "eq_cap": optimization_case["eq_cap"],
        "nvial": optimization_case["nvial"],
    }

    pressure = create_pressure_optimization_model(
        optimization_case["vial"],
        optimization_case["product"],
        optimization_case["ht"],
        optimization_case["pchamber"],
        optimization_case["tshelf"],
        **common,
    )
    shelf = create_shelf_temperature_optimization_model(
        optimization_case["vial"],
        optimization_case["product"],
        optimization_case["ht"],
        optimization_case["pchamber"],
        optimization_case["tshelf"],
        **common,
    )
    joint = create_joint_optimization_model(
        optimization_case["vial"],
        optimization_case["product"],
        optimization_case["ht"],
        optimization_case["pchamber"],
        optimization_case["tshelf"],
        **common,
    )

    assert pressure.optimization_mode == OptimizationMode.PRESSURE.value
    assert shelf.optimization_mode == OptimizationMode.SHELF_TEMPERATURE.value
    assert joint.optimization_mode == OptimizationMode.JOINT.value


def test_mode_aliases_and_validation_errors(optimization_case):
    model = create_primary_drying_optimization_model(
        optimization_case["vial"],
        optimization_case["product"],
        optimization_case["ht"],
        optimization_case["pchamber"],
        optimization_case["tshelf"],
        n_steps=2,
        dt=0.5,
        mode="Pch",
        final_dried_fraction=0.10,
    )

    assert model.optimization_mode == OptimizationMode.PRESSURE.value

    with pytest.raises(ValueError, match="mode must be one of"):
        create_primary_drying_optimization_model(
            optimization_case["vial"],
            optimization_case["product"],
            optimization_case["ht"],
            optimization_case["pchamber"],
            optimization_case["tshelf"],
            n_steps=2,
            dt=0.5,
            mode="unsupported",
        )

    with pytest.raises(KeyError, match="pchamber is missing required key\\(s\\): min"):
        create_primary_drying_optimization_model(
            optimization_case["vial"],
            optimization_case["product"],
            optimization_case["ht"],
            {"max": 0.5},
            optimization_case["tshelf"],
            n_steps=2,
            dt=0.5,
            mode=OptimizationMode.PRESSURE,
        )


def test_joint_mode_can_enforce_legacy_ramp_rates(optimization_case):
    model = create_joint_optimization_model(
        optimization_case["vial"],
        optimization_case["product"],
        optimization_case["ht"],
        optimization_case["pchamber"],
        optimization_case["tshelf"],
        n_steps=3,
        dt=0.25,
        final_dried_fraction=0.10,
        enforce_ramp_rates=True,
    )

    assert hasattr(model, "chamber_pressure_ramp_up")
    assert hasattr(model, "chamber_pressure_ramp_down")
    assert hasattr(model, "shelf_temperature_ramp_up")
    assert hasattr(model, "shelf_temperature_ramp_down")


def _solver_comparison_case(mode: OptimizationMode, base_case: Dict[str, object]) -> Dict[str, object]:
    case = {
        "vial": dict(base_case["vial"]),
        "product": dict(base_case["product"]),
        "ht": dict(base_case["ht"]),
        "pchamber": dict(base_case["pchamber"]),
        "tshelf": dict(base_case["tshelf"]),
        "eq_cap": dict(base_case["eq_cap"]),
        "nvial": base_case["nvial"],
    }
    if mode is OptimizationMode.PRESSURE:
        case["product"]["T_pr_crit"] = -5.0
        case["pchamber"]["max"] = 5.0
        case["tshelf"]["init"] = -25.0
    return case


def _legacy_reference(mode: OptimizationMode, case: Dict[str, object], dt: float) -> np.ndarray:
    if mode is OptimizationMode.PRESSURE:
        with warnings.catch_warnings(record=True) as emitted:
            warnings.simplefilter("always")
            output = opt_Pch.dry(
                case["vial"],
                dict(case["product"]),
                case["ht"],
                dict(case["pchamber"]),
                dict(case["tshelf"]),
                dt,
                case["eq_cap"],
                case["nvial"],
            )
        failure_messages = [
            str(warning.message)
            for warning in emitted
            if "Optimization failed" in str(warning.message)
        ]
        assert not failure_messages, (
            "pressure SciPy reference should converge without optimization failure warnings"
        )
        return output
    if mode is OptimizationMode.SHELF_TEMPERATURE:
        return opt_Tsh.dry(
            case["vial"],
            dict(case["product"]),
            case["ht"],
            dict(case["pchamber"]),
            dict(case["tshelf"]),
            dt,
            case["eq_cap"],
            case["nvial"],
        )
    return opt_Pch_Tsh.dry(
        case["vial"],
        dict(case["product"]),
        case["ht"],
        {"min": 0.05, "max": 0.5},
        {"min": -45.0, "max": 50.0},
        dt,
        case["eq_cap"],
        case["nvial"],
    )


def _assert_mode_invariants(table: np.ndarray, mode: OptimizationMode, case: Dict[str, object]) -> None:
    pch_torr = table[:, 4] / constant.Torr_to_mTorr
    dmdt = table[:, 5] * case["vial"]["Ap"] * constant.cm_To_m**2
    equipment_capability = case["eq_cap"]["a"] + case["eq_cap"]["b"] * pch_torr

    assert table.shape[1] == 7
    assert np.all(np.isfinite(table))
    assert np.max(table[:, 2]) <= case["product"]["T_pr_crit"] + 1.0e-5
    assert np.max(dmdt - equipment_capability) <= 5.0e-6

    if mode in (OptimizationMode.PRESSURE, OptimizationMode.JOINT):
        assert np.min(table[:, 4]) >= case["pchamber"]["min"] * constant.Torr_to_mTorr - 1.0e-3
        assert np.max(table[:, 4]) <= case["pchamber"]["max"] * constant.Torr_to_mTorr + 1.0e-3
    if mode in (OptimizationMode.SHELF_TEMPERATURE, OptimizationMode.JOINT):
        assert np.min(table[:, 3]) >= case["tshelf"]["min"] - 1.0e-5
        assert np.max(table[:, 3]) <= case["tshelf"]["max"] + 1.0e-5


@pytest.mark.parametrize(
    "mode",
    [OptimizationMode.PRESSURE, OptimizationMode.SHELF_TEMPERATURE, OptimizationMode.JOINT],
)
def test_optimization_modes_solve_and_compare_to_scipy_reference(optimization_case, mode):
    solver = require_pyomo_solver("ipopt")
    n_steps = 8
    dt = 0.25
    final_dried_fraction = 0.30
    comparison_case = _solver_comparison_case(mode, optimization_case)
    time_points = _time_points(n_steps, dt)
    reference = _legacy_reference(mode, comparison_case, dt)

    result = solve_primary_drying_optimization(
        comparison_case["vial"],
        comparison_case["product"],
        comparison_case["ht"],
        comparison_case["pchamber"],
        comparison_case["tshelf"],
        n_steps=n_steps,
        dt=dt,
        mode=mode,
        final_dried_fraction=final_dried_fraction,
        eq_cap=comparison_case["eq_cap"],
        nvial=comparison_case["nvial"],
        solver=solver,
    )

    assert result.success, result.message
    assert max(violation or 0.0 for violation in result.constraint_violations.values()) < 1.0e-5
    table = result.as_table()
    assert table.shape == (n_steps + 1, 7)
    assert table[-1, 6] >= final_dried_fraction * 100.0
    _assert_mode_invariants(table, mode, comparison_case)

    if mode is OptimizationMode.PRESSURE:
        expected_tsh = sample_ramp_profile(comparison_case["tshelf"], time_points)
        np.testing.assert_allclose(table[:, 3], expected_tsh, atol=1.0e-6)
    elif mode is OptimizationMode.SHELF_TEMPERATURE:
        expected_pch = (
            sample_ramp_profile(comparison_case["pchamber"], time_points)
            * constant.Torr_to_mTorr
        )
        np.testing.assert_allclose(table[:, 4], expected_pch, atol=1.0e-6)

    reference_percent = np.interp(table[-1, 0], reference[:, 0], reference[:, 6])
    reference_tsh = np.interp(table[-1, 0], reference[:, 0], reference[:, 3])
    reference_pch = np.interp(table[-1, 0], reference[:, 0], reference[:, 4])

    # The Pyomo trajectory is a simultaneous fixed-horizon backward-Euler
    # formulation. These tolerances document agreement with the sequential
    # SciPy optimizers at the same elapsed time without implying identity.
    assert table[-1, 6] == pytest.approx(reference_percent, abs=8.0)
    assert table[-1, 3] == pytest.approx(reference_tsh, abs=8.0)
    assert table[-1, 4] == pytest.approx(reference_pch, abs=100.0)
