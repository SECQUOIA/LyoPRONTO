"""Tests for the typed RF/microwave primary-drying solver."""

from dataclasses import replace
import math
import numpy as np
import pytest

from lyopronto import (
    BoundedKBBTransform,
    KBBTransform,
    PrimaryDryFit,
    Q_,
    RFDiagnostics,
    RFParams,
    RFSolution,
    RampedVariable,
    RpFormFit,
    calc_rf_heat_terms,
    calc_rf_u0,
    err_rf,
    fit_rf_primary_drying,
    gen_sol_rf,
    get_rf_tstops,
    obj_rf,
    physical_properties,
    qrf_integrate,
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
    terms = calc_rf_heat_terms(
        calc_rf_u0(synthetic_rf_params), synthetic_rf_params, 0.0
    )

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


def test_qrf_integrate_uses_trapezoids_julia_key_order_and_excludes_qshw(
    synthetic_rf_params,
):
    def diagnostics(t_hr, q_sub, q_shf, q_vwf, q_rf_f, q_rf_vw, q_shw):
        return RFDiagnostics(
            t=Q_(t_hr, "hour"),
            m_frozen=Q_(1.0, "gram"),
            h_frozen=Q_(1.0, "centimeter"),
            h_dried=Q_(0.0, "centimeter"),
            tf=Q_(250.0, "kelvin"),
            tvw=Q_(251.0, "kelvin"),
            pch=Q_(100.0, "millitorr"),
            tsh=Q_(260.0, "kelvin"),
            rp=Q_(1.0, "centimeter ** 2 * hour * torr / gram"),
            mflow=Q_(0.0, "gram / hour"),
            dmfdt=Q_(0.0, "gram / hour"),
            q_sub=Q_(q_sub, "watt"),
            q_shf=Q_(q_shf, "watt"),
            q_vwf=Q_(q_vwf, "watt"),
            q_rf_f=Q_(q_rf_f, "watt"),
            q_rf_vw=Q_(q_rf_vw, "watt"),
            q_shw=Q_(q_shw, "watt"),
        )

    solution = RFSolution(
        t=np.array([0.0, 1.0, 3.0]),
        y=np.zeros((3, 3)),
        diagnostics=(
            diagnostics(0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 100.0),
            diagnostics(1.0, 3.0, 4.0, 5.0, 6.0, 7.0, 200.0),
            diagnostics(3.0, 5.0, 6.0, 7.0, 8.0, 9.0, 300.0),
        ),
        params=synthetic_rf_params,
    )

    energies = qrf_integrate(solution)

    assert set(energies) == {"Qsub", "Qshf", "Qvwf", "QRFf", "QRFvw"}
    expected_watt_hours = {
        "Qsub": 10.0,
        "Qshf": 13.0,
        "Qvwf": 16.0,
        "QRFf": 19.0,
        "QRFvw": 22.0,
    }
    for key, expected in expected_watt_hours.items():
        assert energies[key].check("[energy]")
        assert energies[key].to("watt * hour").magnitude == pytest.approx(expected)


def test_rf_length_callable_errors_are_not_masked(synthetic_rf_params):
    def broken_rp(height):
        if hasattr(height, "to"):
            raise ValueError("bug in user callable")
        return Q_(1.4, "centimeter ** 2 * hour * torr / gram")

    params = replace(synthetic_rf_params, Rp=broken_rp)

    with pytest.raises(ValueError, match="bug in user callable"):
        calc_rf_heat_terms(calc_rf_u0(params), params, 0.0)


def test_rf_dielectric_callable_errors_are_not_masked(synthetic_rf_params):
    def broken_epp(temperature, frequency):
        if hasattr(temperature, "to") or hasattr(frequency, "to"):
            raise ValueError("bug in dielectric callable")
        return 0.02

    params = replace(synthetic_rf_params, eppf=broken_epp)

    with pytest.raises(ValueError, match="bug in dielectric callable"):
        calc_rf_heat_terms(calc_rf_u0(params), params, 0.0)


def test_rf_scalar_callable_fallbacks_still_work(synthetic_rf_params):
    def scalar_rp(height_cm):
        if hasattr(height_cm, "to"):
            raise TypeError("float-only resistance")
        return 1.4 + 0.0 * height_cm

    def scalar_epp(temperature_k, frequency_hz):
        if hasattr(temperature_k, "to") or hasattr(frequency_hz, "to"):
            raise TypeError("float-only dielectric loss")
        return 0.02 + 0.0 * temperature_k + 0.0 * frequency_hz

    params = replace(synthetic_rf_params, Rp=scalar_rp, eppf=scalar_epp)

    terms = calc_rf_heat_terms(calc_rf_u0(params), params, 0.0)

    assert len(terms) == 6
    assert np.all(np.isfinite([term.to("watt").magnitude for term in terms]))


def _rf_fit_data(params, save_at=None):
    if save_at is None:
        save_at = np.linspace(0.0, 14.0, 5)
    sol = solve_rf(params, t_span=(0.0, 80.0), save_at=save_at)
    return PrimaryDryFit(sol.t_hours, sol.tf, Tvws=sol.tvw, t_end=sol.drying_time)


def _ratio(value, target):
    return value.to(target.units).magnitude / target.magnitude


def test_kbb_transforms_map_rf_guess_values(synthetic_rf_params):
    transform = KBBTransform(
        synthetic_rf_params.Kvwf * 0.5,
        synthetic_rf_params.Bf * 0.5,
        synthetic_rf_params.Bvw * 0.5,
    )

    updates = transform(np.log([2.0, 2.0, 2.0]))

    assert _ratio(updates["Kvwf"], synthetic_rf_params.Kvwf) == pytest.approx(1.0)
    assert _ratio(updates["Bf"], synthetic_rf_params.Bf) == pytest.approx(1.0)
    assert _ratio(updates["Bvw"], synthetic_rf_params.Bvw) == pytest.approx(1.0)

    bounded = BoundedKBBTransform(synthetic_rf_params)
    bounded_updates = bounded(np.zeros(3))

    assert _ratio(bounded_updates["Kvwf"], synthetic_rf_params.Kvwf) == pytest.approx(
        1.0
    )
    assert _ratio(bounded_updates["Bf"], synthetic_rf_params.Bf) == pytest.approx(1.0)
    assert _ratio(bounded_updates["Bvw"], synthetic_rf_params.Bvw) == pytest.approx(1.0)

    high = bounded(np.full(3, 1000.0))
    assert _ratio(high["Kvwf"], synthetic_rf_params.Kvwf) <= 1e2
    assert _ratio(high["Bf"], synthetic_rf_params.Bf) <= 1e4
    assert _ratio(high["Bvw"], synthetic_rf_params.Bvw) <= 1e4

    with pytest.raises(ValueError, match="Kvwf_scalefac"):
        BoundedKBBTransform(synthetic_rf_params, Kvwf_scalefac=1.0)


def test_rf_solution_objective_and_residuals_use_primary_dry_fit(
    synthetic_rf_params,
):
    fit = _rf_fit_data(synthetic_rf_params)
    transform = KBBTransform(
        synthetic_rf_params.Kvwf * 0.5,
        synthetic_rf_params.Bf * 0.5,
        synthetic_rf_params.Bvw * 0.5,
    )
    exact = np.log([2.0, 2.0, 2.0])

    sol = gen_sol_rf(exact, transform, synthetic_rf_params, fit)
    assert sol.terminated_by_drying
    assert obj_rf(exact, transform, synthetic_rf_params, fit) == pytest.approx(
        0.0, abs=1e-10
    )
    assert np.isnan(
        obj_rf(
            exact,
            transform,
            synthetic_rf_params,
            fit,
            badprms=lambda _params: True,
        )
    )

    residuals = err_rf(np.zeros(3), transform, synthetic_rf_params, fit)
    n_tf = int(sum(fit.Tf_iend))
    n_tvw = int(sum(fit.Tvw_iend))
    assert np.any(np.abs(residuals[:n_tf]) > 0.0)
    assert np.any(np.abs(residuals[n_tf : n_tf + n_tvw]) > 0.0)


def test_fit_rf_primary_drying_least_squares_recovers_kbb(synthetic_rf_params):
    fit = _rf_fit_data(synthetic_rf_params)
    transform = KBBTransform(
        synthetic_rf_params.Kvwf * 0.5,
        synthetic_rf_params.Bf * 0.5,
        synthetic_rf_params.Bvw * 0.5,
    )

    result = fit_rf_primary_drying(
        synthetic_rf_params,
        fit,
        transform,
        max_nfev=16,
        xtol=1e-7,
        ftol=1e-7,
        gtol=1e-7,
    )

    fitted = result.fitted_params
    assert result.success
    assert result.objective == pytest.approx(0.0, abs=1e-8)
    assert _ratio(fitted.Kvwf, synthetic_rf_params.Kvwf) == pytest.approx(1.0, rel=0.3)
    assert _ratio(fitted.Bf, synthetic_rf_params.Bf) == pytest.approx(1.0, rel=0.5)
    assert _ratio(fitted.Bvw, synthetic_rf_params.Bvw) == pytest.approx(1.0, rel=0.3)


def test_fit_rf_primary_drying_minimize_recovers_kbb(synthetic_rf_params):
    fit = _rf_fit_data(synthetic_rf_params, save_at=np.array([0.0, 14.0]))
    transform = KBBTransform(
        synthetic_rf_params.Kvwf * 0.5,
        synthetic_rf_params.Bf * 0.5,
        synthetic_rf_params.Bvw * 0.5,
    )
    rough_objective = obj_rf(np.zeros(3), transform, synthetic_rf_params, fit)

    result = fit_rf_primary_drying(
        synthetic_rf_params,
        fit,
        transform,
        theta0=np.log([2.0, 2.0, 2.0]) + np.array([0.02, -0.01, 0.015]),
        method="minimize",
        optimizer_method="Nelder-Mead",
        options={"maxiter": 20, "xatol": 5e-2, "fatol": 2e-2},
    )

    fitted = result.fitted_params
    assert result.success
    assert result.fit_method == "minimize"
    assert result.nfev > transform.dimension
    assert result.objective < rough_objective
    assert _ratio(fitted.Kvwf, synthetic_rf_params.Kvwf) == pytest.approx(1.0, rel=0.3)
    assert _ratio(fitted.Bf, synthetic_rf_params.Bf) == pytest.approx(1.0, rel=0.5)
    assert _ratio(fitted.Bvw, synthetic_rf_params.Bvw) == pytest.approx(1.0, rel=0.3)
