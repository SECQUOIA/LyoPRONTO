# Benchmark Results Directory

This directory contains generated benchmark data from comparing Pyomo and scipy optimizers.

## Version Control Policy

Most generated results are **not tracked in git** (see `.gitignore`). Results can be reproduced by running the benchmark scripts.

## Representative Examples (Tracked)

The following files are kept in version control as reference examples:

- **`baseline_Tsh_3x3.jsonl`** (29KB)
  - Tsh optimization on 3×3 parameter grid (A1 × KC)
  - 27 runs: 9 scipy baseline, 9 FD (n=24), 9 collocation (n=24, ncp=3)
  - Generated with IPOPT warmstart properly disabled
  - Demonstrates ~5-10% objective parity, ~250× speedup

- **`baseline_Tsh_3x3_objective_diff.png`**
  - Heatmap showing % objective difference from scipy baseline
  - FD and collocation methods side-by-side with shared colorbar

- **`baseline_Tsh_3x3_speedup.png`**
  - Heatmap showing wall-clock speedup over scipy
  - Demonstrates 9-344× speedup range

## Regenerating Results

```bash
# Generate the reference benchmark
python benchmarks/grid_cli.py generate \
  --task Tsh --scenario baseline \
  --vary product.A1=16,18,20 \
  --vary ht.KC=2.75e-4,3.3e-4,4.0e-4 \
  --methods scipy,fd,colloc \
  --n-elements 24 --n-collocation 3 \
  --out benchmarks/results/grid_Tsh_3x3_no_warmstart.jsonl \
  --force

# Analyze and generate plots
jupyter notebook benchmarks/grid_analysis.ipynb
```

## Other Generated Files (Not Tracked)

Any other `.jsonl`, `.png`, or `.csv` files in this directory are local working files and should not be committed.
