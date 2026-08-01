from __future__ import annotations

import numpy as np
import pytest

from lyopronto import constant, functions
from tests.pyomo_solver import require_pyomo_solver

pyo = pytest.importorskip("pyomo.environ")

from lyopronto.pyomo_models import (
    DaeDiscretization,
    create_dae_shelf_temperature_optimization_model,
    solve_dae_shelf_temperature_optimization,
)

pytestmark = pytest.mark.pyomo


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


def test_dae_warmstart_converts_legacy_trajectory_units(dae_case) -> None:
    """Seed normalized DAE variables from the legacy seven-column unit contract."""
    # Columns are time [hr], temperatures [degC], pressure [mTorr],
    # sublimation flux [kg/hr/m^2], and percent dried [0-100].
    initialize = np.array(
        [
            [0.0, -35.0, -30.0, 10.0, 100.0, 0.5, 0.0],
            [2.0, -34.0, -29.0, 11.0, 100.0, 1.0, 50.0],
            [4.0, -33.0, -28.0, 12.0, 100.0, 1.5, 100.0],
        ]
    )
    model = create_dae_shelf_temperature_optimization_model(
        dae_case["vial"],
        dae_case["product"],
        dae_case["ht"],
        dae_case["pchamber"],
        dae_case["tshelf"],
        eq_cap=dae_case["eq_cap"],
        nvial=dae_case["nvial"],
        nfe=2,
        initialize=initialize,
    )

    horizon_hr = initialize[-1, 0]
    area_m2 = dae_case["vial"]["Ap"] * constant.cm_To_m**2
    lpr0_cm = float(pyo.value(model.Lpr0))
    length_factor = float(pyo.value(model.drying_length_factor))
    assert pyo.value(model.t_final) == pytest.approx(horizon_hr)
    for tau, row in zip(sorted(model.t), initialize):
        dmdt_kg_per_hr_vial = row[5] * area_m2
        psub_torr = functions.Vapor_pressure(row[1])
        assert pyo.value(model.Lck[tau]) == pytest.approx(row[6] / 100.0 * lpr0_cm)
        assert pyo.value(model.Tsub[tau]) == pytest.approx(row[1])
        assert pyo.value(model.Tbot[tau]) == pytest.approx(row[2])
        assert pyo.value(model.Tsh[tau]) == pytest.approx(row[3])
        assert pyo.value(model.Pch[tau]) == pytest.approx(row[4] / constant.Torr_to_mTorr)
        assert pyo.value(model.dmdt[tau]) == pytest.approx(dmdt_kg_per_hr_vial)
        assert pyo.value(model.Psub[tau]) == pytest.approx(psub_torr)
        assert pyo.value(model.log_Psub[tau]) == pytest.approx(np.log(psub_torr))
        assert pyo.value(model.Kv[tau]) == pytest.approx(
            functions.Kv_FUN(
                dae_case["ht"]["KC"],
                dae_case["ht"]["KP"],
                dae_case["ht"]["KD"],
                row[4] / constant.Torr_to_mTorr,
            )
        )
        assert pyo.value(model.dLck_dt[tau]) == pytest.approx(
            horizon_hr * dmdt_kg_per_hr_vial * length_factor
        )


@pytest.mark.parametrize(
    ("initialize", "message"),
    [
        (np.array([[0.0] * 6, [1.0] * 6]), "two-dimensional, seven-column"),
        (np.zeros((2, 7)), "finite positive-time"),
    ],
)
def test_dae_model_rejects_invalid_warmstart_tables(dae_case, initialize, message) -> None:
    with pytest.raises(ValueError, match=message):
        create_dae_shelf_temperature_optimization_model(
            dae_case["vial"],
            dae_case["product"],
            dae_case["ht"],
            dae_case["pchamber"],
            dae_case["tshelf"],
            eq_cap=dae_case["eq_cap"],
            nvial=dae_case["nvial"],
            initialize=initialize,
        )


def test_dae_model_rejects_missing_required_input(dae_case) -> None:
    del dae_case["product"]["A1"]

    with pytest.raises(KeyError, match=r"product is missing required key\(s\): A1"):
        create_dae_shelf_temperature_optimization_model(
            dae_case["vial"],
            dae_case["product"],
            dae_case["ht"],
            dae_case["pchamber"],
            dae_case["tshelf"],
            eq_cap=dae_case["eq_cap"],
            nvial=dae_case["nvial"],
        )


