"""Runnable examples for the typed, Pint-aware Julia-parity APIs.

These examples exercise the typed API added in the Julia-parity series
(issues #37-#47). They are intentionally small and self-contained so they can
run as plain Python under pytest (see ``tests/test_typed_examples.py``) without
Jupyter or papermill.

The legacy dict-based calculators (``lyopronto.calc_knownRp``,
``lyopronto.calc_unknownRp``, ``lyopronto.design_space``, the optimizers, and
the web-style I/O) remain fully supported and keep their float/unit
conventions. The typed API documented here is additive: it uses Pint
quantities where units matter and also accepts plain floats in the canonical
units described in ``docs/TYPED_API_GUIDE.md``.

Run directly to print a short summary of every example::

    python -m examples.typed_api_examples
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from lyopronto import (
    BoundedKBBTransform,
    KBBTransform,
    KRpTransform,
    PikalParams,
    PrimaryDryFit,
    Q_,
    RampedVariable,
    RFParams,
    RpFormFit,
    calc_hRp_T,
    eccurt,
    fit_primary_drying,
    fit_rf_primary_drying,
    identify_pd_end,
    physical_properties,
    qrf_integrate,
    solve_pikal,
    solve_rf,
    vials,
)
from lyopronto.typed import ConstPhysProp


def _conventional_params() -> PikalParams:
    """Build a typed conventional Pikal parameter set for a 6R vial."""

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


def _rf_params() -> RFParams:
    """Build a typed RF/microwave parameter set for a 6R vial."""

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
                    Q_(8.93e-4, "calorie / second / kelvin / centimeter ** 2 / torr"),
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


def run_typed_conventional_simulation() -> dict[str, Any]:
    """Solve a conventional primary-drying cycle with the typed Pikal solver."""

    params = _conventional_params()
    sol = solve_pikal(params, t_span=(0.0, 40.0))
    return {
        "drying_time_hr": float(sol.drying_time.to("hour").magnitude),
        "final_tf_K": float(sol.tf[-1].to("kelvin").magnitude),
        "n_points": int(sol.t.size),
    }


def run_conventional_kv_rp_fitting() -> dict[str, Any]:
    """Recover Kv and Rp from synthetic product-temperature data."""

    params = _conventional_params()
    sol = solve_pikal(params)
    fit = PrimaryDryFit(sol.t_hours, sol.tf, t_end=sol.drying_time)
    transform = KRpTransform(
        params.Kshf.value * 0.75,
        params.Rp.R0 * 0.5,
        params.Rp.A1 * 2.0,
        params.Rp.A2 * 0.5,
    )
    result = fit_primary_drying(
        params, fit, transform, max_nfev=80, xtol=1e-8, ftol=1e-8, gtol=1e-8
    )
    fitted = result.fitted_params
    return {
        "success": bool(result.success),
        "objective": float(result.objective),
        "kv_ratio": fitted.Kshf(0).to(params.Kshf.value.units).magnitude
        / params.Kshf.value.magnitude,
        "r0_ratio": fitted.Rp.R0.to(params.Rp.R0.units).magnitude
        / params.Rp.R0.magnitude,
    }


def run_direct_rp_estimation() -> dict[str, Any]:
    """Estimate Rp(h_d) directly from a measured product-temperature series."""

    params = _conventional_params()
    times = np.linspace(0.0, 8.0, 25)
    sol = solve_pikal(params, t_span=(0.0, 8.0), save_at=times)
    fit = PrimaryDryFit(sol.t_hours, sol.tf)
    h_dried, rp = calc_hRp_T(params, fit)
    return {
        "n_points": int(h_dried.to("centimeter").magnitude.size),
        "max_h_dried_cm": float(np.max(h_dried.to("centimeter").magnitude)),
        "rp_units_ok": bool(rp.check("[length] ** 2 * [time] * [pressure] / [mass]")),
    }


def run_rf_simulation() -> dict[str, Any]:
    """Solve an RF/microwave primary-drying cycle with the typed RF solver."""

    params = _rf_params()
    sol = solve_rf(params, t_span=(0.0, 400.0))
    return {
        "terminated_by_drying": bool(sol.terminated_by_drying),
        "drying_time_hr": float(sol.drying_time.to("hour").magnitude),
        "final_tf_K": float(sol.tf[-1].to("kelvin").magnitude),
    }


def run_rf_energy_accounting() -> dict[str, Any]:
    """Integrate RF heat-transfer modes over a solved RF trajectory."""

    params = _rf_params()
    sol = solve_rf(params, t_span=(0.0, 400.0))
    energies = qrf_integrate(sol)
    return {key: float(value.to("joule").magnitude) for key, value in energies.items()}


def run_rf_fitting() -> dict[str, Any]:
    """Recover RF Kvwf/Bf/Bvw from synthetic RF data with a KBB transform."""

    params = _rf_params()
    sol = solve_rf(params, t_span=(0.0, 80.0), save_at=np.linspace(0.0, 14.0, 5))
    fit = PrimaryDryFit(sol.t_hours, sol.tf, Tvws=sol.tvw, t_end=sol.drying_time)
    transform = KBBTransform(params.Kvwf * 0.5, params.Bf * 0.5, params.Bvw * 0.5)
    result = fit_rf_primary_drying(
        params, fit, transform, max_nfev=24, xtol=1e-7, ftol=1e-7, gtol=1e-7
    )
    fitted = result.fitted_params
    return {
        "success": bool(result.success),
        "objective": float(result.objective),
        "kvwf_ratio": fitted.Kvwf.to(params.Kvwf.units).magnitude
        / params.Kvwf.magnitude,
    }


def run_bounded_rf_transform() -> dict[str, Any]:
    """Show the bounded logistic KBB transform mapping zero theta to guesses."""

    params = _rf_params()
    transform = BoundedKBBTransform(params)
    updates = transform(np.zeros(3))
    return {
        "kvwf_ratio": updates["Kvwf"].to(params.Kvwf.units).magnitude
        / params.Kvwf.magnitude,
    }


def run_vial_utilities() -> dict[str, Any]:
    """Use the SCHOTT vial metadata utilities."""

    rad_i, rad_o = vials.get_vial_radii("6R")
    mass = vials.get_vial_mass("6R")
    shape = vials.get_vial_shape("6R")
    return {
        "inner_radius_cm": float(rad_i.to("centimeter").magnitude),
        "outer_radius_cm": float(rad_o.to("centimeter").magnitude),
        "mass_g": float(mass.to("gram").magnitude),
        "shape_type": type(shape).__name__,
    }


def run_eccurt_equipment_capability() -> dict[str, Any]:
    """Evaluate ECCURT equipment-capability pressures and lines."""

    pressures = eccurt.eq_cap_pressure(
        np.array([0.1, 0.3, 0.5, 0.8]), 120.0, 50.0, 300.0, 0.092
    )
    line = eccurt.eq_cap_line_new(120.0, 50.0, 300.0, 0.092)
    return {
        "pressures_mtorr": [float(value) for value in np.asarray(pressures)],
        "line_slope": float(line.k),
        "line_intercept": float(line.b),
    }


def run_primary_drying_end_detection() -> dict[str, Any]:
    """Detect the end of primary drying from a synthetic Pirani trace."""

    t = np.linspace(0.0, 100.0, 101)
    pch_pir = 20.0 - 20.0 * np.tanh((t - 60.0) / 5.0)
    t_end = identify_pd_end(Q_(t, "hour"), Q_(pch_pir, "pascal"), "der2")
    onset, offset = identify_pd_end(Q_(t, "hour"), Q_(pch_pir, "pascal"), "onoff")
    return {
        "der2_end_hr": float(t_end.to("hour").magnitude),
        "onset_hr": float(onset.to("hour").magnitude),
        "offset_hr": float(offset.to("hour").magnitude),
    }


EXAMPLES = (
    run_typed_conventional_simulation,
    run_conventional_kv_rp_fitting,
    run_direct_rp_estimation,
    run_rf_simulation,
    run_rf_energy_accounting,
    run_rf_fitting,
    run_bounded_rf_transform,
    run_vial_utilities,
    run_eccurt_equipment_capability,
    run_primary_drying_end_detection,
)


def main() -> None:
    for example in EXAMPLES:
        print(f"{example.__name__}: {example()}")


if __name__ == "__main__":
    main()
