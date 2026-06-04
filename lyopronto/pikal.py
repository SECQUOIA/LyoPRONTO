"""Typed conventional Pikal primary-drying solver.

This module mirrors the Julia ``ParamObjPikal`` model while keeping the
legacy ``calc_knownRp.dry`` path unchanged. Plain floats are interpreted in
the canonical units used by the Julia-facing model: centimeters, hours,
kelvin, torr, grams per milliliter, and ``cal/s/K/cm^2``.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
import math
from typing import Any
import warnings

import numpy as np
from scipy.integrate import solve_ivp
from scipy.optimize import brentq

from . import physical_properties
from .typed import Q_, RampedVariable, as_quantity, is_quantity, to_magnitude

_RP_UNIT = "centimeter ** 2 * hour * torr / gram"
_KSHF_UNIT = "calorie / second / kelvin / centimeter ** 2"
_AREA_UNIT = "centimeter ** 2"
_HEIGHT_UNIT = "centimeter"
_PRESSURE_UNIT = "torr"
_TEMPERATURE_UNIT = "kelvin"
_CONCENTRATION_UNIT = "gram / milliliter"


@dataclass(frozen=True)
class PikalParams:
    """Parameter container for the conventional Pikal primary-drying model."""

    Rp: Any
    hf0: Any
    csolid: Any
    rho_solution: Any
    Kshf: Any
    Av: Any
    Ap: Any
    pch: Any
    Tsh: Any

    @classmethod
    def from_nested_tuple(cls, values: tuple[Any, Any, Any]) -> "PikalParams":
        """Build params from Julia's legacy tuple-of-tuples layout."""

        return cls(*values[0], *values[1], *values[2])


@dataclass(frozen=True)
class PikalDiagnostics:
    """Mass and heat-balance diagnostics at one solver state."""

    t: Any
    h_frozen: Any
    h_dried: Any
    tf: Any
    t_sub: Any
    pch: Any
    tsh: Any
    delta_p: Any
    rp: Any
    q_shf: Any
    dmdt: Any


@dataclass(frozen=True)
class PikalSolution:
    """Typed Pikal solution returned by :func:`solve_pikal`."""

    t: np.ndarray
    y: np.ndarray
    diagnostics: tuple[PikalDiagnostics, ...]
    params: PikalParams
    raw_segments: tuple[Any, ...] = ()

    @property
    def t_hours(self) -> Any:
        """Solution times as Pint hours."""

        return Q_(self.t, "hour")

    @property
    def hf(self) -> Any:
        """Frozen product height as Pint centimeters."""

        return Q_(self.y[0], _HEIGHT_UNIT)

    @property
    def tf(self) -> Any:
        """Product temperature state as Pint kelvin."""

        return Q_(self.y[1], _TEMPERATURE_UNIT)

    @property
    def drying_time(self) -> Any:
        """Final solution time as a Pint hour quantity."""

        return Q_(float(self.t[-1]), "hour")

    def to_legacy_table(self) -> np.ndarray:
        """Return the existing seven-column primary-drying output table."""

        return pikal_solution_to_legacy_table(self)


def _q(value: Any, unit: str) -> Any:
    return as_quantity(value, unit)


def _call_with_fallback(
    func: Any,
    quantity_arg: Any,
    magnitude_arg: float,
    output_unit: str,
) -> Any:
    try:
        value = func(quantity_arg)
    except Exception:
        value = func(magnitude_arg)
    return _q(value, output_unit)


def _call_time_control(control: Any, t_hr: float, output_unit: str) -> Any:
    t_quantity = Q_(t_hr, "hour")
    if callable(control):
        return _call_with_fallback(control, t_quantity, t_hr, output_unit)
    return _q(control, output_unit)


def _call_length_function(func: Any, length: Any, output_unit: str) -> Any:
    length_cm = to_magnitude(length, _HEIGHT_UNIT)
    if callable(func):
        return _call_with_fallback(
            func, Q_(length_cm, _HEIGHT_UNIT), length_cm, output_unit
        )
    return _q(func, output_unit)


