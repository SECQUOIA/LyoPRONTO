# Grid CLI Complete Usage Guide

## Overview

`grid_cli.py` is the command-line tool for generating benchmark data across N-dimensional parameter grids. It runs optimization tasks with different methods (scipy, finite differences, collocation) and saves results to JSONL format.

## Common Mistakes (Read This First!)

❌ **Mistake 1: Forgetting the `generate` subcommand**
```bash
# ❌ Wrong - missing subcommand
python benchmarks/scripts/grid_cli.py --task Tsh ...

# ✅ Correct
python benchmarks/scripts/grid_cli.py generate --task Tsh ...
```

❌ **Mistake 2: Using wrong scenario name**
```bash
# ❌ Wrong - no "standard" scenario
--scenario standard

# ✅ Correct - it's "baseline"
--scenario baseline
```

❌ **Mistake 3: Missing `=` in `--vary` syntax**
```bash
# ❌ Wrong
--vary product.A1 5,10,20

# ✅ Correct
--vary product.A1=5,10,20
```

❌ **Mistake 4: Wrong generate_reports output path**
```bash
# ❌ Wrong - creates benchmarks/results/test/analysis/figures/
python benchmarks/scripts/generate_reports.py \
    benchmarks/results/test/raw \
    --output benchmarks/results/test/analysis

# ✅ Correct - creates benchmarks/results/test/figures/
python benchmarks/scripts/generate_reports.py \
    benchmarks/results/test/raw \
    --output benchmarks/results/test
```

❌ **Mistake 5: Including scipy in --methods**
```bash
# ❌ Unnecessary - scipy is auto-included
--methods scipy,fd,colloc

# ✅ Better - scipy baseline runs automatically
--methods fd,colloc
```

## Dependencies

Before using the benchmark tools, ensure all required packages are installed:

```bash
pip install -r requirements.txt
```

**Required packages for analysis and visualization:**
- `numpy`, `scipy`, `pandas` - Core scientific computing
- `matplotlib` - Basic plotting
- `seaborn` - Statistical visualizations (heatmaps, etc.)
- `pyomo`, `idaes-pse` - Optimization framework

If you encounter `ModuleNotFoundError: No module named 'seaborn'` when running `generate_reports.py`, install it with:

```bash
pip install seaborn
```

## Quick Reference

```bash
# Basic usage pattern (note the 'generate' subcommand)
python benchmarks/scripts/grid_cli.py generate \
    --task <Tsh|Pch|both> \
    --scenario <scenario_name> \
    --vary <param.path>=<val1>,<val2>,... \
    --methods <fd,colloc> \
    --n-elements <N> \
    --out <output.jsonl>

# Example: 2x2 parameter grid for Tsh task
python benchmarks/scripts/grid_cli.py generate \
    --task Tsh \
    --scenario baseline \
    --vary product.R0=0.4,0.8 \
    --vary product.A1=5,20 \
    --methods fd,colloc \
    --n-elements 1000 \
    --out benchmarks/results/test/raw/Tsh_2x2.jsonl
```

**Important Notes:**
- The `generate` subcommand is **required**
- Parameter variation uses `=` not `:` (e.g., `product.R0=0.4,0.8`)
- Scipy baseline is automatically included with Pyomo methods
- Available scenarios: `baseline`, `high_resistance`, `tight_temperature`, `aggressive_drying`, `large_batch`

## Arguments Reference

### Required Arguments

| Argument | Description | Example |
|----------|-------------|---------||
| `--task` | Which variables to optimize | `Tsh`, `Pch`, or `both` |
| `--scenario` | Base scenario from `scenarios.py` | `baseline`, `high_resistance`, `tight_temperature`, `aggressive_drying`, `large_batch` |
| `--vary` | Parameters to vary (repeatable, use `=`) | `--vary product.A1=5,10,20` |
| `--out` | Output JSONL file path | `benchmarks/results/test/raw/Tsh_3x3.jsonl` |

