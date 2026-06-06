"""Tests for direct product-resistance estimation from temperature series."""

from dataclasses import replace
import math

import numpy as np
import pytest

from lyopronto import (
    PikalParams,
    PrimaryDryFit,
    Q_,
    RampedVariable,
    RpEstimator,
    RpFormFit,
    calc_unknownRp,
    calc_hRp_T,
    legacy_unknown_rp_to_hRp,
    solve_pikal,
    vials,
)
from lyopronto.typed import ConstPhysProp


@pytest.fixture
def direct_rp_params():
    rad_i, rad_o = vials.get_vial_radii("6R")
    ap = math.pi * rad_i**2
    av = math.pi * rad_o**2

    return PikalParams(
        Rp=RpFormFit(
            Q_(0.8, "centimeter ** 2 * torr * hour / gram"),
            Q_(14.0, "centimeter * torr * hour / gram"),
            Q_(1.0, "1 / centimeter"),
        ),
        hf0=Q_(3.0, "milliliter") / ap,
        csolid=Q_(0.06, "gram / milliliter"),
        rho_solution=Q_(1.0, "gram / milliliter"),
        Kshf=ConstPhysProp(Q_(2.75e-4, "calorie / second / kelvin / centimeter ** 2")),
        Av=av,
        Ap=ap,
        pch=RampedVariable.constant(Q_(70.0, "millitorr")),
        Tsh=RampedVariable.linear(
            [Q_(273.15 - 15.0, "kelvin"), Q_(273.15 + 10.0, "kelvin")],
            Q_(0.5, "kelvin / minute"),
        ),
    )


def test_calc_hRp_T_recovers_known_typed_resistance_curve(direct_rp_params):
    times = np.linspace(0.0, 8.0, 25)
    sol = solve_pikal(direct_rp_params, t_span=(0.0, 8.0), save_at=times)
    fit = PrimaryDryFit(sol.t_hours, sol.tf)

    h_dried, rp = calc_hRp_T(direct_rp_params, fit)

    expected_h_dried = np.array(
        [diag.h_dried.to("centimeter").magnitude for diag in sol.diagnostics]
    )
    expected_rp = np.array(
        [
            diag.rp.to("centimeter ** 2 * hour * torr / gram").magnitude
            for diag in sol.diagnostics
        ]
    )

    assert h_dried.check("[length]")
    assert rp.check("[length] ** 2 * [time] * [pressure] / [mass]")
    np.testing.assert_allclose(
        h_dried.to("centimeter").magnitude,
        expected_h_dried,
        rtol=0.0,
        atol=2e-3,
    )
    np.testing.assert_allclose(
        rp.to("centimeter ** 2 * hour * torr / gram").magnitude,
        expected_rp,
        rtol=2e-3,
        atol=0.0,
    )


def test_calc_hRp_T_selects_one_temperature_series_and_warns_for_default(
    direct_rp_params,
):
    times = np.linspace(0.0, 6.0, 19)
    base = solve_pikal(direct_rp_params, t_span=(0.0, 6.0), save_at=times)
    warmer_params = replace(
        direct_rp_params,
        Rp=RpFormFit(
            Q_(0.5, "centimeter ** 2 * torr * hour / gram"),
            Q_(8.0, "centimeter * torr * hour / gram"),
            Q_(0.5, "1 / centimeter"),
        ),
    )
    warmer = solve_pikal(warmer_params, t_span=(0.0, 6.0), save_at=times)
    fit = PrimaryDryFit(base.t_hours, (base.tf, warmer.tf))

    assert RpEstimator(direct_rp_params, fit).is_plural
    with pytest.warns(UserWarning, match="defaulting to i=0"):
        default_h, default_rp = calc_hRp_T(direct_rp_params, fit)
    selected_h, selected_rp = calc_hRp_T(direct_rp_params, fit, i=0)
    second_h, second_rp = calc_hRp_T(direct_rp_params, fit, i=1)

    np.testing.assert_allclose(default_h.magnitude, selected_h.magnitude)
    np.testing.assert_allclose(default_rp.magnitude, selected_rp.magnitude)
    assert not np.allclose(selected_h.magnitude, second_h.magnitude)
    assert not np.allclose(selected_rp.magnitude, second_rp.magnitude)