def _call_pressure_function(func: Any, pressure: Any, output_unit: str) -> Any:
    pressure_torr = to_magnitude(pressure, _PRESSURE_UNIT)
    if callable(func):
        return _call_with_fallback(
            func,
            Q_(pressure_torr, _PRESSURE_UNIT),
            pressure_torr,
            output_unit,
        )
    return _q(func, output_unit)


def _hf0(params: PikalParams) -> Any:
    return _q(params.hf0, _HEIGHT_UNIT)


def _ap(params: PikalParams) -> Any:
    return _q(params.Ap, _AREA_UNIT)


def _av(params: PikalParams) -> Any:
    return _q(params.Av, _AREA_UNIT)


def _csolid(params: PikalParams) -> Any:
    return _q(params.csolid, _CONCENTRATION_UNIT)


def _rho_solution(params: PikalParams) -> Any:
    return _q(params.rho_solution, _CONCENTRATION_UNIT)


def _tsh(params: PikalParams, t_hr: float) -> Any:
    return _call_time_control(params.Tsh, t_hr, _TEMPERATURE_UNIT)


def _pch(params: PikalParams, t_hr: float) -> Any:
    return _call_time_control(params.pch, t_hr, _PRESSURE_UNIT)


def _rp(params: PikalParams, h_dried: Any) -> Any:
    return _call_length_function(params.Rp, h_dried, _RP_UNIT)


def _kshf(params: PikalParams, pch: Any) -> Any:
    return _call_pressure_function(params.Kshf, pch, _KSHF_UNIT)


def calc_pikal_u0(params: PikalParams, t_hr: Any = 0.0) -> np.ndarray:
    """Return the Julia-parity initial state ``[hf, Tf]``.

    The returned magnitudes are ``[cm, K]``.
    """

    t0 = to_magnitude(t_hr, "hour") if is_quantity(t_hr) else float(t_hr)
    return np.array(
        [
            _hf0(params).to(_HEIGHT_UNIT).magnitude,
            _tsh(params, t0).to(_TEMPERATURE_UNIT).magnitude,
        ],
        dtype=float,
    )


def calc_md_q(u: Iterable[Any], params: PikalParams, t_hr: Any) -> PikalDiagnostics:
    """Compute mass flow and shelf heat flow for ``u=[hf, Tf]``.

    Mass flow follows the Julia sign convention: it is negative during
    sublimation because frozen height decreases.
    """

    state = list(u)
    if len(state) != 2:
        raise ValueError("Pikal state must contain [hf, Tf]")
    t_value = to_magnitude(t_hr, "hour") if is_quantity(t_hr) else float(t_hr)

    h_frozen = _q(state[0], _HEIGHT_UNIT)
    tf = _q(state[1], _TEMPERATURE_UNIT)
    h_dried = (_hf0(params) - h_frozen).to(_HEIGHT_UNIT)
    pch = _pch(params, t_value)
    tsh = _tsh(params, t_value)
    rp = _rp(params, h_dried)
    kshf = _kshf(params, pch).to("watt / kelvin / centimeter ** 2")
    av = _av(params)
    ap = _ap(params)

    q_shf = (av * kshf * (tsh - tf)).to("watt")
    t_sub = (tf - q_shf / physical_properties.k_ice / ap * h_frozen).to(
        _TEMPERATURE_UNIT
    )
    delta_p = (physical_properties.calc_psub(t_sub) - pch).to("pascal")
    dmdt = (-(ap * delta_p.to(_PRESSURE_UNIT) / rp)).to("kilogram / second")

    return PikalDiagnostics(
        t=Q_(t_value, "hour"),
        h_frozen=h_frozen,
        h_dried=h_dried,
        tf=tf,
        t_sub=t_sub,
        pch=pch,
        tsh=tsh,
        delta_p=delta_p,
        rp=rp,
        q_shf=q_shf,
        dmdt=dmdt,
    )


def _extract_tstops(control: Any) -> list[float]:
    if isinstance(control, RampedVariable):
        return [float(t) for t in control.timestops_hr if math.isfinite(float(t))]
    if hasattr(control, "timestops_hr"):
        return [float(t) for t in control.timestops_hr if math.isfinite(float(t))]
    if hasattr(control, "times"):
        return [float(t) for t in np.asarray(control.times, dtype=float).ravel()]
    if hasattr(control, "timestops"):
        values = []
        for value in control.timestops:
            try:
                values.append(to_magnitude(value, "hour"))
            except Exception:
                values.append(float(value))
        return [float(t) for t in values if math.isfinite(float(t))]
    return [0.0]


