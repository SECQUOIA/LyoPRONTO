# Benchmarks Directory Structure

This directory contains the Pyomo benchmark infrastructure for LyoPRONTO.

## 📁 Directory Organization

```
benchmarks/
├── src/                    # Reusable Python modules (import as benchmarks.src)
│   ├── __init__.py        # Package initialization
│   ├── paths.py           # Centralized path resolution
│   ├── data_loader.py     # JSONL parsing and organization
│   ├── analyze_benchmark.py  # Metrics computation
│   ├── visualization.py   # Plot generation
│   ├── adapters.py        # Data source adapters
│   ├── scenarios.py       # Benchmark scenario definitions
│   └── schema.py          # Data validation schemas
│
├── scripts/               # CLI entry points and orchestration
│   ├── grid_cli.py        # Main CLI for benchmark generation
│   ├── generate_reports.py  # Analysis report generator
│   ├── run_grid.py        # Grid search runner
│   ├── run_batch.py       # Batch execution
│   ├── validate.py        # Result validation
│   └── repair_failed_runs.py  # Retry failed benchmarks
│
├── notebooks/             # Interactive analysis notebooks
│   ├── grid_analysis_SIMPLE.ipynb  # Primary analysis viewer
│   └── grid_analysis.ipynb         # Advanced analysis (WIP)
│
├── results/               # Versioned benchmark results
│   └── <version>/         # e.g., "test", "v1_baseline", "v2_free_initial"
│       ├── raw/           # Original benchmark outputs (JSONL)
│       ├── processed/     # Derived data (CSV, JSON summaries)
│       └── figures/       # Generated plots (PNG)
│           ├── Tsh/       # Shelf temperature optimization plots
│           ├── Pch/       # Chamber pressure optimization plots
│           └── both/      # Joint Tsh+Pch optimization plots
│
├── archive/               # Historical artifacts
│   ├── legacy_notebooks/  # Superseded notebooks
│   ├── superseded_figures/  # Old/combined plot versions
│   └── README.md          # Archive documentation
│
├── tests/                 # Integration tests for benchmark infra
│
├── cleanup.py             # Automated maintenance utility
└── README.md              # This file
```

## 🚀 Quick Start

### Running Benchmarks

```bash
# From benchmarks/ directory:

# 1. Generate a 2×2 grid benchmark for Tsh optimization
python scripts/grid_cli.py generate \
    --task Tsh \
    --param product.A1 10 20 \
    --param ht.KC 2e-4 4e-4 \
    --version test

# 2. Generate analysis reports (heatmaps, trajectories, summaries)
python scripts/generate_reports.py results/test

# 3. View results in notebook
jupyter notebook notebooks/grid_analysis_SIMPLE.ipynb
```

### Viewing Existing Results

```bash
# Open the notebook and set:
benchmark_version = "test"  # or "v1_baseline", etc.
task = "Tsh"  # or "Pch", "both"

# Run all cells to display:
# - Objective difference heatmaps (% vs scipy)
# - Speedup heatmaps (wall clock time)
# - Trajectory comparisons
# - Summary statistics
```

## 📊 Result Structure

Each benchmark version follows this pattern:

```
results/<version>/
├── raw/
│   └── Tsh_2x2_test.jsonl          # Raw benchmark data
├── processed/
│   ├── summary.json                 # Aggregated statistics
│   └── comparison_table.csv         # Detailed comparison table
└── figures/
    └── Tsh/
        ├── objective_diff_heatmap_fd.png       # FD objective difference
        ├── objective_diff_heatmap_colloc.png   # Collocation objective difference
        ├── speedup_heatmap_fd.png              # FD speedup
        ├── speedup_heatmap_colloc.png          # Collocation speedup
        ├── nominal_trajectory_shelf_temperature.png      # Tsh trajectory
        ├── nominal_trajectory_dried_fraction.png         # Dried fraction trajectory
        ├── nominal_ramp_constraints.png        # Ramp rate validation
        └── speedup_barplot.png                 # Summary bar chart
```

## 🔧 Module Usage

### Path Resolution (Recommended)

```python
from benchmarks.src.paths import get_results_dir, get_figures_dir, get_processed_dir

# Get versioned directories
raw_dir = get_results_dir("v1_baseline") / "raw"
figures_dir = get_figures_dir("v1_baseline", "Tsh")
processed_dir = get_processed_dir("v1_baseline")
```

**Benefits:**
- No hardcoded paths
- Consistent across scripts and notebooks
- Automatic path creation with `ensure_dir()`

### Data Loading

```python
from benchmarks.src.data_loader import load_benchmark_jsonl, organize_by_method

# Load benchmark results
records = load_benchmark_jsonl("results/test/raw/Tsh_2x2.jsonl")
by_method = organize_by_method(records)  # {'scipy': [...], 'fd': [...], 'colloc': [...]}
```

### Analysis

```python
from benchmarks.src.analyze_benchmark import compute_objective_differences, compute_speedups

obj_diff = compute_objective_differences(by_method)
speedups = compute_speedups(by_method)
```

### Visualization

