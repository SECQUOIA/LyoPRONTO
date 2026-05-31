# Benchmark Results Directory

This directory contains generated benchmark data from comparing Pyomo and scipy optimizers.

## Version Control Policy

Generated results are **not tracked in git** by default (see `.gitignore`). Results can be reproduced by running the benchmark scripts.

## Representative Examples (Tracked)

The following files are kept in version control as reference examples:

- **`baseline_Tsh_3x3_summary.jsonl`**
  - Tsh optimization on 3×3 parameter grid (A1 × KC)
  - 27 runs: 9 scipy baseline, 9 FD (n=24), 9 collocation (n=24, ncp=3)
  - Generated with IPOPT warmstart properly disabled
  - Metrics only; full trajectories are not tracked

- **`baseline_Pch_3x3_summary.jsonl`**
  - Pch optimization on the same 3×3 parameter grid
  - 27 runs: 9 scipy baseline, 9 FD (n=24), 9 collocation (n=24, ncp=3)
  - Metrics only; full trajectories are not tracked

## Regenerating Results

```bash
# Generate the reference benchmark
python benchmarks/grid_cli.py generate \
  --task Tsh --scenario baseline \
  --vary product.A1=16,18,20 \
  --vary ht.KC=2.75e-4,3.3e-4,4.0e-4 \
  --methods scipy,fd,colloc \
  --n-elements 24 --n-collocation 3 \
  --out benchmarks/results/baseline_Tsh_3x3_summary.jsonl \
  --force

python benchmarks/grid_cli.py generate \
  --task Pch --scenario baseline \
  --vary product.A1=16,18,20 \
  --vary ht.KC=2.75e-4,3.3e-4,4.0e-4 \
  --methods scipy,fd,colloc \
  --n-elements 24 --n-collocation 3 \
  --out benchmarks/results/baseline_Pch_3x3_summary.jsonl \
  --force

# Analyze and generate plots
JSONL_PATH=benchmarks/results/baseline_Tsh_3x3_summary.jsonl jupyter notebook benchmarks/grid_analysis.ipynb
```

## Other Generated Files (Not Tracked)

Any other files or directories in this directory are local working artifacts and should not be committed. This includes raw JSONL trajectories, generated figures, CSV exports, notebook outputs, and processed summary files unless they are explicitly promoted to the tracked reference list above.
