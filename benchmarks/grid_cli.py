#!/usr/bin/env python
"""Generic benchmarking CLI for Pyomo vs Scipy across N-D parameter grids.

Features
--------
- Cartesian product expansion of --vary key=val1,val2,... specifications.
- Methods: scipy baseline, finite differences (fd), collocation (colloc).
- Discretization controls: --n-elements, --n-collocation, --raw-colloc (disable effective parity).
- Robustness-first: warmstart disabled by default; enable with --warmstart.
- Reuse-first: if output JSONL exists and --force not supplied, skip generation.
- Trajectories embedded; schema v2 serialization handles numpy arrays.

Examples
--------
Generate baseline + FD + collocation over two parameters:
    python benchmarks/grid_cli.py generate \
        --task Tsh --scenario baseline \
        --vary product.A1=16,18,20 --vary ht.KC=2.75e-4,3.3e-4,4.0e-4 \
        --methods scipy,fd,colloc --n-elements 24 --n-collocation 3 \
        --out benchmarks/results/grid_A1_KC_fd_colloc.jsonl

Analysis notebook should treat resulting JSONL as read-only input.
"""
from __future__ import annotations
import argparse
import itertools
import json
import math
import sys
from pathlib import Path
from typing import Dict, Any, List
import time
import copy

import numpy as np

from benchmarks.scenarios import SCENARIOS
from benchmarks.schema import base_record, serialize
from benchmarks.validate import compute_residuals
from benchmarks.adapters import scipy_adapter, pyomo_adapter

VALID_METHODS = {"scipy", "fd", "colloc"}


def parse_vary(values: List[str]) -> List[Dict[str, Any]]:
    """Parse --vary specifications into list of {path, values} dicts."""
    specs = []
    for item in values:
        if "=" not in item:
            raise ValueError(f"Invalid --vary spec (missing '='): {item}")
        path, raw = item.split("=", 1)
        vals = []
        for part in raw.split(","):
            part = part.strip()
            if not part:
                continue
            # Try to interpret numeric; keep original if fails
            try:
                if part.lower().startswith("e"):
                    # Edge case where value like e-4 is passed; prefix with 1
                    part_val = float("1" + part)
                else:
                    part_val = float(part)
                vals.append(part_val)
            except ValueError:
                vals.append(part)  # string value
        if not vals:
            raise ValueError(f"No values parsed for {path}")
        specs.append({"path": path, "values": vals})
    return specs


def set_nested(d: Dict[str, Any], path: str, value: Any) -> None:
    cur = d
    parts = path.split(".")
    for key in parts[:-1]:
        if key not in cur or not isinstance(cur[key], dict):
            cur[key] = {}
        cur = cur[key]
    cur[parts[-1]] = value