```python
from benchmarks.src.visualization import plot_objective_diff_heatmaps, plot_trajectory_comparison

# Returns dict of saved files: {'fd': Path, 'colloc': Path}
heatmap_files = plot_objective_diff_heatmaps(obj_diff, output_dir=figures_dir)

# Returns dict: {'Tsh': Path, 'Pch': Path, 'Dried Fraction': Path}
traj_files = plot_trajectory_comparison(nominal_case, output_dir=figures_dir)
```

## 🧹 Maintenance

### Cleanup Utility

```bash
# Check for duplicates and naming violations (read-only)
python cleanup.py --version test --check-only

# Archive superseded files
python cleanup.py --version test --archive-duplicates

# Generate artifact manifest (inventory of all files)
python cleanup.py --version test --generate-manifest
```

**What it does:**
- Detects combined heatmaps when split versions exist
- Validates file naming conventions
- Archives duplicates to `archive/superseded_figures/`
- Generates `manifest.json` (file inventory with hashes/sizes)

### Naming Conventions

**Figures:**
- Trajectories: `nominal_trajectory_<variable>.png` (e.g., `nominal_trajectory_shelf_temperature.png`)
- Heatmaps: `<metric>_heatmap_<method>.png` (e.g., `objective_diff_heatmap_fd.png`)
- Summaries: `speedup_barplot.png`, `nominal_ramp_constraints.png`

**Data:**
- Raw: `<task>_<grid_size>_<label>.jsonl` (e.g., `Tsh_3x3_baseline.jsonl`)
- Processed: `comparison_table.csv`, `summary.json`, `manifest.json`

### Git Ignore Policy

- **Tracked:** Baseline results (`results/baseline/`), manifests, key figures
- **Ignored:** Test runs (`results/test/`), temporary files (`.tmp`), logs
- **Committed:** Source code in `src/`, `scripts/`, `notebooks/`

## 🗂️ Migration from Old Structure

The previous structure mixed source and generated artifacts:

```
# OLD (before cleanup)
benchmarks/
├── data_loader.py         # ❌ Root-level modules
├── visualization.py
├── grid_cli.py            # ❌ Scripts mixed with modules
├── both_grid_heatmaps.png # ❌ Generated files in root
analysis/                  # ❌ Duplicate structure
└── test/Tsh/*.png

# NEW (after cleanup)
benchmarks/
├── src/                   # ✅ Packaged modules
├── scripts/               # ✅ Separated CLI tools
├── results/test/figures/  # ✅ Unified artifact location
└── archive/               # ✅ Historical artifacts preserved
```

**Key improvements:**
1. **Separation:** Source code (`src/`) vs executables (`scripts/`) vs artifacts (`results/`)
2. **Versioning:** Results organized by version, not scattered
3. **Scalability:** Adding Pyomo methods requires no code changes (data-driven)
4. **Maintainability:** Automated cleanup, manifest tracking, `.gitignore` patterns

## 📚 Related Documentation

- `src/paths.py` - Path resolution API reference
- `archive/README.md` - Archive policy and contents
- `cleanup.py --help` - Maintenance utility usage
- `notebooks/grid_analysis_SIMPLE.ipynb` - Interactive analysis examples

## 🔄 Workflow Summary

1. **Generate:** `scripts/grid_cli.py generate ...` → `results/<version>/raw/*.jsonl`
2. **Analyze:** `scripts/generate_reports.py results/<version>` → `processed/` + `figures/`
3. **View:** Open `notebooks/grid_analysis_SIMPLE.ipynb`, set version/task, run cells
4. **Maintain:** Run `cleanup.py` periodically to archive duplicates and validate naming
5. **Version:** Create new version dirs for major benchmark runs (e.g., `v2_new_solver`)

## 💡 Best Practices

- **Use path helpers:** Import from `src.paths` instead of hardcoding
- **Version everything:** Create distinct `results/<version>/` for each major run
- **Archive old runs:** Compress with `cleanup.py` after 6 months
- **Check manifests:** Run `--generate-manifest` to inventory artifacts
- **Dynamic discovery:** Notebooks auto-detect Pyomo methods from `by_method` dict
- **Split over combined:** Prefer per-method/per-variable plots for scalability

## 🐛 Troubleshooting

**Import errors after restructure:**
```python
# ❌ Old:
from data_loader import load_benchmark_jsonl

# ✅ New:
from benchmarks.src.data_loader import load_benchmark_jsonl
# OR (from within benchmarks/)
from src.data_loader import load_benchmark_jsonl
```

**Path not found:**
```python
# ❌ Old:
analysis_dir = Path("analysis/test/Tsh")

# ✅ New:
from src.paths import get_figures_dir
figures_dir = get_figures_dir("test", "Tsh")
```

**Missing plots in notebook:**
- Check `figures_dir` path matches task
- Re-run `generate_reports.py` to regenerate
- Verify JSONL exists in `results/<version>/raw/`

## 🎯 Future Enhancements

- [ ] Automated compression of old result versions (tar.gz)
- [ ] Pre-commit hook for naming validation
- [ ] Parameter set IDs in filenames (for multi-grid runs)
- [ ] Interactive plotly versions of heatmaps
- [ ] CI integration for benchmark regression testing
