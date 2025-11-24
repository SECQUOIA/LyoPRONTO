# Visualization Update: Separate Figures and Ramp Constraints

**Date**: November 20, 2025

## Changes Made

### 1. Split Trajectory Plots into Separate Figures

**Motivation**: Better scalability when comparing multiple methods. Individual plots are easier to analyze and compare.

**Previous Behavior**: 
- Single combined figure with 2-3 subplots (depending on task)
- All variables plotted together in one file

**New Behavior**:
- Each variable gets its own dedicated figure:
  - `nominal_trajectory_shelf_temperature.png` - Tsh comparison
  - `nominal_trajectory_chamber_pressure.png` - Pch comparison (for 'both' task)
  - `nominal_trajectory_dried_fraction.png` - Dried fraction comparison
- Each figure is saved separately for easier individual inspection
- More scalable if we add additional methods in the future

**Code Changes**:
- `benchmarks/visualization.py`: Modified `plot_trajectory_comparison()` to return dict of saved files instead of single figure
- `benchmarks/generate_reports.py`: Updated to handle multiple output files and print each one
- `benchmarks/grid_analysis_SIMPLE.ipynb`: Updated to display multiple trajectory plots

### 2. Added Ramp Constraint Visualization

**Motivation**: Explicitly visualize whether control variable ramp rates respect constraints, which is critical for equipment safety and process feasibility.

**New Plot**: `nominal_ramp_constraints.png`

**Features**:
- Shows d(Tsh)/dt and/or d(Pch)/dt (rate of change over time)
- Red dotted lines at ±5.0 °C/hr (or mTorr/hr) show constraint boundaries
- Compares scipy baseline vs Pyomo methods (FD and Collocation)
- Uses numpy gradient for smooth derivative estimation
- Zero reference line (gray) to help identify heating vs cooling

**Code Changes**:
- `benchmarks/visualization.py`: Added new `plot_ramp_constraints()` function
- `benchmarks/generate_reports.py`: Calls ramp constraint plot after trajectory plots
- `benchmarks/grid_analysis_SIMPLE.ipynb`: Displays ramp constraint plot in separate section

## Usage

### Generate Reports with New Visualizations

```bash
# From repository root
python benchmarks/generate_reports.py benchmarks/results/test --output analysis/test --task Tsh

# Or from benchmarks directory
cd benchmarks
python generate_reports.py results/v1_baseline --task both
```

### View in Notebook

Open `benchmarks/grid_analysis_SIMPLE.ipynb` and run the "Trajectory Comparison" section. You'll see:
1. Individual trajectory plots for each variable
2. Ramp constraints plot showing rate of change

## Files Modified

1. **benchmarks/visualization.py**
   - Modified `plot_trajectory_comparison()` - now returns dict of saved files
   - Added `plot_ramp_constraints()` - new function for ramp rate visualization

2. **benchmarks/generate_reports.py**
   - Added import for `plot_ramp_constraints`
   - Updated trajectory plotting to handle multiple output files
   - Added ramp constraint plot generation

3. **benchmarks/grid_analysis_SIMPLE.ipynb**
   - Updated trajectory display cell to show multiple plots
   - Added ramp constraints display
   - Updated documentation markdown cells

## Example Output

For a Tsh optimization task, you'll now get:
- `nominal_trajectory_shelf_temperature.png` - Tsh vs time
- `nominal_trajectory_dried_fraction.png` - Dried fraction vs time
- `nominal_ramp_constraints.png` - d(Tsh)/dt vs time with constraint boundaries

For a "both" task, you additionally get:
- `nominal_trajectory_chamber_pressure.png` - Pch vs time
- Ramp constraints shows both Tsh and Pch ramp rates

## Insights from Ramp Constraint Plot

The ramp constraint visualization reveals:
1. **Initial transient**: Large negative spike at t=0 (equipment ramping from initial conditions)
2. **Constraint adherence**: After initial transient, all methods stay within ±5°C/hr bounds
3. **Method comparison**: Shows how scipy vs Pyomo discretization methods handle constraints
4. **Stability**: Ramp rates converge to ~0 as process reaches steady state

## Backward Compatibility

- Old `nominal_trajectory.png` file is no longer generated
- Notebooks/scripts referencing the old file should be updated to use new individual files
- All other outputs (heatmaps, tables, summary stats) unchanged