### Optional Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `--methods` | `fd,colloc` | Methods to run (comma-separated). Scipy baseline is automatically included. |
| `--n-elements` | `1000` | Number of finite elements for FD/colloc |
| `--n-collocation` | `3` | Collocation points per element |
| `--dt` | `0.01` | Time step for scipy baseline |
| `--warmstart` | Off | Enable scipy warmstart (off by default for fair benchmarking) |
| `--raw-colloc` | Off | Disable effective-nfe parity for colloc |
| `--force` | Off | Overwrite existing output file |

### Ramp Rate Constraints (Pyomo Only)

| Argument | Description | Units | Example |
|----------|-------------|-------|---------|
| `--ramp-Tsh-max` | Max shelf temp ramp rate | °C/hr | `40.0` |
| `--ramp-Pch-max` | Max pressure change rate | Torr/hr | `0.05` |
| `--fix-initial-Tsh` | Fix initial shelf temperature | °C | `-45.0` |
| `--fix-initial-Pch` | Fix initial pressure | Torr | `0.08` |

## Generating Analysis Reports

After generating benchmark data, use `generate_reports.py` to create visualizations and summaries:

```bash
# Generate analysis (outputs to results/<version>/figures/ and results/<version>/processed/)
python benchmarks/scripts/generate_reports.py \
    benchmarks/results/<version>/raw \
    --output benchmarks/results/<version>

# Example for test benchmark
python benchmarks/scripts/generate_reports.py \
    benchmarks/results/test/raw \
    --output benchmarks/results/test
```

**What this generates:**
- `figures/<task>/objective_diff_heatmap_fd.png` - FD objective difference heatmap
- `figures/<task>/objective_diff_heatmap_colloc.png` - Collocation objective difference heatmap
- `figures/<task>/speedup_heatmap_fd.png` - FD speedup heatmap
- `figures/<task>/speedup_heatmap_colloc.png` - Collocation speedup heatmap
- `figures/<task>/nominal_trajectory_*.png` - Trajectory comparisons
- `figures/<task>/nominal_ramp_constraints.png` - Ramp rate constraint plot
- `figures/<task>/speedup_barplot.png` - Summary bar chart
- `processed/comparison_table.csv` - Detailed comparison table
- `processed/summary.json` - Aggregated statistics

**Important**: The `--output` path should point to the parent directory (e.g., `results/test`), not the `raw` subdirectory. The tool will create `figures/` and `processed/` subdirectories automatically.

## Parameter Variation with `--vary`

### Syntax

```bash
--vary <nested.path.to.param>=<value1>,<value2>,...
```

**Key Points**:
- Can specify multiple `--vary` flags (Cartesian product)
- Dot notation accesses nested dictionaries
- Values are comma-separated (no spaces around commas)
- Numeric values auto-detected; strings preserved

### Available Parameter Paths

Based on scenario structure (see `benchmarks/scenarios.py`):

```python
SCENARIOS = {
    'baseline': {
        'vial': {...},           # Vial geometry
        'product': {...},        # Product properties
        'ht': {...},            # Heat transfer
        'eq_cap': {...},        # Equipment capabilities
        'nVial': 400,           # Number of vials
    }
}
```

#### Common Parameters to Vary

**Product Resistance** (`product.*`):
- `product.R0` - Base resistance (cm²·hr·Torr/g)
- `product.A1` - Resistance coefficient 1
- `product.A2` - Resistance coefficient 2

**Heat Transfer** (`ht.*`):
- `ht.KC` - Heat transfer coefficient (cal/s/K/cm²)
- `ht.KP` - Pressure-dependent term
- `ht.KD` - Dried cake term

**Vial Geometry** (`vial.*`):
- `vial.Vfill` - Fill volume (mL)
- `vial.Ap` - Product area (cm²)
- `vial.Av` - Vial area (cm²)