def get_pikal_tstops(params: PikalParams) -> np.ndarray:
    """Return sorted unique time stops from ramped shelf and pressure controls."""

    stops = [0.0]
    stops.extend(_extract_tstops(params.Tsh))
    stops.extend(_extract_tstops(params.pch))
    return np.asarray(sorted(set(float(t) for t in stops if math.isfinite(t))))


def _shelf_pressure_margin(params: PikalParams, t_hr: float) -> float:
    tsh = _tsh(params, t_hr)
    pch = _pch(params, t_hr).to("pascal")
    return (physical_properties.calc_psub(tsh) - pch).to("pascal").magnitude


def get_pikal_t0(params: PikalParams, t_span: tuple[Any, Any] = (0.0, 1000.0)) -> float:
    """Return the delayed drying start time used by the Julia Pikal model."""

    start = (
        to_magnitude(t_span[0], "hour") if is_quantity(t_span[0]) else float(t_span[0])
    )
    end = (
        to_magnitude(t_span[1], "hour") if is_quantity(t_span[1]) else float(t_span[1])
    )

    if _shelf_pressure_margin(params, start) >= 0.0:
        return start

    stops = get_pikal_tstops(params)
    candidates = [start, end]
    candidates.extend(float(t) for t in stops if start < float(t) < end)
    candidates = sorted(set(candidates))

    for left, right in zip(candidates[:-1], candidates[1:]):
        f_left = _shelf_pressure_margin(params, left)
        f_right = _shelf_pressure_margin(params, right)
        if f_left == 0.0:
            return min(left * 1.001, end)
        if f_left < 0.0 <= f_right:
            root = brentq(lambda t: _shelf_pressure_margin(params, t), left, right)
            return min(root * 1.001, end)

    sample = np.linspace(start, end, 200)
    margins = np.array([_shelf_pressure_margin(params, float(t)) for t in sample])
    crossing = np.where((margins[:-1] < 0.0) & (margins[1:] >= 0.0))[0]
    if crossing.size:
        left = float(sample[crossing[0]])
        right = float(sample[crossing[0] + 1])
        root = brentq(lambda t: _shelf_pressure_margin(params, t), left, right)
        return min(root * 1.001, end)

    warnings.warn(
        "Shelf vapor pressure remains below chamber pressure; drying cannot proceed.",
        UserWarning,
    )
    return end


def _algebraic_diagnostics(
    h_frozen_cm: float,
    params: PikalParams,
    t_hr: float,
) -> PikalDiagnostics:
    h_frozen = Q_(max(h_frozen_cm, 0.0), _HEIGHT_UNIT)
    h_dried = (_hf0(params) - h_frozen).to(_HEIGHT_UNIT)
    pch = _pch(params, t_hr)
    tsh = _tsh(params, t_hr)
    rp = _rp(params, h_dried)
    kshf = _kshf(params, pch).to("watt / kelvin / centimeter ** 2")
    av = _av(params)
    ap = _ap(params)

    pch_psub_t = physical_properties.calc_tsub(pch)
    lower = pch_psub_t.to(_TEMPERATURE_UNIT).magnitude
    upper = tsh.to(_TEMPERATURE_UNIT).magnitude
    if upper <= lower:
        tf = tsh
        return calc_md_q([h_frozen, tf], params, t_hr)

    thermal_resistance = (
        1 / (av * kshf) + h_frozen / (physical_properties.k_ice * ap)
    ).to("kelvin / watt")

    def residual(t_sub_k: float) -> float:
        t_sub = Q_(t_sub_k, _TEMPERATURE_UNIT)
        delta_p = (physical_properties.calc_psub(t_sub) - pch).to(_PRESSURE_UNIT)
        q_mass = (ap * delta_p / rp * physical_properties.delta_h_sub).to("watt")
        q_heat = ((tsh - t_sub) / thermal_resistance).to("watt")
        return (q_mass - q_heat).to("watt").magnitude

    eps = max((upper - lower) * 1e-12, 1e-9)
    left = lower + eps
    right = upper
    f_left = residual(left)
    f_right = residual(right)
    if f_left > 0.0 or f_right < 0.0:
        grid = np.linspace(lower + eps, upper, 80)
        values = np.array([residual(float(value)) for value in grid])
        brackets = np.where((values[:-1] <= 0.0) & (values[1:] >= 0.0))[0]
        if brackets.size == 0:
            raise RuntimeError(
                "Could not bracket Pikal algebraic temperature solve at "
                f"t={t_hr:.6g} hr"
            )
        left = float(grid[brackets[0]])
        right = float(grid[brackets[0] + 1])

    t_sub = Q_(brentq(residual, left, right), _TEMPERATURE_UNIT)
    delta_p = (physical_properties.calc_psub(t_sub) - pch).to("pascal")
    q_shf = ((tsh - t_sub) / thermal_resistance).to("watt")
    tf = (tsh - q_shf / (av * kshf)).to(_TEMPERATURE_UNIT)
    dmdt = (-(ap * delta_p.to(_PRESSURE_UNIT) / rp)).to("kilogram / second")

    return PikalDiagnostics(
        t=Q_(t_hr, "hour"),
        h_frozen=h_frozen,
        h_dried=h_dried,
        tf=tf,
        t_sub=t_sub,
        pch=pch,
        tsh=tsh,
        delta_p=delta_p,
        rp=rp,
        q_shf=q_shf,
        dmdt=dmdt,
    )


