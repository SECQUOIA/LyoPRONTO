#!/usr/bin/env python3
"""Generate comprehensive analysis reports from benchmark JSONL files.

Usage:
    python generate_reports.py <benchmark_dir> [--output <output_dir>]
    
Example:
    python generate_reports.py results/v2_free_initial --output analysis/v2_free_initial
    
This will:
1. Discover all JSONL files in benchmark_dir
2. For each task (Tsh/Pch/both), generate:
   - Objective difference heatmaps (FD and collocation vs scipy)
   - Speedup heatmaps
   - Comparison tables (CSV)
   - Nominal case trajectories
   - Summary statistics (JSON)
3. Save all artifacts to output_dir/<task>/
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, Any

# Add benchmarks to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.data_loader import (
    load_benchmark_jsonl,
    organize_by_method,
    extract_parameter_grid,
)
from src.analyze_benchmark import (
    compute_objective_differences,
    compute_speedups,
    extract_nominal_case,
    generate_summary_stats,
    validate_solver_status,
    pivot_for_heatmap,
)
from src.visualization import (
    plot_objective_diff_heatmaps,
    plot_speedup_heatmaps,
    plot_trajectory_comparison,
    plot_ramp_constraints,
    create_comparison_table,
    plot_summary_barplot,
)
from src.paths import get_results_dir, get_figures_dir, get_processed_dir


def analyze_single_benchmark(
    jsonl_path: Path,
    output_dir: Path,
    task: str,
) -> Dict[str, Any]:
    """Analyze a single benchmark JSONL file and generate all artifacts.
    
    Args:
        jsonl_path: Path to benchmark JSONL file
        output_dir: Directory to save outputs
        task: Task type ('Tsh', 'Pch', or 'both')
        
    Returns:
        Dict with analysis summary
    """
    print(f"\n{'='*70}")
    print(f"Analyzing: {jsonl_path.name}")
    print(f"Task: {task}")
    print(f"Output: {output_dir}")
    print(f"{'='*70}\n")
    
    # Create output subdirectories (processed/ and figures/task/)
    processed_dir = output_dir / 'processed'
    figures_dir = output_dir / 'figures' / task
    processed_dir.mkdir(parents=True, exist_ok=True)
    figures_dir.mkdir(parents=True, exist_ok=True)
    
    # Load data
    print("Loading benchmark data...")
    records = load_benchmark_jsonl(jsonl_path)
    print(f"  Loaded {len(records)} records")
    
    # Organize by method
    records_by_method = organize_by_method(records)
    print(f"  Scipy: {len(records_by_method['scipy'])} records")
    print(f"  FD: {len(records_by_method['fd'])} records")
    print(f"  Collocation: {len(records_by_method['colloc'])} records")
    
    # Extract parameter info
    param_info = extract_parameter_grid(records)
    param1_name = param_info.get('param1_name', 'param1')
    param2_name = param_info.get('param2_name', 'param2')
    param1_vals = param_info.get('param1_values', [])
    param2_vals = param_info.get('param2_values', [])
    
    print(f"\nParameter Grid:")
    print(f"  {param1_name}: {param1_vals}")
    print(f"  {param2_name}: {param2_vals}")
    
    # Compute comparisons
    print("\nComputing objective differences...")
    comparison_df = compute_objective_differences(records_by_method)
    print(f"  Generated {len(comparison_df)} comparison records")
    
    if len(comparison_df) == 0:
        print("  WARNING: No successful comparisons found!")
        return {'status': 'no_data'}
    
    # Generate summary statistics
    print("\nGenerating summary statistics...")
    summary_stats = generate_summary_stats(comparison_df)
    
    # Save summary JSON
    summary_path = processed_dir / 'summary.json'
    with open(summary_path, 'w') as f:
        json.dump(summary_stats, f, indent=2)
    print(f"  Saved: {summary_path.name}")
    
    # Create comparison table
    print("\nCreating comparison table...")
    table_path = processed_dir / 'comparison_table.csv'
    create_comparison_table(comparison_df, table_path)
    print(f"  Saved: {table_path.name}")
    
    # Generate objective difference heatmaps
    print("\nGenerating objective difference heatmaps...")
    
    obj_diff_base = figures_dir / 'objective_diff_heatmap'
    obj_diff_files = plot_objective_diff_heatmaps(
        comparison_df,
        param1_name,
        param2_name,
        obj_diff_base,
    )
    for method_name, path in obj_diff_files.items():
        print(f"  Saved: {path.name}")
    
    # Generate speedup heatmaps
    print("\nGenerating speedup heatmaps...")
    
    speedup_base = figures_dir / 'speedup_heatmap'
    speedup_files = plot_speedup_heatmaps(
        comparison_df,
        param1_name,
        param2_name,
        speedup_base,
    )
    for method_name, path in speedup_files.items():
        print(f"  Saved: {path.name}")
    
    # Generate nominal case trajectory choosing a combo present for all methods
    if len(param1_vals) > 0 and len(param2_vals) > 0:
        print("\nGenerating nominal trajectory...")
        # Find common parameter combinations across all methods
        method_combos = {}  # method -> set of (p1, p2) combos
        for rec in records:
            pyomo = rec.get('pyomo')
            if not isinstance(pyomo, dict):
                continue
            if not pyomo.get('success', False):
                continue  # only include successful solves
            disc_method = pyomo.get('discretization', {}).get('method')
            if not disc_method:
                continue
            grid = rec.get('grid', {})
            p1 = grid.get('param1', {}).get('value')
            p2 = grid.get('param2', {}).get('value')
            if p1 is None or p2 is None:
                continue
            if disc_method not in method_combos:
                method_combos[disc_method] = set()
            method_combos[disc_method].add((p1, p2))
        
        # Find combos common to all methods
        if not method_combos:
            print("  No successful Pyomo runs; skipping trajectory plot")
        else:
            common = set.intersection(*method_combos.values()) if method_combos else set()
            if not common:
                print(f"  No common parameter combo across all methods; skipping trajectory plot")
            else:
                median_p1 = param1_vals[len(param1_vals)//2]
                median_p2 = param2_vals[len(param2_vals)//2]
                chosen_p1, chosen_p2 = min(common, key=lambda xy: abs(xy[0]-median_p1) + abs(xy[1]-median_p2))
                
                # Extract scipy baseline
                traj_scipy = extract_nominal_case(records, chosen_p1, chosen_p2, 'scipy')
                
                # Extract all Pyomo method trajectories dynamically
                traj_pyomo = {}
                for method in method_combos.keys():
                    traj = extract_nominal_case(records, chosen_p1, chosen_p2, method)
                    if traj is not None:
                        traj_pyomo[method] = traj
                
                print(f"  Nominal combo: {param1_name}={chosen_p1}, {param2_name}={chosen_p2}")
                traj_lens = ", ".join([f"{m}:{len(t)}" for m, t in traj_pyomo.items()])
                print(f"  Trajectory lengths -> scipy:{0 if traj_scipy is None else len(traj_scipy)}, {traj_lens}")
                
                traj_base = figures_dir / 'nominal_trajectory'
                param_str = f"({param1_name}={chosen_p1}, {param2_name}={chosen_p2})"
                saved_files = plot_trajectory_comparison(
                    traj_scipy,
                    traj_pyomo,
                    traj_base,
                    task,
                    param_str,
                )
                for var_name, path in saved_files.items():
                    print(f"  Saved: {path.name}")
                
                # Also generate ramp constraint plot
                # Extract ramp constraints from first Pyomo record with this combo
                ramp_constraints = {"Tsh": None, "Pch": None}
                for rec in records:
                    if rec.get('pyomo') and rec.get('pyomo').get('ramp_constraints'):
                        ramp_constraints = rec['pyomo']['ramp_constraints']
                        break
                
                ramp_path = figures_dir / 'nominal_ramp_constraints.png'
                plot_ramp_constraints(
                    traj_scipy,
                    traj_pyomo,
                    ramp_path,
                    task,
                    param_str,
                    max_ramp_rate_Tsh=ramp_constraints.get('Tsh'),
                    max_ramp_rate_Pch=ramp_constraints.get('Pch'),
                )
                print(f"  Saved: {ramp_path.name}")
    
    # Generate summary bar plot
    if len(summary_stats) > 0:
        print("\nGenerating summary plots...")
        barplot_path = figures_dir / 'speedup_barplot.png'
        plot_summary_barplot(summary_stats, barplot_path, metric='speedup')
        print(f"  Saved: {barplot_path.name}")
    
    print(f"\n✓ Analysis complete for {task}")
    return {'status': 'success', 'summary': summary_stats}


def discover_benchmarks(benchmark_dir: Path) -> Dict[str, Path]:
    """Discover benchmark JSONL files in directory.
    
    Args:
        benchmark_dir: Directory containing benchmark files (checks raw/ subdirectory if present)
        
    Returns:
        Dict mapping task name to JSONL path
    """
    benchmarks = {}
    
    # Check if we're given a version dir - look in raw/ subdirectory
    raw_dir = benchmark_dir / 'raw'
    search_dir = raw_dir if raw_dir.exists() else benchmark_dir
    
    # Look for standard naming patterns
    for jsonl_file in search_dir.glob('*.jsonl'):
        name = jsonl_file.stem
        
        # Try to infer task from filename
        if 'Tsh' in name and 'both' not in name.lower():
            benchmarks['Tsh'] = jsonl_file
        elif 'Pch' in name and 'both' not in name.lower():
            benchmarks['Pch'] = jsonl_file
        elif 'both' in name.lower():
            benchmarks['both'] = jsonl_file
    
    return benchmarks


def main():
    parser = argparse.ArgumentParser(
        description='Generate analysis reports from benchmark data',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument(
        'benchmark_dir',
        type=Path,
        help='Directory containing benchmark JSONL files'
    )
    parser.add_argument(
        '--output',
        type=Path,
        help='Output directory for analysis (default: analysis/<benchmark_dir_name>)'
    )
    parser.add_argument(
        '--task',
        choices=['Tsh', 'Pch', 'both', 'all'],
        default='all',
        help='Specific task to analyze (default: all)'
    )
    
    args = parser.parse_args()
    
    # Validate benchmark directory
    if not args.benchmark_dir.exists():
        print(f"Error: Benchmark directory not found: {args.benchmark_dir}")
        sys.exit(1)
    
    # Determine output directory
    if args.output:
        output_base = args.output
    else:
        # Default: write back into the benchmark_dir itself (results/test/ structure)
        output_base = args.benchmark_dir
    
    print(f"\nBenchmark Analysis Tool")
    print(f"{'='*70}")
    print(f"Input: {args.benchmark_dir}")
    print(f"Output: {output_base}")
    
    # Discover benchmarks
    benchmarks = discover_benchmarks(args.benchmark_dir)
    
    if not benchmarks:
        print(f"\nNo benchmark files found in {args.benchmark_dir}")
        sys.exit(1)
    
    print(f"\nDiscovered benchmarks:")
    for task, path in benchmarks.items():
        print(f"  {task}: {path.name}")
    
    # Analyze each benchmark
    results = {}
    tasks_to_analyze = [args.task] if args.task != 'all' else benchmarks.keys()
    
    for task in tasks_to_analyze:
        if task not in benchmarks:
            print(f"\nWarning: No benchmark file found for task '{task}'")
            continue
        
        jsonl_path = benchmarks[task]
        # Pass output_base - the function creates figures/task/ and processed/ subdirs
        output_dir = output_base
        
        try:
            result = analyze_single_benchmark(jsonl_path, output_dir, task)
            results[task] = result
        except Exception as e:
            print(f"\n✗ Error analyzing {task}: {e}")
            import traceback
            traceback.print_exc()
            results[task] = {'status': 'error', 'message': str(e)}
    
    # Summary
    print(f"\n{'='*70}")
    print(f"ANALYSIS SUMMARY")
    print(f"{'='*70}")
    for task, result in results.items():
        status = result.get('status', 'unknown')
        print(f"{task}: {status.upper()}")
    
    print(f"\nAll outputs saved to: {output_base}")
    print("\n" + "="*70)
    print("📊 VIEW RESULTS IN NOTEBOOK")
    print("="*70)
    
    # Extract benchmark folder name from output_base
    # e.g., benchmarks/results/pch_test -> "pch_test"
    benchmark_folder = output_base.name
    
    print(f"\n1. Open: benchmarks/notebooks/grid_analysis_SIMPLE.ipynb")
    print(f"\n2. In the configuration cell, set:")
    print(f'   benchmark_folder = "{benchmark_folder}"')
    print(f"\n3. Run all cells to view:")
    for task in results.keys():
        print(f"   • {task} heatmaps (objective difference & speedup)")
        print(f"   • {task} trajectory comparisons")
        print(f"   • {task} ramp constraint plots")
    print("\n" + "="*70)
    

if __name__ == '__main__':
    main()