def test_calc_hRp_T_skips_invalid_initial_transfer_period(direct_rp_params):
    fit = PrimaryDryFit(
        Q_(np.arange(6.0), "hour"),
        Q_([-10.0, -8.0, -25.0, -24.0, -23.0, -22.0], "degC"),
    )

    h_dried, rp = calc_hRp_T(direct_rp_params, fit)

    assert len(h_dried.magnitude) < 6
    assert np.all(rp.to("centimeter ** 2 * hour * torr / gram").magnitude >= 0.0)


def test_calc_hRp_T_truncates_temperature_series_after_drying_completion(
    direct_rp_params,
):
    fast_params = replace(
        direct_rp_params,
        Rp=RpFormFit(
            Q_(0.05, "centimeter ** 2 * torr * hour / gram"),
            Q_(0.1, "centimeter * torr * hour / gram"),
            Q_(0.0, "1 / centimeter"),
        ),
        hf0=Q_(0.3, "milliliter") / direct_rp_params.Ap,
    )
    times = np.linspace(0.0, 24.0, 49)
    sol = solve_pikal(fast_params, t_span=(0.0, 24.0), save_at=times)
    sol_tf_K = sol.tf.to("kelvin").magnitude
    fit_times = np.concatenate([sol.t, sol.t[-1] + np.array([0.5, 1.0, 1.5])])
    fit_tf_K = np.concatenate([sol_tf_K, np.repeat(sol_tf_K[-1], 3)])
    fit = PrimaryDryFit(Q_(fit_times, "hour"), Q_(fit_tf_K, "kelvin"))

    h_dried, rp = calc_hRp_T(fast_params, fit)

    assert len(h_dried.magnitude) < len(fit_times)
    assert (
        np.max(h_dried.to("centimeter").magnitude)
        <= fast_params.hf0.to("centimeter").magnitude + 1e-9
    )
    assert np.all(rp.to("centimeter ** 2 * hour * torr / gram").magnitude >= 0.0)


def test_legacy_unknown_rp_adapter_returns_typed_height_and_resistance():
    product_res = np.array(
        [
            [0.0, 0.0, 1.2],
            [1.0, 0.1, 2.5],
        ]
    )

    h_dried, rp = legacy_unknown_rp_to_hRp(product_res)

    assert h_dried.check("[length]")
    assert rp.check("[length] ** 2 * [time] * [pressure] / [mass]")
    np.testing.assert_allclose(h_dried.to("centimeter").magnitude, product_res[:, 1])
    np.testing.assert_allclose(
        rp.to("centimeter ** 2 * hour * torr / gram").magnitude,
        product_res[:, 2],
    )


def test_legacy_unknown_rp_adapter_accepts_real_unknown_rp_output(
    standard_vial,
    standard_ht,
    standard_pchamber,
    standard_tshelf,
):
    product = {"cSolid": 0.05, "T_pr_crit": -25.0}
    time = np.array([0.0, 1.0, 2.0, 3.0])
    tbot_exp = np.array([-40.0, -38.0, -32.0, -25.0])
    _output, product_res = calc_unknownRp.dry(
        standard_vial,
        product,
        standard_ht,
        standard_pchamber,
        standard_tshelf,
        time,
        tbot_exp,
    )

    h_dried, rp = legacy_unknown_rp_to_hRp(product_res)

    np.testing.assert_allclose(h_dried.to("centimeter").magnitude, product_res[:, 1])
    np.testing.assert_allclose(
        rp.to("centimeter ** 2 * hour * torr / gram").magnitude,
        product_res[:, 2],
    )
