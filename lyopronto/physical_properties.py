"""Julia-parity physical-property helpers.

The constants in this module are Pint quantities that mirror the Unitful
constants in Julia ``physical_properties.jl``. Functions also accept plain
numbers in the same base units used by the Julia code: kelvin, pascal, and
hertz.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import numpy as np

from .typed import Q_, is_quantity, to_magnitude_array


__all__ = [
    "Mw",
    "e_0",
    "sigma",
    "delta_h_sub",
    "delta_h",
    "theta_sub",
    "k_ice",
    "cp_ice",
    "rho_ice",
    "k_gl",
    "cp_gl",
    "rho_glass",
    "epp_gl",
    "k_sucrose",
    "rho_sucrose",
    "mu_vap",
    "calc_psub",
    "calc_tsub",
    "calc_Tsub",
    "eppf",
]


Mw = Q_(18.015, "gram / mole")
e_0 = Q_(8.854187e-12, "farad / meter")
sigma = Q_(5.670367e-8, "watt / meter ** 2 / kelvin ** 4")

delta_h_sub = Q_(2838.0, "kilojoule / kilogram")
delta_h = delta_h_sub
_gas_constant = Q_(1.0, "molar_gas_constant")
theta_sub = (delta_h_sub * Mw / _gas_constant).to("kelvin")

k_ice = Q_(2.4, "watt / meter / kelvin")
cp_ice = Q_(2.09e3, "joule / kilogram / kelvin")
rho_ice = Q_(0.918, "gram / centimeter ** 3")

k_gl = Q_(1.0, "watt / meter / kelvin")
cp_gl = Q_(839.0, "joule / kilogram / kelvin")
rho_glass = Q_(2.23, "gram / centimeter ** 3")
epp_gl = 2.4e-2

k_sucrose = Q_(0.139, "watt / meter / kelvin")
rho_sucrose = Q_(892.0, "kilogram / meter ** 3")
mu_vap = Q_(8.1, "micropascal * second")

_PSUB_PREF_PA = 359.7e10
_THETA_SUB_K = theta_sub.to("kelvin").magnitude

_TREF_K = np.array([190, 200, 220, 240, 248, 253, 258, 263, 265], dtype=float)
_BREF = np.array(
    [1.537, 1.747, 2.469, 3.495, 4.006, 4.380, 4.696, 5.277, 5.646],
    dtype=float,
) * 1e-5
_CREF = np.array(
    [1.175, 1.168, 1.129, 1.088, 1.073, 1.062, 1.056, 1.038, 1.024],
    dtype=float,
)
_DIELECTRIC_BETA_K = 2.37e4
_DIELECTRIC_T0_K = 15.0
_DIELECTRIC_E1_OVER_R_K = 55.3e3 / 8.3145
_DIELECTRIC_E2_OVER_R_K = 22.6e3 / 8.3145


def _contains_quantity(value: Any) -> bool:
    if is_quantity(value):
        return True
    if isinstance(value, Iterable) and not isinstance(value, (str, bytes)):
        return any(_contains_quantity(item) for item in value)
    if isinstance(value, np.ndarray) and value.dtype == object:
        return any(_contains_quantity(item) for item in value.ravel())
    return False


def _maybe_scalar(value: Any) -> Any:
    arr = np.asarray(value)
    if arr.ndim == 0:
        return float(arr)
    return value


def _linear_interp_extrap(x: Any, xp: np.ndarray, fp: np.ndarray) -> np.ndarray:
    x_arr = np.asarray(x, dtype=float)
    flat = x_arr.ravel()
    result = np.interp(flat, xp, fp)

    below = flat < xp[0]
    if np.any(below):
        slope = (fp[1] - fp[0]) / (xp[1] - xp[0])
        result[below] = fp[0] + (flat[below] - xp[0]) * slope

    above = flat > xp[-1]
    if np.any(above):
        slope = (fp[-1] - fp[-2]) / (xp[-1] - xp[-2])
        result[above] = fp[-1] + (flat[above] - xp[-1]) * slope

    return result.reshape(x_arr.shape)


def calc_psub(T: Any) -> Any:
    """Return sublimation pressure at temperature ``T``.

    Plain numbers are interpreted as kelvin and return pascal magnitudes.
    Pint quantities are converted to kelvin and return pascal quantities.
    """

    temperatures = to_magnitude_array(T, "kelvin")
    pressure = _PSUB_PREF_PA * np.exp(-_THETA_SUB_K / temperatures)
    if _contains_quantity(T):
        return Q_(_maybe_scalar(pressure), "pascal")
    return _maybe_scalar(pressure)


def calc_tsub(p: Any) -> Any:
    """Return sublimation temperature at pressure ``p``.

    Plain numbers are interpreted as pascals and return kelvin magnitudes.
    Pint quantities are converted to pascals and return kelvin quantities.
    """

    pressure = to_magnitude_array(p, "pascal")
    temperature = -_THETA_SUB_K / np.log(pressure / _PSUB_PREF_PA)
    if _contains_quantity(p):
        return Q_(_maybe_scalar(temperature), "kelvin")
    return _maybe_scalar(temperature)


calc_Tsub = calc_tsub


def eppf(T: Any, f: Any) -> Any:
    """Return ice dielectric loss as a function of temperature and frequency.

    Plain numbers are interpreted as kelvin and hertz. Pint inputs are
    converted to those units. The result is dimensionless.
    """

    temperature = to_magnitude_array(T, "kelvin")
    frequency_hz = to_magnitude_array(f, "hertz")
    frequency_ghz = frequency_hz / 1e9

    arrhenius = np.where(
        temperature > 223.0,
        1.08 * np.exp(_DIELECTRIC_E1_OVER_R_K / temperature),
        4.9e7 * np.exp(_DIELECTRIC_E2_OVER_R_K / temperature),
    )
    relaxation = 5.3e-16 * arrhenius
    resonant_frequency = 1.0 / (2.0 * np.pi * relaxation)
    debye_amplitude = (
        _DIELECTRIC_BETA_K / (temperature - _DIELECTRIC_T0_K)
    ) * resonant_frequency

    b_coeff = _linear_interp_extrap(temperature, _TREF_K, _BREF)
    c_coeff = _linear_interp_extrap(temperature, _TREF_K, _CREF)

    with np.errstate(divide="ignore", invalid="ignore"):
        loss = (
            debye_amplitude / frequency_hz
            + b_coeff * np.power(frequency_ghz, c_coeff)
        )
    loss = np.where(frequency_hz == 0.0, 0.0, loss)
    return _maybe_scalar(loss)
