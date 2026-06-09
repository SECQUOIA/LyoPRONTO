"""ECCURT equipment-capability interpolation.

Plain numeric inputs use explicit canonical units:

- duct diameter, valve thickness, and duct length in millimeters;
- chamber volume in cubic meters;
- mass flow in kilograms per hour;
- pressure in millitorr.

The ECCURT pressure tables and line construction were ported from
``LyoHUB/LyoPronto.jl`` ``src/eq_cap_ECCURT.jl`` at commit
``f452ad4ea8f8569783c9f05fa004b7258a158438``. The source tables are
MIT-derived upstream material.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import warnings

import numpy as np
from scipy.interpolate import RegularGridInterpolator

from .typed import Q_, as_quantity, is_quantity, to_magnitude

_MASS_FLOW_UNIT = "kilogram / hour"
_PRESSURE_UNIT = "millitorr"
_LINE_SLOPE_UNIT = "kilogram / hour / millitorr"
_LINE_INTERCEPT_UNIT = "kilogram / hour"

M_DOT = np.array([0.1291, 0.4644, 0.7776, 1.1772], dtype=float)
"""Mass-flow sample points in kilograms per hour."""

D_SAMPLE = np.array([59.6, 98.0, 304.8], dtype=float)
"""Duct diameter sample points in millimeters."""

DA_SAMPLE = np.array([2.24, 6.49, 21.75], dtype=float)
"""Duct-diameter to valve-thickness ratio sample points."""

L_SAMPLE = np.array([100.0, 441.0, 890.0], dtype=float)
"""Duct length sample points in millimeters, sorted increasing."""

VOLUME_SAMPLE = np.array([0.092, 0.44], dtype=float)
"""Chamber volume sample points in cubic meters."""

PCH = np.array(
    [
        227.9,
        557.5,
        865.4,
        1258.2,
        223.8,
        556.8,
        867.8,
        1264.6,
        110.7,
        261.1,
        400.0,
        579.2,
        110.3,
        260.2,
        400.2,
        578.8,
        13.4,
        32.5,
        48.4,
        68.0,
        12.7,
        30.9,
        46.15,
        65.0,
        175.2,
        374.3,
        560.2,
        797.5,
        177.9,
        390.8,
        589.6,
        843.3,
        79.0,
        166.6,
        248.3,
        352.6,
        64.9,
        159.3,
        247.5,
        360.0,
        11.9,
        22.8,
        33.0,
        46.0,
        11.7,
        21.1,
        30.0,
        41.3,
        169.4,
        351.7,
        522.0,
        740.0,
        173.2,
        358.1,
        530.9,
        751.3,
        75.0,
        154.3,
        228.0,
        322.0,
        75.9,
        154.6,
        228.0,
        321.7,
        8.9,
        20.9,
        30.6,
        42.5,
        9.8,
        18.69,
        27.0,
        37.6,
        241.3,
        635.8,
        1004.1,
        1474.2,
        248.5,
        644.4,
        1014.1,
        1485.8,
        93.7,
        250.5,
        390.4,
        569.3,
        93.7,
        250.6,
        390.9,
        569.8,
        15.1,
        31.8,
        47.4,
        67.3,
        14.4,
        30.4,
        45.4,
        64.5,
        158.4,
        377.2,
        581.6,
        842.4,
        168.4,
        399.1,
        614.7,
        889.7,
        67.0,
        151.7,
        230.9,
        331.9,
        66.5,
        151.1,
        230.1,
        331.0,
        10.9,
        21.5,
        31.5,
        44.2,
        14.4,
        22.5,
        30.0,
        39.6,
        148.6,
        344.3,
        527.1,
        760.3,
        151.7,
        351.1,
        537.4,
        775.1,
        60.9,
        136.7,
        207.6,
        298.0,
        60.5,
        136.1,
        206.6,
        296.6,
        10.0,
        19.8,
        29.0,
        40.7,
        8.28,
        16.93,
        25.0,
        35.3,
        203.8,
        605.4,
        980.4,
        1458.9,
        158.5,
        571.2,
        956.7,
        1448.6,
        88.0,
        239.5,
        381.0,
        561.5,
        88.5,
        239.4,
        380.4,
        560.2,
        14.3,
        31.2,
        47.0,
        67.2,
        13.3,
        29.5,
        44.7,
        64.0,
        116.4,
        331.7,
        532.9,
        789.5,
        118.6,
        338.2,
        543.2,
        804.8,
        50.2,
        133.8,
        212.0,
        311.6,
        50.5,
        133.4,
        210.9,
        309.7,
        9.9,
        20.6,
        30.6,
        43.4,
        9.3,
        18.6,
        27.3,
        38.5,
        107.2,
        295.1,
        470.6,
        694.5,
        109.1,
        299.9,
        478.1,
        705.5,
        43.6,
        116.8,
        185.2,
        272.4,
        43.9,
        116.4,
        184.1,
        270.5,
        9.2,
        18.9,
        28.0,
        39.5,
        7.3,
        15.8,
        23.8,
        33.9,
    ],
    dtype=float,
).reshape((4, 2, 3, 3, 3), order="F")
"""Pressure table in millitorr with axes ``mass_flow, volume, d, d/vt, l``."""


@dataclass(frozen=True)
class ECLine:
    """Linear equipment capability ``kg/hr = k * pressure_mTorr + b``."""

    k: Any
    b: Any

    def __call__(self, pressure: Any) -> Any:
        if is_quantity(self.k) or is_quantity(self.b) or is_quantity(pressure):
            k = as_quantity(self.k, _LINE_SLOPE_UNIT)
            b = as_quantity(self.b, _LINE_INTERCEPT_UNIT)
            pressure_q = as_quantity(pressure, _PRESSURE_UNIT)
            return k * pressure_q + b
        return self.k * np.asarray(pressure) + self.b


def _regular_grid(points: tuple[np.ndarray, ...], values: np.ndarray):
    return RegularGridInterpolator(
        points,
        values,
        bounds_error=False,
        fill_value=None,
    )


_AK = (M_DOT[2] - M_DOT[3]) / (PCH[2, 0, :, :, :] - PCH[3, 0, :, :, :])
_AB = M_DOT[2] - _AK * PCH[2, 0, :, :, :]
_BK = (M_DOT[2] - M_DOT[3]) / (PCH[2, 1, :, :, :] - PCH[3, 1, :, :, :])
_BB = M_DOT[2] - _BK * PCH[2, 1, :, :, :]

_ALPHA = np.stack((_AK[:, :, ::-1], _BK[:, :, ::-1]), axis=-1)
_BETA = np.stack((_AB[:, :, ::-1], _BB[:, :, ::-1]), axis=-1)
_ALPHA_INTERP = _regular_grid((D_SAMPLE, DA_SAMPLE, L_SAMPLE, VOLUME_SAMPLE), _ALPHA)
_BETA_INTERP = _regular_grid((D_SAMPLE, DA_SAMPLE, L_SAMPLE, VOLUME_SAMPLE), _BETA)

_PCH_INTERPS = tuple(
    _regular_grid(
        (VOLUME_SAMPLE, D_SAMPLE, DA_SAMPLE, L_SAMPLE),
        PCH[index, :, :, :, ::-1],
    )
    for index in range(len(M_DOT))
)


def _as_output(value: Any, unit: str, use_quantities: bool) -> Any:
    if use_quantities:
        return Q_(value, unit)
    arr = np.asarray(value)
    if arr.ndim == 0:
        return float(arr)
    return arr


def _geometry_magnitudes(
    d: Any,
    valve_thickness: Any,
    duct_length: Any,
    chamber_volume: Any,
) -> tuple[float, float, float, float, bool]:
    use_quantities = any(
        is_quantity(value)
        for value in (d, valve_thickness, duct_length, chamber_volume)
    )
    return (
        to_magnitude(d, "millimeter"),
        to_magnitude(valve_thickness, "millimeter"),
        to_magnitude(duct_length, "millimeter"),
        to_magnitude(chamber_volume, "meter ** 3"),
        use_quantities,
    )


def _warn_if_extrapolating(
    d_mm: float,
    diameter_to_valve: float,
    duct_length_mm: float,
    chamber_volume_m3: float,
) -> None:
    if (
        not D_SAMPLE[0] <= d_mm <= D_SAMPLE[-1]
        or not DA_SAMPLE[0] <= diameter_to_valve <= DA_SAMPLE[-1]
        or not L_SAMPLE[0] <= duct_length_mm <= L_SAMPLE[-1]
        or not VOLUME_SAMPLE[0] <= chamber_volume_m3 <= VOLUME_SAMPLE[-1]
    ):
        warnings.warn(
            "Input geometry parameters are outside the range of the original "
            "ECCURT data, so linear extrapolation is being used. Results may "
            "be inaccurate.",
            UserWarning,
            stacklevel=3,
        )


def eq_cap_line(
    d: Any,
    valve_thickness: Any,
    duct_length: Any,
    chamber_volume: Any,
) -> ECLine:
    """Return the original ECCURT equipment-capability line.

    Plain floats are interpreted as ``d``/``valve_thickness``/``duct_length`` in
    millimeters and ``chamber_volume`` in cubic meters. The returned line maps
    pressure in millitorr to mass flow in kilograms per hour.
    """

    d_mm, vt_mm, l_mm, volume_m3, use_quantities = _geometry_magnitudes(
        d,
        valve_thickness,
        duct_length,
        chamber_volume,
    )
    diameter_to_valve = d_mm / vt_mm
    _warn_if_extrapolating(d_mm, diameter_to_valve, l_mm, volume_m3)
    point = (d_mm, diameter_to_valve, l_mm, volume_m3)
    k = float(_ALPHA_INTERP(point))
    b = float(_BETA_INTERP(point))
    return ECLine(
        _as_output(k, _LINE_SLOPE_UNIT, use_quantities),
        _as_output(b, _LINE_INTERCEPT_UNIT, use_quantities),
    )


def eq_cap_pressure(
    mass_flow: Any,
    d: Any,
    valve_thickness: Any,
    duct_length: Any,
    chamber_volume: Any,
) -> Any:
    """Return pressure for a mass-flow rate using the original ECCURT line.

    Plain numeric ``mass_flow`` is in kilograms per hour. Plain numeric results
    are returned in millitorr. Pint quantities are converted to these units and
    return a Pint pressure quantity.
    """

    line = eq_cap_line(d, valve_thickness, duct_length, chamber_volume)
    if is_quantity(mass_flow) or is_quantity(line.k) or is_quantity(line.b):
        mass_flow_q = as_quantity(mass_flow, _MASS_FLOW_UNIT)
        k = as_quantity(line.k, _LINE_SLOPE_UNIT)
        b = as_quantity(line.b, _LINE_INTERCEPT_UNIT)
        return ((mass_flow_q - b) / k).to(_PRESSURE_UNIT)
    pressure = (np.asarray(mass_flow) - line.b) / line.k
    return _as_output(pressure, _PRESSURE_UNIT, False)


def eq_cap_pressures_new(
    d: Any,
    valve_thickness: Any,
    duct_length: Any,
    chamber_volume: Any,
) -> Any:
    """Return interpolated pressures at ECCURT's four mass-flow sample points.

    Plain numeric results are in millitorr and follow the same order as
    :data:`M_DOT`. Pint geometry inputs return a Pint array in millitorr.
    """

    d_mm, vt_mm, l_mm, volume_m3, use_quantities = _geometry_magnitudes(
        d,
        valve_thickness,
        duct_length,
        chamber_volume,
    )
    diameter_to_valve = d_mm / vt_mm
    _warn_if_extrapolating(d_mm, diameter_to_valve, l_mm, volume_m3)
    point = (volume_m3, d_mm, diameter_to_valve, l_mm)
    pressures = np.array([float(interp(point)) for interp in _PCH_INTERPS])
    return _as_output(pressures, _PRESSURE_UNIT, use_quantities)


def eq_cap_line_new(
    d: Any,
    valve_thickness: Any,
    duct_length: Any,
    chamber_volume: Any,
) -> ECLine:
    """Return the pressure-interpolated ECCURT equipment-capability line.

    This method interpolates the four pressure table values first, then fits
    ``kg/hr = k * pressure_mTorr + b`` by linear regression. It is generally a
    lower-error fit to the tabulated ECCURT pressures than the original line.
    """

    pressures = eq_cap_pressures_new(d, valve_thickness, duct_length, chamber_volume)
    use_quantities = is_quantity(pressures)
    pch = np.asarray(
        pressures.to(_PRESSURE_UNIT).magnitude if use_quantities else pressures,
        dtype=float,
    )

    n_md = len(M_DOT)
    spch = float(np.sum(pch))
    sum_md = float(np.sum(M_DOT))
    md_dot_pch = float(np.sum(M_DOT * pch))
    pch_sq = float(np.sum(pch**2))
    regress_denom = n_md * pch_sq - spch**2

    k = (n_md * md_dot_pch - sum_md * spch) / regress_denom
    b = (pch_sq * sum_md - spch * md_dot_pch) / regress_denom
    return ECLine(
        _as_output(k, _LINE_SLOPE_UNIT, use_quantities),
        _as_output(b, _LINE_INTERCEPT_UNIT, use_quantities),
    )


__all__ = [
    "DA_SAMPLE",
    "D_SAMPLE",
    "ECLine",
    "L_SAMPLE",
    "M_DOT",
    "PCH",
    "VOLUME_SAMPLE",
    "eq_cap_line",
    "eq_cap_line_new",
    "eq_cap_pressure",
    "eq_cap_pressures_new",
]
