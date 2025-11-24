#!/usr/bin/env python
"""Merge scipy results from old benchmark with new Pyomo results.

This allows regenerating Pyomo benchmarks with different discretization
without recomputing scipy baselines (which are deterministic and expensive).

Usage:
    python benchmarks/merge_scipy_results.py \
        --old benchmarks/results/baseline_Tsh_3x3.jsonl \
        --new benchmarks/results/baseline_Tsh_3x3_fine_pyomo_only.jsonl \
        --out benchmarks/results/baseline_Tsh_3x3_fine.jsonl
"""
import argparse
import json
from pathlib import Path
from typing import Dict, Tuple


def get_grid_key(rec: Dict) -> Tuple:
    """Extract grid parameter tuple for matching records."""
    grid = rec.get('grid', {})
    params = []
    for key in sorted(grid.keys()):
        if key.startswith('param'):
            params.append((grid[key]['path'], grid[key]['value']))
    return tuple(params)


def main():
    parser = argparse.ArgumentParser(description='Merge scipy results with new Pyomo results')
    parser.add_argument('--old', required=True, help='Old JSONL with scipy results')
    parser.add_argument('--new', required=True, help='New JSONL with Pyomo results only')
    parser.add_argument('--out', required=True, help='Output JSONL with merged results')
    args = parser.parse_args()
    
    old_path = Path(args.old)
    new_path = Path(args.new)
    out_path = Path(args.out)
    
    if not old_path.exists():
        print(f"ERROR: Old file not found: {old_path}")
        return 1
    if not new_path.exists():
        print(f"ERROR: New file not found: {new_path}")
        return 1
    
    # Load scipy results from old file
    print(f"Loading scipy results from {old_path}...")
    scipy_cache = {}
    with old_path.open('r') as f:
        for line in f:
            rec = json.loads(line)
            if rec.get('scipy'):
                key = get_grid_key(rec)
                scipy_cache[key] = rec['scipy']
    
    print(f"  Cached {len(scipy_cache)} scipy results")
    
    # Process new file and merge
    print(f"Merging with new Pyomo results from {new_path}...")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    
    merged_count = 0
    missing_count = 0
    
    with new_path.open('r') as f_in, out_path.open('w') as f_out:
        for line in f_in:
            rec = json.loads(line)
            key = get_grid_key(rec)
            
            # Replace scipy section with cached version if available
            if key in scipy_cache:
                rec['scipy'] = scipy_cache[key]
                merged_count += 1
            else:
                print(f"  WARNING: No cached scipy result for {key}")
                missing_count += 1
            
            f_out.write(json.dumps(rec) + '\n')
    
    print(f"✓ Merged {merged_count} records")
    if missing_count > 0:
        print(f"⚠ {missing_count} records missing scipy cache")
    print(f"→ {out_path}")
    
    return 0


if __name__ == '__main__':
    exit(main())