**Equipment** (`eq_cap.*`):
- `eq_cap.mdot_max` - Max sublimation rate (kg/hr)

### Examples

```bash
# Single parameter, 3 values
--vary product.A1=5,10,20

# Two parameters (3×3 = 9 combinations)
--vary product.A1=5,10,20 \
--vary ht.KC=1e-4,2e-4,4e-4

# Three parameters (3×3×2 = 18 combinations)
--vary product.A1=5,10,20 \
--vary ht.KC=1e-4,2e-4,4e-4 \
--vary vial.Vfill=3.0,5.0
```

## Complete Examples

### Example 1: Tsh Optimization (3×3 Grid)

```bash
python benchmarks/scripts/grid_cli.py generate \
    --task Tsh \
    --scenario baseline \
    --vary product.A1=5,10,20 \
    --vary ht.KC=1e-4,2e-4,4e-4 \
    --methods fd,colloc \
    --n-elements 1000 \
    --ramp-Tsh-max 40.0 \
    --out benchmarks/results/v2/Tsh_3x3.jsonl
```

**What this does**:
- Optimizes **shelf temperature** trajectory (Pch fixed)
- Tests 9 combinations (3 A1 × 3 KC)
- Runs FD and collocation methods (scipy baseline auto-included)
- Uses 1000 elements for discretization
- Limits temperature ramp to 40°C/hr (Pch has no ramp constraint)
- Generates 27 records (9 combos × 3 methods)

### Example 2: Pch Optimization (3×3 Grid)

```bash
python benchmarks/scripts/grid_cli.py generate \
    --task Pch \
    --scenario baseline \
    --vary product.A1=5,10,20 \
    --vary ht.KC=1e-4,2e-4,4e-4 \
    --methods fd,colloc \
    --n-elements 1000 \
    --ramp-Pch-max 0.05 \
    --out benchmarks/results/v2/Pch_3x3.jsonl
```

**What this does**:
- Optimizes **pressure** trajectory (Tsh fixed)
- Tests 9 combinations (3 A1 × 3 KC)
- Runs FD and collocation methods (scipy baseline auto-included)
- Limits pressure change to 0.05 Torr/hr (Tsh has no ramp constraint)
- Generates 27 records

### Example 3: Both Variables (3×3 Grid)

```bash
python benchmarks/scripts/grid_cli.py generate \
    --task both \
    --scenario baseline \
    --vary product.A1=5,10,20 \
    --vary ht.KC=1e-4,2e-4,4e-4 \
    --methods fd,colloc \
    --n-elements 1000 \
    --ramp-Tsh-max 40.0 \
    --ramp-Pch-max 0.05 \
    --out benchmarks/results/v2/both_3x3.jsonl
```

**What this does**:
- Optimizes **both Tsh and Pch** simultaneously
- Tests 9 combinations
- Runs FD and collocation methods (scipy baseline auto-included)
- Limits both temperature (40°C/hr) and pressure (0.05 Torr/hr) ramps
- Generates 27 records

### Example 4: FD Only (No Collocation)

```bash
python benchmarks/scripts/grid_cli.py generate \
    --task Tsh \
    --scenario baseline \
    --vary product.A1=5,10,20 \
    --vary ht.KC=1e-4,2e-4,4e-4 \
    --methods fd \
    --n-elements 1000 \
    --ramp-Tsh-max 40.0 \
    --out benchmarks/results/fd_only.jsonl
```

**What this does**:
- Runs scipy baseline + FD only (skip collocation)
- Faster than including collocation
- 18 records (9 combos × 2 methods)

### Example 5: High-Resolution Grid (5×5)

```bash
python benchmarks/scripts/grid_cli.py generate \
    --task both \
    --scenario baseline \
    --vary product.A1=5,10,15,20,25 \
    --vary ht.KC=1e-4,2e-4,3e-4,4e-4,5e-4 \
    --methods fd,colloc \
    --n-elements 1000 \
    --ramp-Tsh-max 40.0 \
    --ramp-Pch-max 0.05 \
    --out benchmarks/results/both_5x5.jsonl
```

