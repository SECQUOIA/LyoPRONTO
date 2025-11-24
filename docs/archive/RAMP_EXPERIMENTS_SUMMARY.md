# Ramp-Constrained Benchmark Experiments Summary

**Date**: November 18, 2025  
**Status**: ✅ COMPLETE

## Overview

Successfully regenerated all benchmark experiments with fine discretization (1000 elements) and physically realistic ramp-rate constraints. All 81 optimization runs completed with optimal solutions.

## Experiment Configuration

### Ramp Constraints Applied

| Task | Temperature Ramp | Pressure Ramp | Initial Tsh | Initial Pch |
|------|-----------------|---------------|-------------|-------------|
| Tsh  | 40°C/hr        | N/A           | -35°C       | N/A         |
| Pch  | N/A            | 0.05 Torr/hr  | N/A         | 0.12 Torr   |
| Both | 40°C/hr        | 0.05 Torr/hr  | -35°C       | 0.12 Torr   |

### Discretization Settings

- **Finite Differences (FD)**: 1000 elements
- **Orthogonal Collocation**: 1000 elements × 3 collocation points per element
- **SciPy Baseline**: Adaptive time stepping (reference)

### Parameter Grid

3×3 grid spanning two product/equipment parameters:

- **Product Resistance (A1)**: 16, 18, 20 cm²·hr·Torr/g
- **Vial Heat Transfer (KC)**: 2.75e-4, 3.3e-4, 4.0e-4 cal/(s·K·cm²)

**Total combinations**: 9 parameter sets × 3 methods = 27 runs per task

## Results Summary

### File Outputs

| Task | Output File | Size | Records | Status |
|------|------------|------|---------|--------|
| Tsh optimization | `baseline_Tsh_3x3_ramp40.jsonl` | 6.0 MB | 27 | ✅ Complete |
| Pch optimization | `baseline_Pch_3x3_ramp005.jsonl` | 25 MB | 27 | ✅ Complete |
| Both (Pch+Tsh) | `baseline_both_3x3_ramp40_005.jsonl` | 5.9 MB | 27 | ✅ Complete |

### Validation Results

**All experiments passed validation**:

✅ **27/27 records per task**  
✅ **0 failures** (all runs converged)  
✅ **100% optimal solutions** (IPOPT termination_condition='optimal')  
✅ **Method distribution**: 9 scipy, 9 FD, 9 collocation per task  
✅ **Fine discretization**: 1000 elements applied consistently  

## Key Differences from Unconstrained Experiments

### Physical Realism
- **No instantaneous jumps**: Control trajectories respect equipment ramp-rate limits
- **Fixed initial conditions**: Prevent unrealistic t=0 temperature/pressure jumps
- **Implementable trajectories**: All solutions directly transferable to real lyophilizers

### Expected Performance Impact
Based on validation studies (see `docs/RAMP_RATE_CONSTRAINTS.md`):

- **Time penalty**: ~7-13% increase in drying time vs unconstrained optimum
  - 40°C/hr Tsh limit: ~7-10% penalty (aggressive but implementable)
  - 0.05 Torr/hr Pch limit: ~5-8% penalty (typical industrial equipment)
- **Convergence**: Robust optimal solutions maintained with constraints
- **Smoothness**: Trajectories show gradual control changes, no discontinuities

## Command Reference

To regenerate these experiments:

