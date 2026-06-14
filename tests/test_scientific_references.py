"""Scientific reference scenarios for issue #69."""

import math

import numpy as np
import pytest
import scipy.optimize as sp

from lyopronto import (
    PikalParams,
    Q_,
    RFParams,
    RampedVariable,
    RpFormFit,
    calc_knownRp,
    calc_rf_heat_terms,
    calc_rf_u0,
    calc_unknownRp,
    design_space,
    opt_Pch,
    opt_Tsh,
    physical_properties,
    qrf_integrate,
    solve_pikal,
    solve_rf,
    vials,
)
from lyopronto.freezing import freeze
from lyopronto.functions import Rp_FUN

from .scientific_reference_scenarios import REFERENCE_SCENARIOS


def _legacy_vial():
    return {"Av": 3.8, "Ap": 3.14, "Vfill": 2.0}


def _legacy_product(t_pr_crit=None):
    product = {"R0": 1.4, "A1": 16.0, "A2": 0.0, "cSolid": 0.05}
    if t_pr_crit is not None:
        product["T_pr_crit"] = t_pr_crit
    return product


def _legacy_ht():
    return {"KC": 0.000275, "KP": 0.000893, "KD": 0.46}


def _legacy_pchamber():
    return {"setpt": [0.15], "dt_setpt": [1800.0], "ramp_rate": 0.5}


def _legacy_tshelf():
    return {"init": -35.0, "setpt": [20.0], "dt_setpt": [1800.0], "ramp_rate": 1.0}


def _eq_cap():
    return {"a": -0.182, "b": 11.7}


def _assert_close(actual, scenario, metric):
    assert actual == pytest.approx(
        scenario.expected[metric], abs=scenario.tolerances[metric]
    )


def _load_temperature_series(reference_data_path):
    data = np.loadtxt(reference_data_path / "temperature.txt")
    if data.ndim == 1:
        return np.array([data[0]]), np.array([data[1]])
    if data.shape[1] == 2:
        return data[:, 0], data[:, 1]
    return data[:, 1], data[:, 2]


def _sucrose_pikal_params():
    rad_i, rad_o = vials.get_vial_radii("10R")
    ap = math.pi * rad_i**2
    av = math.pi * rad_o**2

    return PikalParams(
        Rp=RpFormFit(
            Q_(0.8, "centimeter ** 2 * torr * hour / gram"),
            Q_(14.0, "centimeter * torr * hour / gram"),
            Q_(1.0, "1 / centimeter"),
        ),
        hf0=Q_(4.0, "milliliter") / ap,
        csolid=Q_(0.05, "gram / milliliter"),
        rho_solution=Q_(1.0, "gram / milliliter"),
        Kshf=RpFormFit(
            Q_(3.58e-4, "calorie / second / kelvin / centimeter ** 2"),
            Q_(8.93e-4, "calorie / second / kelvin / centimeter ** 2 / torr"),
            Q_(0.46, "1 / torr"),
        ),
        Av=av,
        Ap=ap,
        pch=RampedVariable.constant(Q_(70.0, "millitorr")),
        Tsh=RampedVariable.linear(
            [Q_(273.15 - 45.0, "kelvin"), Q_(273.15 - 25.0, "kelvin")],
            Q_(1.0, "kelvin / minute"),
        ),
    )


def _synthetic_rf_params():
    rad_i, rad_o = vials.get_vial_radii("6R")
    ap = math.pi * rad_i**2
    av = math.pi * rad_o**2
    mv = vials.get_vial_mass("6R")

    csolid = Q_(0.05, "gram / milliliter")
    rho_solution = Q_(1.0, "gram / milliliter")
    vfill = Q_(5.0, "milliliter")

    return RFParams.from_nested_tuple(
        (
            (
                RpFormFit(
                    Q_(1.4, "centimeter ** 2 * hour * torr / gram"),
                    Q_(16.0, "centimeter * hour * torr / gram"),
                    Q_(0.0, "1 / centimeter"),
                ),
                vfill / ap,
                csolid,
                rho_solution,
            ),
            (
                RpFormFit(
                    Q_(2.75e-4, "calorie / second / kelvin / centimeter ** 2"),
                    Q_(
                        8.93e-4,
                        "calorie / second / kelvin / centimeter ** 2 / torr",
                    ),
                    Q_(0.46, "1 / torr"),
                ),
                av,
                ap,
            ),
            (
                RampedVariable.constant(Q_(100.0, "millitorr")),
                RampedVariable.linear(
                    [Q_(233.15, "kelvin"), Q_(283.15, "kelvin")],
                    Q_(0.5, "kelvin / minute"),
                ),
                RampedVariable.constant(Q_(10.0, "watt") / 17.0 * 0.54),
            ),
            (
                vfill * rho_solution,
                physical_properties.cp_ice,
                mv,
                physical_properties.cp_gl,
            ),
            (
                Q_(8.0, "gigahertz"),
                physical_properties.eppf,
                physical_properties.epp_gl,
            ),
            (
                Q_(1.0e-3, "calorie / second / kelvin / centimeter ** 2"),
                Q_(2.0e7, "ohm / meter ** 2"),
                Q_(0.9e7, "ohm / meter ** 2"),
            ),
        )
    )


