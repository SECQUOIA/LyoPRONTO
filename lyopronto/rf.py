"""Typed RF/microwave lumped-capacitance primary-drying solver.

This module ports Julia's RF primary-drying state model. Plain floats use the
same canonical units as the typed Pikal API: hours, grams, kelvin, torr,
centimeters, square centimeters, ``cm^2*hr*Torr/g`` for ``Rp``, and
``cal/s/K/cm^2`` for heat-transfer coefficients. RF power is per vial in
watts, frequency is in hertz, and fit factors ``Bf``/``Bvw`` are
``ohm/meter^2``.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from functools import lru_cache
import math
from typing import Any, cast

import numpy as np
from pint.errors import DimensionalityError
from scipy import special
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
_MASS_UNIT = "gram"
_CP_UNIT = "joule / kilogram / kelvin"
_POWER_UNIT = "watt"
_FREQUENCY_UNIT = "hertz"
_FIELD_FACTOR_UNIT = "ohm / meter ** 2"
_CALLABLE_FALLBACK_EXCEPTIONS = (TypeError, DimensionalityError)


@dataclass(frozen=True)
class RFParams:
    """Parameter container for the RF primary-drying model.

    ``Tsh``, ``pch``, and ``P_per_vial`` may be constants, callables, or
    :class:`~lyopronto.typed.RampedVariable` schedules. ``P_per_vial`` is the
    per-vial RF power in watts, not total batch power.
    """

    Rp: Any
    hf0: Any
    csolid: Any
    rho_solution: Any
    Kshf: Any
    Av: Any
    Ap: Any
    pch: Any
    Tsh: Any
    P_per_vial: Any
    mf0: Any
    cpf: Any
    mv: Any
    cpv: Any
    f_RF: Any
    eppf: Any
    eppvw: Any
    Kvwf: Any
    Bf: Any
    Bvw: Any
    Arad: Any = None
    alpha: Any = None

    @classmethod
    def from_nested_tuple(cls, values: tuple[Any, ...]) -> "RFParams":
        """Build params from Julia's tuple-of-tuples RF layout."""

        if len(values) != 6:
            raise ValueError("RF nested tuple must contain six parameter groups")

        product = tuple(values[0])
        geometry = tuple(values[1])
        controls = tuple(values[2])
        vial = tuple(values[3])
        dielectric = tuple(values[4])
        fit = tuple(values[5])

        if len(product) != 4:
            raise ValueError("RF product group must contain 4 values")
        if len(geometry) != 3:
            raise ValueError("RF geometry group must contain 3 values")
        if len(controls) != 3:
            raise ValueError("RF control group must contain 3 values")
        if len(vial) not in (4, 5):
            raise ValueError("RF vial group must contain 4 or 5 values")
        if len(dielectric) != 3:
            raise ValueError("RF dielectric group must contain 3 values")
        if len(fit) not in (3, 4):
            raise ValueError("RF fit group must contain 3 or 4 values")

        mf0, cpf, mv, cpv = vial[:4]
        arad = vial[4] if len(vial) == 5 else None
        kvwf, bf, bvw = fit[:3]
        alpha = fit[3] if len(fit) == 4 else None

        return cls(
            *product,
            *geometry,
            *controls,
            mf0,
            cpf,
            mv,
            cpv,
            *dielectric,
            kvwf,
            bf,
            bvw,
            arad,
            alpha,
        )


