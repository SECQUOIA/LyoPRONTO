"""Tests for the typed RF/microwave primary-drying solver."""

from dataclasses import replace
import math

import numpy as np
import pytest

from lyopronto import (
    Q_,
    RFParams,
    RampedVariable,
    RpFormFit,
    calc_rf_heat_terms,
    calc_rf_u0,
    get_rf_tstops,
    physical_properties,
    solve_rf,
    vials,
)


@pytest.fixture
def synthetic_rf_params():
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


def test_rf_heat_terms_return_julia_order_and_units(synthetic_rf_params):
    terms = calc_rf_heat_terms(calc_rf_u0(synthetic_rf_params), synthetic_rf_params, 0.0)

    assert len(terms) == 6
    for term in terms:
        assert term.check("[power]")
        assert math.isfinite(term.to("watt").magnitude)

    q_sub, q_shf, q_vwf, q_rf_f, q_rf_vw, q_shw = terms
    assert math.isfinite(q_sub.to("watt").magnitude)
    assert q_shf.to("watt").magnitude == pytest.approx(0.0)
    assert q_vwf.to("watt").magnitude == pytest.approx(0.0)
    assert q_rf_f.to("watt").magnitude > 0.0
    assert q_rf_vw.to("watt").magnitude > 0.0
    assert q_shw.to("watt").magnitude == pytest.approx(0.0)


def test_solve_rf_synthetic_setup_terminates_by_drying_event(synthetic_rf_params):
    sol = solve_rf(synthetic_rf_params, t_span=(0.0, 400.0))

    assert sol.terminated_by_drying
    assert sol.drying_time.to("hour").magnitude < 400.0
    assert sol.y.shape[0] == 3
    assert np.all(np.isfinite(sol.y))
    assert sol.mf[-1].to("gram").magnitude <= (
        synthetic_rf_params.mf0.to("gram").magnitude * 1e-6
    )
    assert np.nanmin(sol.tf.to("kelvin").magnitude) > 150.0
    assert np.nanmax(sol.tf.to("kelvin").magnitude) < 400.0
    assert np.nanmin(sol.tvw.to("kelvin").magnitude) > 150.0
    assert np.nanmax(sol.tvw.to("kelvin").magnitude) < 400.0


def test_solve_rf_accepts_ramped_power_control(synthetic_rf_params):
    base_power = synthetic_rf_params.P_per_vial(0.0)
    params = replace(
        synthetic_rf_params,
        P_per_vial=RampedVariable.linear(
            [base_power * 0.5, base_power],
            Q_(0.1, "watt / minute"),
        ),
    )

    assert np.any(get_rf_tstops(params) > 0.0)

    sol = solve_rf(params, t_span=(0.0, 400.0), save_at=np.linspace(0.0, 12.0, 7))

    assert sol.terminated_by_drying
    assert sol.t[-1] == pytest.approx(sol.drying_time.to("hour").magnitude)
    assert np.all(np.isfinite(sol.y))
    assert sol.diagnostics[-1].heat_terms_watts.shape == (6,)