**What this does**:
- Finer parameter grid (25 combinations)
- 75 total records (25 × 3 methods)
- Takes longer but more detailed analysis

## Output Format

### JSONL Structure

Each line is a JSON record with this structure:

```json
{
  "task": "Tsh",
  "scenario": "baseline",
  "grid": {
    "param1": {"path": "product.A1", "value": 20.0},
    "param2": {"path": "ht.KC", "value": 0.0004}
  },
  "scipy": {
    "success": true,
    "wall_time_s": 1.234,
    "objective_time_hr": 10.5,
    "solver": {...},
    "metrics": {...},
    "trajectory": [[t0, Tsub0, ...], [t1, Tsub1, ...], ...]
  },
  "pyomo": {
    "success": true,
    "wall_time_s": 45.678,
    "objective_time_hr": 10.3,
    "solver": {...},
    "metrics": {...},
    "discretization": {
      "method": "fd",
      "n_elements_requested": 1000,
      "n_elements_applied": 1000
    },
    "warmstart_used": false,
    "trajectory": [[t0, Tsub0, ...], ...]
  },
  "failed": false
}
```

### Trajectory Format

Each trajectory is a 2D array with 7 columns:

| Index | Variable | Units |
|-------|----------|-------|
| 0 | `time` | hr |
| 1 | `Tsub` | °C |
| 2 | `Tbot` | °C |
| 3 | `Tsh` | °C |
| 4 | `Pch` | mTorr ⚠️ |
| 5 | `flux` | kg/hr/m² |
| 6 | `frac_dried` | 0-1 (fraction) |

⚠️ **Important**: Pressure is in **mTorr** in output, not Torr!

## Workflow Integration

### Step 1: Generate Benchmarks

```bash
# Create versioned directory structure
mkdir -p benchmarks/results/v2/raw

# Generate all three tasks
python benchmarks/scripts/grid_cli.py generate \
    --task Tsh --scenario baseline \
    --vary product.A1=5,10,20 --vary ht.KC=1e-4,2e-4,4e-4 \
    --methods fd,colloc --n-elements 1000 \
    --ramp-Tsh-max 40.0 \
    --out benchmarks/results/v2/raw/Tsh_3x3.jsonl

python benchmarks/scripts/grid_cli.py generate \
    --task Pch --scenario baseline \
    --vary product.A1=5,10,20 --vary ht.KC=1e-4,2e-4,4e-4 \
    --methods fd,colloc --n-elements 1000 \
    --ramp-Pch-max 0.05 \
    --out benchmarks/results/v2/raw/Pch_3x3.jsonl

python benchmarks/scripts/grid_cli.py generate \
    --task both --scenario baseline \
    --vary product.A1=5,10,20 --vary ht.KC=1e-4,2e-4,4e-4 \
    --methods fd,colloc --n-elements 1000 \
    --ramp-Tsh-max 40.0 --ramp-Pch-max 0.05 \
    --out benchmarks/results/v2/raw/both_3x3.jsonl
```

### Step 2: Generate Analysis

```bash
# One command generates all heatmaps, tables, trajectories
# Output path should be parent directory (not raw/)
python benchmarks/scripts/generate_reports.py \
    benchmarks/results/v2/raw \
    --output benchmarks/results/v2
```

### Step 3: View in Notebook

```python
# In grid_analysis.ipynb
benchmark_version = "v2"  # or "test"
task = "Tsh"  # or "Pch" or "both"

# Notebook displays pre-generated figures from benchmarks/results/v2/figures/
```

## Troubleshooting

### Issue: "Reuse-first: output exists"

**Cause**: Output file already exists  
**Solution**: Use `--force` to overwrite