@dataclass(frozen=True)
class RFDiagnostics:
    """Mass, temperature, and heat diagnostics at one RF solver state."""

    t: Any
    m_frozen: Any
    h_frozen: Any
    h_dried: Any
    tf: Any
    tvw: Any
    pch: Any
    tsh: Any
    rp: Any
    mflow: Any
    dmfdt: Any
    q_sub: Any
    q_shf: Any
    q_vwf: Any
    q_rf_f: Any
    q_rf_vw: Any
    q_shw: Any

    @property
    def heat_terms(self) -> tuple[Any, Any, Any, Any, Any, Any]:
        """Return ``[Q_sub, Q_shf, Q_vwf, Q_RF_f, Q_RF_vw, Q_shw]``."""

        return (
            self.q_sub,
            self.q_shf,
            self.q_vwf,
            self.q_rf_f,
            self.q_rf_vw,
            self.q_shw,
        )

    @property
    def heat_terms_watts(self) -> np.ndarray:
        """Return heat diagnostics as watt magnitudes in Julia order."""

        return np.asarray([term.to(_POWER_UNIT).magnitude for term in self.heat_terms])


@dataclass(frozen=True)
class RFSolution:
    """Typed RF solution returned by :func:`solve_rf`."""

    t: np.ndarray
    y: np.ndarray
    diagnostics: tuple[RFDiagnostics, ...]
    params: RFParams
    raw_segments: tuple[Any, ...] = ()
    drying_event_time_hr: float | None = None

    @property
    def t_hours(self) -> Any:
        """Solution times as Pint hours."""

        return Q_(self.t, "hour")

    @property
    def mf(self) -> Any:
        """Frozen product mass state as Pint grams."""

        return Q_(self.y[0], _MASS_UNIT)

    @property
    def tf(self) -> Any:
        """Frozen product temperature state as Pint kelvin."""

        return Q_(self.y[1], _TEMPERATURE_UNIT)

    @property
    def tvw(self) -> Any:
        """Vial-wall temperature state as Pint kelvin."""

        return Q_(self.y[2], _TEMPERATURE_UNIT)

    @property
    def drying_time(self) -> Any:
        """Final solution time as a Pint hour quantity."""

        return Q_(float(self.t[-1]), "hour")

    @property
    def terminated_by_drying(self) -> bool:
        """Return True when the drying-completion event stopped integration."""

        return self.drying_event_time_hr is not None


def _q(value: Any, unit: str) -> Any:
    return as_quantity(value, unit)


def _dimensionless(value: Any) -> float:
    if is_quantity(value):
        return float(value.to("").magnitude)
    return float(value)


def _call_with_fallback(
    func: Any,
    quantity_arg: Any,
    magnitude_arg: float,
    output_unit: str,
) -> Any:
    try:
        value = func(quantity_arg)
    except _CALLABLE_FALLBACK_EXCEPTIONS:
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


def _call_dielectric_loss(func: Any, temperature: Any, frequency: Any) -> float:
    temperature_k = to_magnitude(temperature, _TEMPERATURE_UNIT)
    frequency_hz = to_magnitude(frequency, _FREQUENCY_UNIT)
    if callable(func):
        try:
            value = func(temperature, frequency)
        except TypeError:
            try:
                value = func(temperature)
            except _CALLABLE_FALLBACK_EXCEPTIONS:
                value = func(temperature_k, frequency_hz)
        except DimensionalityError:
            value = func(temperature_k, frequency_hz)
    else:
        value = func
    return _dimensionless(value)


def _hf0(params: RFParams) -> Any:
    return _q(params.hf0, _HEIGHT_UNIT)


def _csolid(params: RFParams) -> Any:
    return _q(params.csolid, _CONCENTRATION_UNIT)


def _rho_solution(params: RFParams) -> Any:
    return _q(params.rho_solution, _CONCENTRATION_UNIT)


def _av(params: RFParams) -> Any:
    return _q(params.Av, _AREA_UNIT)


def _ap(params: RFParams) -> Any:
    return _q(params.Ap, _AREA_UNIT)


def _mf0(params: RFParams) -> Any:
    return _q(params.mf0, _MASS_UNIT)


def _mv(params: RFParams) -> Any:
    return _q(params.mv, _MASS_UNIT)


def _cpf(params: RFParams) -> Any:
    return _q(params.cpf, _CP_UNIT)


