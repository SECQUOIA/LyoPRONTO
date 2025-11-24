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

__all__ = ["compute_residuals"]
