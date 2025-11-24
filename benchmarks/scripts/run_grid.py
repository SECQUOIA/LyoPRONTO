"""2-parameter grid runner for system variables (not solver params).

Usage examples:
  python -m benchmarks.run_grid --task Tsh --scenario baseline \
    --param1 product.A1:16,20 --param2 ht.KC:2.75e-4,4.00e-4 \
    --outfile benchmarks/results/grid.jsonl

Notes:
- Only system variables are allowed: roots in {vial, product, ht, eq_cap, nVial}
- Each parameter must specify exactly two values (comma-separated)
- Records include objective time and solver termination metadata
"""
from __future__ import annotations
import argparse
import copy
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np

from .scenarios import SCENARIOS
from .adapters import scipy_adapter, pyomo_adapter
from .schema import base_record, serialize
from .validate import compute_residuals

ALLOWED_ROOTS = {"vial", "product", "ht", "eq_cap", "nVial"}


def parse_param_spec(spec: str) -> Tuple[List[str], List[float]]:
    """Parse a parameter spec like "product.A1:16,20".

    Returns (path_list, values)
    """
    if ":" not in spec:
        raise argparse.ArgumentTypeError("Parameter spec must be of form path:val1,val2")
    path_str, values_str = spec.split(":", 1)
    path = path_str.split(".")
    if not path or path[0] not in ALLOWED_ROOTS:
        raise argparse.ArgumentTypeError(
            f"Root must be one of {sorted(ALLOWED_ROOTS)}; got '{path[0] if path else ''}'"
        )
    vals = [v for v in values_str.split(",") if v.strip() != ""]
    if len(vals) != 2:
        raise argparse.ArgumentTypeError("Each parameter must provide exactly two values")
    try:
        values = [float(eval(v)) for v in vals]  # allow 2.75e-4
    except Exception:
        raise argparse.ArgumentTypeError(f"Invalid numeric values in '{spec}'")
    return path, values


def set_nested(d: Dict[str, Any], path: List[str], value: Any) -> None:
    """Set d[path[0]]...[path[-1]] = value, creating nested dicts if needed."""
    cur = d
    for key in path[:-1]:
        if key not in cur or not isinstance(cur[key], dict):
            cur[key] = {}
        cur = cur[key]
    cur[path[-1]] = value


def get_nested(d: Dict[str, Any], path: List[str]) -> Any:
    cur = d
    for key in path:
        cur = cur[key]
    return cur


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run 2-parameter system grid for benchmarks")
    p.add_argument("--task", choices=["Tsh", "Pch", "both"], default="Tsh")
    p.add_argument("--scenario", choices=list(SCENARIOS.keys()), default="baseline")
    p.add_argument("--param1", required=True, help="e.g., product.A1:16,20")
    p.add_argument("--param2", required=True, help="e.g., ht.KC:2.75e-4,4.00e-4")
    p.add_argument("--outfile", default="benchmarks/results/grid.jsonl")
    return p.parse_args(argv)


def run_grid(task: str, scenario_name: str, param1: str, param2: str, outfile: str) -> Path:
    path1, values1 = parse_param_spec(param1)
    path2, values2 = parse_param_spec(param2)

    if path1 == path2:
        raise ValueError("param1 and param2 cannot reference the same path")

    scen_base = copy.deepcopy(SCENARIOS[scenario_name])
    outpath = Path(outfile)
    outpath.parent.mkdir(parents=True, exist_ok=True)

    total = len(values1) * len(values2)
    k = 0
    with open(outpath, "a", encoding="utf-8") as f:
        for v1 in values1:
            for v2 in values2:
                k += 1
                scen = copy.deepcopy(scen_base)
                set_nested(scen, path1, v1)
                set_nested(scen, path2, v2)

                # Pull pieces
                vial = scen["vial"]
                product = scen["product"]
                ht = scen["ht"]
                eq_cap = scen["eq_cap"]
                nVial = scen.get("nVial", 400)

                # Run solvers
                scipy_res = scipy_adapter(task, vial, product, ht, eq_cap, nVial, scen)
                pyomo_res = pyomo_adapter(task, vial, product, ht, eq_cap, nVial, scen, dt=0.01, warmstart=False)

                # Metrics
                sc_metrics = compute_residuals(scipy_res["trajectory"]) if scipy_res["success"] else {}
                py_metrics = compute_residuals(pyomo_res["trajectory"]) if pyomo_res["success"] else {}

                rec = base_record()
                rec.update({
                    "task": task,
                    "scenario": scenario_name,
                    "grid": {
                        "param1": {"path": ".".join(path1), "value": v1},
                        "param2": {"path": ".".join(path2), "value": v2},
                    },
                    "scipy": {
                        "success": scipy_res["success"],
                        "wall_time_s": scipy_res["wall_time_s"],
                        "objective_time_hr": scipy_res.get("objective_time_hr"),
                        "solver": scipy_res.get("solver", {}),
                        "metrics": sc_metrics,
                    },
                    "pyomo": {
                        "success": pyomo_res["success"],
                        "wall_time_s": pyomo_res["wall_time_s"],
                        "objective_time_hr": pyomo_res.get("objective_time_hr"),
                        "solver": pyomo_res.get("solver", {}),
                        "metrics": py_metrics,
                    },
                })

                # Failure highlighting flag
                rec["failed"] = (not rec["scipy"]["success"]) or (not rec["pyomo"]["success"]) or \
                                  (not rec["scipy"]["metrics"].get("dryness_target_met", True)) or \
                                  (not rec["pyomo"]["metrics"].get("dryness_target_met", True))

                f.write(serialize(rec) + "\n")
                f.flush()
                status = "FAIL" if rec["failed"] else "OK"
                print(f"[{k}/{total}] {status} {task}@{scenario_name} {path1[-1]}={v1}, {path2[-1]}={v2}")

    return outpath


def main(argv=None):
    ns = parse_args(argv)
    run_grid(ns.task, ns.scenario, ns.param1, ns.param2, ns.outfile)
    return 0


if __name__ == "__main__":  # pragma: no cover
    import sys
    raise SystemExit(main(sys.argv[1:]))