def _cpv(params: RFParams) -> Any:
    return _q(params.cpv, _CP_UNIT)


def _frequency(params: RFParams) -> Any:
    return _q(params.f_RF, _FREQUENCY_UNIT)


def _kvwf(params: RFParams) -> Any:
    return _q(params.Kvwf, _KSHF_UNIT)


def _bf(params: RFParams) -> Any:
    return _q(params.Bf, _FIELD_FACTOR_UNIT)


def _bvw(params: RFParams) -> Any:
    return _q(params.Bvw, _FIELD_FACTOR_UNIT)


def _tsh(params: RFParams, t_hr: float) -> Any:
    return _call_time_control(params.Tsh, t_hr, _TEMPERATURE_UNIT)


def _pch(params: RFParams, t_hr: float) -> Any:
    return _call_time_control(params.pch, t_hr, _PRESSURE_UNIT)


def _power(params: RFParams, t_hr: float) -> Any:
    return _call_time_control(params.P_per_vial, t_hr, _POWER_UNIT)


def _rp(params: RFParams, h_dried: Any) -> Any:
    return _call_length_function(params.Rp, h_dried, _RP_UNIT)


def _kshf(params: RFParams, pch: Any) -> Any:
    return _call_pressure_function(params.Kshf, pch, _KSHF_UNIT)


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


def get_rf_tstops(params: RFParams) -> np.ndarray:
    """Return sorted unique time stops from RF, shelf, and pressure controls."""

    stops = [0.0]
    stops.extend(_extract_tstops(params.Tsh))
    stops.extend(_extract_tstops(params.pch))
    stops.extend(_extract_tstops(params.P_per_vial))
    return np.asarray(sorted(set(float(t) for t in stops if math.isfinite(t))))


def calc_rf_u0(params: RFParams, t_hr: Any = 0.0) -> np.ndarray:
    """Return the Julia-parity initial state ``[m_f, T_f, T_vw]``.

    The returned magnitudes are ``[g, K, K]``.
    """

    t0 = to_magnitude(t_hr, "hour") if is_quantity(t_hr) else float(t_hr)
    tsh0 = _tsh(params, t0).to(_TEMPERATURE_UNIT).magnitude
    return np.array(
        [
            _mf0(params).to(_MASS_UNIT).magnitude,
            tsh0,
            tsh0,
        ],
        dtype=float,
    )


def shape_factor(Bi: Any, modes: int = 200) -> float:
    """Return Julia's cylindrical RF wall-product shape factor."""

    bi = _dimensionless(Bi)
    if bi < 0.0:
        raise ValueError("Bi must be nonnegative")
    return _shape_factor_cached(round(float(bi), 12), int(modes))


@lru_cache(maxsize=256)
def _shape_factor_cached(bi: float, modes: int) -> float:
    if bi == 0.0:
        return 0.0

    def charfunc(x: float) -> float:
        return -x * special.j1(x) + bi * special.j0(x)

    roots: list[float] = []
    x_left = 1e-10
    f_left = charfunc(x_left)
    step = math.pi / 16.0
    max_x = (modes + 3) * math.pi

    while len(roots) < modes and x_left < max_x:
        x_right = x_left + step
        f_right = charfunc(x_right)
        if f_left == 0.0:
            roots.append(x_left)
        elif f_left * f_right < 0.0:
            roots.append(brentq(charfunc, x_left, x_right))
        x_left = x_right
        f_left = f_right

    if len(roots) < modes:
        raise RuntimeError("Could not find enough roots for RF shape factor")

    lm = np.asarray(roots, dtype=float)
    j0 = special.j0(lm)
    j1 = special.j1(lm)
    cm = 2.0 / lm * j1 / (j0**2 + j1**2)
    return float(np.sum(cm * j1 * np.tanh(lm)))


def _porosity(params: RFParams) -> float:
    return (
        (_rho_solution(params) - _csolid(params)) / _rho_solution(params)
    ).to("").magnitude


