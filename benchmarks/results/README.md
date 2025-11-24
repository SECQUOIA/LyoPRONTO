# Benchmark Results Directory

This directory contains all benchmark results organized in a **standardized structure**.

## Directory Structure

Each benchmark folder follows this structure:

```
benchmarks/results/<benchmark_name>/
├── raw/                    # Raw JSONL benchmark data
│   └── *.jsonl            # Benchmark output files
├── processed/             # Processed analysis results
│   ├── summary.json       # Summary statistics by method
│   └── comparison_table.csv  # Detailed comparison table
└── figures/               # Generated visualizations
    └── <task>/           # Task-specific plots (Tsh, Pch, both)
        ├── objective_diff_heatmap_*.png
        ├── speedup_heatmap_*.png
        ├── nominal_trajectory_*.png
        ├── nominal_ramp_constraints.png
        └── speedup_barplot.png
```

## Available Benchmarks

### Active Benchmarks
- **`test/`** - Tsh optimization test (2×2 parameter grid, single task)
- **`pch_test/`** - Pch optimization test (2×2 parameter grid, single task)
- **`v1_baseline/`** - **Multi-task benchmark** with Tsh, Pch, and both (3×3 grids, various ramp constraints)

### Archived
- **`archive/`** - Old benchmark files (legacy format, kept for reference)

## Multi-Task Benchmarks

A single benchmark folder can contain **multiple tasks**:
- **`Tsh`** - Optimize shelf temperature only
- **`Pch`** - Optimize chamber pressure only  
- **`both`** - Simultaneous optimization of Tsh and Pch

Example: `v1_baseline/raw/` contains:
- `baseline_Tsh_3x3_ramp40_free.jsonl` → Tsh task
- `baseline_Pch_3x3_ramp005_free.jsonl` → Pch task
- `baseline_both_3x3_ramp40_005_free.jsonl` → both task

Running `generate_reports.py` on a multi-task folder creates separate `figures/<task>/` directories for each task.

## Workflow

### 1. Generate Benchmark
```bash
python benchmarks/scripts/grid_cli.py generate \
    --task Tsh \
    --scenario baseline \
    --vary product.R0=0.4,0.8 \
    --vary product.A1=5,20 \
    --methods fd,colloc \
    --n-elements 1000 \
    --out benchmarks/results/<benchmark_name>/raw/<task>_benchmark.jsonl
```

### 2. Analyze Results
```bash
python benchmarks/scripts/generate_reports.py \
    benchmarks/results/<benchmark_name>/raw \
    --output benchmarks/results/<benchmark_name>
```

This creates `processed/` and `figures/` with all analysis outputs.

### 3. View in Notebook
Open `benchmarks/notebooks/grid_analysis_SIMPLE.ipynb` and set:
```python
benchmark_folder = "<benchmark_name>"
```

Then run all cells to view heatmaps, trajectories, and comparisons.

---

**Migration Notes (Nov 21, 2025)**: Standardized all folders to consistent 3-tier structure (`raw/`, `processed/`, `figures/`)
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
