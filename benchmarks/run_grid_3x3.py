"""3x3 grid runner for system variables with reuse logic delegated to caller.

Usage:
  python -m benchmarks.run_grid_3x3 \
    --task Tsh --scenario baseline \
    --p1-path product.A1 --p2-path ht.KC \
    --p1-values 16,18,20 --p2-values 2.75e-4,3.3e-4,4.0e-4 \
    --outfile benchmarks/results/grid_3x3.jsonl

Notes:
- Only system variables are allowed (same roots as run_grid.py):
  {vial, product, ht, eq_cap, nVial}
- This module writes a fresh JSONL with exactly 9 records (3x3).
"""
from __future__ import annotations
import argparse
import copy
from pathlib import Path
from typing import List

from .scenarios import SCENARIOS
from .adapters import scipy_adapter, pyomo_adapter
from .schema import base_record, serialize
from .validate import compute_residuals

ALLOWED_ROOTS = {"vial", "product", "ht", "eq_cap", "nVial"}


def _parse_values(csv: str) -> List[float]:
    vals = [v.strip() for v in csv.split(",") if v.strip()]
    return [float(eval(v)) for v in vals]


def _validate_root(path: str) -> None:
    root = path.split(".")[0]
    if root not in ALLOWED_ROOTS:
        raise argparse.ArgumentTypeError(
            f"Root must be one of {sorted(ALLOWED_ROOTS)}; got '{root}'"
        )


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run a 3x3 system grid for benchmarks")
    p.add_argument("--task", choices=["Tsh", "Pch", "both"], default="Tsh")
    p.add_argument("--scenario", choices=list(SCENARIOS.keys()), default="baseline")
    p.add_argument("--p1-path", required=True)
    p.add_argument("--p2-path", required=True)
    p.add_argument("--p1-values", required=True, help="Comma-separated; length 3")
    p.add_argument("--p2-values", required=True, help="Comma-separated; length 3")
    p.add_argument("--outfile", default="benchmarks/results/grid_3x3.jsonl")
    return p.parse_args(argv)


def set_nested(d, dotted: str, value):
    cur = d
    parts = dotted.split(".")
    for key in parts[:-1]:
        if key not in cur or not isinstance(cur[key], dict):
            cur[key] = {}
        cur = cur[key]
    cur[parts[-1]] = value


def run(task: str, scenario: str, p1_path: str, p2_path: str, p1_vals_csv: str, p2_vals_csv: str, outfile: str) -> Path:
    _validate_root(p1_path)
    _validate_root(p2_path)
    p1_vals = _parse_values(p1_vals_csv)
    p2_vals = _parse_values(p2_vals_csv)
    if len(p1_vals) != 3 or len(p2_vals) != 3:
        raise ValueError("p1-values and p2-values must each have exactly 3 values")

    scen_base = copy.deepcopy(SCENARIOS[scenario])
    out = Path(outfile)
    out.parent.mkdir(parents=True, exist_ok=True)

    total = len(p1_vals) * len(p2_vals)
    with open(out, "w", encoding="utf-8") as f:
        k = 0
        for v1 in p1_vals:
            for v2 in p2_vals:
                k += 1
                scen = copy.deepcopy(scen_base)
                set_nested(scen, p1_path, v1)
                set_nested(scen, p2_path, v2)

                vial = scen["vial"]
                product = scen["product"]
                ht = scen["ht"]
                eq_cap = scen["eq_cap"]
                nVial = scen.get("nVial", 400)

                scipy_res = scipy_adapter(task, vial, product, ht, eq_cap, nVial, scen)
                pyomo_res = pyomo_adapter(task, vial, product, ht, eq_cap, nVial, scen, dt=0.01, warmstart=False)

                sc_metrics = compute_residuals(scipy_res["trajectory"]) if scipy_res["success"] else {}
                py_metrics = compute_residuals(pyomo_res["trajectory"]) if pyomo_res["success"] else {}

                rec = base_record()
                rec.update(
                    {
                        "task": task,
                        "scenario": scenario,
                        "grid": {
                            "param1": {"path": p1_path, "value": v1},
                            "param2": {"path": p2_path, "value": v2},
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
                    }
                )
                rec["failed"] = (
                    (not rec["scipy"]["success"]) or (not rec["pyomo"]["success"]) or
                    (not rec["scipy"]["metrics"].get("dryness_target_met", True)) or
                    (not rec["pyomo"]["metrics"].get("dryness_target_met", True))
                )

                f.write(serialize(rec) + "\n")
                f.flush()
                status = "FAIL" if rec["failed"] else "OK"
                print(
                    f"[{k}/{total}] {status} {task}@{scenario} "
                    f"{p1_path.split('.')[-1]}={v1}, {p2_path.split('.')[-1]}={v2}"
                )

    return out


def main(argv=None):
    ns = parse_args(argv)
    run(ns.task, ns.scenario, ns.p1_path, ns.p2_path, ns.p1_values, ns.p2_values, ns.outfile)
    return 0


if __name__ == "__main__":  # pragma: no cover
    import sys
    raise SystemExit(main(sys.argv[1:]))