def test_reference_scenarios_document_units_tolerances_and_provenance():
    required = {
        "known_rp_primary_drying",
        "unknown_rp_estimation",
        "shelf_temperature_optimizer",
        "pressure_optimizer",
        "freezing",
        "design_space",
        "typed_pikal",
        "typed_rf",
    }

    assert required.issubset(REFERENCE_SCENARIOS)

    for scenario in REFERENCE_SCENARIOS.values():
        assert scenario.name
        assert scenario.category
        assert scenario.input_units
        assert scenario.output_units
        assert scenario.expected
        assert scenario.tolerances
        assert scenario.tolerance_notes
        assert scenario.provenance


def test_known_rp_primary_drying_reference():
    scenario = REFERENCE_SCENARIOS["known_rp_primary_drying"]

    output = calc_knownRp.dry(
        _legacy_vial(),
        _legacy_product(),
        _legacy_ht(),
        _legacy_pchamber(),
        _legacy_tshelf(),
        0.01,
    )

    assert output.shape == (scenario.expected["rows"], 7)
    _assert_close(output[-1, 0], scenario, "drying_time_hr")
    _assert_close(output[:, 1].max(), scenario, "max_tsub_c")
    _assert_close(output[:, 2].max(), scenario, "max_tbot_c")
    _assert_close(output[-1, 3], scenario, "final_tsh_c")
    _assert_close(output[0, 4], scenario, "pch_mtorr")
    _assert_close(output[:, 5].max(), scenario, "max_flux_kg_hr_m2")
    _assert_close(output[-1, 6], scenario, "final_percent_dried")


def test_unknown_rp_estimation_reference(reference_data_path):
    scenario = REFERENCE_SCENARIOS["unknown_rp_estimation"]
    time, tbot_exp = _load_temperature_series(reference_data_path)

    output, product_res = calc_unknownRp.dry(
        _legacy_vial(),
        {"cSolid": 0.05, "T_pr_crit": -25.0},
        _legacy_ht(),
        _legacy_pchamber(),
        _legacy_tshelf(),
        time,
        tbot_exp,
    )
    params, _params_covariance = sp.curve_fit(
        Rp_FUN,
        product_res[:, 1],
        product_res[:, 2],
        p0=[1.0, 1.0, 0.0],
    )

    assert output.shape == (scenario.expected["rows_output"], 7)
    assert product_res.shape == (scenario.expected["rows_product_res"], 3)
    _assert_close(output[-1, 0], scenario, "final_time_hr")
    _assert_close(output[-1, 6], scenario, "final_percent_dried")
    _assert_close(product_res[-1, 1], scenario, "final_Lck_cm")
    _assert_close(product_res[-1, 2], scenario, "final_Rp_cm2_hr_torr_g")
    _assert_close(params[0], scenario, "fit_R0")
    _assert_close(params[1], scenario, "fit_A1")
    _assert_close(params[2], scenario, "fit_A2")


@pytest.mark.slow
def test_shelf_temperature_optimizer_reference():
    scenario = REFERENCE_SCENARIOS["shelf_temperature_optimizer"]

    output = opt_Tsh.dry(
        _legacy_vial(),
        _legacy_product(t_pr_crit=-5.0),
        _legacy_ht(),
        {
            "setpt": np.array([0.15]),
            "dt_setpt": np.array([1800]),
            "ramp_rate": 0.5,
        },
        {
            "min": -45.0,
            "max": 120.0,
            "init": -35.0,
            "ramp_rate": 1.0,
        },
        0.01,
        _eq_cap(),
        398,
    )

    assert output.shape == (scenario.expected["rows"], 7)
    _assert_close(output[-1, 0], scenario, "drying_time_hr")
    _assert_close(output[:, 2].max(), scenario, "max_tbot_c")
    _assert_close(output[:, 3].max(), scenario, "max_tsh_c")
    _assert_close(output[0, 4], scenario, "pch_mtorr")
    _assert_close(output[:, 5].max(), scenario, "max_flux_kg_hr_m2")
    _assert_close(output[-1, 6], scenario, "final_percent_dried")


@pytest.mark.slow
def test_pressure_optimizer_reference():
    scenario = REFERENCE_SCENARIOS["pressure_optimizer"]

    output = opt_Pch.dry(
        _legacy_vial(),
        _legacy_product(t_pr_crit=-5.0),
        _legacy_ht(),
        {"min": 0.05, "max": 1000.0},
        {
            "init": -35.0,
            "setpt": np.array([20.0]),
            "dt_setpt": np.array([1800]),
            "ramp_rate": 1.0,
        },
        0.01,
        _eq_cap(),
        398,
    )

    assert output.shape == (scenario.expected["rows"], 7)
    _assert_close(output[-1, 0], scenario, "drying_time_hr")
    _assert_close(output[:, 2].max(), scenario, "max_tbot_c")
    _assert_close(output[:, 4].min(), scenario, "min_pch_mtorr")
    _assert_close(output[:, 4].max(), scenario, "max_pch_mtorr")
    _assert_close(output[:, 5].max(), scenario, "max_flux_kg_hr_m2")
    _assert_close(output[-1, 6], scenario, "final_percent_dried")


