#!/usr/bin/env python
"""Extract scipy-only records from a benchmark JSONL file.

This creates a new file with only the scipy results (pyomo set to None),
which can be used as input for merge operations or analysis.

Usage:
    python benchmarks/extract_scipy.py \
        --input benchmarks/results/baseline_Pch_3x3.jsonl \
        --output benchmarks/results/baseline_Pch_3x3_scipy_only.jsonl
"""
import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description='Extract scipy-only records from benchmark JSONL')
    parser.add_argument('--input', required=True, help='Input JSONL file')
    parser.add_argument('--output', required=True, help='Output JSONL file with scipy records only')
    args = parser.parse_args()
    
    input_path = Path(args.input)
    output_path = Path(args.output)
    
    if not input_path.exists():
        print(f"ERROR: Input file not found: {input_path}")
        return 1
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    scipy_count = 0
    with input_path.open('r') as f_in, output_path.open('w') as f_out:
        for line in f_in:
            rec = json.loads(line)
            # Only keep records where pyomo is None (scipy-only records)
            if rec.get('pyomo') is None and rec.get('scipy') is not None:
                f_out.write(line)
                scipy_count += 1
    
    print(f"✓ Extracted {scipy_count} scipy-only records")
    print(f"→ {output_path}")
    
    return 0


if __name__ == '__main__':
    exit(main())
