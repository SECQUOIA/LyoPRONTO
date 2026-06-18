"""Result utilities for optional Pyomo primary-drying prototypes."""

from __future__ import annotations

from typing import Mapping, Optional

import numpy as np

from .. import constant


def format_single_step_output(
    values: Mapping[str, Optional[float]],
    time: float,
    ap: float,
    percent_dried: float,
) -> np.ndarray:
    """Format solved single-step values like the legacy seven-column outputs."""
    required = ("Tsub", "Tbot", "Tsh", "Pch", "dmdt")
    missing = [key for key in required if values.get(key) is None]
    if missing:
        joined = ", ".join(missing)
        raise ValueError(f"Cannot format output with missing value(s): {joined}")

    return np.array(
        [
            time,
            values["Tsub"],
            values["Tbot"],
            values["Tsh"],
            values["Pch"] * constant.Torr_to_mTorr,  # type: ignore[operator]
            values["dmdt"] / (ap * constant.cm_To_m**2),  # type: ignore[operator]
            percent_dried,
        ],
        dtype=float,
    )
