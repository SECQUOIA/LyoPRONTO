"""Aggregate JSONL benchmark outputs.

Usage:
python -m benchmarks.aggregate benchmarks/results/batch_*.jsonl
"""
from __future__ import annotations
import argparse
import glob
import json
from pathlib import Path
from typing import Dict, List, Any, Tuple
from statistics import mean


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Aggregate benchmark JSONL outputs")
    p.add_argument("paths", nargs="+", help="JSONL files or globs")
    return p.parse_args(argv)


def iter_records(paths: List[str]):
    files: List[str] = []
    for pat in paths:
        files.extend(glob.glob(pat))
    for fp in files:
        with open(fp, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue


def summarize(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    # Group by (task, scenario)
    groups: Dict[Tuple[str,str], List[Dict[str,Any]]] = {}
    for r in records:
        key = (r.get("task","?"), r.get("scenario","?"))
        groups.setdefault(key, []).append(r)

    summary: Dict[str, Any] = {"groups": {}}
    for (task, scen), recs in groups.items():
        def metric_list(path: List[str]) -> List[float]:
            vals = []
            for rr in recs:
                cur: Any = rr
                ok = True
                for p in path:
                    if isinstance(cur, dict) and p in cur:
                        cur = cur[p]
                    else:
                        ok = False
                        break
                if ok and isinstance(cur, (int, float)):
                    vals.append(float(cur))
            return vals

        sc_succ = [bool(r.get("scipy",{}).get("success", False)) for r in recs]
        py_succ = [bool(r.get("pyomo",{}).get("success", False)) for r in recs]
        sc_t = metric_list(["scipy","wall_time_s"])
        py_t = metric_list(["pyomo","wall_time_s"])
        sc_obj = metric_list(["scipy","objective_time_hr"])
        py_obj = metric_list(["pyomo","objective_time_hr"])

        # Time ratios available only where both present
        ratios = [py/sc for (py, sc) in zip(py_t, sc_t) if sc > 0]

        # Dryness flag
        sc_dry = [bool(r.get("scipy",{}).get("metrics",{}).get("dryness_target_met", False)) for r in recs]
        py_dry = [bool(r.get("pyomo",{}).get("metrics",{}).get("dryness_target_met", False)) for r in recs]

        out = {
            "n": len(recs),
            "scipy_success_rate": sum(sc_succ)/len(sc_succ) if sc_succ else None,
            "pyomo_success_rate": sum(py_succ)/len(py_succ) if py_succ else None,
            "avg_scipy_time_s": mean(sc_t) if sc_t else None,
            "avg_pyomo_time_s": mean(py_t) if py_t else None,
            "avg_scipy_objective_hr": mean(sc_obj) if sc_obj else None,
            "avg_pyomo_objective_hr": mean(py_obj) if py_obj else None,
            "avg_time_ratio_pyomo_over_scipy": mean(ratios) if ratios else None,
            "scipy_dryness_rate": sum(sc_dry)/len(sc_dry) if sc_dry else None,
            "pyomo_dryness_rate": sum(py_dry)/len(py_dry) if py_dry else None,
        }
        summary["groups"][f"{task}:{scen}"] = out
    return summary


def main(argv=None):
    ns = parse_args(argv)
    recs = list(iter_records(ns.paths))
    s = summarize(recs)
    print(json.dumps(s, indent=2))
    return 0

if __name__ == "__main__":  # pragma: no cover
    import sys
    raise SystemExit(main(sys.argv[1:]))
