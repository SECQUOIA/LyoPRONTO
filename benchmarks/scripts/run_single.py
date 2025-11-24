"""Single benchmark run script (importable) for one scenario & task.

Usage (from CLI):
python -m benchmarks.run_single Tsh baseline
"""
from __future__ import annotations
import json
import sys
from pathlib import Path
from typing import Any, Dict

import numpy as np

from .scenarios import SCENARIOS
from .schema import base_record, serialize
from .adapters import scipy_adapter, pyomo_adapter
from .validate import compute_residuals

# Minimal default physical parameter dicts; real scenarios may override
DEFAULT_VIAL = {"Av": 6.16, "Ap": 6.16, "Vfill": 5.0}
DEFAULT_PRODUCT = {"Lpr0": 0.8, "R0": 0.6, "A1": 2.3, "A2": 0.4}
DEFAULT_HT = {"Kv": 3.5}
DEFAULT_EQ = {"dHs": 650.0}
N_VIAL = 100

VALID_TASKS = {"Tsh", "Pch", "both"}


def run(task: str, scenario_name: str) -> Dict[str, Any]:
    if task not in VALID_TASKS:
        raise ValueError(f"Invalid task {task}")
    if scenario_name not in SCENARIOS:
        raise ValueError(f"Unknown scenario {scenario_name}")
    scenario = SCENARIOS[scenario_name]

    # Merge scenario overrides (if any)
    vial = {**DEFAULT_VIAL, **scenario.get("vial", {})}
    product = {**DEFAULT_PRODUCT, **scenario.get("product", {})}
    ht = {**DEFAULT_HT, **scenario.get("ht", {})}
    eq_cap = {**DEFAULT_EQ, **scenario.get("eq_cap", {})}

    scipy_res = scipy_adapter(task, vial, product, ht, eq_cap, N_VIAL, scenario)
    pyomo_res = pyomo_adapter(task, vial, product, ht, eq_cap, N_VIAL, scenario, dt=0.01, warmstart=False)

    scipy_metrics = compute_residuals(scipy_res["trajectory"])
    pyomo_metrics = compute_residuals(pyomo_res["trajectory"])

    record = base_record()
    record.update({
        "task": task,
        "scenario": scenario_name,
        "scipy": {
            "success": scipy_res["success"],
            "wall_time_s": scipy_res["wall_time_s"],
            "objective_time_hr": scipy_res.get("objective_time_hr"),
            "solver": scipy_res.get("solver", {}),
            "metrics": scipy_metrics,
        },
        "pyomo": {
            "success": pyomo_res["success"],
            "wall_time_s": pyomo_res["wall_time_s"],
            "objective_time_hr": pyomo_res.get("objective_time_hr"),
            "solver": pyomo_res.get("solver", {}),
            "metrics": pyomo_metrics,
        },
    })
    return record


def main(argv=None):
    argv = argv or sys.argv[1:]
    if len(argv) != 2:
        print("Usage: python -m benchmarks.run_single <task> <scenario>")
        return 1
    task, scenario = argv
    rec = run(task, scenario)
    print(serialize(rec))
    return 0

if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
