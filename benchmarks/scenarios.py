"""Benchmark scenario definitions for LyoPRONTO optimization tasks.

Each scenario is a dictionary with the required parameter sets:
- vial
- product
- ht (heat transfer parameters)
- eq_cap (equipment capability)
- nVial
- meta (description)

Scenarios chosen to exercise different numerical regimes.
"""
from __future__ import annotations

SCENARIOS = {
    "baseline": {
        "vial": {"Av": 3.8, "Ap": 3.14, "Vfill": 2.0},
        "product": {"R0": 1.4, "A1": 16.0, "A2": 0.0, "T_pr_crit": -25.0, "cSolid": 0.05},
        "ht": {"KC": 2.75e-4, "KP": 8.93e-4, "KD": 0.46},
        "eq_cap": {"a": -0.182, "b": 11.7},
        "nVial": 400,
        "meta": "Moderate fill, standard resistance"
    },
    "high_resistance": {
        "vial": {"Av": 3.8, "Ap": 3.14, "Vfill": 2.0},
        "product": {"R0": 1.4, "A1": 30.0, "A2": 0.2, "T_pr_crit": -25.0, "cSolid": 0.05},
        "ht": {"KC": 2.75e-4, "KP": 8.93e-4, "KD": 0.46},
        "eq_cap": {"a": -0.182, "b": 11.7},
        "nVial": 400,
        "meta": "Increased A1/A2 to stress Rp growth"
    },
    "tight_temperature": {
        "vial": {"Av": 3.8, "Ap": 3.14, "Vfill": 2.0},
        "product": {"R0": 1.4, "A1": 16.0, "A2": 0.0, "T_pr_crit": -15.0, "cSolid": 0.05},
        "ht": {"KC": 2.75e-4, "KP": 8.93e-4, "KD": 0.46},
        "eq_cap": {"a": -0.182, "b": 11.7},
        "nVial": 400,
        "meta": "Critical temperature near operating range"
    },
    "aggressive_drying": {
        "vial": {"Av": 3.8, "Ap": 3.14, "Vfill": 2.0},
        "product": {"R0": 1.4, "A1": 16.0, "A2": 0.0, "T_pr_crit": -25.0, "cSolid": 0.05},
        "ht": {"KC": 4.00e-4, "KP": 1.20e-3, "KD": 0.46},
        "eq_cap": {"a": -0.182, "b": 11.7},
        "nVial": 400,
        "meta": "Higher heat transfer to push sublimation rate"
    },
    "large_batch": {
        "vial": {"Av": 3.8, "Ap": 3.14, "Vfill": 2.5},
        "product": {"R0": 1.4, "A1": 16.0, "A2": 0.0, "T_pr_crit": -25.0, "cSolid": 0.05},
        "ht": {"KC": 2.75e-4, "KP": 8.93e-4, "KD": 0.46},
        "eq_cap": {"a": -0.182, "b": 11.7},
        "nVial": 1200,
        "meta": "Large batch size stresses scaling"
    },
}

def get_scenario(name: str) -> dict:
    if name not in SCENARIOS:
        raise KeyError(f"Unknown scenario '{name}'. Available: {list(SCENARIOS)}")
    return SCENARIOS[name]
