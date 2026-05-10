# Copyright (C) 2026, SECQUOIA

"""Validation utilities for benchmark outputs.

Computes physical residuals and simple quality checks.
Returns a dict of metrics and flags.
"""

from __future__ import annotations

from typing import Any

import numpy as np

# Column indices per project instructions
IDX_TIME = 0
IDX_TSUB = 1
IDX_TBOT = 2
IDX_TSH = 3
IDX_PCH = 4  # mTorr
IDX_FLUX = 5
IDX_PERCENT = 6  # percent_dried (0-100%)
TEMP_TOL = 1e-6
RAMP_TOL = 1e-9
DRYNESS_TARGET_PERCENT = 98.9
DRYNESS_TOL_PERCENT = 0.1


def _safe(arr: np.ndarray) -> np.ndarray:
    return arr if arr.size else np.array([])


def _max_abs_rate(values: np.ndarray, time: np.ndarray) -> float:
    """Return the maximum absolute first-difference rate over positive intervals."""
    if values.size < 2 or time.size < 2:
        return 0.0
    dt = np.diff(time)
    positive = dt > 0
    if not np.any(positive):
        return 0.0
    rates = np.diff(values)[positive] / dt[positive]
    return float(np.max(np.abs(rates)))


def _ramp_metrics(
    values: np.ndarray,
    time: np.ndarray,
    limit: float | None,
    *,
    metric_name: str,
    unit: str,
) -> dict[str, Any]:
    """Compute ramp-rate metrics using the caller-provided output units."""
    key_prefix = f"{metric_name}_{unit}"
    if limit is None:
        return {
            f"{metric_name}_limit_{unit}": None,
            f"max_{key_prefix}": None,
            f"max_{metric_name}_violation_{unit}": None,
            f"{metric_name}_ok": None,
        }

    max_rate = _max_abs_rate(values, time)
    violation = max(0.0, max_rate - float(limit))
    return {
        f"{metric_name}_limit_{unit}": float(limit),
        f"max_{key_prefix}": max_rate,
        f"max_{metric_name}_violation_{unit}": float(violation),
        f"{metric_name}_ok": bool(violation <= RAMP_TOL),
    }