def _dhf_dt_cm_hr(h_frozen_cm: float, params: PikalParams, t_hr: float) -> float:
    diagnostics = _algebraic_diagnostics(h_frozen_cm, params, t_hr)
    denominator = ((_rho_solution(params) - _csolid(params)) * _ap(params)).to(
        "gram / centimeter"
    )
    rate = (diagnostics.dmdt / denominator).to("centimeter / hour").magnitude
    return min(0.0, float(rate))


def _normalize_t_span(t_span: tuple[Any, Any]) -> tuple[float, float]:
    start = (
        to_magnitude(t_span[0], "hour") if is_quantity(t_span[0]) else float(t_span[0])
    )
    end = (
        to_magnitude(t_span[1], "hour") if is_quantity(t_span[1]) else float(t_span[1])
    )
    if end <= start:
        raise ValueError("t_span end must be greater than start")
    return start, end


def _normalize_save_at(save_at: Any) -> np.ndarray | None:
    if save_at is None:
        return None
    if is_quantity(save_at):
        values = np.asarray(save_at.to("hour").magnitude, dtype=float)
    else:
        values = np.asarray(list(save_at), dtype=float)
    return np.asarray(sorted(set(float(value) for value in values)), dtype=float)


def solve_pikal(
    params: PikalParams,
    t_span: tuple[Any, Any] = (0.0, 1000.0),
    save_at: Any = None,
    **solve_ivp_options: Any,
) -> PikalSolution:
    """Solve the typed conventional Pikal primary-drying model."""

    start, end = _normalize_t_span(t_span)
    t0 = get_pikal_t0(params, (start, end))
    save_times = _normalize_save_at(save_at)
    hf0_cm = _hf0(params).to(_HEIGHT_UNIT).magnitude

    if t0 >= end:
        t_values = np.array([start], dtype=float)
        diagnostics = tuple(
            _algebraic_diagnostics(hf0_cm, params, float(t)) for t in t_values
        )
        y = np.vstack(
            [
                np.full_like(t_values, hf0_cm, dtype=float),
                np.array(
                    [diag.tf.to(_TEMPERATURE_UNIT).magnitude for diag in diagnostics],
                    dtype=float,
                ),
            ]
        )
        return PikalSolution(t_values, y, diagnostics, params)

    stops = get_pikal_tstops(params)
    breakpoints = [t0, end]
    breakpoints.extend(float(t) for t in stops if t0 < float(t) < end)
    breakpoints = sorted(set(breakpoints))

    t_outputs: list[float] = []
    hf_outputs: list[float] = []
    raw_segments: list[Any] = []
    y0 = np.array([hf0_cm], dtype=float)

    def finish(_t: float, y: np.ndarray) -> float:
        return y[0] - 1e-10

    finish.terminal = True
    finish.direction = -1

    default_options = {
        "method": "BDF",
        "rtol": 1e-6,
        "atol": 1e-9,
        "dense_output": True,
    }
    default_options.update(solve_ivp_options)

    for left, right in zip(breakpoints[:-1], breakpoints[1:]):
        if y0[0] <= 1e-10:
            break
        if right <= left:
            continue

        if save_times is None:
            t_eval = None
        else:
            mask = (save_times >= left - 1e-12) & (save_times <= right + 1e-12)
            t_eval = save_times[mask]
            if t_eval.size == 0:
                t_eval = None

        sol = solve_ivp(
            lambda t, y: [_dhf_dt_cm_hr(float(y[0]), params, float(t))],
            (left, right),
            y0,
            events=finish,
            t_eval=t_eval,
            **default_options,
        )
        raw_segments.append(sol)
        if not sol.success:
            raise RuntimeError(sol.message)

        if save_times is None:
            segment_t = sol.t
            segment_y = sol.y[0]
        elif t_eval is None:
            segment_t = np.array([], dtype=float)
            segment_y = np.array([], dtype=float)
        else:
            segment_t = sol.t
            segment_y = sol.y[0]

        t_outputs.extend(float(t) for t in segment_t)
        hf_outputs.extend(float(y) for y in segment_y)

        if sol.t_events[0].size:
            t_event = float(sol.t_events[0][0])
            y_event = float(sol.y_events[0][0][0])
            if not t_outputs or not math.isclose(t_outputs[-1], t_event):
                t_outputs.append(t_event)
                hf_outputs.append(y_event)
            break

        y0 = np.array([float(sol.y[0, -1])], dtype=float)

    if not t_outputs:
        t_outputs.append(t0)
        hf_outputs.append(hf0_cm)

    order = np.argsort(t_outputs)
    t_sorted = np.asarray(t_outputs, dtype=float)[order]
    hf_sorted = np.asarray(hf_outputs, dtype=float)[order]
    t_unique, unique_indices = np.unique(t_sorted, return_index=True)
    hf_unique = hf_sorted[unique_indices]

    diagnostics = tuple(
        _algebraic_diagnostics(float(hf), params, float(t))
        for t, hf in zip(t_unique, hf_unique)
    )
    tf_values = np.array(
        [diag.tf.to(_TEMPERATURE_UNIT).magnitude for diag in diagnostics],
        dtype=float,
    )
    y = np.vstack([hf_unique, tf_values])

    return PikalSolution(
        t=t_unique,
        y=y,
        diagnostics=diagnostics,
        params=params,
        raw_segments=tuple(raw_segments),
    )


