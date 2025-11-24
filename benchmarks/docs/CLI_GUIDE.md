# Grid CLI Complete Usage Guide

## Overview

`grid_cli.py` is the command-line tool for generating benchmark data across N-dimensional parameter grids. It runs optimization tasks with different methods (scipy, finite differences, collocation) and saves results to JSONL format.

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
# Basic usage pattern
python benchmarks/grid_cli.py generate \
    --task <Tsh|Pch|both> \
    --scenario <scenario_name> \
    --vary <param.path=val1,val2,...> \
    --methods <scipy,fd,colloc> \
    --n-elements <N> \
    --out <output.jsonl>
```

## Arguments Reference

### Required Arguments

| Argument | Description | Example |
|----------|-------------|---------|
| `--task` | Which variables to optimize | `Tsh`, `Pch`, or `both` |
| `--scenario` | Base scenario from `scenarios.py` | `baseline` |
| `--vary` | Parameters to vary (repeatable) | `--vary product.A1=5,10,20` |
| `--out` | Output JSONL file path | `results/v2/Tsh_3x3.jsonl` |

### Optional Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `--methods` | `scipy,fd,colloc` | Methods to run (comma-separated) |
| `--n-elements` | `24` | Number of finite elements for FD/colloc |
| `--n-collocation` | `3` | Collocation points per element |
| `--dt` | `0.01` | Time step for scipy baseline |
| `--warmstart` | Off | Enable scipy warmstart (off by default) |
| `--raw-colloc` | Off | Disable effective-nfe parity for colloc |
| `--force` | Off | Overwrite existing output file |

### Ramp Rate Constraints (Pyomo Only)

| Argument | Description | Units | Example |
|----------|-------------|-------|---------|
| `--ramp-Tsh-max` | Max shelf temp ramp rate | °C/hr | `40.0` |
| `--ramp-Pch-max` | Max pressure change rate | Torr/hr | `0.05` |
| `--fix-initial-Tsh` | Fix initial shelf temperature | °C | `-45.0` |
| `--fix-initial-Pch` | Fix initial pressure | Torr | `0.08` |

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
python benchmarks/grid_cli.py generate \
    --task Tsh \
    --scenario baseline \
    --vary product.A1=5,10,20 \
    --vary ht.KC=1e-4,2e-4,4e-4 \
    --methods scipy,fd,colloc \
    --n-elements 1000 \
    --ramp-Tsh-max 40.0 \
    --out results/v2_free_initial/Tsh_3x3_ramp40.jsonl
```

**What this does**:
- Optimizes **shelf temperature** trajectory (Pch fixed)
- Tests 9 combinations (3 A1 × 3 KC)
- Runs 3 methods: scipy, FD, collocation
- Uses 1000 elements for discretization
- Limits temperature ramp to 40°C/hr
- Generates 27 records (9 combos × 3 methods)

### Example 2: Pch Optimization (3×3 Grid)

```bash
python benchmarks/grid_cli.py generate \
    --task Pch \
    --scenario baseline \
    --vary product.A1=5,10,20 \
    --vary ht.KC=1e-4,2e-4,4e-4 \
    --methods scipy,fd,colloc \
    --n-elements 1000 \
    --ramp-Pch-max 0.05 \
    --out results/v2_free_initial/Pch_3x3_ramp005.jsonl
```

**What this does**:
- Optimizes **pressure** trajectory (Tsh fixed)
- Tests 9 combinations (3 A1 × 3 KC)
- Runs 3 methods
- Limits pressure change to 0.05 Torr/hr
- Generates 27 records

### Example 3: Both Variables (3×3 Grid)

```bash
python benchmarks/grid_cli.py generate \
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

**What this does**:
- Optimizes **both Tsh and Pch** simultaneously
- Tests 9 combinations
- Limits both temperature (40°C/hr) and pressure (0.05 Torr/hr) ramps
- Generates 27 records

### Example 4: Scipy Only (Baseline)

```bash
python benchmarks/grid_cli.py generate \
    --task both \
    --scenario baseline \
    --vary product.A1=16,18,20 \
    --methods scipy \
    --dt 0.01 \
    --out results/scipy_baseline.jsonl