def compute_residuals(
    traj: np.ndarray,
    product_critical_temp: float | None = None,
    tsh_ramp_rate: float | None = None,
    pch_ramp_rate: float | None = None,
    dryness_target_percent: float = DRYNESS_TARGET_PERCENT,
) -> dict[str, Any]:
    """Compute residual style metrics for a trajectory."""
    if traj.size == 0:
        return {
            "n_points": 0,
            "final_percent_dried": None,
            "dryness_target_percent": float(dryness_target_percent),
            "dryness_tolerance_percent": DRYNESS_TOL_PERCENT,
            "final_dryness_shortfall_percent": None,
            "monotonic_dried": None,
            "tsh_bounds_ok": None,
            "pch_positive": None,
            "flux_nonnegative": None,
            "dryness_target_met": None,
            "product_temp_ok": None,
            "max_Tbot": None,
            "product_critical_temp": product_critical_temp,
            "max_product_temp_violation_C": None,
            "tsh_ramp_limit_C_per_hr": tsh_ramp_rate,
            "max_tsh_ramp_C_per_hr": None,
            "max_tsh_ramp_violation_C_per_hr": None,
            "tsh_ramp_ok": None if tsh_ramp_rate is None else False,
            "pch_ramp_limit_Torr_per_hr": pch_ramp_rate,
            "max_pch_ramp_Torr_per_hr": None,
            "max_pch_ramp_violation_Torr_per_hr": None,
            "pch_ramp_ok": None if pch_ramp_rate is None else False,
        }
    time = traj[:, IDX_TIME]
    percent = traj[:, IDX_PERCENT]
    tbot = traj[:, IDX_TBOT]
    tsh = traj[:, IDX_TSH]
    pch_mTorr = traj[:, IDX_PCH]
    flux = traj[:, IDX_FLUX]

    # Monotonicity (allow tiny numerical dips)
    diffs = np.diff(percent)
    monotonic = bool(np.all(diffs >= -1e-2))  # tolerance in percentage units

    tsh_ok = bool(np.all((tsh > -60) & (tsh < 60)))
    pch_pos = bool(np.all(pch_mTorr > 0))
    flux_ok = bool(np.all(flux >= -1e-8))

    dryness_threshold = float(dryness_target_percent) - DRYNESS_TOL_PERCENT
    dryness_shortfall = max(0.0, float(dryness_target_percent) - float(percent[-1]))
    dryness_target = bool(percent[-1] >= dryness_threshold)
    max_tbot = float(np.max(tbot))
    product_temp_violation = (
        None
        if product_critical_temp is None
        else max(0.0, max_tbot - float(product_critical_temp))
    )
    product_temp_ok = (
        None
        if product_critical_temp is None
        else bool(product_temp_violation <= TEMP_TOL)
    )
    tsh_ramp_metrics = _ramp_metrics(
        tsh,
        time,
        tsh_ramp_rate,
        metric_name="tsh_ramp",
        unit="C_per_hr",
    )
    pch_ramp_metrics = _ramp_metrics(
        pch_mTorr / 1000.0,
        time,
        pch_ramp_rate,
        metric_name="pch_ramp",
        unit="Torr_per_hr",
    )

    metrics = {
        "n_points": int(traj.shape[0]),
        "final_percent_dried": float(percent[-1]),
        "dryness_target_percent": float(dryness_target_percent),
        "dryness_tolerance_percent": DRYNESS_TOL_PERCENT,
        "final_dryness_shortfall_percent": float(dryness_shortfall),
        "max_Tbot": max_tbot,
        "monotonic_dried": monotonic,
        "tsh_bounds_ok": tsh_ok,
        "pch_positive": pch_pos,
        "flux_nonnegative": flux_ok,
        "dryness_target_met": dryness_target,
        "product_temp_ok": product_temp_ok,
        "product_critical_temp": product_critical_temp,
        "max_product_temp_violation_C": product_temp_violation,
    }
    metrics.update(tsh_ramp_metrics)
    metrics.update(pch_ramp_metrics)
    return metrics


