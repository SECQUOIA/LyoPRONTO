"""Tests for the typed conventional Pikal primary-drying solver."""

from dataclasses import replace
import math

import numpy as np
import pytest

from lyopronto import (
    PikalParams,
    PrimaryDryFit,
    Q_,
    RampedVariable,
    RpFormFit,
    calc_knownRp,
    calc_md_q,
    constant,
    err_expT,
    get_pikal_t0,
    get_pikal_tstops,
    num_errs,
    obj_expT,
    physical_properties,
    solve_pikal,
    vials,
)


@pytest.fixture
def sucrose_pikal_params():
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


def test_solve_pikal_matches_julia_sucrose_benchmark(sucrose_pikal_params):
    sol = solve_pikal(sucrose_pikal_params)

    assert sol.drying_time.to("hour").magnitude == pytest.approx(45.8, rel=0.1)
    assert sol.tf[-1].to("degC").magnitude == pytest.approx(-32.1975, abs=0.1)
    assert sol.hf[-1].to("centimeter").magnitude == pytest.approx(0.0, abs=1e-8)

    legacy = sol.to_legacy_table()
    assert legacy.shape[1] == 7
    assert legacy[-1, 6] == pytest.approx(100.0, abs=1e-6)


def test_calc_md_q_exposes_reusable_heat_and_mass_diagnostics(sucrose_pikal_params):
    sol = solve_pikal(sucrose_pikal_params, save_at=[1.0])
    diag = calc_md_q(
        [sol.hf[0], sol.tf[0]],
        sucrose_pikal_params,
        sol.t[0],
    )

    assert diag.t_sub.check("[temperature]")
    assert diag.delta_p.to("pascal").magnitude > 0.0
    assert diag.dmdt.to("kilogram / second").magnitude < 0.0

    energy_residual = (diag.q_shf + diag.dmdt * physical_properties.delta_h_sub).to(
        "watt"
    )
    assert energy_residual.magnitude == pytest.approx(0.0, abs=1e-8)


def test_solve_pikal_returns_requested_save_times_when_feasible(sucrose_pikal_params):
    sol = solve_pikal(sucrose_pikal_params, save_at=Q_([1.0, 5.0, 10.0], "hour"))

    np.testing.assert_allclose(sol.t[:3], [1.0, 5.0, 10.0])
    assert sol.t[-1] == pytest.approx(sol.drying_time.to("hour").magnitude)
    assert sol.t[-1] > 10.0


def test_pikal_solution_works_with_primary_dry_fit_helpers(sucrose_pikal_params):
    sol = solve_pikal(sucrose_pikal_params, save_at=Q_([1.0, 5.0, 10.0], "hour"))
    fit = PrimaryDryFit(sol.t_hours, sol.tf, t_end=sol.drying_time)

    assert num_errs(fit) == len(sol.t) + 1
    np.testing.assert_allclose(err_expT(sol, fit), np.zeros(num_errs(fit)), atol=1e-9)
    assert obj_expT(sol, fit) == pytest.approx(0.0, abs=1e-18)

    incomplete = solve_pikal(
        sucrose_pikal_params,
        t_span=(0.0, 2.0),
        save_at=[1.0, 2.0],
    )
    assert np.all(np.isnan(err_expT(incomplete, fit)))
    assert np.isnan(obj_expT(incomplete, fit))


def test_sparse_save_at_does_not_change_multisegment_ramp_state(sucrose_pikal_params):
    params = replace(
        sucrose_pikal_params,
        Tsh=RampedVariable.multi(
            [
                Q_(273.15 - 45.0, "kelvin"),
                Q_(273.15 - 35.0, "kelvin"),
                Q_(273.15 - 25.0, "kelvin"),
            ],
            [Q_(1.0, "kelvin / minute"), Q_(1.0, "kelvin / minute")],
            [Q_(1.0, "hour")],
        ),
    )

    late_only = solve_pikal(params, t_span=(0.0, 5.0), save_at=[2.0])
    with_early = solve_pikal(params, t_span=(0.0, 5.0), save_at=[0.5, 2.0])

    np.testing.assert_allclose(with_early.t, [0.5, 2.0])
    assert late_only.y[0, -1] == pytest.approx(with_early.y[0, -1], abs=1e-8)


def test_pikal_tstops_and_delayed_start_match_ramped_controls(sucrose_pikal_params):
    tstops = get_pikal_tstops(sucrose_pikal_params)
    t0 = get_pikal_t0(sucrose_pikal_params)

    assert 0.0 in tstops
    assert np.any(np.isclose(tstops, 20.0 / 60.0))
    assert 0.0 < t0 < 20.0 / 60.0


def test_solve_pikal_accepts_ramped_pressure_controls(sucrose_pikal_params):
    params = replace(
        sucrose_pikal_params,
        pch=RampedVariable.linear(
            [Q_(70.0, "millitorr"), Q_(90.0, "millitorr")],
            Q_(10.0, "millitorr / minute"),
        ),
    )

    sol = solve_pikal(params, t_span=(0.0, 2.0), save_at=[1.0, 2.0])
    legacy = sol.to_legacy_table()

    np.testing.assert_allclose(sol.t, [1.0, 2.0])
    assert legacy[0, 4] == pytest.approx(90.0)
    assert legacy[1, 4] == pytest.approx(90.0)
    assert legacy[1, 6] > legacy[0, 6]


def test_legacy_knownrp_output_table_contract_is_unchanged(standard_setup):
    knownRp_standard_setup = (
        standard_setup["vial"],
        standard_setup["product"],
        standard_setup["ht"],
        standard_setup["Pchamber"],
        standard_setup["Tshelf"],
        standard_setup["dt"],
    )
    output = calc_knownRp.dry(*knownRp_standard_setup)

    assert output.shape[1] == 7
    assert output[0, 4] == pytest.approx(
        knownRp_standard_setup[3]["setpt"][0] * constant.Torr_to_mTorr
    )
