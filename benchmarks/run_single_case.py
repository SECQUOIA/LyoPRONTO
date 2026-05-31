#!/usr/bin/env python

# Copyright (C) 2026, SECQUOIA

"""Run one benchmark case with SciPy and Pyomo summaries.

This debug runner reuses the benchmark adapters and validation helpers without
writing JSONL records or image artifacts. It is intended for reproducing one
case before adding it to a larger grid run.
"""

from __future__ import annotations

import argparse
import ast
import copy
import sys
from pathlib import Path
from typing import Any

import numpy as np

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from benchmarks.adapters import pyomo_adapter, scipy_adapter
from benchmarks.grid_cli import (
    metrics_failed,
    pyomo_metric_kwargs,
    scipy_metric_kwargs,
    set_nested,
)
from benchmarks.scenarios import SCENARIOS
from benchmarks.validate import compute_residuals


def _parse_scalar(raw: str) -> Any:
    """Parse one CLI value while preserving strings when numeric parsing fails."""
    lowered = raw.strip().lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    if lowered in {"none", "null"}:
        return None
    try:
        return ast.literal_eval(raw)
    except (SyntaxError, ValueError):
        try:
            return float("1" + raw) if lowered.startswith("e") else float(raw)
        except ValueError:
            return raw


def parse_override(spec: str) -> tuple[str, Any]:
    """Parse a single PATH=VALUE override."""
    if "=" not in spec:
        raise argparse.ArgumentTypeError(
            f"Invalid override '{spec}'. Expected PATH=VALUE."
        )
    path, raw_value = spec.split("=", 1)
    path = path.strip()
    if not path:
        raise argparse.ArgumentTypeError(
            f"Invalid override '{spec}'. Expected non-empty PATH."
        )
    return path, _parse_scalar(raw_value.strip())


def build_case(scenario_name: str, overrides: list[tuple[str, Any]]) -> dict[str, Any]:
    """Return a scenario copy with single-case overrides applied."""
    scenario = copy.deepcopy(SCENARIOS[scenario_name])
    for path, value in overrides:
        set_nested(scenario, path, value)
    return scenario


def _trajectory_size(result: dict[str, Any]) -> str:
    traj = result.get("trajectory")
    shape = getattr(traj, "shape", ())
    if len(shape) == 2:
        return f"{shape[0]} points x {shape[1]} columns"
    if len(shape) == 1:
        return f"{shape[0]} points"
    return "0 points"


def _fmt(value: Any, digits: int = 4) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.{digits}g}"
    return str(value)


def _compute_metrics(
    result: dict[str, Any], metric_kwargs: dict[str, Any]
) -> dict[str, Any]:
    traj = result.get("trajectory")
    if traj is None or getattr(traj, "size", 0) == 0:
        return compute_residuals(np.array([]), **metric_kwargs)
    return compute_residuals(traj, **metric_kwargs)


def _metric_items(metrics: dict[str, Any]) -> list[tuple[str, Any]]:
    keys = [
        "final_percent_dried",
        "dryness_target_met",
        "product_temp_ok",
        "max_product_temp_violation_C",
        "tsh_ramp_ok",
        "max_tsh_ramp_C_per_hr",
        "max_tsh_ramp_violation_C_per_hr",
        "pch_ramp_ok",
        "max_pch_ramp_Torr_per_hr",
        "max_pch_ramp_violation_Torr_per_hr",
    ]
    return [(key, metrics.get(key)) for key in keys if key in metrics]


def print_summary(name: str, result: dict[str, Any], metrics: dict[str, Any]) -> None:
    """Print a compact solver and validation summary."""
    solver = result.get("solver") or {}
    print(f"\n{name} summary")
    print(f"  success: {result.get('success')}")
    print(f"  objective_time_hr: {_fmt(result.get('objective_time_hr'))}")
    print(f"  wall_time_s: {_fmt(result.get('wall_time_s'))}")
    print(f"  solver_status: {_fmt(solver.get('status'))}")
    print(f"  termination_condition: {_fmt(solver.get('termination_condition'))}")
    print(f"  trajectory_size: {_trajectory_size(result)}")
    if result.get("message"):
        print(f"  message: {result['message']}")
    print("  validation_metrics:")
    for key, value in _metric_items(metrics):
        print(f"    {key}: {_fmt(value)}")


