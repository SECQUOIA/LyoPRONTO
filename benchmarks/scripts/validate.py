"""Validation utilities for benchmark outputs.

Computes physical residuals and simple quality checks.
Returns a dict of metrics and flags.
"""
from __future__ import annotations
import numpy as np
from typing import Dict, Any

# Column indices per project instructions
IDX_TIME = 0
IDX_TSUB = 1
IDX_TBOT = 2
IDX_TSH  = 3
IDX_PCH  = 4  # mTorr
IDX_FLUX = 5
IDX_FRAC = 6

def _safe(arr: np.ndarray) -> np.ndarray:
    return arr if arr.size else np.array([])

def compute_residuals(traj: np.ndarray) -> Dict[str, Any]:
    """Compute residual style metrics for a trajectory."""
    if traj.size == 0:
        return {
            "n_points": 0,
            "final_frac_dried": None,
            "monotonic_dried": None,
            "tsh_bounds_ok": None,
            "pch_positive": None,
            "flux_nonnegative": None,
            "dryness_target_met": None,
        }
    frac = traj[:, IDX_FRAC]
    tsh = traj[:, IDX_TSH]
    pch_mTorr = traj[:, IDX_PCH]
    flux = traj[:, IDX_FLUX]

    # Monotonicity (allow tiny numerical dips)
    diffs = np.diff(frac)
    monotonic = bool(np.all(diffs >= -1e-4))

    tsh_ok = bool(np.all((tsh > -60) & (tsh < 60)))
    pch_pos = bool(np.all(pch_mTorr > 0))
    flux_ok = bool(np.all(flux >= -1e-8))

    dryness_target = frac[-1] >= 0.989 - 1e-3

    return {
        "n_points": int(traj.shape[0]),
        "final_frac_dried": float(frac[-1]),
        "monotonic_dried": monotonic,
        "tsh_bounds_ok": tsh_ok,
        "pch_positive": pch_pos,
        "flux_nonnegative": flux_ok,
        "dryness_target_met": dryness_target,
    }


def validate_constraints(
    traj: np.ndarray, 
    T_pr_crit: float = -25.0,
    ramp_Tsh_max: float | None = None,
    ramp_Pch_max: float | None = None,
    tolerance: float = 1e-3
) -> Dict[str, Any]:
    """Validate that a trajectory satisfies all optimization constraints.
    
    Args:
        traj: Trajectory array (N x 7): [time, Tsub, Tbot, Tsh, Pch_mTorr, flux, frac_dried]
        T_pr_crit: Critical product temperature [°C] (Tsub must stay below this)
        ramp_Tsh_max: Maximum shelf temperature ramp rate [°C/hr] (None = no constraint)
        ramp_Pch_max: Maximum chamber pressure ramp rate [Torr/hr] (None = no constraint)
        tolerance: Numerical tolerance for constraint violations
        
    Returns:
        Dict with validation results including:
        - constraints_satisfied: Overall pass/fail
        - dryness_ok: Final dried fraction >= 0.99
        - temperature_ok: All Tsub <= T_pr_crit
        - ramp_Tsh_ok: Tsh ramp rate within limits (if constraint specified)
        - ramp_Pch_ok: Pch ramp rate within limits (if constraint specified)
        - max_Tsub_violation: Maximum temperature violation [°C]
        - max_Tsh_ramp_violation: Maximum Tsh ramp violation [°C/hr]
        - max_Pch_ramp_violation: Maximum Pch ramp violation [Torr/hr]
    """
    if traj.size == 0:
        return {
            "constraints_satisfied": False,
            "dryness_ok": False,
            "temperature_ok": False,
            "ramp_Tsh_ok": None if ramp_Tsh_max is None else False,
            "ramp_Pch_ok": None if ramp_Pch_max is None else False,
        }
    
    # Extract columns
    time = traj[:, IDX_TIME]
    Tsub = traj[:, IDX_TSUB]
    Tsh = traj[:, IDX_TSH]
    Pch_mTorr = traj[:, IDX_PCH]
    frac_dried = traj[:, IDX_FRAC]
    
    # Check dryness target (99%)
    dryness_ok = frac_dried[-1] >= (0.99 - tolerance)
    
    # Check product temperature constraint
    max_Tsub = np.max(Tsub)
    Tsub_violation = max(0.0, max_Tsub - T_pr_crit)
    temperature_ok = Tsub_violation <= tolerance
    
    # Check ramp rate constraints if specified
    ramp_Tsh_ok = None
    max_Tsh_ramp_violation = 0.0
    if ramp_Tsh_max is not None and len(time) > 1:
        dt = np.diff(time)
        dTsh_dt = np.diff(Tsh) / dt
        max_Tsh_ramp = np.max(np.abs(dTsh_dt))
        max_Tsh_ramp_violation = max(0.0, max_Tsh_ramp - ramp_Tsh_max)
        ramp_Tsh_ok = max_Tsh_ramp_violation <= tolerance
    
    ramp_Pch_ok = None
    max_Pch_ramp_violation = 0.0
    if ramp_Pch_max is not None and len(time) > 1:
        dt = np.diff(time)
        Pch_Torr = Pch_mTorr / 1000.0  # Convert mTorr to Torr
        dPch_dt = np.diff(Pch_Torr) / dt
        max_Pch_ramp = np.max(np.abs(dPch_dt))
        max_Pch_ramp_violation = max(0.0, max_Pch_ramp - ramp_Pch_max)
        ramp_Pch_ok = max_Pch_ramp_violation <= tolerance
    
    # Overall constraint satisfaction
    all_ok = dryness_ok and temperature_ok
    if ramp_Tsh_ok is not None:
        all_ok = all_ok and ramp_Tsh_ok
    if ramp_Pch_ok is not None:
        all_ok = all_ok and ramp_Pch_ok
    
    return {
        "constraints_satisfied": all_ok,
        "dryness_ok": dryness_ok,
        "temperature_ok": temperature_ok,
        "ramp_Tsh_ok": ramp_Tsh_ok,
        "ramp_Pch_ok": ramp_Pch_ok,
        "final_frac_dried": float(frac_dried[-1]),
        "max_Tsub": float(max_Tsub),
        "max_Tsub_violation": float(Tsub_violation),
        "max_Tsh_ramp_violation": float(max_Tsh_ramp_violation),
        "max_Pch_ramp_violation": float(max_Pch_ramp_violation),
    }


__all__ = ["compute_residuals", "validate_constraints"]