def test_dae_model_rejects_unknown_discretization(dae_case) -> None:
    with pytest.raises(ValueError, match="finite_difference.*collocation"):
        create_dae_shelf_temperature_optimization_model(
            dae_case["vial"],
            dae_case["product"],
            dae_case["ht"],
            dae_case["pchamber"],
            dae_case["tshelf"],
            eq_cap=dae_case["eq_cap"],
            nvial=dae_case["nvial"],
            discretization="spectral_magic",
        )


def test_dae_model_rejects_nonpositive_pressure(dae_case) -> None:
    dae_case["pchamber"]["setpt"] = [0.0]

    with pytest.raises(ValueError, match="setpoint must be positive"):
        create_dae_shelf_temperature_optimization_model(
            dae_case["vial"],
            dae_case["product"],
            dae_case["ht"],
            dae_case["pchamber"],
            dae_case["tshelf"],
            eq_cap=dae_case["eq_cap"],
            nvial=dae_case["nvial"],
        )


@pytest.mark.parametrize(
    ("keyword", "value", "message"),
    [
        ("nfe", 0, "nfe must be at least one"),
        ("ncp", 0, "ncp must be at least one"),
        ("nvial", 0, "nvial must be at least one"),
        ("final_dried_fraction", 0.0, "0 < value <= 1"),
        ("t_final_bounds", (0.0, 50.0), "positive and increasing"),
    ],
)
def test_dae_model_rejects_invalid_numeric_arguments(dae_case, keyword, value, message) -> None:
    arguments = {"eq_cap": dae_case["eq_cap"], "nvial": dae_case["nvial"]}
    arguments[keyword] = value
    with pytest.raises(ValueError, match=message):
        create_dae_shelf_temperature_optimization_model(
            dae_case["vial"],
            dae_case["product"],
            dae_case["ht"],
            dae_case["pchamber"],
            dae_case["tshelf"],
            **arguments,
        )


def test_dae_model_rejects_reversed_shelf_temperature_bounds(dae_case) -> None:
    dae_case["tshelf"]["max"] = dae_case["tshelf"]["min"]

    with pytest.raises(ValueError, match="tshelf max must be greater"):
        create_dae_shelf_temperature_optimization_model(
            dae_case["vial"],
            dae_case["product"],
            dae_case["ht"],
            dae_case["pchamber"],
            dae_case["tshelf"],
            eq_cap=dae_case["eq_cap"],
            nvial=dae_case["nvial"],
        )


@pytest.mark.parametrize(
    ("configured_scaling", "expected_scaling"),
    [(None, "user-scaling"), ("gradient-based", "gradient-based")],
)
def test_dae_solver_enables_model_scaling_without_overriding_user_choice(
    dae_case, configured_scaling, expected_scaling
) -> None:
    class StopAfterOptionsSolver:
        name = "ipopt"

        def __init__(self) -> None:
            self.options = {}
            if configured_scaling is not None:
                self.options["nlp_scaling_method"] = configured_scaling

        def solve(self, _model, *, tee):
            raise RuntimeError(f"stop after inspecting options (tee={tee})")

    solver = StopAfterOptionsSolver()
    result = solve_dae_shelf_temperature_optimization(
        dae_case["vial"],
        dae_case["product"],
        dae_case["ht"],
        dae_case["pchamber"],
        dae_case["tshelf"],
        eq_cap=dae_case["eq_cap"],
        nvial=dae_case["nvial"],
        nfe=2,
        solver=solver,
    )

    assert not result.success
    assert solver.options["nlp_scaling_method"] == expected_scaling


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
    assert result.discretization["n_variables"] > 0
    assert result.discretization["n_constraints"] > 0
    assert result.discretization["solver_iterations"] is None or (
        result.discretization["solver_iterations"] >= 0
    )
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
        kv = functions.Kv_FUN(dae_case["ht"]["KC"], dae_case["ht"]["KP"], dae_case["ht"]["KD"], pch)
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
