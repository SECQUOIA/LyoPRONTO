"""Shadow-price reporting for the free-final-time Pyomo.DAE optimizers."""

from __future__ import annotations

import pytest

from tests.pyomo_solver import require_pyomo_solver

pyo = pytest.importorskip("pyomo.environ")

from lyopronto.pyomo_models import (  # noqa: E402
    DaeOptimizationResult,
    create_dae_joint_optimization_model,
    solve_dae_chamber_pressure_optimization,
    solve_dae_joint_optimization,
    solve_dae_shelf_temperature_optimization,
)

pytestmark = pytest.mark.pyomo


@pytest.fixture
def joint_case():
    return {
        "vial": {"Av": 3.8, "Ap": 3.14, "Vfill": 2.0},
        "product": {
            "cSolid": 0.05,
            "R0": 1.4,
            "A1": 16.0,
            "A2": 0.0,
            "T_pr_crit": -25.0,
        },
        "ht": {"KC": 2.75e-4, "KP": 8.93e-4, "KD": 0.46},
        "pchamber": {"min": 0.05, "max": 0.5},
        "tshelf": {"min": -45.0, "max": 120.0, "init": -35.0},
        "eq_cap": {"a": -0.182, "b": 11.7},
        "nvial": 400,
    }


def _solve(case, solver, **overrides):
    product = dict(case["product"])
    pchamber = dict(case["pchamber"])
    tshelf = dict(case["tshelf"])
    eq_cap = dict(case["eq_cap"])
    product.update(overrides.pop("product", {}))
    pchamber.update(overrides.pop("pchamber", {}))
    tshelf.update(overrides.pop("tshelf", {}))
    eq_cap.update(overrides.pop("eq_cap", {}))
    return solve_dae_joint_optimization(
        case["vial"],
        product,
        case["ht"],
        pchamber,
        tshelf,
        eq_cap=eq_cap,
        nvial=case["nvial"],
        nfe=8,
        discretization="collocation",
        ncp=3,
        solver=solver,
        **overrides,
    )


def test_dae_model_imports_multiplier_suffixes(joint_case) -> None:
    """The model requests the suffixes needed to report shadow prices."""
    model = create_dae_joint_optimization_model(
        joint_case["vial"],
        joint_case["product"],
        joint_case["ht"],
        joint_case["pchamber"],
        joint_case["tshelf"],
        eq_cap=joint_case["eq_cap"],
        nvial=joint_case["nvial"],
        nfe=4,
        discretization="collocation",
        ncp=3,
    )

    for name in ("dual", "ipopt_zL_out", "ipopt_zU_out"):
        suffix = getattr(model, name)
        assert suffix.direction is pyo.Suffix.IMPORT


def test_result_defaults_to_empty_shadow_prices() -> None:
    """Constructing a result without multipliers keeps the mapping empty."""
    result = DaeOptimizationResult(
        success=False,
        solver_status="ok",
        termination_condition="optimal",
        message="",
        objective_time_hr=None,
        values={},
        constraint_violations={},
        discretization={},
    )

    assert result.shadow_prices == {}


def test_shadow_prices_identify_the_active_set(joint_case) -> None:
    """Binding limits carry a sensitivity and inactive limits report near zero."""
    solver = require_pyomo_solver("ipopt")
    result = _solve(joint_case, solver)

    assert result.success, result.message
    prices = result.shadow_prices
    assert set(prices) == {
        "product_temperature_limit",
        "equipment_capability",
        "final_drying_target",
        "chamber_pressure_lower_bound",
        "chamber_pressure_upper_bound",
        "shelf_temperature_lower_bound",
        "shelf_temperature_upper_bound",
    }

    # Pressure rides its floor and the product-temperature limit binds, so
    # raising the floor costs time while extra temperature headroom saves it.
    assert prices["chamber_pressure_lower_bound"] > 1.0
    assert prices["product_temperature_limit"] < -0.1

    # Equipment capacity keeps positive margin and the shelf bounds stay slack.
    assert abs(prices["equipment_capability"]) < 1.0e-3
    assert abs(prices["shelf_temperature_lower_bound"]) < 1.0e-3
    assert abs(prices["shelf_temperature_upper_bound"]) < 1.0e-3
    assert abs(prices["chamber_pressure_upper_bound"]) < 1.0e-3


@pytest.mark.parametrize(
    ("key", "base_overrides", "perturbed_overrides", "delta"),
    [
        (
            "product_temperature_limit",
            {},
            {"product": {"T_pr_crit": -24.5}},
            0.5,
        ),
        (
            "equipment_capability",
            {"eq_cap": {"a": 0.1, "b": 0.0}},
            {"eq_cap": {"a": 0.105, "b": 0.0}},
            0.005,
        ),
        (
            "chamber_pressure_lower_bound",
            {},
            {"pchamber": {"min": 0.055}},
            0.005,
        ),
    ],
)
def test_shadow_prices_predict_the_re_solved_drying_time(
    joint_case, key, base_overrides, perturbed_overrides, delta
) -> None:
    """Each reported sensitivity matches a finite-difference re-solve."""
    solver = require_pyomo_solver("ipopt")
    base = _solve(joint_case, solver, **base_overrides)
    perturbed = _solve(joint_case, solver, **perturbed_overrides)

    assert base.success and perturbed.success
    predicted = base.shadow_prices[key] * delta
    observed = perturbed.objective_time_hr - base.objective_time_hr

    assert observed == pytest.approx(predicted, rel=0.2)


@pytest.mark.parametrize(
    ("solve", "pchamber", "tshelf", "present_prefix", "absent_prefix"),
    [
        (
            solve_dae_shelf_temperature_optimization,
            {"setpt": [0.1]},
            {"min": -45.0, "max": 120.0, "init": -35.0},
            "shelf_temperature_",
            "chamber_pressure_",
        ),
        (
            solve_dae_chamber_pressure_optimization,
            {"min": 0.05, "max": 0.5},
            {"init": -18.0, "setpt": [-18.0]},
            "chamber_pressure_",
            "shelf_temperature_",
        ),
    ],
)
def test_shadow_prices_only_report_optimized_control_bounds(
    joint_case, solve, pchamber, tshelf, present_prefix, absent_prefix
) -> None:
    """A fixed setpoint is not mislabeled as a one-sided bound."""
    solver = require_pyomo_solver("ipopt")
    result = solve(
        joint_case["vial"],
        joint_case["product"],
        joint_case["ht"],
        pchamber,
        tshelf,
        eq_cap=joint_case["eq_cap"],
        nvial=joint_case["nvial"],
        nfe=8,
        discretization="collocation",
        ncp=3,
        solver=solver,
    )

    assert result.success, result.message
    assert any(key.startswith(present_prefix) for key in result.shadow_prices)
    assert not any(key.startswith(absent_prefix) for key in result.shadow_prices)


def test_unsuccessful_solve_reports_no_shadow_prices(joint_case) -> None:
    """Multipliers describe an optimum, so a failed solve reports none."""
    solver = require_pyomo_solver("ipopt")
    result = _solve(
        joint_case,
        solver,
        initial_pressure=0.15,
        initial_shelf_temperature=120.0,
        pressure_ramp_rate=0.6,
        shelf_temperature_ramp_rate=60.0,
    )

    assert not result.success
    assert result.shadow_prices == {}