def generate(args: argparse.Namespace) -> int:
    task = args.task
    scenario_name = args.scenario
    methods = [m.strip().lower() for m in args.methods.split(",") if m.strip()]
    unknown = [m for m in methods if m not in VALID_METHODS]
    if unknown:
        print(f"ERROR: Unknown methods: {unknown}", file=sys.stderr)
        return 2
    if scenario_name not in SCENARIOS:
        print(f"ERROR: Unknown scenario '{scenario_name}'. Available: {list(SCENARIOS.keys())}", file=sys.stderr)
        return 2
    vary_specs = parse_vary(args.vary)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if out_path.exists() and not args.force:
        print(f"Reuse-first: output exists, skipping generation: {out_path}")
        return 0

    base_scen = copy.deepcopy(SCENARIOS[scenario_name])
    vial = base_scen["vial"]
    product = base_scen["product"]
    ht = base_scen["ht"]
    eq_cap = base_scen["eq_cap"]
    nVial = base_scen.get("nVial", 400)

    # Build cartesian product of parameter values
    vary_paths = [spec["path"] for spec in vary_specs]
    vary_values_lists = [spec["values"] for spec in vary_specs]
    combos = list(itertools.product(*vary_values_lists))

    total = len(combos)
    print(f"Generating {total} combinations × {len(methods)} methods → {total * len(methods)} records")

    with out_path.open("w", encoding="utf-8") as f:
        k = 0
        for combo in combos:
            # Clone scenario and apply parameter values
            scen = copy.deepcopy(base_scen)
            for path, val in zip(vary_paths, combo):
                set_nested(scen, path, val)
            vial_c = scen["vial"]; product_c = scen["product"]; ht_c = scen["ht"]
            eq_cap_c = scen["eq_cap"]; nVial_c = scen.get("nVial", nVial)

            scipy_res = None  # compute baseline once if requested
            for method in methods:
                k += 1
                # Run scipy baseline if method == 'scipy'
                if method == "scipy":
                    scipy_res = scipy_adapter(task, vial_c, product_c, ht_c, eq_cap_c, nVial_c, scen, dt=args.dt)
                    sc_metrics = compute_residuals(scipy_res["trajectory"]) if scipy_res["success"] else {}
                    rec = base_record()
                    rec.update({
                        "task": task,
                        "scenario": scenario_name,
                        "grid": {**{f"param{i+1}": {"path": p, "value": v} for i, (p, v) in enumerate(zip(vary_paths, combo))}},
                        "scipy": {
                            "success": scipy_res["success"],
                            "wall_time_s": scipy_res["wall_time_s"],
                            "objective_time_hr": scipy_res.get("objective_time_hr"),
                            "solver": scipy_res.get("solver", {}),
                            "metrics": sc_metrics,
                        },
                        "pyomo": None,  # placeholder for analysis scripts
                    })
                    rec["failed"] = (not rec["scipy"]["success"]) or (not rec["scipy"]["metrics"].get("dryness_target_met", True))
                    f.write(serialize(rec) + "\n")
                    f.flush()
                    status = "FAIL" if rec["failed"] else "OK"
                    print(f"[{k}/{total * len(methods)}] {status} scipy combo={combo}")
                    continue

                # Pyomo methods
                # Ensure scipy baseline available for potential future warmstart logic
                if scipy_res is None:
                    scipy_res = scipy_adapter(task, vial_c, product_c, ht_c, eq_cap_c, nVial_c, scen, dt=args.dt)
                py_res = pyomo_adapter(
                    task,
                    vial_c,
                    product_c,
                    ht_c,
                    eq_cap_c,
                    nVial_c,
                    scen,
                    dt=args.dt,
                    warmstart=args.warmstart,
                    method=method,
                    n_elements=args.n_elements,
                    n_collocation=args.n_collocation,
                    effective_nfe=(not args.raw_colloc),
                )
                sc_metrics = compute_residuals(scipy_res["trajectory"]) if scipy_res["success"] else {}
                py_metrics = compute_residuals(py_res["trajectory"]) if py_res["success"] else {}
                rec = base_record()
                rec.update({
                    "task": task,
                    "scenario": scenario_name,
                    "grid": {**{f"param{i+1}": {"path": p, "value": v} for i, (p, v) in enumerate(zip(vary_paths, combo))}},
                    "scipy": {
                        "success": scipy_res["success"],
                        "wall_time_s": scipy_res["wall_time_s"],
                        "objective_time_hr": scipy_res.get("objective_time_hr"),
                        "solver": scipy_res.get("solver", {}),
                        "metrics": sc_metrics,
                    },
                    "pyomo": {
                        "success": py_res["success"],
                        "wall_time_s": py_res["wall_time_s"],
                        "objective_time_hr": py_res.get("objective_time_hr"),
                        "solver": py_res.get("solver", {}),
                        "metrics": py_metrics,
                        "discretization": py_res.get("discretization"),
                        "warmstart_used": py_res.get("warmstart_used"),
                    },
                })
                rec["failed"] = (
                    (not rec["scipy"]["success"]) or
                    (not rec["pyomo"]["success"]) or
                    (not rec["scipy"]["metrics"].get("dryness_target_met", True)) or
                    (not rec["pyomo"]["metrics"].get("dryness_target_met", True))
                )
                f.write(serialize(rec) + "\n")
                f.flush()
                status = "FAIL" if rec["failed"] else "OK"
                disc = rec["pyomo"].get("discretization", {}) if rec.get("pyomo") else {}
                disc_tag = f"{disc.get('method')} n={disc.get('n_elements_requested')}" + (f" ncp={disc.get('n_collocation')}" if disc.get('method')=='colloc' else '')
                print(f"[{k}/{total * len(methods)}] {status} {method} combo={combo} {disc_tag}")
    print(f"Done → {out_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="grid_cli", description="Benchmark generation CLI (Pyomo vs Scipy)")
    sub = p.add_subparsers(dest="command", required=True)

    g = sub.add_parser("generate", help="Generate JSONL records for parameter grid")
    g.add_argument("--task", required=True, choices=["Tsh", "Pch", "both"], help="Optimization task variant")
    g.add_argument("--scenario", required=True, help="Scenario name from benchmarks.scenarios")
    g.add_argument("--vary", action="append", required=True, help="Parameter path=value1,value2,... (repeatable)")
    g.add_argument("--methods", default="scipy,fd,colloc", help="Comma-separated methods to run")
    g.add_argument("--n-elements", type=int, default=24, help="Number of finite elements")
    g.add_argument("--n-collocation", type=int, default=3, help="Collocation points per element (colloc only)")
    g.add_argument("--raw-colloc", action="store_true", help="Disable effective-nfe parity reporting for collocation")
    g.add_argument("--warmstart", action="store_true", help="Enable scipy warmstart (default off)")
    g.add_argument("--dt", type=float, default=0.01, help="Time step for scipy baseline trajectory")
    g.add_argument("--out", required=True, help="Output JSONL path")
    g.add_argument("--force", action="store_true", help="Force regeneration even if file exists")

    return p


def main(argv: List[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "generate":
        return generate(args)
    parser.print_help()
    return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