def _dry_mass_floor(params: RFParams) -> float:
    mf0_g = _mf0(params).to(_MASS_UNIT).magnitude
    return max(1e-8, 1e-8 * float(mf0_g))


def calc_rf_diagnostics(
    u: Iterable[Any],
    params: RFParams,
    t_hr: Any,
) -> RFDiagnostics:
    """Compute RF mass, temperature, and heat diagnostics for one state.

    Heat terms are returned in watts with Julia ordering available through
    :attr:`RFDiagnostics.heat_terms`.
    """

    state = list(u)
    if len(state) != 3:
        raise ValueError("RF state must contain [m_f, T_f, T_vw]")
    t_value = to_magnitude(t_hr, "hour") if is_quantity(t_hr) else float(t_hr)

    mf0 = _mf0(params)
    mf0_g = mf0.to(_MASS_UNIT).magnitude
    mf_g = max(_q(state[0], _MASS_UNIT).to(_MASS_UNIT).magnitude, 0.0)
    mf = Q_(mf_g, _MASS_UNIT)
    tf = _q(state[1], _TEMPERATURE_UNIT)
    tvw = _q(state[2], _TEMPERATURE_UNIT)

    porosity = _porosity(params)
    if porosity <= 0.0:
        raise ValueError("RF porosity must be positive")

    hf0 = _hf0(params)
    ratio = min(max(float(mf_g / mf0_g), 0.0), 1.0)
    h_frozen = (hf0 * ratio).to(_HEIGHT_UNIT)
    h_dried = (hf0 - h_frozen).to(_HEIGHT_UNIT)

    pch = _pch(params, t_value)
    tsh = _tsh(params, t_value)
    rp = _rp(params, h_dried)
    kshf = _kshf(params, pch).to("watt / kelvin / centimeter ** 2")
    av = _av(params)
    ap = _ap(params)

    q_shf = (kshf * ap * (tsh - tf)).to(_POWER_UNIT)
    q_shw = (kshf * (av - ap) * (tsh - tvw)).to(_POWER_UNIT)

    delta_p = (physical_properties.calc_psub(tf) - pch).to(_PRESSURE_UNIT)
    mflow = (ap * delta_p / rp).to("gram / hour")
    q_sub = (mflow * physical_properties.delta_h_sub).to(_POWER_UNIT)

    rad = Q_(math.sqrt(ap.to("meter ** 2").magnitude / math.pi), "meter")
    k_dry = (
        physical_properties.k_sucrose * (1.0 - porosity)
    ).to("watt / meter / kelvin")
    kvwf = _kvwf(params).to("watt / kelvin / meter ** 2")
    bi = (kvwf * rad / k_dry).to("")
    s_factor = shape_factor(bi)
    q_vwf = (
        2.0
        * math.pi
        * (
            kvwf * rad * h_frozen.to("meter")
            + k_dry * h_dried.to("meter") * s_factor
        )
        * (tvw - tf)
    ).to(_POWER_UNIT)

    frequency = _frequency(params)
    power = _power(params, t_value)
    epp_f = _call_dielectric_loss(params.eppf, tf, frequency)
    epp_vw = _call_dielectric_loss(params.eppvw, tvw, frequency)
    qppp_rf_f = (
        2.0
        * math.pi
        * frequency
        * physical_properties.e_0
        * epp_f
        * power
        * _bf(params)
    ).to("watt / meter ** 3")
    qppp_rf_vw = (
        2.0
        * math.pi
        * frequency
        * physical_properties.e_0
        * epp_vw
        * power
        * _bvw(params)
    ).to("watt / meter ** 3")
    vial_volume = (_mv(params) / physical_properties.rho_glass).to("meter ** 3")
    q_rf_f = (qppp_rf_f * ap.to("meter ** 2") * h_frozen.to("meter")).to(
        _POWER_UNIT
    )
    q_rf_vw = (qppp_rf_vw * vial_volume).to(_POWER_UNIT)

    dmf_candidate = (-mflow / porosity).to("gram / hour")
    dmfdt = Q_(min(0.0, float(dmf_candidate.magnitude)), "gram / hour")

    return RFDiagnostics(
        t=Q_(t_value, "hour"),
        m_frozen=mf,
        h_frozen=h_frozen,
        h_dried=h_dried,
        tf=tf,
        tvw=tvw,
        pch=pch,
        tsh=tsh,
        rp=rp,
        mflow=mflow,
        dmfdt=dmfdt,
        q_sub=q_sub,
        q_shf=q_shf,
        q_vwf=q_vwf,
        q_rf_f=q_rf_f,
        q_rf_vw=q_rf_vw,
        q_shw=q_shw,
    )


