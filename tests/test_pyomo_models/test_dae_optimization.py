from __future__ import annotations

import numpy as np
import pytest

from lyopronto import constant, functions
from lyopronto.pyomo_models import (
    DaeDiscretization,
    create_dae_shelf_temperature_optimization_model,
    solve_dae_shelf_temperature_optimization,
)
from tests.pyomo_solver import require_pyomo_solver


@pytest.fixture
def dae_case():
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
        "pchamber": {"setpt": [0.1], "dt_setpt": [1800.0], "ramp_rate": 0.5},
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
def test_dae_model_constructs_with_selected_transformation(
    dae_case, method, expected_points
) -> None:
    model = create_dae_shelf_temperature_optimization_model(
        dae_case["vial"],
        dae_case["product"],
        dae_case["ht"],
        dae_case["pchamber"],
        dae_case["tshelf"],
        eq_cap=dae_case["eq_cap"],
        nvial=dae_case["nvial"],
        nfe=4,
        discretization=method,
        ncp=3,
    )

    assert model.discretization_method == method.value
    assert len(model.t) == expected_points
    assert model.t_final.is_variable_type()
    assert model.obj.expr is model.t_final
    assert np.isclose(model.final_dried_fraction.value, 1.0)


def test_dae_model_rejects_changing_fixed_pressure_profile(dae_case) -> None:
    dae_case["pchamber"]["setpt"] = [0.1, 0.2]

    with pytest.raises(ValueError, match="one constant"):
        create_dae_shelf_temperature_optimization_model(
            dae_case["vial"],
            dae_case["product"],
            dae_case["ht"],
            dae_case["pchamber"],
            dae_case["tshelf"],
            eq_cap=dae_case["eq_cap"],
            nvial=dae_case["nvial"],
        )


@pytest.mark.pyomo
@pytest.mark.parametrize("method", ["finite_difference", "collocation"])
def test_dae_model_solves_to_complete_drying(dae_case, method) -> None:
    solver = require_pyomo_solver("ipopt")
    result = solve_dae_shelf_temperature_optimization(
        dae_case["vial"],
        dae_case["product"],
        dae_case["ht"],
        dae_case["pchamber"],
        dae_case["tshelf"],
        eq_cap=dae_case["eq_cap"],
        nvial=dae_case["nvial"],
        nfe=8,
        discretization=method,
        ncp=3,
        solver=solver,
    )

    table = result.as_table()
    assert result.success, result.message
    assert result.objective_time_hr == pytest.approx(table[-1, 0])
    assert table[-1, 6] >= 100.0 - 1.0e-3
    assert np.max(table[:, 2]) <= dae_case["product"]["T_pr_crit"] + 1.0e-4
    assert max(value or 0.0 for value in result.constraint_violations.values()) < 1.0e-4

    lpr0 = functions.Lpr0_FUN(
        dae_case["vial"]["Vfill"],
        dae_case["vial"]["Ap"],
        dae_case["product"]["cSolid"],
    )
    residuals = []
    for row in table:
        pch = row[4] / constant.Torr_to_mTorr
        dmdt = row[5] * dae_case["vial"]["Ap"] * constant.cm_To_m**2
        lck = row[6] / 100.0 * lpr0
        psub = functions.Vapor_pressure(row[1])
        kv = functions.Kv_FUN(
            dae_case["ht"]["KC"], dae_case["ht"]["KP"], dae_case["ht"]["KD"], pch
        )
        rp = functions.Rp_FUN(
            lck,
            dae_case["product"]["R0"],
            dae_case["product"]["A1"],
            dae_case["product"]["A2"],
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
                dae_case["vial"]["Av"],
                dae_case["vial"]["Ap"],
                rp,
            )
        )
    assert np.max(np.abs(residuals)) < 1.0e-4