```

**What this does**:
- Runs only scipy (no Pyomo)
- 3 combinations, 3 records total
- Useful for quick baseline without optimization

### Example 5: FD Only (No Collocation)

```bash
python benchmarks/grid_cli.py generate \
    --task Tsh \
    --scenario baseline \
    --vary product.A1=5,10,20 \
    --vary ht.KC=1e-4,2e-4,4e-4 \
    --methods scipy,fd \
    --n-elements 1000 \
    --ramp-Tsh-max 40.0 \
    --out results/fd_only.jsonl
```

**What this does**:
- Runs scipy + FD only (skip collocation)
- Faster than including collocation
- 18 records (9 combos × 2 methods)

### Example 6: High-Resolution Grid (5×5)

```bash
python benchmarks/grid_cli.py generate \
    --task both \
    --scenario baseline \
    --vary product.A1=5,10,15,20,25 \
    --vary ht.KC=1e-4,2e-4,3e-4,4e-4,5e-4 \
    --methods scipy,fd,colloc \
    --n-elements 1000 \
    --ramp-Tsh-max 40.0 \
    --ramp-Pch-max 0.05 \
    --out results/both_5x5_high_res.jsonl
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
# Create versioned directory
mkdir -p results/v2_free_initial

# Generate all three tasks
python benchmarks/grid_cli.py generate \
    --task Tsh --scenario baseline \
    --vary product.A1=5,10,20 --vary ht.KC=1e-4,2e-4,4e-4 \
    --methods scipy,fd,colloc --n-elements 1000 \
    --ramp-Tsh-max 40.0 \
    --out results/v2_free_initial/Tsh_3x3_ramp40.jsonl

python benchmarks/grid_cli.py generate \
    --task Pch --scenario baseline \
    --vary product.A1=5,10,20 --vary ht.KC=1e-4,2e-4,4e-4 \
    --methods scipy,fd,colloc --n-elements 1000 \
    --ramp-Pch-max 0.05 \
    --out results/v2_free_initial/Pch_3x3_ramp005.jsonl

python benchmarks/grid_cli.py generate \
    --task both --scenario baseline \
    --vary product.A1=5,10,20 --vary ht.KC=1e-4,2e-4,4e-4 \
    --methods scipy,fd,colloc --n-elements 1000 \
    --ramp-Tsh-max 40.0 --ramp-Pch-max 0.05 \
    --out results/v2_free_initial/both_3x3_ramp40_005.jsonl
```

### Step 2: Generate Analysis

```bash
# One command generates all heatmaps, tables, trajectories
python benchmarks/generate_reports.py results/v2_free_initial
```

### Step 3: View in Notebook

```python
# In grid_analysis.ipynb
benchmark_version = "v2_free_initial"
task = "Tsh"  # or "Pch" or "both"

# Notebook displays pre-generated figures
```

## Troubleshooting

### Issue: "Reuse-first: output exists"

**Cause**: Output file already exists  
**Solution**: Use `--force` to overwrite

```bash
python benchmarks/grid_cli.py generate ... --force
```

### Issue: "Unknown scenario 'xyz'"

**Cause**: Scenario name not in `scenarios.py`  
**Solution**: Check available scenarios:

```python
from benchmarks.scenarios import SCENARIOS
print(list(SCENARIOS.keys()))  # ['baseline', ...]
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
   python benchmarks/grid_cli.py generate --task Tsh ... &
   
   # Terminal 2
   python benchmarks/grid_cli.py generate --task Pch ... &
   
   # Terminal 3
   python benchmarks/grid_cli.py generate --task both ... &
   ```

2. **Skip collocation for quick tests**:
   ```bash
   --methods scipy,fd  # Skip collocation (slower)
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
python benchmarks/grid_cli.py generate \
    --task both \
    --scenario baseline \
    --vary product.A1=5,10,20 \
    --vary ht.KC=1e-4,2e-4,4e-4 \
    --vary vial.Vfill=3.0,5.0 \
    --methods scipy,fd,colloc \
    --n-elements 1000 \
    --out results/3d_grid.jsonl