def calc_rf_heat_terms(
    u: Iterable[Any],
    params: RFParams,
    t_hr: Any,
) -> tuple[Any, Any, Any, Any, Any, Any]:
    """Return ``[Q_sub, Q_shf, Q_vwf, Q_RF_f, Q_RF_vw, Q_shw]`` in watts."""

    return calc_rf_diagnostics(u, params, t_hr).heat_terms


def rf_rhs(t_hr: Any, u: Iterable[Any], params: RFParams) -> np.ndarray:
    """Return RF state derivatives ``[g/hr, K/hr, K/hr]``."""

    diagnostics = calc_rf_diagnostics(u, params, t_hr)
    state = list(u)
    mf_g = max(_q(state[0], _MASS_UNIT).to(_MASS_UNIT).magnitude, 0.0)
    mf_energy = Q_(max(mf_g, _dry_mass_floor(params)), _MASS_UNIT)
    tf = _q(state[1], _TEMPERATURE_UNIT)
    dmfdt = diagnostics.dmfdt

    d_tf = (
        (
            diagnostics.q_shf
            + diagnostics.q_vwf
            + diagnostics.q_rf_f
            - diagnostics.q_sub
        )
        / (mf_energy * _cpf(params))
    ).to("kelvin / hour") - (tf * dmfdt / mf_energy).to("kelvin / hour")
    d_tvw = (
        (diagnostics.q_shw - diagnostics.q_vwf + diagnostics.q_rf_vw)
        / (_mv(params) * _cpv(params))
    ).to("kelvin / hour")

    return np.array(
        [
            dmfdt.to("gram / hour").magnitude,
            d_tf.to("kelvin / hour").magnitude,
            d_tvw.to("kelvin / hour").magnitude,
        ],
        dtype=float,
    )


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