```bash
python benchmarks/scripts/grid_cli.py generate ... --force
```

### Issue: "Unknown scenario 'standard'"

**Cause**: Scenario name not in `scenarios.py`  
**Solution**: Use correct scenario name - it's `baseline`, not `standard`

Available scenarios:
- `baseline` - Standard lyophilization conditions
- `high_resistance` - Difficult-to-dry product
- `tight_temperature` - Strict temperature constraints
- `aggressive_drying` - Fast drying conditions
- `large_batch` - High vial count

```python
# Check available scenarios programmatically
from benchmarks.scenarios import SCENARIOS
print(list(SCENARIOS.keys()))
```

### Issue: "Invalid --vary spec (missing '=')"

**Cause**: Forgot `=` in `--vary` argument  
**Solution**: Use correct syntax:

```bash
# ❌ Wrong
--vary product.A1 5,10,20

# ✅ Correct
--vary product.A1=5,10,20
```

### Issue: "No values parsed"

**Cause**: Empty values or trailing comma  
**Solution**: Remove trailing commas:

```bash
# ❌ Wrong
--vary product.A1=5,10,20,

# ✅ Correct
--vary product.A1=5,10,20
```

### Issue: Scientific notation not working

**Cause**: Leading `e` interpreted incorrectly  
**Solution**: Use full notation:

```bash
# ❌ Might fail
--vary ht.KC=e-4,2e-4

# ✅ Better
--vary ht.KC=1e-4,2e-4,4e-4
```

## Performance Tips

### Faster Benchmarking

1. **Run tasks separately** (parallel in different terminals):
   ```bash
   # Terminal 1
   python benchmarks/scripts/grid_cli.py generate --task Tsh ... &
   
   # Terminal 2
   python benchmarks/scripts/grid_cli.py generate --task Pch ... &
   
   # Terminal 3
   python benchmarks/scripts/grid_cli.py generate --task both ... &
   ```

2. **Skip collocation for quick tests**:
   ```bash
   --methods fd  # FD only (collocation is slower)
   ```

3. **Use fewer elements for testing**:
   ```bash
   --n-elements 100  # Quick test (not production!)
   ```

4. **Test small grid first**:
   ```bash
   # Test 2×2 first
   --vary product.A1=10,20 --vary ht.KC=2e-4,4e-4
   
   # Then scale to 3×3 or larger
   --vary product.A1=5,10,20 --vary ht.KC=1e-4,2e-4,4e-4
   ```

### Disk Space

Each record with trajectory (~1000 points × 7 columns) ≈ 50-100 KB.

Example sizes:
- 3×3 grid, 3 methods = 27 records ≈ 2-3 MB
- 5×5 grid, 3 methods = 75 records ≈ 6-8 MB
- 10×10 grid, 3 methods = 300 records ≈ 25-30 MB

## Advanced Usage

### Custom Scenarios

1. Add to `benchmarks/scenarios.py`:
   ```python
   SCENARIOS['my_custom'] = {
       'vial': {...},
       'product': {...},
       'ht': {...},
       'eq_cap': {...},
   }
   ```

2. Use in CLI:
   ```bash
   --scenario my_custom
   ```

### Three-Way Grid (3D)

```bash
python benchmarks/scripts/grid_cli.py generate \
    --task both \
    --scenario baseline \
    --vary product.A1=5,10,20 \
    --vary ht.KC=1e-4,2e-4,4e-4 \
    --vary vial.Vfill=3.0,5.0 \
    --methods fd,colloc \
    --n-elements 1000 \
    --out benchmarks/results/3d_grid.jsonl
```

This creates 3×3×2 = 18 combinations × 3 methods = 54 records.

### Fixed Initial Conditions

