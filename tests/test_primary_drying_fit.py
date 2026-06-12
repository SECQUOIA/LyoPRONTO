"""Tests for typed conventional primary-drying parameter fitting."""

from dataclasses import replace
import math
from types import SimpleNamespace

import numpy as np
import pytest

import lyopronto.fitting as fitting_module
from lyopronto import (
    KRpTransform,
    KTransform,
    PikalParams,
    PrimaryDryFit,
    Q_,
    RpFormFit,
    RpTransform,
    RampedVariable,
    SharedSeparateTransform,
    fit_primary_drying,
    gen_nsol_pd,
    gen_sol_pd,
    obj_pd,
    objn_pd,
    solve_pikal,
    vials,
)
from lyopronto.typed import ConstPhysProp


@pytest.fixture(scope="module")
def primary_drying_fit_case():
    rad_i, rad_o = vials.get_vial_radii("6R")
    ap = math.pi * rad_i**2
    av = math.pi * rad_o**2

    values = {
        "R0": Q_(0.8, "centimeter ** 2 * torr * hour / gram"),
        "A1": Q_(14.0, "centimeter * torr * hour / gram"),
        "A2": Q_(1.0, "1 / centimeter"),
        "K": Q_(2.75e-4, "calorie / second / kelvin / centimeter ** 2"),
    }
    params = PikalParams(
        Rp=RpFormFit(values["R0"], values["A1"], values["A2"]),
        hf0=Q_(3.0, "milliliter") / ap,
        csolid=Q_(0.06, "gram / milliliter"),
        rho_solution=Q_(1.0, "gram / milliliter"),
        Kshf=ConstPhysProp(values["K"]),
        Av=av,
        Ap=ap,
        pch=RampedVariable.constant(Q_(70.0, "millitorr")),
        Tsh=RampedVariable.linear(
            [Q_(273.15 - 15.0, "kelvin"), Q_(273.15 + 10.0, "kelvin")],
            Q_(0.5, "kelvin / minute"),
        ),
    )
    sol = solve_pikal(params)
    fit = PrimaryDryFit(sol.t_hours, sol.tf, t_end=sol.drying_time)
    return params, fit, values


def _krp_transform(values):
    return KRpTransform(
        values["K"] * 0.75,
        values["R0"] * 0.5,
        values["A1"] * 2.0,
        values["A2"] * 0.5,
    )


def _rp_transform(values):
    return RpTransform(values["R0"] * 0.5, values["A1"] * 2.0, values["A2"] * 0.5)


def _ratio(value, target, unit):
    return value.to(unit).magnitude / target.to(unit).magnitude


def _log_ratio(target, guess, unit):
    return math.log(target.to(unit).magnitude / guess.to(unit).magnitude)


def test_gen_sol_pd_uses_log_space_transforms_and_bad_parameter_gate(
    primary_drying_fit_case,
):
    params, fit, values = primary_drying_fit_case
    transform = _krp_transform(values)
    exact = np.log([1 / 0.75, 2.0, 0.5, 2.0])

    sol = gen_sol_pd(exact, transform, params, fit)

    assert obj_pd(exact, transform, params, fit) == pytest.approx(0.0, abs=1e-18)
    assert sol.params.Kshf(0).to(values["K"].units).magnitude == pytest.approx(
        values["K"].magnitude
    )
    assert np.isnan(
        obj_pd(
            np.zeros(_rp_transform(values).dimension),
            _rp_transform(values),
            params,
            fit,
            badprms=lambda _params: True,
        )
    )


def test_fitting_generators_return_nan_for_transform_overflow(
    primary_drying_fit_case,
):
    params, fit, values = primary_drying_fit_case
    rp_transform = _rp_transform(values)

    assert np.isnan(gen_sol_pd([1000.0, 0.0, 0.0], rp_transform, params, fit))

    transform = SharedSeparateTransform(
        shared=KTransform(values["K"]),
        separate=rp_transform,
        n_separate=1,
    )
    sols = gen_nsol_pd(np.full(transform.dimension, 1000.0), transform, [params], [fit])

    assert len(sols) == 1
    assert np.isnan(sols[0])


@pytest.mark.slow
def test_fit_primary_drying_recovers_k_and_rp(primary_drying_fit_case):
    params, fit, values = primary_drying_fit_case
    transform = _krp_transform(values)

    result = fit_primary_drying(
        params,
        fit,
        transform,
        max_nfev=80,
        xtol=1e-8,
        ftol=1e-8,
        gtol=1e-8,
    )

    fitted = result.fitted_params
    assert result.success
    assert result.objective == pytest.approx(0.0, abs=1e-10)
    assert _ratio(fitted.Kshf(0), values["K"], values["K"].units) == pytest.approx(
        1.0, rel=0.1
    )
    assert _ratio(fitted.Rp.R0, values["R0"], values["R0"].units) == pytest.approx(
        1.0, rel=0.1
    )
    assert _ratio(fitted.Rp.A1, values["A1"], values["A1"].units) == pytest.approx(
        1.0, rel=0.1
    )
    assert _ratio(fitted.Rp.A2, values["A2"], values["A2"].units) == pytest.approx(
        1.0, rel=0.3
    )


