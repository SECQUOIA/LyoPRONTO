from __future__ import annotations

import numpy as np
import pytest

from lyopronto import constant, functions
from tests.pyomo_solver import require_pyomo_solver

pyo = pytest.importorskip("pyomo.environ")

from lyopronto.pyomo_models import (
    DaeDiscretization,
    create_dae_chamber_pressure_optimization_model,
    solve_dae_chamber_pressure_optimization,
)

pytestmark = pytest.mark.pyomo


@pytest.fixture
def pressure_case():
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
        "tshelf": {
            "init": -18.0,
            "setpt": [-18.0],
            "dt_setpt": [6000.0],
            "ramp_rate": 1.0,
        },
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
def test_pressure_dae_model_constructs_with_selected_transformation(
    pressure_case, method, expected_points
) -> None:
    model = create_dae_chamber_pressure_optimization_model(
        pressure_case["vial"],
        pressure_case["product"],
        pressure_case["ht"],
        pressure_case["pchamber"],
        pressure_case["tshelf"],
        eq_cap=pressure_case["eq_cap"],
        nvial=pressure_case["nvial"],
        nfe=4,
        discretization=method,
        ncp=3,
    )

    first = model.t.first()
    assert model.optimized_control == "chamber_pressure"
    assert model.discretization_method == method.value
    assert len(model.t) == expected_points
    assert model.Pch[first].bounds == pytest.approx((0.05, 0.5))
    assert model.Tsh[first].bounds == pytest.approx((-18.0, -18.0))
    assert pyo.value(model.fixed_Tsh) == pytest.approx(-18.0)
    assert model.obj.expr is model.t_final


def test_pressure_dae_model_rejects_changing_fixed_shelf_profile(pressure_case) -> None:
    pressure_case["tshelf"]["setpt"] = [-18.0, -15.0]

    with pytest.raises(ValueError, match="one constant tshelf setpoint"):
        create_dae_chamber_pressure_optimization_model(
            pressure_case["vial"],
            pressure_case["product"],
            pressure_case["ht"],
            pressure_case["pchamber"],
            pressure_case["tshelf"],
            eq_cap=pressure_case["eq_cap"],
            nvial=pressure_case["nvial"],
        )


@pytest.mark.parametrize(
    ("bounds", "message"),
    [
        ({"min": 0.0, "max": 0.5}, "positive and increasing"),
        ({"min": 0.5, "max": 0.05}, "positive and increasing"),
    ],
)
def test_pressure_dae_model_rejects_invalid_pressure_bounds(
    pressure_case, bounds, message
) -> None:
    pressure_case["pchamber"] = bounds

    with pytest.raises(ValueError, match=message):
        create_dae_chamber_pressure_optimization_model(
            pressure_case["vial"],
            pressure_case["product"],
            pressure_case["ht"],
            pressure_case["pchamber"],
            pressure_case["tshelf"],
            eq_cap=pressure_case["eq_cap"],
            nvial=pressure_case["nvial"],
        )


@pytest.mark.parametrize("method", ["finite_difference", "collocation"])
def test_pressure_dae_model_solves_equivalent_complete_drying_problem(
    pressure_case, method
) -> None:
    solver = require_pyomo_solver("ipopt")
    nfe = 8 if method == "finite_difference" else 4
    result = solve_dae_chamber_pressure_optimization(
        pressure_case["vial"],
        pressure_case["product"],
        pressure_case["ht"],
        pressure_case["pchamber"],
        pressure_case["tshelf"],
        eq_cap=pressure_case["eq_cap"],
        nvial=pressure_case["nvial"],
        nfe=nfe,
        discretization=method,
        ncp=2,
        solver=solver,
    )

    table = result.as_table()
    assert result.success, result.message
    assert result.discretization["optimized_control"] == "chamber_pressure"
    assert result.discretization["method"] == method
    assert result.discretization["nfe"] == nfe
    assert result.discretization["ncp"] == (None if method == "finite_difference" else 2)
    assert result.objective_time_hr == pytest.approx(table[-1, 0])
    assert table[-1, 6] >= 100.0 - 1.0e-3
    assert np.max(table[:, 2]) <= pressure_case["product"]["T_pr_crit"] + 1.0e-4
    assert table[:, 3] == pytest.approx(pressure_case["tshelf"]["init"], abs=1.0e-8)
    assert np.min(table[:, 4]) >= pressure_case["pchamber"]["min"] * 1000.0 - 1.0e-3
    assert np.max(table[:, 4]) <= pressure_case["pchamber"]["max"] * 1000.0 + 1.0e-3
    assert table[0, 4] == pytest.approx(table[1, 4], abs=1.0e-3)
    assert max(value or 0.0 for value in result.constraint_violations.values()) < 1.0e-4

    lpr0 = functions.Lpr0_FUN(
        pressure_case["vial"]["Vfill"],
        pressure_case["vial"]["Ap"],
        pressure_case["product"]["cSolid"],
    )
    residuals = []
    for row in table:
        pch = row[4] / constant.Torr_to_mTorr
        dmdt = row[5] * pressure_case["vial"]["Ap"] * constant.cm_To_m**2
        lck = row[6] / 100.0 * lpr0
        psub = functions.Vapor_pressure(row[1])
        kv = functions.Kv_FUN(
            pressure_case["ht"]["KC"],
            pressure_case["ht"]["KP"],
            pressure_case["ht"]["KD"],
            pch,
        )
        rp = functions.Rp_FUN(
            lck,
            pressure_case["product"]["R0"],
            pressure_case["product"]["A1"],
            pressure_case["product"]["A2"],
        )
        residuals.extend(
            functions.Eq_Constraints(
                pch,
                dmdt,
                row[2],
                row[3],
                psub,
                row[1],
                kv,
                lpr0,
                lck,
                pressure_case["vial"]["Av"],
                pressure_case["vial"]["Ap"],
                rp,
            )
        )
    assert np.max(np.abs(residuals)) < 1.0e-4
