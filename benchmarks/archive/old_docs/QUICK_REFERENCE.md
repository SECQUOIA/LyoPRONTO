# Benchmark Workflow - Quick Reference Card

## 🎯 Complete Workflow (3 Steps)

### Step 1: Generate Benchmarks

```bash
cd benchmarks

# Create version directory
mkdir -p results/v2_free_initial

# Generate Tsh task
python grid_cli.py generate \
    --task Tsh \
    --scenario baseline \
    --vary product.A1=5,10,20 \
    --vary ht.KC=1e-4,2e-4,4e-4 \
    --methods scipy,fd,colloc \
    --n-elements 1000 \
    --ramp-Tsh-max 40.0 \
    --out results/v2_free_initial/Tsh_3x3_ramp40.jsonl

# Generate Pch task
python grid_cli.py generate \
    --task Pch \
    --scenario baseline \
    --vary product.A1=5,10,20 \
    --vary ht.KC=1e-4,2e-4,4e-4 \
    --methods scipy,fd,colloc \
    --n-elements 1000 \
    --ramp-Pch-max 0.05 \
    --out results/v2_free_initial/Pch_3x3_ramp005.jsonl

# Generate both task
python grid_cli.py generate \
    --task both \
    --scenario baseline \
    --vary product.A1=5,10,20 \
    --vary ht.KC=1e-4,2e-4,4e-4 \
    --methods scipy,fd,colloc \
    --n-elements 1000 \
    --ramp-Tsh-max 40.0 \
    --ramp-Pch-max 0.05 \
    --out results/v2_free_initial/both_3x3_ramp40_005.jsonl
```

**Output**: 3 JSONL files, 27 records each (9 combos × 3 methods)

### Step 2: Generate Analysis

```bash
# One command generates all figures, tables, summaries
python generate_reports.py results/v2_free_initial
```

**Output**:
```
analysis/v2_free_initial/
├── Tsh/
│   ├── objective_diff_heatmap.png
│   ├── speedup_heatmap.png
│   ├── trajectory_A1_10.0_KC_0.0002.png
│   ├── comparison_table.csv
│   └── summary_stats.json
├── Pch/
│   └── ...
└── both/
    └── ...
```

### Step 3: View Results

```bash
# Open simplified notebook
jupyter notebook grid_analysis_SIMPLE.ipynb

# Or use the old detailed notebook
jupyter notebook grid_analysis.ipynb
```

In notebook:
```python
benchmark_version = "v2_free_initial"
task = "Tsh"  # or "Pch" or "both"
# Run cells to view figures
```

---

## 📋 grid_cli.py - Quick Syntax

### Minimal Command
```bash
python grid_cli.py generate \
    --task Tsh \
    --scenario baseline \
    --vary product.A1=10,20 \
    --out results/test.jsonl
```

### Full Options
```bash
python grid_cli.py generate \
    --task <Tsh|Pch|both> \                # Required
    --scenario baseline \                   # Required
    --vary <param.path>=<val1,val2> \      # Required (repeatable)
    --methods scipy,fd,colloc \            # Default: all three
    --n-elements 1000 \                    # Default: 24
    --n-collocation 3 \                    # Default: 3
    --dt 0.01 \                            # Default: 0.01
    --ramp-Tsh-max 40.0 \                  # Optional
    --ramp-Pch-max 0.05 \                  # Optional
    --fix-initial-Tsh -45.0 \              # Optional
    --fix-initial-Pch 0.08 \               # Optional
    --warmstart \                          # Optional (off by default)
    --force \                              # Optional (overwrite)
    --out results/output.jsonl             # Required
```

### Common --vary Parameters

| Parameter | Description | Typical Values |
|-----------|-------------|----------------|
| `product.A1` | Resistance coefficient | `5, 10, 20` |
| `product.A2` | Resistance coefficient | `0.001, 0.01` |
| `product.R0` | Base resistance | `0.5, 1.0, 2.0` |
| `ht.KC` | Heat transfer coeff | `1e-4, 2e-4, 4e-4` |
| `ht.KP` | Pressure term | `0.5, 1.0, 1.5` |
| `vial.Vfill` | Fill volume (mL) | `3.0, 5.0, 7.0` |

