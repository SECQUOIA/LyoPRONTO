# Benchmark Analysis - Professional Infrastructure

This directory contains a professional benchmark analysis system for comparing Pyomo optimization methods (Finite Differences and Collocation) against the scipy baseline.

## 🏗️ Architecture

### Directory Structure
```
benchmarks/
├── results/                    # Raw benchmark data (JSONL)
│   ├── v2_free_initial/       # Current: Free initial conditions + fixed discretization  
│   └── archive/               # Old unorganized files
│
├── analysis/                   # Generated artifacts (auto-created)
│   └── v2_free_initial/
│       ├── Tsh/
│       │   ├── objective_diff_heatmap.png
│       │   ├── speedup_heatmap.png
│       │   ├── comparison_table.csv
│       │   ├── nominal_trajectory.png
│       │   └── summary.json
│       ├── Pch/
│       └── both/
│   
├── Core Modules:
├── data_loader.py             # JSONL loading & validation
├── analyze_benchmark.py       # Pure analysis functions
├── visualization.py           # Plotting utilities  
├── generate_reports.py        # CLI orchestrator ⭐
├── grid_cli.py               # Benchmark data generator
└── grid_analysis.ipynb       # Simplified viewer (100 lines, was 1800)
```

### Design Principles
- **Separation of Concerns**: Data → Analysis → Visualization → Presentation
- **Pure Functions**: Analysis logic is testable, no I/O
- **Versioning**: Each code change gets new version directory
- **Automation**: CLI-driven, reproducible, parallelizable

## 🚀 Quick Start

### 1. Generate Benchmarks
```bash
# Tsh optimization (3×3 grid, ramp constraints)
python grid_cli.py generate \
    --task Tsh --scenario baseline \
    --vary A1=5,10,20 KC=1e-4,2e-4,4e-4 \
    --methods scipy fd colloc \
    --n-elements 1000 \
    --ramp-Tsh-max 40.0 \
    --out results/v2_free_initial/Tsh_3x3_ramp40.jsonl

# Pch optimization
python grid_cli.py generate \
    --task Pch --scenario baseline \
    --vary A1=5,10,20 KC=1e-4,2e-4,4e-4 \
    --methods scipy fd colloc \
    --n-elements 1000 \
    --ramp-Pch-max 0.05 \
    --out results/v2_free_initial/Pch_3x3_ramp005.jsonl

# Joint optimization
python grid_cli.py generate \
    --task both --scenario baseline \
    --vary A1=5,10,20 KC=1e-4,2e-4,4e-4 \
    --methods scipy fd colloc \
    --n-elements 1000 \
    --ramp-Tsh-max 40.0 --ramp-Pch-max 0.05 \
    --out results/v2_free_initial/both_3x3_ramp40_005.jsonl
```

### 2. Generate Analysis ⭐
```bash
# Analyze all benchmarks in version directory
python generate_reports.py results/v2_free_initial

# Analyze specific task only
python generate_reports.py results/v2_free_initial --task Tsh

# Custom output location
python generate_reports.py results/v2_free_initial --output analysis/custom
```

**Output**: All figures, tables, and summaries automatically generated!

### 3. View in Notebook
```python
# In grid_analysis.ipynb (now just ~100 lines!)
benchmark_version = "v2_free_initial"
analysis_dir = Path(f"analysis/{benchmark_version}")

# Load and display pre-generated figures
display(Image(f"{analysis_dir}/Tsh/objective_diff_heatmap.png"))
display(Image(f"{analysis_dir}/Tsh/speedup_heatmap.png"))
pd.read_csv(f"{analysis_dir}/Tsh/comparison_table.csv")
```

## 📊 Generated Artifacts

For each task (Tsh/Pch/both), `generate_reports.py` creates:

1. **objective_diff_heatmap.png** - 2-panel heatmap (FD/Collocation) showing % difference vs scipy
2. **speedup_heatmap.png** - 2-panel heatmap showing wall time speedup vs scipy
3. **comparison_table.csv** - Detailed numerical results for all parameter combinations
4. **nominal_trajectory.png** - Control trajectories (Tsh/Pch vs time) for nominal case
5. **speedup_barplot.png** - Bar chart comparing mean speedup across methods
6. **summary.json** - Aggregated statistics (mean/std/min/max for all metrics)

## 📦 Module Documentation

### `data_loader.py`
Utilities for loading and organizing benchmark data:
- `load_benchmark_jsonl(path)` → List of records
- `organize_by_method(records)` → Dict by scipy/fd/colloc
- `extract_parameter_grid(records)` → Parameter names and values
- `get_matching_records(records, p1, p2)` → Find specific parameter combo
- `filter_successful(records)` → Only successful runs

### `analyze_benchmark.py`
Pure analysis functions (no I/O, fully testable):
- `compute_objective_differences()` → DataFrame with % diff vs scipy
- `compute_speedups()` → DataFrame with wall time ratios
- `extract_nominal_case()` → Trajectory array for specific parameters
- `generate_summary_stats()` → Aggregated metrics dict
- `validate_solver_status()` → Report of IPOPT failures
- `pivot_for_heatmap()` → Reshape data for visualization