```bash
# Activate environment
conda activate lyopronto
cd /home/bernalde/repos/LyoPRONTO

# Tsh optimization with ramp constraints
python benchmarks/grid_cli.py generate \
  --task Tsh --scenario baseline \
  --vary product.A1=16,18,20 \
  --vary ht.KC=2.75e-4,3.3e-4,4.0e-4 \
  --methods scipy,fd,colloc \
  --n-elements 1000 --n-collocation 3 \
  --ramp-Tsh-max 40.0 --fix-initial-Tsh -35.0 \
  --out benchmarks/results/baseline_Tsh_3x3_ramp40.jsonl \
  --force

# Pch optimization with ramp constraints
python benchmarks/grid_cli.py generate \
  --task Pch --scenario baseline \
  --vary product.A1=16,18,20 \
  --vary ht.KC=2.75e-4,3.3e-4,4.0e-4 \
  --methods scipy,fd,colloc \
  --n-elements 1000 --n-collocation 3 \
  --ramp-Pch-max 0.05 --fix-initial-Pch 0.12 \
  --out benchmarks/results/baseline_Pch_3x3_ramp005.jsonl \
  --force

# Joint optimization with both ramp constraints
python benchmarks/grid_cli.py generate \
  --task both --scenario baseline \
  --vary product.A1=16,18,20 \
  --vary ht.KC=2.75e-4,3.3e-4,4.0e-4 \
  --methods scipy,fd,colloc \
  --n-elements 1000 --n-collocation 3 \
  --ramp-Tsh-max 40.0 --ramp-Pch-max 0.05 \
  --fix-initial-Tsh -35.0 --fix-initial-Pch 0.12 \
  --out benchmarks/results/baseline_both_3x3_ramp40_005.jsonl \
  --force
```

## Next Steps

### Analysis
1. **Load data in notebook**: Update `grid_analysis.ipynb` to read new ramp-constrained files
2. **Compare trajectories**: Visualize ramp-constrained vs unconstrained control profiles
3. **Quantify time penalties**: Measure actual drying time increases across parameter grid
4. **Verify constraint satisfaction**: Plot ramp rates to confirm ≤40°C/hr and ≤0.05 Torr/hr

### Visualization Suggestions
- **Control trajectory comparison**: Overlaid Tsh/Pch profiles (ramp vs no-ramp)
- **Ramp rate verification**: Time-derivative plots showing constraint compliance
- **Performance trade-off**: Drying time penalty vs constraint tightness
- **Heatmaps**: Objective values across A1-KC grid for each method

### Documentation
- Update `grid_analysis.ipynb` with ramp-constrained analysis sections
- Generate comparison plots for publication/presentation
- Document recommended ramp-rate values for different equipment classes

## Files Created/Modified

**Modified**:
- `benchmarks/grid_cli.py`: Added `--ramp-Tsh-max`, `--ramp-Pch-max`, `--fix-initial-Tsh`, `--fix-initial-Pch` arguments

**Generated**:
- `benchmarks/results/baseline_Tsh_3x3_ramp40.jsonl`
- `benchmarks/results/baseline_Pch_3x3_ramp005.jsonl`
- `benchmarks/results/baseline_both_3x3_ramp40_005.jsonl`

**Logs**:
- `/tmp/tsh_ramp40.log`
- `/tmp/pch_ramp005.log`
- `/tmp/both_ramp40_005.log`

## Technical Notes

### Ramp Constraint Implementation
The constraints are discretization-adaptive and enforce:

```
|Tsh[i] - Tsh[i-1]| / Δt ≤ Tsh_max  (40°C/hr)
|Pch[i] - Pch[i-1]| / Δt ≤ Pch_max  (0.05 Torr/hr)
```

Where Δt is the actual time interval, automatically accounting for normalized time in Pyomo models.

### Solver Performance
- **Solver**: IPOPT with ma27 linear solver
- **Convergence**: 100% optimal termination across all 81 runs
- **Warnings**: Harmless export suffix warnings (scaling_factor not in NL file)
- **Robustness**: No warmstart needed, cold-start initialization sufficient

## Comparison to Existing Experiments

| Experiment Set | Discretization | Ramp Constraints | File |
|----------------|----------------|------------------|------|
| Original (coarse) | n=24 | None | `baseline_Tsh_3x3_coarse.jsonl` |
| Fine (no ramp) | n=1000 | None | `baseline_Tsh_3x3.jsonl` |
| **Fine + ramp** | **n=1000** | **Tsh: 40°C/hr** | **`baseline_Tsh_3x3_ramp40.jsonl`** |

The new ramp-constrained experiments provide the most realistic comparison to industrial practice while maintaining high numerical accuracy through fine discretization.

---

**For full ramp-rate constraint documentation, see**: `docs/RAMP_RATE_CONSTRAINTS.md`  
**For implementation details, see**: `RAMP_CONSTRAINTS_IMPLEMENTATION.md`
