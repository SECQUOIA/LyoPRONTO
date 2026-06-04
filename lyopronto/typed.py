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
                    "number of ramp rates must be one fewer than "
                    "number of setpoints"
                )
            if len(self.holds) != max(len(self.ramprates) - 1, 0):
                raise ValueError(
                    "number of holds must be one fewer than "
                    "number of ramp rates"
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
            raise ValueError(
                "linear RampedVariable requires exactly two setpoints"
            )
        rates = tuple(quantity_list(ramprate))
        if len(rates) != 1:
            raise ValueError(
                "linear RampedVariable requires exactly one ramp rate"
            )
        duration = _duration_hours(pts[1] - pts[0], rates[0])
        if duration < 0:
            warnings.warn(
                "Ramp rate given with probably the wrong sign, "
                "changing its sign",
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
            raise ValueError(
                "number of ramps must be one more than number of holds"
            )
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
]
