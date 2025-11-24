"""Summarize 2-parameter grid JSONL into CSV and optional heatmap.

Usage examples:
  # CSV of Pyomo objective times (hours)
  python -m benchmarks.summarize_grid benchmarks/results/grid.jsonl \
    --metric pyomo.objective_time_hr --csv benchmarks/results/grid_pyomo_obj.csv

  # Time ratio heatmap (Pyomo/Scipy)
  python -m benchmarks.summarize_grid benchmarks/results/grid.jsonl \
    --metric ratio.pyomo_over_scipy --heatmap benchmarks/results/grid_ratio.png

Notes:
- Expects records created by benchmarks.run_grid with rec['grid'] metadata.
- Requires matplotlib only if --heatmap is specified.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Summarize grid JSONL into CSV/heatmap")
    p.add_argument("jsonl", help="Path to grid .jsonl file")
    p.add_argument("--metric", default="pyomo.objective_time_hr",
                   help="Metric to pivot: pyomo.objective_time_hr | scipy.objective_time_hr | ratio.pyomo_over_scipy")
    p.add_argument("--csv", default=None, help="Output CSV path")
    p.add_argument("--heatmap", default=None, help="Output PNG path for heatmap (optional)")
    return p.parse_args(argv)


def iter_records(path: str):
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def extract_params_and_metric(recs: List[Dict[str, Any]], metric: str):
    # Collect unique values and verify consistent paths
    p1_path = None
    p2_path = None
    p1_vals: List[float] = []
    p2_vals: List[float] = []
    rows: List[Tuple[float, float, float]] = []

    for r in recs:
        if "grid" not in r or "param1" not in r["grid"] or "param2" not in r["grid"]:
            continue
        g = r["grid"]
        cur_p1_path = g["param1"]["path"]
        cur_p2_path = g["param2"]["path"]
        if p1_path is None:
            p1_path = cur_p1_path
        if p2_path is None:
            p2_path = cur_p2_path
        if cur_p1_path != p1_path or cur_p2_path != p2_path:
            # Mixed grids not supported in one file
            continue

        v1 = float(g["param1"]["value"])
        v2 = float(g["param2"]["value"])
        if v1 not in p1_vals:
            p1_vals.append(v1)
        if v2 not in p2_vals:
            p2_vals.append(v2)

        if metric == "pyomo.objective_time_hr":
            val = r.get("pyomo", {}).get("objective_time_hr")
        elif metric == "scipy.objective_time_hr":
            val = r.get("scipy", {}).get("objective_time_hr")
        elif metric == "ratio.pyomo_over_scipy":
            py = r.get("pyomo", {}).get("objective_time_hr")
            sc = r.get("scipy", {}).get("objective_time_hr")
            val = (float(py) / float(sc)) if (py not in (None, 0) and sc not in (None, 0)) else None
        else:
            raise ValueError(f"Unknown metric '{metric}'")

        rows.append((v1, v2, None if val is None else float(val)))

    p1_vals = sorted(p1_vals)
    p2_vals = sorted(p2_vals)
    return p1_path, p2_path, p1_vals, p2_vals, rows


def pivot_to_matrix(p1_vals: List[float], p2_vals: List[float], rows: List[Tuple[float, float, float]]):
    mat = np.full((len(p1_vals), len(p2_vals)), np.nan)
    idx1 = {v: i for i, v in enumerate(p1_vals)}
    idx2 = {v: j for j, v in enumerate(p2_vals)}
    for v1, v2, val in rows:
        i = idx1[v1]; j = idx2[v2]
        if val is not None:
            mat[i, j] = val
    return mat


def write_csv(path: str, p1_path: str, p2_path: str, p1_vals: List[float], p2_vals: List[float], mat: np.ndarray):
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        # Header: param2 axis along columns
        header = [f"{p1_path}\\{p2_path}"] + [str(v) for v in p2_vals]
        f.write(",".join(header) + "\n")
        for i, v1 in enumerate(p1_vals):
            row = [str(v1)] + ["" if np.isnan(mat[i, j]) else f"{mat[i,j]:.6g}" for j in range(len(p2_vals))]
            f.write(",".join(row) + "\n")


def write_heatmap(path: str, title: str, p1_vals: List[float], p2_vals: List[float], mat: np.ndarray):
    try:
        import matplotlib.pyplot as plt
    except Exception:
        print("matplotlib not available; skipping heatmap")
        return
    fig, ax = plt.subplots(figsize=(6, 4))
    im = ax.imshow(mat, origin="lower", aspect="auto", cmap="viridis")
    ax.set_xticks(range(len(p2_vals)))
    ax.set_xticklabels([str(v) for v in p2_vals], rotation=45, ha="right")
    ax.set_yticks(range(len(p1_vals)))
    ax.set_yticklabels([str(v) for v in p1_vals])
    ax.set_xlabel("param2 values")
    ax.set_ylabel("param1 values")
    ax.set_title(title)
    cbar = plt.colorbar(im, ax=ax)
    cbar.set_label(title)
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(out, dpi=150)
    plt.close(fig)


def main(argv=None):
    ns = parse_args(argv)
    recs = list(iter_records(ns.jsonl))
    p1_path, p2_path, p1_vals, p2_vals, rows = extract_params_and_metric(recs, ns.metric)
    if not p1_vals or not p2_vals:
        print("No grid records found or malformed input file.")
        return 1
    mat = pivot_to_matrix(p1_vals, p2_vals, rows)

    title = ns.metric
    if ns.csv:
        write_csv(ns.csv, p1_path, p2_path, p1_vals, p2_vals, mat)
        print(f"Wrote CSV → {ns.csv}")
    if ns.heatmap:
        write_heatmap(ns.heatmap, title, p1_vals, p2_vals, mat)
        print(f"Wrote heatmap → {ns.heatmap}")
    if not ns.csv and not ns.heatmap:
        # Print a compact matrix preview
        print("Matrix preview (NaN=blank):")
        for i, v1 in enumerate(p1_vals):
            row = ["" if np.isnan(mat[i, j]) else f"{mat[i,j]:.4g}" for j in range(len(p2_vals))]
            print(f"{p1_path}={v1}:\t" + ", ".join(row))
    return 0


if __name__ == "__main__":  # pragma: no cover
    import sys
    raise SystemExit(main(sys.argv[1:]))
