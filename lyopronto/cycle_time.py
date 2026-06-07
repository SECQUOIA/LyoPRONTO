"""Primary-drying cycle-time utilities."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
import operator
from typing import Any

import numpy as np
from scipy.signal import savgol_filter

from .typed import Q_, is_quantity, to_magnitude, to_magnitude_array

_POLY_ORDER = 3
_SG_MODE = "nearest"
_VALID_KINDS = ("der2", "onoff")


def identify_pd_end(
    t: Any,
    pch_pir: Any = None,
    kind: str | None = None,
    *,
    window_width: int = 91,
    tmin: Any = 0,
    tmax: Any = np.inf,
) -> Any:
    """Identify the end of primary drying from Pirani pressure data.

    Parameters are plain floats in the caller's time and pressure units, or
    Pint quantities. When time inputs carry units, returned times carry the
    same unit as the input time series.

    The Savitzky-Golay ``window_width`` is in samples and should be chosen for
    the sampling density and transition width of the Pirani trace. The default
    mirrors Julia LyoPronto, but short or sparsely sampled traces may require a
    smaller odd window. The ``der2`` detector is especially sensitive when the
    window approaches the full series length.
    """

    t, pch_pir, kind = _normalize_call(t, pch_pir, kind)
    normalized_kind = _normalize_kind(kind)

    time_unit = _quantity_unit(t, "time", "t")
    pressure_unit = _quantity_unit(pch_pir, "pressure", "pch_pir")
    t_values = to_magnitude_array(t, time_unit)
    p_values = to_magnitude_array(pch_pir, pressure_unit)

    _validate_input_arrays(t_values, p_values)
    width = _validate_window_width(window_width, len(t_values))

    tmin_value = _time_bound_to_magnitude(tmin, time_unit, "tmin")
    tmax_value = _time_bound_to_magnitude(tmax, time_unit, "tmax")
    if not tmin_value < tmax_value:
        raise ValueError("tmin must be less than tmax")

    analysis_indices = np.flatnonzero((tmin_value < t_values) & (t_values < tmax_value))
    if analysis_indices.size == 0:
        raise ValueError("analysis window must contain at least one time point")

    if normalized_kind == "der2":
        deriv2 = savgol_filter(
            p_values,
            width,
            _POLY_ORDER,
            deriv=2,
            delta=_mean_dt(t_values),
            mode=_SG_MODE,
        )
        end_index = analysis_indices[np.argmax(deriv2[analysis_indices])]
        return _with_time_units(t_values[end_index], time_unit)

    smoothed = savgol_filter(
        p_values,
        width,
        _POLY_ORDER,
        deriv=0,
        mode=_SG_MODE,
    )
    deriv1 = savgol_filter(
        p_values,
        width,
        _POLY_ORDER,
        deriv=1,
        delta=_mean_dt(t_values),
        mode=_SG_MODE,
    )

    mid_index = analysis_indices[np.argmin(deriv1[analysis_indices])]
    slope = deriv1[mid_index]
    if np.isclose(slope, 0.0):
        raise ValueError("Pirani pressure derivative is zero in the analysis window")

    t_mid = t_values[mid_index]
    p_mid = smoothed[mid_index]
    p_window = smoothed[analysis_indices]
    onset = (np.max(p_window) - p_mid) / slope + t_mid
    offset = (np.min(p_window) - p_mid) / slope + t_mid
    return (
        _with_time_units(onset, time_unit),
        _with_time_units(offset, time_unit),
    )


def _normalize_call(t: Any, pch_pir: Any, kind: str | None) -> tuple[Any, Any, str]:
    if kind is None:
        if isinstance(pch_pir, str):
            data_t, data_pch_pir = _extract_data(t)
            return data_t, data_pch_pir, pch_pir
        raise TypeError(
            'identify_pd_end requires kind="der2" or kind="onoff" '
            "when t and pch_pir are passed separately"
        )

    if pch_pir is None:
        data_t, data_pch_pir = _extract_data(t)
        return data_t, data_pch_pir, kind

    return t, pch_pir, kind


def _extract_data(data: Any) -> tuple[Any, Any]:
    if isinstance(data, Mapping):
        missing = [key for key in ("t", "pch_pir") if key not in data]
        if missing:
            raise ValueError("data mapping must contain 't' and 'pch_pir'")
        return data["t"], data["pch_pir"]
    if hasattr(data, "t") and hasattr(data, "pch_pir"):
        return data.t, data.pch_pir
    raise ValueError("data must be a mapping or object with t and pch_pir")


def _normalize_kind(kind: Any) -> str:
    normalized = kind.lower() if isinstance(kind, str) else kind
    if normalized not in _VALID_KINDS:
        raise ValueError('kind must be "der2" or "onoff"')
    return normalized


def _validate_input_arrays(t_values: np.ndarray, p_values: np.ndarray) -> None:
    if t_values.ndim != 1 or p_values.ndim != 1:
        raise ValueError("t and pch_pir must be one-dimensional arrays")
    if len(t_values) != len(p_values):
        raise ValueError("t and pch_pir must have the same length")
    if len(t_values) < 2:
        raise ValueError("t and pch_pir must contain at least two points")
    if not np.all(np.isfinite(t_values)):
        raise ValueError("t must contain only finite values")
    if not np.all(np.isfinite(p_values)):
        raise ValueError("pch_pir must contain only finite values")
    if not np.all(np.diff(t_values) > 0.0):
        raise ValueError("t must be strictly increasing")


def _validate_window_width(window_width: int, input_length: int) -> int:
    try:
        width = operator.index(window_width)
    except TypeError as exc:
        raise ValueError("window_width must be an odd integer") from exc
    if width <= _POLY_ORDER:
        raise ValueError("window_width must be at least 5 for a cubic filter")
    if width % 2 == 0:
        raise ValueError("window_width must be odd")
    if width > input_length:
        raise ValueError("window_width cannot exceed input length")
    return width


def _quantity_unit(values: Any, dimension: str, name: str) -> Any:
    quantity = _first_quantity(values)
    if quantity is None:
        return None
    if not quantity.check(f"[{dimension}]"):
        raise ValueError(f"{name} values must have units of {dimension}")
    return quantity.units


def _first_quantity(values: Any) -> Any:
    if is_quantity(values):
        return values
    if isinstance(values, np.ndarray) and values.dtype != object:
        return None
    if isinstance(values, Iterable) and not isinstance(values, (str, bytes)):
        for value in values:
            if is_quantity(value):
                return value
    return None


def _time_bound_to_magnitude(value: Any, time_unit: Any, name: str) -> float:
    if is_quantity(value):
        if time_unit is None:
            raise ValueError(f"{name} cannot have units when t is unitless")
        if not value.check("[time]"):
            raise ValueError(f"{name} must have units of time")
        return to_magnitude(value, time_unit)
    return float(value)


def _mean_dt(t_values: np.ndarray) -> float:
    return float(np.mean(np.diff(t_values)))


def _with_time_units(value: float, time_unit: Any) -> Any:
    if time_unit is None:
        return float(value)
    return Q_(float(value), time_unit)


__all__ = ["identify_pd_end"]