### Cartesian Product Examples

```bash
# 1D: 3 points
--vary product.A1=5,10,20
# → 3 combinations

# 2D: 3×3 grid = 9 points
--vary product.A1=5,10,20 \
--vary ht.KC=1e-4,2e-4,4e-4
# → 9 combinations

# 3D: 3×3×2 = 18 points
--vary product.A1=5,10,20 \
--vary ht.KC=1e-4,2e-4,4e-4 \
--vary vial.Vfill=3.0,5.0
# → 18 combinations
```

---

## 📊 generate_reports.py - Quick Syntax

### Basic Usage
```bash
python generate_reports.py <benchmark_dir>
```

### Examples
```bash
# Generate all analysis for a version
python generate_reports.py results/v2_free_initial

# Specific task only
python generate_reports.py results/v2_free_initial --task Tsh

# Custom output directory
python generate_reports.py results/v2_free_initial --output analysis/custom
```

### What It Generates

For each task (Tsh, Pch, both):

1. **objective_diff_heatmap.png** - 2-panel heatmap (FD vs colloc)
2. **speedup_heatmap.png** - Wall time speedup heatmap
3. **trajectory_*.png** - Trajectory comparisons for each parameter combo
4. **comparison_table.csv** - Detailed metrics table
5. **summary_stats.json** - Aggregated statistics

---

## 📓 Notebook Usage

### Simplified Notebook (Recommended)
**File**: `grid_analysis_SIMPLE.ipynb` (~150 lines)

```python
# Configuration
benchmark_version = "v2_free_initial"
task = "Tsh"

# Run cells to view:
# - Summary statistics
# - Objective difference heatmaps
# - Speedup heatmaps
# - Trajectory comparisons
# - Comparison tables
```

### Old Notebook (Reference)
**File**: `grid_analysis_OLD.ipynb` (~1700 lines)

Contains all inline analysis logic (now in Python modules). Kept for historical reference.

---

## 🔍 Common Tasks

### View Specific Parameter Combo
```python
# In notebook
custom_params = {'A1': 20.0, 'KC': 0.0004}
param_str = "_".join([f"{k}_{v}" for k, v in custom_params.items()])
display(Image(filename=f"analysis/{version}/{task}/trajectory_{param_str}.png"))
```

### Regenerate Analysis After Code Changes
```bash
# 1. Update Python code (e.g., fix optimizer bug)

# 2. Generate new benchmarks with new version name
mkdir -p results/v3_fixed_bug
python grid_cli.py generate ... --out results/v3_fixed_bug/...

# 3. Generate analysis
python generate_reports.py results/v3_fixed_bug

# 4. Compare versions in notebook
benchmark_version = "v3_fixed_bug"  # vs "v2_free_initial"
```

### Compare Discretization Levels
```bash
# Generate with different n-elements
python grid_cli.py generate ... --n-elements 100 --out results/n100.jsonl
python grid_cli.py generate ... --n-elements 1000 --out results/n1000.jsonl

# Analyze separately
python generate_reports.py results/n100 --output analysis/n100
python generate_reports.py results/n1000 --output analysis/n1000

# View both in notebook and compare
```

### Run Subset of Methods
```bash
# Scipy + FD only (skip collocation - faster)
python grid_cli.py generate ... --methods scipy,fd --out results/fd_only.jsonl

# FD only (with scipy baseline auto-computed)
python grid_cli.py generate ... --methods fd --out results/fd_test.jsonl
```

---

## 🚀 Performance Tips

### Parallel Generation
Run tasks in parallel (different terminals):
```bash
# Terminal 1
python grid_cli.py generate --task Tsh ... &

# Terminal 2
python grid_cli.py generate --task Pch ... &

# Terminal 3
python grid_cli.py generate --task both ... &
```

### Quick Testing
```bash
# Small 2×2 grid for testing
python grid_cli.py generate \
    --task Tsh --scenario baseline \
    --vary product.A1=10,20 \
    --vary ht.KC=2e-4,4e-4 \
    --methods scipy,fd \
    --n-elements 100 \
    --out results/test.jsonl

# Then scale up to 3×3 or larger
```

