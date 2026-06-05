"""Typed convenience objects for Julia-parity lyophilization APIs.

This module is additive: existing dict-based calculators continue to use the
legacy float units documented in their modules. New APIs use Pint quantities
where units matter, while also accepting plain floats in canonical units.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
import math
from typing import Any
import warnings

import numpy as np
from pint import UnitRegistry

ureg: UnitRegistry = UnitRegistry(autoconvert_offset_to_baseunit=True)
Q_ = ureg.Quantity


def is_quantity(value: Any) -> bool:
    """Return True when *value* behaves like a Pint quantity."""

    return hasattr(value, "to") and hasattr(value, "magnitude")


def as_quantity(value: Any, unit: str):
    """Return *value* as a Pint quantity in *unit*.

    Plain numbers are interpreted in *unit*. Existing quantities are converted.
    """

    if is_quantity(value):
        return value.to(unit)
    return Q_(value, unit)


def to_magnitude(value: Any, unit: str | None = None) -> float:
    """Return *value* as a float magnitude, optionally converted to *unit*."""

    if is_quantity(value):
        return float(value.to(unit).magnitude if unit else value.magnitude)
    return float(value)


def to_magnitude_array(values: Any, unit: str | None = None) -> np.ndarray:
    """Return *values* as a float array, converting quantities when present."""

    if is_quantity(values):
        magnitude = values.to(unit).magnitude if unit else values.magnitude
        return np.asarray(magnitude, dtype=float)
    if isinstance(values, Iterable) and not isinstance(values, (str, bytes)):
        values_list = list(values)
        if any(is_quantity(value) for value in values_list):
            return np.asarray(
                [to_magnitude(value, unit) for value in values_list],
                dtype=float,
            )
    arr = np.asarray(values)
    if arr.dtype == object:
        converted = [to_magnitude(value, unit) for value in arr.ravel()]
        return np.asarray(converted, dtype=float).reshape(arr.shape)
    return arr.astype(float)


def quantity_list(values: Any) -> list[Any]:
    """Normalize a scalar, iterable, or Pint array into a Python list."""

    if is_quantity(values):
        magnitude = np.asarray(values.magnitude)
        if magnitude.ndim == 0:
            return [values]
        return [Q_(value, values.units) for value in magnitude.tolist()]
    if isinstance(values, np.ndarray):
        return values.tolist()
    if isinstance(values, Iterable) and not isinstance(values, (str, bytes)):
        return list(values)
    return [values]


def _time_to_hours(value: Any) -> float:
    if value in (math.inf, -math.inf):
        return float(value)
    return to_magnitude(value, "hour") if is_quantity(value) else float(value)


def _duration_hours(delta: Any, rate: Any) -> float:
    duration = delta / rate
    if is_quantity(duration):
        return to_magnitude(duration, "hour")
    return float(duration)


@dataclass(frozen=True)
class RpFormFit:
    """Callable form ``R0 + A1*x/(1 + A2*x)`` for product resistance fits."""

    R0: Any
    A1: Any
    A2: Any

    def __call__(self, x: Any) -> Any:
        return self.R0 + self.A1 * x / (1 + self.A2 * x)


@dataclass(frozen=True)
class ConstPhysProp:
    """Callable constant physical property."""

    value: Any

    def __call__(self, *args: Any) -> Any:
        return self.value


@dataclass(frozen=True)
class RampedVariable:
    """Piecewise constant/linear setpoint schedule.

    Time arguments are hours for plain floats, or any Pint time quantity.
    Ramp rates should have compatible units when quantities are used.
    """

    setpts: tuple[Any, ...]
    ramprates: tuple[Any, ...] = ()
    holds: tuple[Any, ...] = ()
    timestops_hr: tuple[float, ...] = (0.0,)

    def __post_init__(self) -> None:
        if len(self.setpts) == 0:
            raise ValueError("RampedVariable requires at least one setpoint")
        if len(self.setpts) == 1:
            if self.ramprates or self.holds:
                raise ValueError(
                    "constant RampedVariable cannot define ramp rates or holds"
                )
        else:
            if len(self.ramprates) != len(self.setpts) - 1:
                raise ValueError(
                    "number of ramp rates must be one fewer than " "number of setpoints"
                )
            if len(self.holds) != max(len(self.ramprates) - 1, 0):
                raise ValueError(
                    "number of holds must be one fewer than " "number of ramp rates"
                )

        expected_timestops = 1 + len(self.ramprates) + len(self.holds)
        if len(self.timestops_hr) != expected_timestops:
            raise ValueError(
                "timestops_hr must contain the initial time plus each "
                "ramp and hold stop; use RampedVariable.constant, "
                ".linear, or .multi to construct schedules"
            )

    @classmethod
    def constant(cls, value: Any) -> "RampedVariable":
        return cls((value,), (), (), (0.0,))

    @classmethod
    def linear(cls, setpts: Any, ramprate: Any) -> "RampedVariable":
        pts = tuple(quantity_list(setpts))
        if len(pts) != 2:
            raise ValueError("linear RampedVariable requires exactly two setpoints")
        rates = tuple(quantity_list(ramprate))
        if len(rates) != 1:
            raise ValueError("linear RampedVariable requires exactly one ramp rate")
        duration = _duration_hours(pts[1] - pts[0], rates[0])
        if duration < 0:
            warnings.warn(
                "Ramp rate given with probably the wrong sign, " "changing its sign",
                UserWarning,
            )
            duration = abs(duration)
        return cls(pts, rates, (), (0.0, duration))

    @classmethod
    def multi(
        cls,
        setpts: Any,
        ramprates: Any,
        holds: Any,
    ) -> "RampedVariable":
        pts = tuple(quantity_list(setpts))
        rates = tuple(quantity_list(ramprates))
        hold_values = tuple(quantity_list(holds))
        if len(rates) == 0 or len(rates) != len(hold_values) + 1:
            raise ValueError("number of ramps must be one more than number of holds")
        if len(pts) != len(rates) + 1:
            raise ValueError(
                "number of setpoints must be one more than number of ramps"
            )

        times = [0.0]
        current = 0.0
        for index, rate in enumerate(rates):
            ramp_time = _duration_hours(pts[index + 1] - pts[index], rate)
            if ramp_time < 0:
                warnings.warn(
                    "Ramp rate given with probably the wrong sign, "
                    "changing its sign",
                    UserWarning,
                )
                ramp_time = abs(ramp_time)
            current += ramp_time
            times.append(current)
            if index < len(hold_values):
                current += _time_to_hours(hold_values[index])
                times.append(current)
        return cls(pts, rates, hold_values, tuple(times))

    @property
    def timestops(self) -> list[Any]:
        return [Q_(time, "hour") for time in self.timestops_hr]

    @property
    def is_constant(self) -> bool:
        return len(self.setpts) == 1

    def __call__(self, t: Any) -> Any:
        if self.is_constant:
            return self.setpts[0]

        th = _time_to_hours(t)
        if th <= self.timestops_hr[0]:
            return self.setpts[0]
        if th >= self.timestops_hr[-1]:
            return self.setpts[-1]

        cursor = self.timestops_hr[0]
        time_index = 1
        for index, _rate in enumerate(self.ramprates):
            ramp_end = self.timestops_hr[time_index]
            if th <= ramp_end:
                if ramp_end == cursor:
                    return self.setpts[index + 1]
                frac = (th - cursor) / (ramp_end - cursor)
                return self.setpts[index] + frac * (
                    self.setpts[index + 1] - self.setpts[index]
                )
            cursor = ramp_end
            time_index += 1
            if index < len(self.holds):
                hold_end = self.timestops_hr[time_index]
                if th <= hold_end:
                    return self.setpts[index + 1]
                cursor = hold_end
                time_index += 1
        return self.setpts[-1]


@dataclass(frozen=True)
class PrimaryDryFit:
    """Container for primary-drying temperature data used in fitting."""

    t: tuple[Any, ...]
    Tfs: tuple[tuple[Any, ...], ...]
    Tf_iend: tuple[int, ...]
    Tvws: tuple[tuple[Any, ...], ...] | Any | None = None
    Tvw_iend: tuple[int, ...] | None = None
    t_end: Any = None

    def __init__(
        self,
        t: Any,
        Tfs: Any,
        *,
        Tf_iend: Any = None,
        Tvws: Any = None,
        Tvw_iend: Any = None,
        t_end: Any = None,
    ) -> None:
        times = tuple(quantity_list(t))
        if not times:
            raise ValueError("t must contain at least one time point")
        _validate_unit_sequence(times, "time", "t")

        tf_series = _normalize_temperature_series(Tfs, "Tfs")
        if Tf_iend is None:
            tf_iend = tuple(len(series) for series in tf_series)
        else:
            tf_iend = _normalize_iend(Tf_iend, len(tf_series), "Tf_iend")
        _validate_iend_bounds(tf_iend, tf_series, "Tf_iend")

        if Tvws is None:
            tvw_value = None
            tvw_iend = None
        elif _looks_like_endpoint(Tvws):
            _validate_unit_value(Tvws, "temperature", "Tvws")
            tvw_value = Tvws
            tvw_iend = None
        else:
            tvw_series = _normalize_temperature_series(Tvws, "Tvws")
            tvw_value = tvw_series
            if Tvw_iend is None:
                tvw_iend = tuple(len(series) for series in tvw_series)
            else:
                tvw_iend = _normalize_iend(Tvw_iend, len(tvw_series), "Tvw_iend")
            _validate_iend_bounds(tvw_iend, tvw_series, "Tvw_iend")

        object.__setattr__(self, "t", times)
        object.__setattr__(self, "Tfs", tf_series)
        object.__setattr__(self, "Tf_iend", tf_iend)
        object.__setattr__(self, "Tvws", tvw_value)
        object.__setattr__(self, "Tvw_iend", tvw_iend)
        object.__setattr__(self, "t_end", _normalize_t_end(t_end))

    @property
    def t_hr(self) -> np.ndarray:
        """Fit times as float hours."""

        return to_magnitude_array(self.t, "hour")

    @property
    def Tfs_K(self) -> tuple[np.ndarray, ...]:
        """Product-temperature series as float kelvin arrays."""

        return tuple(to_magnitude_array(series, "kelvin") for series in self.Tfs)

    @property
    def Tvws_K(self) -> tuple[np.ndarray, ...] | float | None:
        """Vial-wall data as kelvin arrays, endpoint kelvin, or ``None``."""

        if self.Tvws is None:
            return None
        if self.Tvw_iend is None:
            return to_magnitude(self.Tvws, "kelvin")
        return tuple(to_magnitude_array(series, "kelvin") for series in self.Tvws)


def _normalize_temperature_series(
    series: Any, name: str
) -> tuple[tuple[Any, ...], ...]:
    normalized = _normalize_series(series)
    for index, values in enumerate(normalized):
        if not values:
            raise ValueError(f"{name} temperature series cannot be empty")
        _validate_unit_sequence(values, "temperature", f"{name}[{index}]")
    return normalized


def _normalize_series(series: Any) -> tuple[tuple[Any, ...], ...]:
    if _looks_like_endpoint(series):
        return (tuple(quantity_list(series)),)
    if is_quantity(series):
        values = quantity_list(series)
        return (tuple(values),)
    if isinstance(series, np.ndarray):
        if series.ndim <= 1:
            return (tuple(series.tolist()),)
        return tuple(tuple(row) for row in series.tolist())
    if not isinstance(series, (tuple, list)):
        return (tuple(quantity_list(series)),)
    if len(series) == 0:
        raise ValueError("temperature series cannot be empty")
    if all(_looks_like_scalar(value) for value in series):
        return (tuple(series),)
    return tuple(tuple(quantity_list(value)) for value in series)


def _normalize_iend(values: Any, nseries: int, name: str) -> tuple[int, ...]:
    iend = tuple(int(value) for value in quantity_list(values))
    if len(iend) != nseries:
        raise ValueError(f"{name} must have one value for each temperature series")
    if any(value < 0 for value in iend):
        raise ValueError(f"{name} values must be nonnegative")
    return iend


def _validate_iend_bounds(
    iend: tuple[int, ...],
    series: tuple[tuple[Any, ...], ...],
    name: str,
) -> None:
    for value, values in zip(iend, series):
        if value > len(values):
            raise ValueError(f"{name} cannot exceed its temperature series length")


def _normalize_t_end(t_end: Any) -> Any:
    if t_end is None:
        return None
    if _looks_like_scalar(t_end):
        _validate_unit_value(t_end, "time", "t_end")
        return t_end

    values = tuple(quantity_list(t_end))
    if len(values) != 2:
        raise ValueError("t_end must be a time or a two-time window")
    _validate_unit_sequence(values, "time", "t_end")
    ordered = sorted(values, key=lambda value: to_magnitude(value, "hour"))
    return tuple(ordered)


def _looks_like_scalar(value: Any) -> bool:
    if is_quantity(value):
        return np.asarray(value.magnitude).ndim == 0
    return np.isscalar(value)


def _looks_like_endpoint(value: Any) -> bool:
    return _looks_like_scalar(value)


def _validate_unit_sequence(values: tuple[Any, ...], dimension: str, name: str) -> None:
    for value in values:
        _validate_unit_value(value, dimension, name)


def _validate_unit_value(value: Any, dimension: str, name: str) -> None:
    if is_quantity(value) and not value.check(f"[{dimension}]"):
        raise ValueError(f"{name} values must have units of {dimension}")


__all__ = [
    "ureg",
    "Q_",
    "is_quantity",
    "as_quantity",
    "to_magnitude",
    "to_magnitude_array",
    "quantity_list",
    "RpFormFit",
    "ConstPhysProp",
    "RampedVariable",
    "PrimaryDryFit",
]
