from __future__ import annotations

from typing import Dict

import numpy as np
import pytest
import scipy.optimize as sp

from lyopronto import constant, functions
from tests.pyomo_solver import require_pyomo_solver

pyo = pytest.importorskip("pyomo.environ")

from lyopronto.pyomo_models.single_step import create_single_step_model, solve_single_step
from lyopronto.pyomo_models.utils import format_single_step_output

pytestmark = pytest.mark.pyomo


@pytest.fixture
def standard_case() -> Dict[str, object]:
    vial = {"Av": 3.8, "Ap": 3.14, "Vfill": 2.0}
    product = {
        "T_pr_crit": -20.0,
        "cSolid": 0.05,
        "R0": 1.4,
        "A1": 16.0,
        "A2": 0.0,
    }
    ht = {"KC": 0.000275, "KP": 0.000893, "KD": 0.46}
    eq_cap = {"a": -0.182, "b": 11.7}
    lpr0 = functions.Lpr0_FUN(vial["Vfill"], vial["Ap"], product["cSolid"])
    return {
        "vial": vial,
        "product": product,
        "ht": ht,
        "eq_cap": eq_cap,
        "nvial": 398,
        "lpr0": lpr0,
        "lck": 0.5 * lpr0,
        "fixed_pch": 0.15,
        "tsh_bounds": (-45.0, 20.0),
    }


def _scipy_single_step_reference(case: Dict[str, object]) -> Dict[str, float]:
    vial = case["vial"]
    product = case["product"]
    ht = case["ht"]
    eq_cap = case["eq_cap"]
    lpr0 = case["lpr0"]
    lck = case["lck"]
    fixed_pch = case["fixed_pch"]
    tsh_bounds = case["tsh_bounds"]
    rp = functions.Rp_FUN(lck, product["R0"], product["A1"], product["A2"])

    def objective(x):
        return x[0] - x[4]

    constraints = (
        {
            "type": "eq",
            "fun": lambda x: functions.Eq_Constraints(
                x[0],
                x[1],
                x[2],
                x[3],
                x[4],
                x[5],
                x[6],
                lpr0,
                lck,
                vial["Av"],
                vial["Ap"],
                rp,
            )[0],
        },
        {
            "type": "eq",
            "fun": lambda x: functions.Eq_Constraints(
                x[0],
                x[1],
                x[2],
                x[3],
                x[4],
                x[5],
                x[6],
                lpr0,
                lck,
                vial["Av"],
                vial["Ap"],
                rp,
            )[1],
        },
        {
            "type": "eq",
            "fun": lambda x: functions.Eq_Constraints(
                x[0],
                x[1],
                x[2],
                x[3],
                x[4],
                x[5],
                x[6],
                lpr0,
                lck,
                vial["Av"],
                vial["Ap"],
                rp,
            )[2],
        },
        {
            "type": "eq",
            "fun": lambda x: functions.Eq_Constraints(
                x[0],
                x[1],
                x[2],
                x[3],
                x[4],
                x[5],
                x[6],
                lpr0,
                lck,
                vial["Av"],
                vial["Ap"],
                rp,
            )[3],
        },
        {
            "type": "eq",
            "fun": lambda x: x[6] - functions.Kv_FUN(ht["KC"], ht["KP"], ht["KD"], x[0]),
        },
        {"type": "eq", "fun": lambda x: x[0] - fixed_pch},
        {
            "type": "ineq",
            "fun": lambda x: functions.Ineq_Constraints(
                x[0],
                x[1],
                product["T_pr_crit"],
                x[2],
                eq_cap["a"],
                eq_cap["b"],
                case["nvial"],
            )[0],
        },
        {
            "type": "ineq",
            "fun": lambda x: functions.Ineq_Constraints(
                x[0],
                x[1],
                product["T_pr_crit"],
                x[2],
                eq_cap["a"],
                eq_cap["b"],
                case["nvial"],
            )[1],
        },
    )
    x0 = np.array(
        [
            fixed_pch,
            1.0e-4,
            product["T_pr_crit"] - 0.1,
            product["T_pr_crit"] + 1.0,
            fixed_pch * 2.0,
            product["T_pr_crit"] - 1.0,
            functions.Kv_FUN(ht["KC"], ht["KP"], ht["KD"], fixed_pch),
        ]
    )
    result = sp.minimize(
        objective,
        x0,
        bounds=(
            (None, None),
            (0.0, None),
            (None, None),
            tsh_bounds,
            (0.0, None),
            (-60.0, 0.0),
            (0.0, None),
        ),
        constraints=constraints,
        method="SLSQP",
        options={"ftol": 1.0e-10, "maxiter": 1000},
    )
    assert result.success, result.message
    keys = ("Pch", "dmdt", "Tbot", "Tsh", "Psub", "Tsub", "Kv")
    return dict(zip(keys, map(float, result.x)))