```

This creates 3×3×2 = 18 combinations × 3 methods = 54 records.

### Fixed Initial Conditions

```bash
python benchmarks/grid_cli.py generate \
    --task both \
    --scenario baseline \
    --vary product.A1=5,10,20 \
    --methods scipy,fd,colloc \
    --n-elements 1000 \
    --fix-initial-Tsh -45.0 \
    --fix-initial-Pch 0.08 \
    --ramp-Tsh-max 40.0 \
    --ramp-Pch-max 0.05 \
    --out results/fixed_initial.jsonl
```

Forces optimization to start at specific Tsh/Pch values.

## Common Patterns

### Pattern 1: Standard 3×3 Benchmark Suite

```bash
#!/bin/bash
VERSION="v2_free_initial"
mkdir -p results/$VERSION

# Tsh optimization
python benchmarks/grid_cli.py generate \
    --task Tsh --scenario baseline \
    --vary product.A1=5,10,20 --vary ht.KC=1e-4,2e-4,4e-4 \
    --methods scipy,fd,colloc --n-elements 1000 \
    --ramp-Tsh-max 40.0 \
    --out results/$VERSION/Tsh_3x3_ramp40.jsonl

# Pch optimization
python benchmarks/grid_cli.py generate \
    --task Pch --scenario baseline \
    --vary product.A1=5,10,20 --vary ht.KC=1e-4,2e-4,4e-4 \
    --methods scipy,fd,colloc --n-elements 1000 \
    --ramp-Pch-max 0.05 \
    --out results/$VERSION/Pch_3x3_ramp005.jsonl

# Both optimization
python benchmarks/grid_cli.py generate \
    --task both --scenario baseline \
    --vary product.A1=5,10,20 --vary ht.KC=1e-4,2e-4,4e-4 \
    --methods scipy,fd,colloc --n-elements 1000 \
    --ramp-Tsh-max 40.0 --ramp-Pch-max 0.05 \
    --out results/$VERSION/both_3x3_ramp40_005.jsonl

# Generate all analysis
python benchmarks/generate_reports.py results/$VERSION
```

### Pattern 2: Method Comparison (Same Grid)

```bash
# FD with different discretizations
python benchmarks/grid_cli.py generate \
    --task Tsh --scenario baseline \
    --vary product.A1=10,20 --vary ht.KC=2e-4,4e-4 \
    --methods scipy,fd --n-elements 100 \
    --out results/fd_n100.jsonl

python benchmarks/grid_cli.py generate \
    --task Tsh --scenario baseline \
    --vary product.A1=10,20 --vary ht.KC=2e-4,4e-4 \
    --methods scipy,fd --n-elements 1000 \
    --out results/fd_n1000.jsonl

# Compare discretization impact
```

### Pattern 3: Sensitivity Analysis

```bash
# Vary single parameter, fix others
python benchmarks/grid_cli.py generate \
    --task both --scenario baseline \
    --vary product.A1=5,7.5,10,12.5,15,17.5,20 \
    --methods scipy,fd,colloc --n-elements 1000 \
    --out results/sensitivity_A1.jsonl
```

## File Naming Conventions

Recommended patterns:

```
results/<version>/<task>_<grid>_<constraints>.jsonl

Examples:
- Tsh_3x3_ramp40.jsonl              # 3×3 grid, Tsh task, 40°C/hr ramp
- Pch_3x3_ramp005.jsonl             # 3×3 grid, Pch task, 0.05 Torr/hr ramp
- both_3x3_ramp40_005.jsonl         # 3×3 grid, both vars, both ramps
- both_5x5_fixed_init.jsonl         # 5×5 grid, fixed initial conditions
- Tsh_sensitivity_A1.jsonl          # Sensitivity study on A1
```

## See Also

- `BENCHMARKS_README.md` - Analysis infrastructure overview
- `generate_reports.py` - Report generation CLI
- `scenarios.py` - Available scenarios and parameters
- `grid_analysis.ipynb` - Notebook for viewing results