### `visualization.py`
Figure generation with matplotlib/seaborn:
- `plot_objective_diff_heatmaps()` → 2-panel comparison
- `plot_speedup_heatmaps()` → 2-panel speedup
- `plot_trajectory_comparison()` → Overlay scipy/FD/colloc
- `create_comparison_table()` → Save detailed CSV
- `plot_summary_barplot()` → Method comparison

### `generate_reports.py` ⭐
CLI orchestrator that ties everything together:
```bash
python generate_reports.py <benchmark_dir> [--output <dir>] [--task <Tsh|Pch|both|all>]
```
- Discovers all JSONL files in directory
- Runs full analysis pipeline for each task
- Generates all figures, tables, summaries
- Provides progress feedback
- Handles errors gracefully

## 🎯 Benefits vs Old Approach

| Aspect | Old (Before) | New (After) |
|--------|--------------|-------------|
| **Notebook Size** | 1800+ lines | ~100 lines |
| **Analysis** | Mixed in notebook | Separate Python modules |
| **Reproducibility** | Manual re-run | CLI-driven automation |
| **Organization** | 36+ files scattered | Versioned directories |
| **Maintainability** | Tangled concerns | Modular design |
| **Testing** | Difficult | Pure functions (testable) |
| **CI/CD** | Not possible | CLI-friendly |

## 📝 File Naming Conventions

### Benchmark Results (JSONL)
- Pattern: `<task>_<grid>_<constraints>.jsonl`
- Examples:
  - `Tsh_3x3_ramp40.jsonl` - Tsh, 3×3 grid, 40°C/hr ramp
  - `Pch_3x3_ramp005.jsonl` - Pch, 3×3 grid, 0.05 Torr/hr ramp  
  - `both_3x3_ramp40_005.jsonl` - Both controls, both ramps

### Version Directories
- Pattern: `v<N>_<description>/`
- Examples:
  - `v1_baseline/` - Initial implementation
  - `v2_free_initial/` - Free initial conditions + fixed discretization
  - `v3_new_solver/` - After adding new solver

## 🔄 Complete Workflow Example

```bash
# After making code changes, create new version

# 1. Generate benchmark data
mkdir -p results/v3_my_feature
python grid_cli.py generate \
    --task Tsh --scenario baseline \
    --vary A1=5,10,20 KC=1e-4,2e-4,4e-4 \
    --methods scipy fd colloc \
    --n-elements 1000 --ramp-Tsh-max 40.0 \
    --out results/v3_my_feature/Tsh_3x3_ramp40.jsonl

# 2. Generate analysis (ONE COMMAND!)
python generate_reports.py results/v3_my_feature

# 3. View in notebook
jupyter notebook grid_analysis.ipynb
# Then select: benchmark_version = "v3_my_feature"
```

## 🧹 Cleanup Strategy

Old scattered files moved to `results/archive/`:
```bash
# View archived files
ls results/archive/

# Restore if needed
cp results/archive/some_file.jsonl results/
```

## 📈 Version History

### v1_baseline (Archived)
- Fixed initial conditions (Tsh=-35°C, Pch=0.12 Torr)
- Incorrect collocation discretization (3× too many mesh points)
- Status: Moved to archive/

### v2_free_initial (Current) ✅
- **Free initial conditions** - optimizer finds optimal start
- **Fixed discretization** - collocation uses correct effective NFE
- Fair comparison: FD ~1001 points, collocation ~1003 points
- Status: Active, ready for analysis

## 🛠️ Advanced Usage

### Parallel Analysis
```bash
# Analyze tasks in parallel (if you have multiple cores)
python generate_reports.py results/v2_free_initial --task Tsh &
python generate_reports.py results/v2_free_initial --task Pch &
python generate_reports.py results/v2_free_initial --task both &
wait
```

### Custom Analysis Scripts
```python
# Example: Custom analysis using the modules
from data_loader import load_benchmark_jsonl, organize_by_method
from analyze_benchmark import compute_objective_differences

records = load_benchmark_jsonl("results/v2_free_initial/Tsh_3x3_ramp40.jsonl")
by_method = organize_by_method(records)
comparison = compute_objective_differences(by_method)

# Now do custom analysis...
print(comparison.groupby('method')['speedup'].describe())
```

## 📚 Additional Resources

- **Main Project**: See `/docs/PYOMO_ROADMAP.md` for overall project plan
- **Physics**: See `/docs/PHYSICS_REFERENCE.md` for equations
- **Testing**: See `/tests/README.md` for test suite
- **Examples**: See `/examples/README.md` for usage examples

## 🤝 Contributing

When adding new analysis types:
1. Add functions to `analyze_benchmark.py` (pure, testable)
2. Add plotting functions to `visualization.py`
3. Update `generate_reports.py` to call new functions
4. Document in this README

## ⚠️ Important Notes

- **Don't modify notebook cells with analysis logic** - use Python modules instead
- **Version your benchmarks** - create new directory after code changes
- **Run generate_reports.py** before opening notebook - ensures fresh figures
- **Check summary.json** for quick metrics without opening notebook

---

**Need help?** Check inline documentation in the modules or run:
```bash
python generate_reports.py --help
python grid_cli.py generate --help
```
