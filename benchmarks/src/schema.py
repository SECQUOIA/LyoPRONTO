"""Result schema utilities for benchmark runs.

Extended to support trajectory storage and discretization metadata for
robust Scipy vs Pyomo (FD & collocation) benchmarking.
"""
from __future__ import annotations
import sys, platform, datetime, json, hashlib
from typing import Any, Dict, List, Tuple

try:
    import pyomo
    PYOMO_VERSION = getattr(pyomo, "__version__", "unknown")
except Exception:
    PYOMO_VERSION = None

import numpy as np

def environment_info() -> Dict[str, Any]:
    return {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "numpy": np.__version__,
        "pyomo": PYOMO_VERSION,
    }

def base_record() -> Dict[str, Any]:
    """Create a base record with timestamp and environment.

    Additional fields will be added by generators (params, solver blocks,
    trajectories, discretization, hashes).
    """
    return {
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        "environment": environment_info(),
        "version": 2,  # schema version
    }

def hash_inputs(params: Dict[str, Any]) -> str:
    """Stable hash for varied input parameters (order-independent)."""
    items = sorted((k, params[k]) for k in params)
    raw = json.dumps(items, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

def hash_record(record: Dict[str, Any]) -> str:
    """Hash entire record excluding existing hash fields to detect duplicates."""
    shadow = {k: v for k, v in record.items() if not k.startswith("hash.")}
    raw = json.dumps(shadow, default=str, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

def serialize(record: Dict[str, Any]) -> str:
    """Serialize a record to compact JSON.

    Ensures hashes are present; if trajectory is a numpy array it is converted
    to a list of lists.
    """
    if "params" in record and "hash.inputs" not in record:
        record["hash.inputs"] = hash_inputs(record["params"])
    if "hash.record" not in record:
        record["hash.record"] = hash_record(record)

    def default(o):
        if isinstance(o, (set, tuple)):
            return list(o)
        try:
            import numpy as _np
            if isinstance(o, _np.ndarray):
                return o.tolist()
        except Exception:
            pass
        return str(o)
    return json.dumps(record, default=default, separators=(",", ":"))