def run_case(args: argparse.Namespace) -> int:
    try:
        overrides = [parse_override(spec) for spec in args.overrides]
    except argparse.ArgumentTypeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    scenario = build_case(args.scenario, overrides)

    vial = scenario["vial"]
    product = scenario["product"]
    ht = scenario["ht"]
    eq_cap = scenario["eq_cap"]
    n_vial = scenario.get("nVial", 400)

    print("Single-case benchmark")
    print(f"  task: {args.task}")
    print(f"  scenario: {args.scenario}")
    print(f"  method: {args.method}")
    print(f"  n_elements: {args.n_elements}")
    if args.method == "colloc":
        print(f"  n_collocation: {args.n_collocation}")
        print(f"  effective_nfe: {not args.raw_colloc}")
    print(f"  warmstart: {args.warmstart}")
    print(f"  tee: {args.tee}")
    print(f"  tsh_ramp: {_fmt(args.tsh_ramp)}")
    print(f"  pch_ramp: {_fmt(args.pch_ramp)}")
    if overrides:
        print("  overrides:")
        for path, value in overrides:
            print(f"    {path}: {_fmt(value)}")

    scipy_result = scipy_adapter(
        args.task,
        vial,
        product,
        ht,
        eq_cap,
        n_vial,
        scenario,
        dt=args.dt,
    )
    scipy_metrics = _compute_metrics(
        scipy_result,
        scipy_metric_kwargs(args, product),
    )
    print_summary("SciPy", scipy_result, scipy_metrics)

    try:
        pyomo_result = pyomo_adapter(
            args.task,
            vial,
            product,
            ht,
            eq_cap,
            n_vial,
            scenario,
            dt=args.dt,
            warmstart=args.warmstart,
            method=args.method,
            n_elements=args.n_elements,
            n_collocation=args.n_collocation,
            effective_nfe=(not args.raw_colloc),
            tsh_ramp_rate=args.tsh_ramp,
            pch_ramp_rate=args.pch_ramp,
            use_secant_ramp_constraints=(not args.no_secant_constraints),
            solver_cpu_time=args.solver_timeout,
            solver_wall_time=args.solver_wall_time,
            tee=args.tee,
        )
    except RuntimeError as exc:
        print("\nPyomo summary")
        print("  success: False")
        print(f"  message: {exc}", file=sys.stderr)
        return 1

    pyomo_metrics = _compute_metrics(
        pyomo_result,
        pyomo_metric_kwargs(args, product),
    )
    print_summary("Pyomo", pyomo_result, pyomo_metrics)

    failed = (
        (not scipy_result["success"])
        or (not pyomo_result["success"])
        or metrics_failed(scipy_metrics)
        or metrics_failed(pyomo_metrics)
    )
    return 1 if failed else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run_single_case",
        description="Run one SciPy/Pyomo benchmark case without writing artifacts.",
    )
    parser.add_argument(
        "--task",
        required=True,
        choices=["Tsh", "Pch", "both"],
        help="Optimization task variant.",
    )
    parser.add_argument(
        "--scenario",
        default="baseline",
        choices=sorted(SCENARIOS),
        help="Scenario name from benchmarks.scenarios.",
    )
    parser.add_argument(
        "--set",
        "--override",
        dest="overrides",
        action="append",
        default=[],
        metavar="PATH=VALUE",
        help="Single parameter override using dotted scenario paths; repeatable.",
    )
    parser.add_argument(
        "--method",
        default="fd",
        choices=["fd", "colloc"],
        help="Pyomo discretization method.",
    )
    parser.add_argument(
        "--n-elements",
        type=int,
        default=24,
        help="Number of finite elements.",
    )
    parser.add_argument(
        "--n-collocation",
        type=int,
        default=3,
        help="Collocation points per element.",
    )
    parser.add_argument(
        "--raw-colloc",
        action="store_true",
        help="Disable effective-nfe parity reporting for collocation.",
    )
    parser.add_argument(
        "--warmstart",
        action="store_true",
        help="Enable scipy warmstart for the Pyomo solve.",
    )
    parser.add_argument(
        "--dt",
        type=float,
        default=0.01,
        help="Time step for scipy baseline trajectory.",
    )
    parser.add_argument(
        "--tsh-ramp",
        type=float,
        default=None,
        help="Max shelf temperature ramp rate [C/hr] for Pyomo and validation.",
    )
    parser.add_argument(
        "--pch-ramp",
        type=float,
        default=None,
        help="Max chamber pressure ramp rate [Torr/hr] for Pyomo and validation.",
    )
    parser.add_argument(
        "--no-secant-constraints",
        action="store_true",
        help="Disable explicit secant slope constraints for collocation ramp rates.",
    )
    parser.add_argument(
        "--solver-timeout",
        type=float,
        default=None,
        help="Optional IPOPT CPU-time limit in seconds.",
    )
    parser.add_argument(
        "--solver-wall-time",
        type=float,
        default=None,
        help="Optional IPOPT wall-clock time limit in seconds when supported.",
    )
    parser.add_argument(
        "--tee",
        "--solver-verbose",
        dest="tee",
        action="store_true",
        help="Show solver output from Pyomo/IPOPT.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return run_case(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
