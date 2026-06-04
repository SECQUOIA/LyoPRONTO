"""SCHOTT vial metadata helpers.

The values mirror the SCHOTT table used by LyoPronto.jl. Public helpers return
Pint quantities; plain numeric fill volumes are interpreted as milliliters for
legacy geometry conversion.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from types import MappingProxyType
from typing import Any

from .typed import Q_, as_quantity, is_quantity, to_magnitude

__all__ = [
    "VIAL_DIMS",
    "VialDimensions",
    "VialShape",
    "select_size",
    "get_vial_radii",
    "get_vial_thickness",
    "get_vial_mass",
    "get_vial_shape",
    "get_vial_areas",
    "make_outlines",
    "legacy_vial_geometry",
]


@dataclass(frozen=True)
class VialDimensions:
    """Raw SCHOTT dimensions for a vial size."""

    size: str
    overflow: Any
    overflow_tol: Any
    a: Any
    d1: Any
    d1_tol: Any
    d2: Any
    d3: Any
    d4: Any
    h1: Any
    h1_tol: Any
    h2: Any
    h3: Any
    h3_tol: Any
    r1: Any
    r2: Any
    s1: Any
    s1_tol: Any
    s2: Any
    t: Any
    mass: Any


@dataclass(frozen=True)
class VialShape:
    """Geometry fields used for vial/fill outlines."""

    rad_i: Any
    rad_o: Any
    bot_thick: Any
    barrel_height: Any
    curve_height: Any
    full_height: Any
    neck_inner: Any
    neck_outer: Any
    neck_curve: Any

    @property
    def product_area(self) -> Any:
        """Return the inner product area as a Pint area quantity."""

        return (math.pi * self.rad_i**2).to("centimeter ** 2")

    @property
    def vial_area(self) -> Any:
        """Return the outer vial cross-section as a Pint area quantity."""

        return (math.pi * self.rad_o**2).to("centimeter ** 2")

    def legacy_geometry(self, vfill: Any) -> dict[str, float]:
        """Return legacy ``Ap``/``Av``/``Vfill`` float values."""

        return _legacy_geometry_from_shape(self, vfill)


def _q(value: float, unit: str) -> Any:
    return Q_(value, unit)


def _build_record(row: tuple[Any, ...]) -> VialDimensions:
    (
        size,
        overflow,
        overflow_tol,
        a,
        d1,
        d1_tol,
        d2,
        d3,
        d4,
        h1,
        h1_tol,
        h2,
        h3,
        h3_tol,
        r1,
        r2,
        s1,
        s1_tol,
        s2,
        t,
        mass,
    ) = row
    return VialDimensions(
        size=size,
        overflow=_q(overflow, "milliliter"),
        overflow_tol=_q(overflow_tol, "milliliter"),
        a=_q(a, "millimeter"),
        d1=_q(d1, "millimeter"),
        d1_tol=_q(d1_tol, "millimeter"),
        d2=_q(d2, "millimeter"),
        d3=_q(d3, "millimeter"),
        d4=_q(d4, "millimeter"),
        h1=_q(h1, "millimeter"),
        h1_tol=_q(h1_tol, "millimeter"),
        h2=_q(h2, "millimeter"),
        h3=_q(h3, "millimeter"),
        h3_tol=_q(h3_tol, "millimeter"),
        r1=_q(r1, "millimeter"),
        r2=_q(r2, "millimeter"),
        s1=_q(s1, "millimeter"),
        s1_tol=_q(s1_tol, "millimeter"),
        s2=_q(s2, "millimeter"),
        t=_q(t, "millimeter"),
        mass=_q(mass, "gram"),
    )


_VIAL_ROWS = (
    (
        "2R",
        4.0,
        0.5,
        1.0,
        16.0,
        0.15,
        13.0,
        10.5,
        7.0,
        35.0,
        0.5,
        22.0,
        8.0,
        0.5,
        2.5,
        1.5,
        1.0,
        0.04,
        0.6,
        0.7,
        4.4,
    ),
    (
        "4R",
        6.0,
        0.5,
        1.0,
        16.0,
        0.15,
        13.0,
        10.5,
        7.0,
        45.0,
        0.5,
        32.0,
        8.0,
        0.5,
        2.5,
        1.5,
        1.0,
        0.04,
        0.6,
        0.7,
        5.7,
    ),
    (
        "6R",
        10.0,
        0.5,
        1.2,
        22.0,
        0.2,
        20.0,
        16.5,
        12.6,
        40.0,
        0.5,
        26.0,
        8.5,
        0.5,
        3.5,
        2.0,
        1.0,
        0.04,
        0.7,
        0.7,
        7.9,
    ),
    (
        "8R",
        11.5,
        0.5,
        1.2,
        22.0,
        0.2,
        20.0,
        16.5,
        12.6,
        45.0,
        0.5,
        31.0,
        8.5,
        0.5,
        3.5,
        2.0,
        1.0,
        0.04,
        0.7,
        0.7,
        8.7,
    ),
    (
        "10R",
        13.5,
        1.0,
        1.2,
        24.0,
        0.2,
        20.0,
        16.5,
        12.6,
        45.0,
        0.5,
        30.0,
        9.0,
        0.5,
        4.0,
        2.0,
        1.0,
        0.04,
        0.7,
        0.7,
        9.5,
    ),
    (
        "15R",
        19.0,
        1.0,
        1.2,
        24.0,
        0.2,
        20.0,
        16.5,
        12.6,
        60.0,
        0.5,
        45.0,
        9.0,
        0.5,
        4.0,
        2.0,
        1.0,
        0.04,
        0.7,
        0.7,
        12.0,
    ),
    (
        "20R",
        26.0,
        1.5,
        1.5,
        30.0,
        0.25,
        20.0,
        17.5,
        12.6,
        55.0,
        0.7,
        35.0,
        10.0,
        0.75,
        5.5,
        2.5,
        1.2,
        0.05,
        0.7,
        1.0,
        16.2,
    ),
    (
        "25R",
        32.5,
        1.5,
        1.5,
        30.0,
        0.25,
        20.0,
        17.5,
        12.6,
        65.0,
        0.7,
        45.0,
        10.0,
        0.75,
        5.5,
        2.5,
        1.2,
        0.05,
        0.7,
        1.0,
        18.9,
    ),
    (
        "30R",
        37.5,
        1.5,
        1.5,
        30.0,
        0.25,
        20.0,
        17.5,
        12.6,
        75.0,
        0.7,
        55.0,
        10.0,
        0.75,
        5.5,
        2.5,
        1.2,
        0.05,
        0.7,
        1.0,
        21.9,
    ),
    (
        "50R",
        62.0,
        4.0,
        2.5,
        40.0,
        0.4,
        20.0,
        17.5,
        12.6,
        73.0,
        0.75,
        49.0,
        10.0,
        0.75,
        6.0,
        4.0,
        1.5,
        0.07,
        0.9,
        1.5,
        34.5,
    ),
    (
        "100R",
        123.0,
        7.0,
        3.5,
        47.0,
        0.5,
        20.0,
        17.5,
        12.6,
        100.0,
        0.75,
        75.0,
        10.0,
        0.75,
        6.5,
        4.0,
        1.7,
        0.07,
        0.9,
        1.5,
        60.0,
    ),
)

VIAL_DIMS = MappingProxyType(
    {record.size: record for record in (_build_record(row) for row in _VIAL_ROWS)}
)


def _normalize_size(size: str) -> str:
    if not isinstance(size, str):
        raise ValueError("invalid vial size; expected a SCHOTT size string")
    normalized = size.strip().upper()
    if normalized not in VIAL_DIMS:
        valid = ", ".join(VIAL_DIMS)
        raise ValueError(f"invalid vial size {size!r}; expected one of: {valid}")
    return normalized


def select_size(size: str) -> VialDimensions:
    """Return the SCHOTT table record for ``size``."""

    return VIAL_DIMS[_normalize_size(size)]


def get_vial_radii(size: str) -> tuple[Any, Any]:
    """Return inner and outer vial radii for a SCHOTT size."""

    dims = select_size(size)
    rad_o = dims.d1 / 2
    rad_i = rad_o - dims.s1
    return rad_i.to("millimeter"), rad_o.to("millimeter")


def get_vial_thickness(size: str) -> Any:
    """Return vial wall thickness for a SCHOTT size."""

    return select_size(size).s1.to("millimeter")


def get_vial_mass(size: str) -> Any:
    """Return vial mass for a SCHOTT size."""

    return select_size(size).mass.to("gram")


def get_vial_shape(size: str) -> VialShape:
    """Return shape dimensions useful for drawing a vial and fill volume."""

    dims = select_size(size)
    rad_i, rad_o = get_vial_radii(size)
    return VialShape(
        rad_i=rad_i,
        rad_o=rad_o,
        bot_thick=dims.s2.to("millimeter"),
        barrel_height=dims.h2.to("millimeter"),
        curve_height=(dims.h1 - dims.h3).to("millimeter"),
        full_height=dims.h1.to("millimeter"),
        neck_inner=(dims.d4 / 2).to("millimeter"),
        neck_outer=(dims.d3 / 2).to("millimeter"),
        neck_curve=dims.r1.to("millimeter"),
    )


def get_vial_areas(size: str) -> tuple[Any, Any]:
    """Return product area ``Ap`` and vial area ``Av`` as Pint quantities."""

    shape = get_vial_shape(size)
    return shape.product_area, shape.vial_area


def _legacy_vfill(vfill: Any) -> float:
    if is_quantity(vfill):
        return to_magnitude(vfill, "milliliter")
    return float(vfill)


def _legacy_geometry_from_shape(shape: VialShape, vfill: Any) -> dict[str, float]:
    return {
        "Ap": to_magnitude(shape.product_area, "centimeter ** 2"),
        "Av": to_magnitude(shape.vial_area, "centimeter ** 2"),
        "Vfill": _legacy_vfill(vfill),
    }


def legacy_vial_geometry(size: str, vfill: Any) -> dict[str, float]:
    """Return legacy calculator vial geometry for ``size`` and fill volume."""

    return get_vial_shape(size).legacy_geometry(vfill)


def make_outlines(
    dims: VialShape,
    vfill: Any,
) -> tuple[list[tuple[Any, Any]], list[tuple[Any, Any]]]:
    """Return vial and fill outline points for a vial shape.

    The returned coordinates are Pint length quantities. Plain numeric fill
    volumes are interpreted as milliliters.
    """

    fill_volume = as_quantity(vfill, "milliliter")
    zero = Q_(0.0, "millimeter")
    rad_o = dims.rad_o
    rad_i = dims.rad_i
    bot_thick = dims.bot_thick
    neck_inner = dims.neck_inner
    neck_outer = dims.neck_outer
    curve_height = dims.curve_height
    barrel_height = dims.barrel_height
    full_height = dims.full_height

    vpoints = [
        (-rad_o, zero),
        (rad_o, zero),
        (rad_o, barrel_height),
        (neck_outer, curve_height),
        (neck_outer, full_height),
        (neck_inner, full_height),
        (neck_inner, curve_height),
        (rad_i, barrel_height),
        (rad_i, bot_thick),
        (-rad_i, bot_thick),
        (-rad_i, barrel_height),
        (-neck_inner, curve_height),
        (-neck_inner, full_height),
        (-neck_outer, full_height),
        (-neck_outer, curve_height),
        (-rad_o, barrel_height),
        (-rad_o, zero),
    ]
    fill_height = (fill_volume / (math.pi * rad_i**2)).to("millimeter")
    fpoints = [
        (-rad_i, bot_thick),
        (rad_i, bot_thick),
        (rad_i, bot_thick + fill_height),
        (-rad_i, bot_thick + fill_height),
        (-rad_i, bot_thick),
    ]
    return vpoints, fpoints