```bash
python benchmarks/scripts/grid_cli.py generate \
    --task both \
    --scenario baseline \
    --vary product.A1=5,10,20 \
    --methods fd,colloc \
    --n-elements 1000 \
    --fix-initial-Tsh -45.0 \
    --fix-initial-Pch 0.08 \
    --ramp-Tsh-max 40.0 \
    --ramp-Pch-max 0.05 \
    --out benchmarks/results/fixed_initial.jsonl
```

Forces optimization to start at specific Tsh/Pch values.

## Common Patterns

### Pattern 1: Standard 3×3 Benchmark Suite

```bash
#!/bin/bash
VERSION="v2"
mkdir -p benchmarks/results/$VERSION/raw

# Tsh optimization
python benchmarks/scripts/grid_cli.py generate \
    --task Tsh --scenario baseline \
    --vary product.A1=5,10,20 --vary ht.KC=1e-4,2e-4,4e-4 \
    --methods fd,colloc --n-elements 1000 \
    --ramp-Tsh-max 40.0 \
    --out benchmarks/results/$VERSION/raw/Tsh_3x3.jsonl

# Pch optimization
python benchmarks/scripts/grid_cli.py generate \
    --task Pch --scenario baseline \
    --vary product.A1=5,10,20 --vary ht.KC=1e-4,2e-4,4e-4 \
    --methods fd,colloc --n-elements 1000 \
    --ramp-Pch-max 0.05 \
    --out benchmarks/results/$VERSION/raw/Pch_3x3.jsonl

# Both optimization
python benchmarks/scripts/grid_cli.py generate \
    --task both --scenario baseline \
    --vary product.A1=5,10,20 --vary ht.KC=1e-4,2e-4,4e-4 \
    --methods fd,colloc --n-elements 1000 \
    --ramp-Tsh-max 40.0 --ramp-Pch-max 0.05 \
    --out benchmarks/results/$VERSION/raw/both_3x3.jsonl

# Generate all analysis
python benchmarks/scripts/generate_reports.py \
    benchmarks/results/$VERSION/raw \
    --output benchmarks/results/$VERSION
```

### Pattern 2: Method Comparison (Same Grid)

```bash
# FD with different discretizations
python benchmarks/scripts/grid_cli.py generate \
    --task Tsh --scenario baseline \
    --vary product.A1=10,20 --vary ht.KC=2e-4,4e-4 \
    --methods fd --n-elements 100 \
    --out benchmarks/results/fd_n100.jsonl

python benchmarks/scripts/grid_cli.py generate \
    --task Tsh --scenario baseline \
    --vary product.A1=10,20 --vary ht.KC=2e-4,4e-4 \
    --methods fd --n-elements 1000 \
    --out benchmarks/results/fd_n1000.jsonl

# Compare discretization impact
```

### Pattern 3: Sensitivity Analysis

```bash
# Vary single parameter, fix others
python benchmarks/scripts/grid_cli.py generate \
    --task both --scenario baseline \
    --vary product.A1=5,7.5,10,12.5,15,17.5,20 \
    --methods fd,colloc --n-elements 1000 \
    --out benchmarks/results/sensitivity_A1.jsonl
```

## File Naming Conventions

Recommended patterns:

```
benchmarks/results/<version>/raw/<task>_<grid>_<description>.jsonl

Examples:
- Tsh_3x3.jsonl                     # 3×3 grid, Tsh task
- Pch_3x3.jsonl                     # 3×3 grid, Pch task
- both_3x3.jsonl                    # 3×3 grid, both vars
- both_5x5.jsonl                    # 5×5 grid, finer resolution
- Tsh_sensitivity_A1.jsonl          # Sensitivity study on A1
- both_fixed_init.jsonl             # Fixed initial conditions
```

Note: Ramp constraints are stored in the JSONL data and don't need to be in the filename.

## See Also

- `BENCHMARKS_README.md` - Analysis infrastructure overview
- `generate_reports.py` - Report generation CLI
- `scenarios.py` - Available scenarios and parameters
- `grid_analysis.ipynb` - Notebook for viewing results