def test_single_step_model_constructs_without_global_state(standard_case):
    model = create_single_step_model(
        standard_case["vial"],
        standard_case["product"],
        standard_case["ht"],
        standard_case["lpr0"],
        standard_case["lck"],
        tsh_bounds=standard_case["tsh_bounds"],
        eq_cap=standard_case["eq_cap"],
        nvial=standard_case["nvial"],
        fixed_pch=standard_case["fixed_pch"],
    )

    assert isinstance(model, pyo.ConcreteModel)
    for name in ("Pch", "Tsh", "Tsub", "Tbot", "Psub", "log_Psub", "dmdt", "Kv"):
        assert hasattr(model, name)
    for name in (
        "vapor_pressure_log",
        "vapor_pressure_exp",
        "mass_transfer",
        "frozen_layer_heat_balance",
        "energy_balance",
        "vial_heat_transfer",
        "equipment_capability",
    ):
        assert hasattr(model, name)
    assert model.Pch.bounds == (0.05, 0.5)
    assert model.Tsh.bounds == standard_case["tsh_bounds"]
    assert pyo.value(model.Rp) == pytest.approx(
        functions.Rp_FUN(
            standard_case["lck"],
            standard_case["product"]["R0"],
            standard_case["product"]["A1"],
            standard_case["product"]["A2"],
        )
    )


def test_equipment_capability_requires_vial_count(standard_case):
    with pytest.raises(ValueError, match="nvial is required"):
        create_single_step_model(
            standard_case["vial"],
            standard_case["product"],
            standard_case["ht"],
            standard_case["lpr0"],
            standard_case["lck"],
            eq_cap=standard_case["eq_cap"],
        )


def test_lck_must_be_inside_primary_drying_front(standard_case):
    with pytest.raises(ValueError, match="0 <= lck < lpr0"):
        create_single_step_model(
            standard_case["vial"],
            standard_case["product"],
            standard_case["ht"],
            standard_case["lpr0"],
            standard_case["lpr0"],
        )


def test_unsolved_single_step_returns_clear_diagnostics(standard_case):
    class FailingSolver:
        options = {}

        def solve(self, model, tee=False):
            raise RuntimeError("solver executable missing")

    model = create_single_step_model(
        standard_case["vial"],
        standard_case["product"],
        standard_case["ht"],
        standard_case["lpr0"],
        standard_case["lck"],
    )

    result = solve_single_step(model, solver=FailingSolver())

    assert not result.success
    assert result.solver_status == "not_available"
    assert "solver executable missing" in result.message
    assert "Pyomo solve failed before returning results" in result.message
    assert "Pch" in result.values
    assert "mass_transfer" in result.constraint_violations


def test_format_single_step_output_uses_legacy_units():
    values = {
        "Pch": 0.15,
        "Tsh": -10.0,
        "Tsub": -25.0,
        "Tbot": -20.0,
        "dmdt": 0.5,
    }

    row = format_single_step_output(values, time=0.25, ap=3.14, percent_dried=42.0)

    np.testing.assert_allclose(
        row,
        np.array([0.25, -25.0, -20.0, -10.0, 150.0, 0.5 / (3.14 * constant.cm_To_m**2), 42.0]),
    )


def test_single_step_solves_and_matches_scipy_reference(standard_case):
    solver = require_pyomo_solver("ipopt")
    reference = _scipy_single_step_reference(standard_case)
    model = create_single_step_model(
        standard_case["vial"],
        standard_case["product"],
        standard_case["ht"],
        standard_case["lpr0"],
        standard_case["lck"],
        tsh_bounds=standard_case["tsh_bounds"],
        eq_cap=standard_case["eq_cap"],
        nvial=standard_case["nvial"],
        fixed_pch=standard_case["fixed_pch"],
        initialize=reference,
    )

    result = solve_single_step(model, solver=solver)

    assert result.success, result.message
    solved = result.as_dict()
    assert solved["Pch"] == pytest.approx(reference["Pch"], abs=1.0e-5)
    assert solved["Tsh"] == pytest.approx(reference["Tsh"], abs=5.0e-2)
    assert solved["Tbot"] == pytest.approx(reference["Tbot"], abs=5.0e-2)
    assert solved["Tsub"] == pytest.approx(reference["Tsub"], abs=5.0e-2)
    assert solved["Psub"] == pytest.approx(reference["Psub"], rel=5.0e-3)
    assert solved["dmdt"] == pytest.approx(reference["dmdt"], rel=5.0e-3, abs=1.0e-7)
    assert max(violation or 0.0 for violation in result.constraint_violations.values()) < 1.0e-5