def compare_trajectories(
    scipy_traj: np.ndarray,
    pyomo_traj: np.ndarray,
    rtol: float = 0.05,
    atol_temp: float = 0.5,
    atol_pch: float = 5.0,
) -> dict[str, Any]:
    """Compare scipy and Pyomo trajectories point-by-point.

    Interpolates Pyomo trajectory onto scipy time grid for fair comparison.
    Returns metrics quantifying agreement between the two solutions.

    Parameters
    ----------
    scipy_traj : np.ndarray
        Scipy trajectory array (n_scipy, 7): time, Tsub, Tbot, Tsh, Pch_mTorr, flux, percent_dried
    pyomo_traj : np.ndarray
        Pyomo trajectory array (n_pyomo, 7): same columns
    rtol : float
        Relative tolerance for "close" comparison (default 5%)
    atol_temp : float
        Absolute tolerance for temperatures in °C (default 0.5°C)
    atol_pch : float
        Absolute tolerance for pressure in mTorr (default 5 mTorr)

    Returns
    -------
    Dict[str, Any]
        Comparison metrics:
        - matched: bool (trajectories are close within tolerances)
        - objective_diff_hr: float (difference in final time)
        - objective_ratio: float (pyomo_time / scipy_time)
        - max_Tsh_diff: float (max shelf temp difference in °C)
        - max_Pch_diff: float (max pressure difference in mTorr)
        - max_Tsub_diff: float (max sublimation temp difference in °C)
        - rmse_Tsh: float (RMSE of shelf temperature)
        - rmse_Pch: float (RMSE of chamber pressure)
        - mean_percent_dried_diff: float (mean difference in drying percentage)
        - n_scipy_points: int
        - n_pyomo_points: int
        - interpolated: bool (True if interpolation was used)
    """
    # Handle empty trajectories
    if scipy_traj.size == 0 or pyomo_traj.size == 0:
        return {
            "matched": False,
            "objective_diff_hr": None,
            "objective_ratio": None,
            "max_Tsh_diff": None,
            "max_Pch_diff": None,
            "max_Tsub_diff": None,
            "rmse_Tsh": None,
            "rmse_Pch": None,
            "mean_percent_dried_diff": None,
            "n_scipy_points": len(scipy_traj) if scipy_traj.size > 0 else 0,
            "n_pyomo_points": len(pyomo_traj) if pyomo_traj.size > 0 else 0,
            "interpolated": False,
            "error": "Empty trajectory",
        }

    # Extract time vectors
    t_scipy = scipy_traj[:, IDX_TIME]
    t_pyomo = pyomo_traj[:, IDX_TIME]

    # Objective times
    obj_scipy = float(t_scipy[-1])
    obj_pyomo = float(t_pyomo[-1])
    obj_diff = obj_pyomo - obj_scipy
    obj_ratio = obj_pyomo / obj_scipy if obj_scipy > 0 else None

    # Interpolate Pyomo onto scipy time grid for point-by-point comparison
    # Use common time range
    t_min = max(t_scipy[0], t_pyomo[0])
    t_max = min(t_scipy[-1], t_pyomo[-1])

    # Filter scipy points within common range
    mask = (t_scipy >= t_min) & (t_scipy <= t_max)
    t_common = t_scipy[mask]

    if len(t_common) < 2:
        return {
            "matched": False,
            "objective_diff_hr": obj_diff,
            "objective_ratio": obj_ratio,
            "max_Tsh_diff": None,
            "max_Pch_diff": None,
            "max_Tsub_diff": None,
            "rmse_Tsh": None,
            "rmse_Pch": None,
            "mean_percent_dried_diff": None,
            "n_scipy_points": len(scipy_traj),
            "n_pyomo_points": len(pyomo_traj),
            "interpolated": False,
            "error": "Insufficient overlap",
        }

    # Interpolate Pyomo values onto common time grid
    pyomo_interp = np.zeros((len(t_common), 7))
    pyomo_interp[:, IDX_TIME] = t_common
    for col in [IDX_TSUB, IDX_TBOT, IDX_TSH, IDX_PCH, IDX_FLUX, IDX_PERCENT]:
        pyomo_interp[:, col] = np.interp(t_common, t_pyomo, pyomo_traj[:, col])

    # Get scipy values at common times
    scipy_common = scipy_traj[mask]

    # Compute differences
    Tsh_diff = pyomo_interp[:, IDX_TSH] - scipy_common[:, IDX_TSH]
    Pch_diff = pyomo_interp[:, IDX_PCH] - scipy_common[:, IDX_PCH]
    Tsub_diff = pyomo_interp[:, IDX_TSUB] - scipy_common[:, IDX_TSUB]
    dried_diff = pyomo_interp[:, IDX_PERCENT] - scipy_common[:, IDX_PERCENT]

    max_Tsh_diff = float(np.max(np.abs(Tsh_diff)))
    max_Pch_diff = float(np.max(np.abs(Pch_diff)))
    max_Tsub_diff = float(np.max(np.abs(Tsub_diff)))
    rmse_Tsh = float(np.sqrt(np.mean(Tsh_diff**2)))
    rmse_Pch = float(np.sqrt(np.mean(Pch_diff**2)))
    mean_dried_diff = float(np.mean(np.abs(dried_diff)))

    # Check if trajectories match within tolerances
    temp_ok = (max_Tsh_diff <= atol_temp) and (max_Tsub_diff <= atol_temp)
    pch_ok = max_Pch_diff <= atol_pch
    obj_ok = abs(obj_diff) <= rtol * abs(obj_scipy) if obj_scipy > 0 else False
    matched = temp_ok and pch_ok and obj_ok

    return {
        "matched": matched,
        "objective_diff_hr": obj_diff,
        "objective_ratio": obj_ratio,
        "max_Tsh_diff": max_Tsh_diff,
        "max_Pch_diff": max_Pch_diff,
        "max_Tsub_diff": max_Tsub_diff,
        "rmse_Tsh": rmse_Tsh,
        "rmse_Pch": rmse_Pch,
        "mean_percent_dried_diff": mean_dried_diff,
        "n_scipy_points": len(scipy_traj),
        "n_pyomo_points": len(pyomo_traj),
        "interpolated": True,
    }


__all__ = ["compute_residuals", "compare_trajectories"]