def solve_rf(
    params: RFParams,
    t_span: tuple[Any, Any] = (0.0, 400.0),
    save_at: Any = None,
    **solve_ivp_options: Any,
) -> RFSolution:
    """Solve the typed RF/microwave primary-drying model."""

    start, end = _normalize_t_span(t_span)
    save_times = _normalize_save_at(save_at)
    stops = get_rf_tstops(params)
    breakpoints = [start, end]
    breakpoints.extend(float(t) for t in stops if start < float(t) < end)
    breakpoints = sorted(set(breakpoints))

    t_outputs: list[float] = []
    y_outputs: list[np.ndarray] = []
    raw_segments: list[Any] = []
    drying_event_time: float | None = None
    y0 = calc_rf_u0(params, start)
    dry_floor = _dry_mass_floor(params)

    def finish(_t: float, y: np.ndarray) -> float:
        return float(y[0]) - dry_floor

    finish_event = cast(Any, finish)
    finish_event.terminal = True
    finish_event.direction = -1

    default_options = {
        "method": "BDF",
        "rtol": 1e-6,
        "atol": [dry_floor * 1e-3, 1e-6, 1e-6],
        "dense_output": True,
    }
    default_options.update(solve_ivp_options)
    default_options["dense_output"] = True

    for left, right in zip(breakpoints[:-1], breakpoints[1:]):
        if y0[0] <= dry_floor:
            drying_event_time = left
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
            lambda t, y: rf_rhs(float(t), y, params),
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
            segment_y = sol.y.T
        elif t_eval is None:
            segment_t = np.array([], dtype=float)
            segment_y = np.empty((0, 3), dtype=float)
        else:
            segment_t = sol.t
            segment_y = sol.y.T

        t_outputs.extend(float(t) for t in segment_t)
        y_outputs.extend(np.asarray(row, dtype=float) for row in segment_y)

        if sol.t_events[0].size:
            t_event = float(sol.t_events[0][0])
            y_event = np.asarray(sol.y_events[0][0], dtype=float)
            drying_event_time = t_event
            if not t_outputs or not math.isclose(t_outputs[-1], t_event):
                t_outputs.append(t_event)
                y_outputs.append(y_event)
            break

        if sol.sol is None:
            raise RuntimeError("RF solver requires dense output for segmented ramps")
        endpoint_y = np.asarray(sol.sol(right), dtype=float).reshape(-1)
        y0 = endpoint_y

    if not t_outputs:
        t_outputs.append(start)
        y_outputs.append(calc_rf_u0(params, start))

    order = np.argsort(t_outputs)
    t_sorted = np.asarray(t_outputs, dtype=float)[order]
    y_sorted = np.asarray(y_outputs, dtype=float)[order]
    t_unique, unique_indices = np.unique(t_sorted, return_index=True)
    y_unique = y_sorted[unique_indices]
    y_unique[:, 0] = np.maximum(y_unique[:, 0], 0.0)

    diagnostics = tuple(
        calc_rf_diagnostics(row, params, float(t))
        for t, row in zip(t_unique, y_unique)
    )

    return RFSolution(
        t=t_unique,
        y=y_unique.T,
        diagnostics=diagnostics,
        params=params,
        raw_segments=tuple(raw_segments),
        drying_event_time_hr=drying_event_time,
    )


_QRF_INTEGRATE_KEYS = ("Qsub", "Qshf", "Qvwf", "QRFf", "QRFvw")


def qrf_integrate(solution: RFSolution) -> dict[str, Any]:
    """Integrate each RF heat-transfer mode over a solved trajectory.

    Returns a dict with keys ``Qsub``, ``Qshf``, ``Qvwf``, ``QRFf``, and
    ``QRFvw`` as Pint energy quantities in watt-hours. Integration is
    trapezoidal over the solution time points (in hours). As in Julia
    ``qrf_integrate``, the shelf-to-wall term ``Q_shw`` is not integrated.
    """

    t_hours = np.asarray(solution.t, dtype=float)
    if t_hours.size == 0:
        raise ValueError("solution has no time points to integrate")
    heat_watts = np.asarray(
        [diag.heat_terms_watts for diag in solution.diagnostics],
        dtype=float,
    )
    if heat_watts.shape[0] != t_hours.size:
        raise ValueError("solution diagnostics do not match solution time points")

    n_keys = len(_QRF_INTEGRATE_KEYS)
    if t_hours.size == 1:
        energies = np.zeros(n_keys, dtype=float)
    else:
        trapezoid = np.trapezoid if hasattr(np, "trapezoid") else np.trapz
        energies = np.array(
            [
                float(trapezoid(heat_watts[:, index], t_hours))
                for index in range(n_keys)
            ],
            dtype=float,
        )
    return {
        key: Q_(float(energy), "watt * hour")
        for key, energy in zip(_QRF_INTEGRATE_KEYS, energies)
    }


__all__ = [
    "RFParams",
    "RFDiagnostics",
    "RFSolution",
    "calc_rf_diagnostics",
    "calc_rf_heat_terms",
    "calc_rf_u0",
    "get_rf_tstops",
    "qrf_integrate",
    "rf_rhs",
    "shape_factor",
    "solve_rf",
]
