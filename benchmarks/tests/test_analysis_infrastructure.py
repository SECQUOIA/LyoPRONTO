#!/usr/bin/env python3
"""Test the benchmark analysis infrastructure on existing data.

This script demonstrates the new analysis pipeline by processing
one of the existing benchmark files.
"""
import sys
from pathlib import Path

# Add benchmarks to path
sys.path.insert(0, str(Path(__file__).parent))

from data_loader import load_benchmark_jsonl, organize_by_method
from analyze_benchmark import compute_objective_differences, generate_summary_stats

def test_analysis():
    """Test analysis on existing benchmark data."""
    
    # Find an existing benchmark file
    results_dir = Path(__file__).parent / 'results'
    benchmark_files = list(results_dir.glob('baseline_Tsh_3x3_ramp40_free.jsonl'))
    
    if not benchmark_files:
        print("No benchmark files found to test.")
        print("Expected: results/baseline_Tsh_3x3_ramp40_free.jsonl")
        return False
    
    benchmark_file = benchmark_files[0]
    print(f"Testing with: {benchmark_file.name}\n")
    
    # Load data
    print("Loading data...")
    try:
        records = load_benchmark_jsonl(benchmark_file)
        print(f"✓ Loaded {len(records)} records\n")
    except Exception as e:
        print(f"✗ Error loading data: {e}")
        return False
    
    # Organize by method
    print("Organizing by method...")
    try:
        by_method = organize_by_method(records)
        print(f"✓ Scipy: {len(by_method['scipy'])} records")
        print(f"✓ FD: {len(by_method['fd'])} records")
        print(f"✓ Collocation: {len(by_method['colloc'])} records\n")
    except Exception as e:
        print(f"✗ Error organizing: {e}")
        return False
    
    # Compute comparisons
    print("Computing objective differences...")
    try:
        comparison_df = compute_objective_differences(by_method)
        print(f"✓ Generated {len(comparison_df)} comparison records\n")
        
        if len(comparison_df) > 0:
            print("Sample comparison data:")
            print(comparison_df.head())
            print()
    except Exception as e:
        print(f"✗ Error computing comparisons: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # Generate summary stats
    if len(comparison_df) > 0:
        print("Generating summary statistics...")
        try:
            summary = generate_summary_stats(comparison_df)
            print("✓ Summary generated:")
            for method, stats in summary.items():
                print(f"\n{method.upper()}:")
                print(f"  Mean speedup: {stats['mean_speedup']:.2f}×")
                print(f"  Mean % diff: {stats['mean_pct_diff']:.2f}%")
                print(f"  Cases: {stats['n_cases']}")
        except Exception as e:
            print(f"✗ Error generating summary: {e}")
            return False
    
    print("\n" + "="*70)
    print("✓ All tests passed! Infrastructure is working.")
    print("="*70)
    return True


if __name__ == '__main__':
    success = test_analysis()
    sys.exit(0 if success else 1)
