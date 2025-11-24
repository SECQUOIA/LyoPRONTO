"""Batch runner for scipy vs Pyomo benchmarks.

Examples:
python -m benchmarks.run_batch --tasks Tsh --scenarios baseline \
  --outfile benchmarks/results/batch_$(date +%s).jsonl

python -m benchmarks.run_batch --tasks Tsh Pch both --scenarios baseline high_resistance
"""
from __future__ import annotations
import argparse
import os
import sys
from pathlib import Path
from datetime import datetime
from typing import List

from .run_single import run as run_single
from .scenarios import SCENARIOS
from .schema import serialize

DEFAULT_OUTDIR = Path("benchmarks/results")


def parse_args(argv: List[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run batch of benchmark cases")
    p.add_argument("--tasks", nargs="+", default=["Tsh"], choices=["Tsh","Pch","both"], help="Tasks to run")
    p.add_argument("--scenarios", nargs="+", default=["baseline"], choices=list(SCENARIOS.keys()), help="Scenarios to run")
    p.add_argument("--repeats", type=int, default=1, help="Repeat each (task,scenario) this many times")
    p.add_argument("--outfile", type=str, default=None, help="Output .jsonl file path")
    return p.parse_args(argv)


def main(argv=None):
    ns = parse_args(argv or sys.argv[1:])

    outdir = DEFAULT_OUTDIR
    outdir.mkdir(parents=True, exist_ok=True)
    outfile = Path(ns.outfile) if ns.outfile else outdir / f"batch_{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}.jsonl"

    total = len(ns.tasks) * len(ns.scenarios) * ns.repeats
    print(f"Running {total} cases → {outfile}")

    with open(outfile, "a", encoding="utf-8") as f:
        k = 0
        for task in ns.tasks:
            for scen in ns.scenarios:
                for r in range(ns.repeats):
                    k += 1
                    print(f"[{k}/{total}] {task} @ {scen} run {r+1}")
                    rec = run_single(task, scen)
                    f.write(serialize(rec) + "\n")
                    f.flush()

    print(f"Done. Wrote {outfile}")
    return 0

if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