### Disk Space Estimates
- 3×3 grid, 3 methods: ~2-3 MB
- 5×5 grid, 3 methods: ~6-8 MB
- 10×10 grid, 3 methods: ~25-30 MB

---

## 📁 File Organization

```
benchmarks/
├── results/                    # Raw benchmark data (versioned)
│   ├── v1_baseline/           # Old: Fixed initial conditions
│   ├── v2_free_initial/       # Current: Free initial, correct discretization
│   └── archive/               # Scattered old files
│
├── analysis/                   # Generated analysis artifacts
│   ├── v1_baseline/
│   │   ├── Tsh/
│   │   ├── Pch/
│   │   └── both/
│   └── v2_free_initial/
│       ├── Tsh/
│       ├── Pch/
│       └── both/
│
├── grid_cli.py                 # Benchmark generation CLI
├── generate_reports.py         # Analysis generation CLI
├── data_loader.py              # Data loading utilities
├── analyze_benchmark.py        # Analysis functions
├── visualization.py            # Plotting utilities
├── grid_analysis_SIMPLE.ipynb  # Simplified viewer (~150 lines)
└── grid_analysis_OLD.ipynb     # Old notebook (~1700 lines)
```

---

## 📖 Documentation

| File | Description |
|------|-------------|
| `GRID_CLI_GUIDE.md` | Complete `grid_cli.py` reference (400+ lines) |
| `BENCHMARKS_README.md` | Analysis infrastructure overview |
| `IMPLEMENTATION_SUMMARY.md` | What was implemented and why |
| `QUICK_REFERENCE.md` | This file (quick workflows) |

---

## ⚠️ Important Notes

### Units in Output
- **Pressure**: mTorr (not Torr!) in trajectory output
- **Dried fraction**: 0-1 (not percentage!)
- **Flux**: kg/hr/m² (normalized by area)

### Ramp Rates
- `--ramp-Tsh-max`: °C/hr (e.g., 40.0)
- `--ramp-Pch-max`: Torr/hr (e.g., 0.05)
- Pyomo only (scipy ignores these)

### Methods
- `scipy`: Baseline (always computed first)
- `fd`: Finite differences (Pyomo)
- `colloc`: Collocation (Pyomo)

### Discretization
- `--n-elements`: For both FD and collocation
- FD: Uses n_elements directly (e.g., 1000 → 1001 mesh points)
- Collocation: Uses n_elements/n_collocation (e.g., 1000/3 → 334 elements → ~1003 mesh points)

---

## 🎓 Example Session

```bash
# Complete workflow from scratch
cd /home/bernalde/repos/LyoPRONTO/benchmarks

# 1. Create new version directory
mkdir -p results/v2_free_initial

# 2. Generate all three tasks (can run in parallel)
python grid_cli.py generate \
    --task Tsh --scenario baseline \
    --vary product.A1=5,10,20 --vary ht.KC=1e-4,2e-4,4e-4 \
    --methods scipy,fd,colloc --n-elements 1000 \
    --ramp-Tsh-max 40.0 \
    --out results/v2_free_initial/Tsh_3x3_ramp40.jsonl

python grid_cli.py generate \
    --task Pch --scenario baseline \
    --vary product.A1=5,10,20 --vary ht.KC=1e-4,2e-4,4e-4 \
    --methods scipy,fd,colloc --n-elements 1000 \
    --ramp-Pch-max 0.05 \
    --out results/v2_free_initial/Pch_3x3_ramp005.jsonl

python grid_cli.py generate \
    --task both --scenario baseline \
    --vary product.A1=5,10,20 --vary ht.KC=1e-4,2e-4,4e-4 \
    --methods scipy,fd,colloc --n-elements 1000 \
    --ramp-Tsh-max 40.0 --ramp-Pch-max 0.05 \
    --out results/v2_free_initial/both_3x3_ramp40_005.jsonl

# 3. Generate all analysis (one command!)
python generate_reports.py results/v2_free_initial

# 4. View results
jupyter notebook grid_analysis_SIMPLE.ipynb
```

Total time: ~15-30 minutes for 3×3 grid × 3 tasks × 3 methods = 81 optimizations
