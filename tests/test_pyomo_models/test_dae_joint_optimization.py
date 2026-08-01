from __future__ import annotations

import numpy as np
import pytest

from tests.pyomo_solver import require_pyomo_solver

pyo = pytest.importorskip("pyomo.environ")

from lyopronto.pyomo_models import (
    DaeDiscretization,
    create_dae_joint_optimization_model,
    solve_dae_joint_optimization,
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


@pytest.mark.parametrize(
    ("method", "expected_points"),
    [
        (DaeDiscretization.FINITE_DIFFERENCE, 5),
        (DaeDiscretization.COLLOCATION, 13),
    ],
)
def test_joint_dae_model_constructs_with_both_controls_variable(
    joint_case, method, expected_points
) -> None:
    model = create_dae_joint_optimization_model(
        joint_case["vial"],
        joint_case["product"],
        joint_case["ht"],
        joint_case["pchamber"],
        joint_case["tshelf"],
        eq_cap=joint_case["eq_cap"],
        nvial=joint_case["nvial"],
        nfe=4,
        discretization=method,
        ncp=3,
    )

    first = model.t.first()
    assert model.optimized_control == "joint"
    assert model.discretization_method == method.value
    assert len(model.t) == expected_points
    assert model.Pch[first].bounds == pytest.approx((0.05, 0.5))
    assert model.Tsh[first].bounds == pytest.approx((-45.0, 120.0))
    assert not hasattr(model, "fixed_Pch")
    assert not hasattr(model, "fixed_Tsh")
    assert hasattr(model, "initial_pressure_continuity")
    assert hasattr(model, "initial_shelf_temperature_continuity")
    assert model.obj.expr is model.t_final


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("pchamber", {"min": 0.0, "max": 0.5}, "positive and increasing"),
        ("pchamber", {"min": 0.5, "max": 0.05}, "positive and increasing"),
        ("tshelf", {"min": 20.0, "max": 20.0}, "greater than"),
    ],
)
def test_joint_dae_model_rejects_invalid_control_bounds(
    joint_case, field, value, message
) -> None:
    joint_case[field] = value

    with pytest.raises(ValueError, match=message):
        create_dae_joint_optimization_model(
            joint_case["vial"],
            joint_case["product"],
            joint_case["ht"],
            joint_case["pchamber"],
            joint_case["tshelf"],
            eq_cap=joint_case["eq_cap"],
            nvial=joint_case["nvial"],
        )


@pytest.mark.parametrize("method", ["finite_difference", "collocation"])
def test_joint_dae_model_solves_equivalent_complete_drying_problem(
    joint_case, method
) -> None:
    solver = require_pyomo_solver("ipopt")
    nfe = 8 if method == "finite_difference" else 4
    result = solve_dae_joint_optimization(
        joint_case["vial"],
        joint_case["product"],
        joint_case["ht"],
        joint_case["pchamber"],
        joint_case["tshelf"],
        eq_cap=joint_case["eq_cap"],
        nvial=joint_case["nvial"],
        nfe=nfe,
        discretization=method,
        ncp=2,
        solver=solver,
    )

    table = result.as_table()
    assert result.success, result.message
    assert result.discretization["optimized_control"] == "joint"
    assert result.discretization["method"] == method
    assert result.discretization["nfe"] == nfe
    assert result.discretization["ncp"] == (
        None if method == "finite_difference" else 2
    )
    assert result.objective_time_hr == pytest.approx(table[-1, 0])
    assert table[-1, 6] >= 100.0 - 1.0e-3
    assert np.max(table[:, 2]) <= joint_case["product"]["T_pr_crit"] + 1.0e-4
    assert np.min(table[:, 3]) >= joint_case["tshelf"]["min"] - 1.0e-4
    assert np.max(table[:, 3]) <= joint_case["tshelf"]["max"] + 1.0e-4
    assert np.min(table[:, 4]) >= joint_case["pchamber"]["min"] * 1000.0 - 1.0e-3
    assert np.max(table[:, 4]) <= joint_case["pchamber"]["max"] * 1000.0 + 1.0e-3
    assert table[0, 3] == pytest.approx(table[1, 3], abs=1.0e-4)
    assert table[0, 4] == pytest.approx(table[1, 4], abs=1.0e-3)
    assert max(value or 0.0 for value in result.constraint_violations.values()) < 1.0e-4
