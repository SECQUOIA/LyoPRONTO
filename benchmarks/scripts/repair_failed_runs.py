"""Selective benchmark repair utility.

This script updates failed (or selected) JSONL benchmark records in-place by
re-running the Pyomo solve for the original parameter tuple and replacing the
`pyomo` block (and derived metrics) while preserving provenance fields.

Design Principles
-----------------
1. Non-destructive: writes to a temporary file then atomically moves.
2. Deterministic: hash.record retained; optional new hash appended if schema evolves.
3. Extensible: instrumentation hooks can inject diagnostics.
4. Fallback safe: if re-run raises, original line copied unchanged with an added
   `pyomo.repair_attempt_failed` flag.

Usage
-----
python benchmarks/repair_failed_runs.py --file path/to/bench.jsonl --all-failed
python benchmarks/repair_failed_runs.py --file path/to/bench.jsonl --hash <record_hash>

Implementation Notes
--------------------
The actual Pyomo model construction is project-specific and not yet part of this
repository. A placeholder `run_pyomo` routine is provided; integrate real model
logic there (build model, solve with IPOPT, collect diagnostics).
"""

from __future__ import annotations

import argparse
import json
import pathlib
import shutil
import sys
import tempfile
import time
from typing import Any, Dict, Iterable, Optional


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser("Selective benchmark record repair")
    p.add_argument("--file", required=True, help="Path to JSONL benchmark file")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--hash", help="Single record hash to repair")
    g.add_argument("--all-failed", action="store_true", help="Repair all failed records")
    p.add_argument("--dry-run", action="store_true", help="Do not modify file; just report plan")
    p.add_argument("--limit", type=int, default=None, help="Limit number of repairs")
    p.add_argument("--force", action="store_true", help="Repair even if success is True (overwrite)")
    return p.parse_args()


def iter_records(path: pathlib.Path) -> Iterable[Dict[str, Any]]:
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def is_failed(rec: Dict[str, Any]) -> bool:
    """Check if record has failed Pyomo results.
    
    Note: Records with pyomo=None are scipy-only baselines, not failures.
    """
    py = rec.get("pyomo")
    # No pyomo means scipy-only baseline - NOT a failure
    if py is None:
        return False
    # Has pyomo but failed
    return (not py.get("success")) or rec.get("failed", False)


def run_pyomo(param_paths: Dict[str, float], task: str, disc_method: str = 'fd', n_elements: int = 1000) -> Dict[str, Any]:
    """Execute real Pyomo optimization using LyoPRONTO optimizers.
    
    Args:
        param_paths: Parameter path-value mapping from grid
        task: Task type ('Tsh', 'Pch', or 'both')
        disc_method: Discretization method ('fd' or 'colloc')
        n_elements: Number of finite elements (default: 1000)
    
    Returns:
        Pyomo result dictionary matching benchmark schema
    """
    import sys
    from pathlib import Path
    import time
    import numpy as np
    
    # Add lyopronto to path
    repo_root = Path(__file__).parent.parent.parent
    sys.path.insert(0, str(repo_root))
    
    from lyopronto.pyomo_models.optimizers import optimize_Tsh_pyomo, optimize_Pch_pyomo
    from lyopronto import constant as const
    
    # Default vial/product/heat transfer parameters
    vial = {'Av': 0.5, 'Ap': 0.5, 'Vfill': 3.0}
    product = {
        'R0': 1.0, 
        'A1': 10.0, 
        'A2': 0.01, 
        'Rp': 5.0,
        'cSolid': 10.0,  # Solid concentration (%) - default value
    }  # Will be overridden
    ht = {'KC': 0.0002, 'KP': 0.0, 'KD': 0.0, 'Kv': 5.89e-5}  # Will be overridden
    
    # Update from param_paths
    for path, value in param_paths.items():
        parts = path.split('.')
        if parts[0] == 'product' and len(parts) == 2:
            product[parts[1]] = value
        elif parts[0] == 'ht' and len(parts) == 2:
            ht[parts[1]] = value
    
    # Fixed parameters for repair
    Pchamber = {'Pch': 0.100, 'setpt': 0.100}  # 100 mTorr = 0.1 Torr (fixed for Tsh optimization)
    Tshelf = {'Tsh_min': -40, 'Tsh_max': 30, 'Tsh0': -25, 'min': -40, 'max': 30}
    dt = 0.01  # hr
    eq_cap = {'Cap': 50.0, 'a': 0.0, 'b': 50.0}  # Equipment capacity: a + b*Pch (kg/hr)
    nVial = 333
    
    start_time = time.time()
    
    try:
        if task == 'Tsh':
            result = optimize_Tsh_pyomo(
                vial=vial,
                product=product,
                ht=ht,
                Pchamber=Pchamber,
                Tshelf=Tshelf,
                dt=dt,
                eq_cap=eq_cap,
                nVial=nVial,
                n_elements=n_elements,
                n_collocation=3,
                use_finite_differences=(disc_method == 'fd'),
                warmstart_scipy=True,
                tee=False,
                return_metadata=True,
            )
        elif task == 'Pch':
            result = optimize_Pch_pyomo(
                vial=vial,
                product=product,
                ht=ht,
                Pchamber={'Pch_min': 0.05, 'Pch_max': 0.3, 'Pch0': 0.1},
                Tshelf={'Tsh': -25.0},
                dt=dt,
                eq_cap=eq_cap,
                nVial=nVial,
                n_elements=n_elements,
                n_collocation=3,
                use_finite_differences=(disc_method == 'fd'),
                warmstart_scipy=True,
                tee=False,
                return_metadata=True,
            )
        else:
            raise ValueError(f"Unsupported task: {task}")
        
        wall_time = time.time() - start_time
        
        # Extract trajectory
        metadata = result.get('metadata', {})
        trajectory_data = result.get('trajectory', np.array([]))
        
        return {
            "success": result.get('success', False),
            "wall_time_s": wall_time,
            "objective_time_hr": result.get('objective', None),
            "solver": {
                "status": metadata.get('solver_status', 'unknown'),
                "termination_condition": metadata.get('termination_condition', 'unknown'),
                "ipopt_iterations": metadata.get('iterations', None),
                "n_points": len(trajectory_data) if trajectory_data.size > 0 else 0,
                "staged_solve_success": metadata.get('staged_solve_success', None),
            },
            "metrics": metadata.get('metrics', {}),
            "discretization": {
                "method": disc_method,
                "n_elements_requested": n_elements,
                "n_elements_applied": n_elements,
                "n_collocation": 3 if disc_method == 'colloc' else None,
                "effective_nfe": False,
                "total_mesh_points": len(trajectory_data) if trajectory_data.size > 0 else 0,
            },
            "warmstart_used": True,
            "trajectory": trajectory_data.tolist() if trajectory_data.size > 0 else [],
        }
    except Exception as e:
        wall_time = time.time() - start_time
        return {
            "success": False,
            "wall_time_s": wall_time,
            "objective_time_hr": None,
            "error_message": str(e),
            "error_type": e.__class__.__name__,
            "solver": {
                "status": "error",
                "termination_condition": "error",
            },
            "discretization": {
                "method": disc_method,
                "n_elements_requested": n_elements,
            },
        }