@pytest.mark.slow
def test_fit_primary_drying_minimize_recovers_heat_transfer(
    primary_drying_fit_case,
):
    params, fit, values = primary_drying_fit_case
    transform = KTransform(values["K"] * 0.8)

    result = fit_primary_drying(
        params,
        fit,
        transform,
        method="minimize",
        optimizer_method="Nelder-Mead",
        options={"maxiter": 80, "xatol": 1e-5, "fatol": 1e-10},
    )

    fitted = result.fitted_params
    assert result.success
    assert result.fit_method == "minimize"
    assert result.objective == pytest.approx(0.0, abs=1e-6)
    assert _ratio(fitted.Kshf(0), values["K"], values["K"].units) == pytest.approx(
        1.0, rel=0.05
    )


def test_fit_primary_drying_forwards_least_squares_optimizer_method(
    monkeypatch,
    primary_drying_fit_case,
):
    params, fit, values = primary_drying_fit_case
    captured = {}

    def fake_least_squares(fun, x0, **kwargs):
        captured["method"] = kwargs.get("method")
        residuals = fun(x0)
        assert np.all(np.isfinite(residuals))
        return SimpleNamespace(x=np.asarray(x0, dtype=float), success=True)

    monkeypatch.setattr(fitting_module, "least_squares", fake_least_squares)

    result = fit_primary_drying(
        params,
        fit,
        KTransform(values["K"]),
        optimizer_method="lm",
    )

    assert captured["method"] == "lm"
    assert result.fit_method == "least_squares"


@pytest.mark.slow
def test_rp_only_fit_recovers_product_resistance(primary_drying_fit_case):
    params, fit, values = primary_drying_fit_case
    transform = _rp_transform(values)

    result = fit_primary_drying(
        params,
        fit,
        transform,
        max_nfev=60,
        xtol=1e-8,
        ftol=1e-8,
        gtol=1e-8,
    )

    fitted = result.fitted_params
    assert result.success
    assert _ratio(fitted.Rp.R0, values["R0"], values["R0"].units) == pytest.approx(
        1.0, rel=0.1
    )
    assert _ratio(fitted.Rp.A1, values["A1"], values["A1"].units) == pytest.approx(
        1.0, rel=0.2
    )
    assert _ratio(fitted.Rp.A2, values["A2"], values["A2"].units) == pytest.approx(
        1.0, rel=0.5
    )


@pytest.mark.slow
def test_shared_k_and_separate_rp_multi_experiment_objective(
    primary_drying_fit_case,
):
    params, _fit, values = primary_drying_fit_case
    r0_unit = values["R0"].units
    a1_unit = values["A1"].units
    a2_unit = values["A2"].units
    params2 = replace(
        params,
        Rp=RpFormFit(
            Q_(2.0, r0_unit),
            Q_(5.0, a1_unit),
            Q_(1.5, a2_unit),
        ),
    )
    params3 = replace(
        params,
        Rp=RpFormFit(
            Q_(0.5, r0_unit),
            Q_(20.0, a1_unit),
            Q_(0.0, a2_unit),
        ),
    )
    param_sets = [params, params2, params3]
    fits = []
    for param in param_sets:
        sol = solve_pikal(param)
        fits.append(PrimaryDryFit(sol.t_hours, sol.tf, t_end=sol.drying_time))

    transform = SharedSeparateTransform(
        shared=KTransform(values["K"] * 0.75),
        separate=RpTransform(
            values["R0"] * 0.75, values["A1"] * 2.0, values["A2"] * 0.5
        ),
        n_separate=3,
    )
    exact = np.asarray(
        [
            math.log(1 / 0.75),
            math.log(1 / 0.75),
            math.log(0.5),
            math.log(2.0),
            _log_ratio(params2.Rp.R0, values["R0"] * 0.75, r0_unit),
            _log_ratio(params2.Rp.A1, values["A1"] * 2.0, a1_unit),
            _log_ratio(params2.Rp.A2, values["A2"] * 0.5, a2_unit),
            _log_ratio(params3.Rp.R0, values["R0"] * 0.75, r0_unit),
            _log_ratio(params3.Rp.A1, values["A1"] * 2.0, a1_unit),
            math.log(1e-20),
        ],
        dtype=float,
    )

    sols = gen_nsol_pd(exact, transform, param_sets, fits)

    assert objn_pd(exact, transform, param_sets, fits) == pytest.approx(0.0, abs=1e-4)
    for sol, param in zip(sols, param_sets):
        assert sol.params.Kshf(0).to(values["K"].units).magnitude == pytest.approx(
            values["K"].magnitude
        )
        assert sol.params.Rp.R0.to(r0_unit).magnitude == pytest.approx(
            param.Rp.R0.to(r0_unit).magnitude
        )
        assert sol.params.Rp.A1.to(a1_unit).magnitude == pytest.approx(
            param.Rp.A1.to(a1_unit).magnitude
        )
        assert sol.params.Rp.A2.to(a2_unit).magnitude == pytest.approx(
            param.Rp.A2.to(a2_unit).magnitude, abs=1e-12
        )
    assert np.isnan(
        objn_pd(
            np.zeros(transform.dimension),
            transform,
            param_sets,
            fits,
            badprms=lambda _params: True,
        )
    )