def test_freezing_reference_summary():
    scenario = REFERENCE_SCENARIOS["freezing"]
    product = {"Tpr0": 15.8, "Tf": -1.54, "Tn": -5.84, "cSolid": 0.05}

    output = freeze(
        _legacy_vial(),
        product,
        38.0,
        {
            "init": 10.0,
            "setpt": np.array([-40.0]),
            "dt_setpt": np.array([180]),
            "ramp_rate": 1.0,
        },
        0.01,
    )
    nucleation_time = output[np.where(output[:, 2] <= product["Tn"])[0][0], 0]
    crystallization_time = output[
        np.where(np.isclose(output[:, 2], product["Tf"]))[0][0], 0
    ]

    assert output.shape == (scenario.expected["rows"], 3)
    _assert_close(output[-1, 0], scenario, "final_time_hr")
    _assert_close(nucleation_time, scenario, "nucleation_time_hr")
    _assert_close(crystallization_time, scenario, "crystallization_start_hr")
    _assert_close(output[-1, 2], scenario, "final_product_temp_c")
    _assert_close(output[-1, 1], scenario, "final_shelf_temp_c")


def test_design_space_reference_grid():
    scenario = REFERENCE_SCENARIOS["design_space"]

    shelf_results, product_results, eq_cap_results = design_space.dry(
        _legacy_vial(),
        _legacy_product(t_pr_crit=-25.0),
        _legacy_ht(),
        {"setpt": np.array([0.05, 0.10, 0.15])},
        {"init": -35.0, "setpt": np.array([-20.0, -10.0, 0.0]), "ramp_rate": 1.0},
        0.01,
        _eq_cap(),
        398,
    )

    assert shelf_results.shape == scenario.expected["shelf_shape"]
    assert product_results.shape == scenario.expected["product_shape"]
    assert eq_cap_results.shape == scenario.expected["eq_shape"]
    np.testing.assert_allclose(
        shelf_results[0],
        np.array(scenario.expected["shelf_Tmax_grid_c"]),
        rtol=0.0,
        atol=scenario.tolerances["shelf_Tmax_grid_c"],
    )
    np.testing.assert_allclose(
        shelf_results[1],
        np.array(scenario.expected["shelf_drying_time_grid_hr"]),
        rtol=0.0,
        atol=scenario.tolerances["shelf_drying_time_grid_hr"],
    )
    np.testing.assert_allclose(
        product_results[0],
        np.array(scenario.expected["product_T_values_c"]),
        rtol=0.0,
        atol=scenario.tolerances["product_T_values_c"],
    )
    np.testing.assert_allclose(
        product_results[1],
        np.array(scenario.expected["product_drying_time_values_hr"]),
        rtol=0.0,
        atol=scenario.tolerances["product_drying_time_values_hr"],
    )
    np.testing.assert_allclose(
        eq_cap_results[2],
        np.array(scenario.expected["eq_flux_values_kg_hr_m2"]),
        rtol=0.0,
        atol=scenario.tolerances["eq_flux_values_kg_hr_m2"],
    )


def test_typed_pikal_reference():
    scenario = REFERENCE_SCENARIOS["typed_pikal"]

    solution = solve_pikal(_sucrose_pikal_params())
    legacy = solution.to_legacy_table()

    _assert_close(
        solution.drying_time.to("hour").magnitude,
        scenario,
        "drying_time_hr",
    )
    _assert_close(solution.tf[-1].to("degC").magnitude, scenario, "final_tf_c")
    _assert_close(solution.hf[-1].to("centimeter").magnitude, scenario, "final_hf_cm")
    _assert_close(legacy[-1, 6], scenario, "legacy_final_percent_dried")
    _assert_close(legacy[-1, 5], scenario, "final_flux_kg_hr_m2")


def test_typed_rf_reference():
    scenario = REFERENCE_SCENARIOS["typed_rf"]
    params = _synthetic_rf_params()

    solution = solve_rf(params, t_span=(0.0, 400.0))
    heat_terms = calc_rf_heat_terms(calc_rf_u0(params), params, 0.0)
    energies = qrf_integrate(solution)

    _assert_close(
        solution.drying_time.to("hour").magnitude,
        scenario,
        "drying_time_hr",
    )
    _assert_close(solution.tf[-1].to("degC").magnitude, scenario, "final_tf_c")
    _assert_close(solution.tvw[-1].to("degC").magnitude, scenario, "final_tvw_c")
    _assert_close(solution.mf[-1].to("gram").magnitude, scenario, "final_mf_g")
    _assert_close(heat_terms[3].to("watt").magnitude, scenario, "qrf_f_watt_initial")
    _assert_close(heat_terms[4].to("watt").magnitude, scenario, "qrf_vw_watt_initial")
    _assert_close(energies["QRFf"].to("watt * hour").magnitude, scenario, "QRFf_Wh")
    _assert_close(energies["QRFvw"].to("watt * hour").magnitude, scenario, "QRFvw_Wh")