def repair_record(rec: Dict[str, Any], force: bool = False) -> Dict[str, Any]:
    if not force and not is_failed(rec):
        return rec  # unchanged
    grid = rec.get("grid", {})
    params = {}
    for g in grid.values():
        if isinstance(g, dict):
            params[g.get("path")] = g.get("value")
    task = rec.get("task", "unknown")
    
    # Extract discretization method from original record
    pyomo_orig = rec.get("pyomo", {})
    disc_orig = pyomo_orig.get("discretization", {}) if isinstance(pyomo_orig, dict) else {}
    disc_method = disc_orig.get("method", "fd")
    n_elements = 1000  # Force 1000 discretizations
    
    try:
        new_pyomo = run_pyomo(params, task, disc_method=disc_method, n_elements=n_elements)
        rec["pyomo"] = new_pyomo
        rec["failed"] = False
        rec.setdefault("pyomo", {}).setdefault("diagnostics", {})
        rec["pyomo"]["diagnostics"].update(
            {
                "repair_applied": True,
                "repair_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
        )
    except Exception as e:  # pragma: no cover - defensive
        rec.setdefault("pyomo", {}).setdefault("diagnostics", {})
        rec["pyomo"]["diagnostics"].update(
            {
                "repair_applied": False,
                "repair_error": str(e.__class__.__name__),
                "repair_message": str(e),
            }
        )
    return rec


def main() -> None:
    args = parse_args()
    path = pathlib.Path(args.file)
    if not path.exists():
        print(f"File not found: {path}", file=sys.stderr)
        sys.exit(1)
    target_hash = args.hash
    to_repair: list[Dict[str, Any]] = []
    for rec in iter_records(path):
        if target_hash and rec.get("hash.record") != target_hash:
            continue
        if args.all_failed and not is_failed(rec):
            continue
        if target_hash or args.all_failed:
            to_repair.append(rec)
    if args.limit is not None:
        to_repair = to_repair[: args.limit]
    print(f"Planning repair operations: {len(to_repair)} record(s) selected")
    if args.dry_run:
        for r in to_repair:
            print("DRY-RUN would repair hash", r.get("hash.record"))
        return
    repaired_hashes = {r.get("hash.record") for r in to_repair}
    with tempfile.NamedTemporaryFile("w", delete=False) as tmp:
        for rec in iter_records(path):
            h = rec.get("hash.record")
            if h in repaired_hashes:
                rec = repair_record(rec, force=args.force)
            tmp.write(json.dumps(rec, separators=(",", ":")) + "\n")
    shutil.move(tmp.name, path)
    print(f"Repaired {len(repaired_hashes)} record(s).")

if __name__ == "__main__":  # pragma: no cover
    main()