def pikal_solution_to_legacy_table(solution: PikalSolution) -> np.ndarray:
    """Convert a typed Pikal solution to the legacy seven-column table."""

    hf0 = _hf0(solution.params)
    ap_m2 = _ap(solution.params).to("meter ** 2")
    rows = []
    for t_hr, h_frozen_cm, diagnostics in zip(
        solution.t,
        solution.y[0],
        solution.diagnostics,
    ):
        h_frozen = Q_(h_frozen_cm, _HEIGHT_UNIT)
        dry_percent = ((hf0 - h_frozen) / hf0).to("").magnitude * 100.0
        mass_rate = max(
            0.0,
            (-diagnostics.dmdt).to("kilogram / hour").magnitude,
        )
        flux = mass_rate / ap_m2.magnitude
        rows.append(
            [
                float(t_hr),
                diagnostics.t_sub.to("degC").magnitude,
                diagnostics.tf.to("degC").magnitude,
                diagnostics.tsh.to("degC").magnitude,
                diagnostics.pch.to("millitorr").magnitude,
                flux,
                dry_percent,
            ]
        )
    return np.asarray(rows, dtype=float)


__all__ = [
    "PikalParams",
    "PikalDiagnostics",
    "PikalSolution",
    "calc_md_q",
    "calc_pikal_u0",
    "get_pikal_t0",
    "get_pikal_tstops",
    "pikal_solution_to_legacy_table",
    "solve_pikal",
]
