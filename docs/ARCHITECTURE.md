# LyoPRONTO Architecture

This document describes the current repository architecture on `main`.

## Current Capabilities

LyoPRONTO models vial-scale lyophilization with:

- freezing calculations
- primary drying with known product resistance
- primary drying with resistance estimated from temperature data
- SciPy-based pressure and shelf-temperature optimization modes
- design-space calculations
- legacy file-oriented compatibility helpers
- typed Pint APIs ported from Julia-facing workflows
- RF, Pikal, fitting, vial, equipment-capability, and cycle-time helpers
- optional Pyomo primary-drying prototypes for single-step and multi-period
  trajectory modeling

Pyomo roadmap planning lives in GitHub issue
[#80](https://github.com/SECQUOIA/LyoPRONTO/issues/80) and its child issues.
Tracked Pyomo implementation status is documented in `docs/PYOMO_STATUS.md`.

## Package Layout

```text
lyopronto/
├── __init__.py              # Lightweight lazy public package interface
├── constant.py              # Legacy constants and unit conversions
├── functions.py             # Legacy physics functions and ramp helpers
├── calc_knownRp.py          # Primary drying with known Rp
├── calc_unknownRp.py        # Rp estimation from temperature data
├── freezing.py              # Freezing calculations
├── design_space.py          # Legacy design-space generator
├── opt_Pch.py               # Pressure-only SciPy optimizer
├── opt_Tsh.py               # Shelf-temperature SciPy optimizer
├── opt_Pch_Tsh.py           # Joint pressure/shelf-temperature SciPy optimizer
├── high_level.py            # File-oriented compatibility helpers
├── plot_styling.py          # Explicit plotting helpers
├── typed.py                 # Pint-aware typed API helpers
├── physical_properties.py   # Typed physical-property utilities
├── pikal.py                 # Typed Pikal primary-drying workflow
├── rf.py                    # Typed RF workflow
├── fitting.py               # SciPy fitting helpers for typed workflows
├── cycle_time.py            # End-of-primary-drying detection
├── eccurt.py                # Equipment capability utilities
├── vials.py                 # Vial geometry and metadata helpers
└── pyomo_models/            # Optional Pyomo primary-drying prototypes
```

Supporting directories:

```text
examples/       # Maintained examples plus legacy examples
test_data/      # Reference inputs and regression data
tests/          # Pytest suite and marker policy
docs/           # Current technical documentation
.github/        # GitHub Actions workflows and contributor tool docs
```

## Public API Layers

### Legacy Dict APIs

The original calculators and optimizers accept dictionaries and plain floats.
They remain supported for existing scripts and examples:

- `calc_knownRp`
- `calc_unknownRp`
- `freezing`
- `design_space`
- `opt_Pch`
- `opt_Tsh`
- `opt_Pch_Tsh`
- `functions`
- `constant`

These APIs use the legacy unit conventions. Primary-drying output arrays have
seven columns: time in hours, sublimation temperature in degC, vial-bottom
temperature in degC, shelf temperature in degC, chamber pressure in mTorr,
sublimation flux in kg/hr/m^2, and percent dried from 0 to 100.

### Typed Pint APIs

The typed API is additive. It uses `lyopronto.Q_` and `lyopronto.ureg` for Pint
quantities while still accepting documented plain-float canonical units. The
current typed modules include:

- `typed`
- `physical_properties`
- `pikal`
- `rf`
- `fitting`
- `cycle_time`
- `eccurt`
- `vials`

See `docs/TYPED_API_GUIDE.md` and `docs/JULIA_PARITY_MATRIX.md` for typed API
status, unit conventions, and Julia attribution.

### High-Level Compatibility Helpers

`high_level.py` provides the file-oriented helpers used by `main.py` and older
workflows:

- `read_inputs`
- `save_inputs`
- `save_inputs_legacy`
- `execute_simulation`
- `save_csv`
- `generate_visualizations`

These helpers are exposed lazily at package level for compatibility with
imports such as `from lyopronto import execute_simulation`.

### Optional Pyomo Models

`lyopronto.pyomo_models` is an additive optional package. It is imported lazily
and requires the `pyomo` extra only when users request Pyomo functionality. The
current tracked models are:

- `single_step`: one primary-drying optimization point
- `trajectory`: a backward-Euler multi-period primary-drying trajectory model

The Pyomo modules share legacy unit conventions and physics helper functions,
but they remain isolated from the existing SciPy calculators.

## Dependency Shape

The legacy path has a shallow dependency graph:

```text
constant.py
    ↓
functions.py
    ↓
calc_knownRp.py ─┐
calc_unknownRp.py│
freezing.py      │
opt_*.py         ├─ high_level.py
design_space.py ─┘
```

The typed path is also additive:

```text
typed.py
physical_properties.py
    ↓
pikal.py, rf.py
    ↓
fitting.py
cycle_time.py, eccurt.py, vials.py
```

The optional Pyomo path depends on `functions.py`, `constant.py`, and Pyomo:

```text
constant.py, functions.py
    ↓
pyomo_models/single_step.py
pyomo_models/trajectory.py
```

`__init__.py` avoids importing heavy plotting or solver modules at top-level
import time. It lazily imports submodules and selected public symbols on first
access.

## Data Flow

### Legacy Primary Drying

```text
vial/product/heat-transfer/process dictionaries
    ↓
calc_knownRp.dry(...)
    ↓
RampInterpolator builds Pch(t) and Tsh(t)
    ↓
solve_ivp integrates dried cake length
    ↓
functions.py computes vapor pressure, Rp, Kv, sublimation rate, and output rows
    ↓
NumPy output table with legacy units
```

### High-Level Compatibility

```text
YAML/CSV-style inputs or in-memory dictionaries
    ↓
high_level.execute_simulation(...)
    ↓
selected calculator, design-space generator, optimizer, or freezing workflow
    ↓
high_level.save_csv(...) and generate_visualizations(...)
```

### Typed Workflows

```text
Pint quantities or canonical plain floats
    ↓
typed dataclasses / workflow-specific parameter objects
    ↓
SciPy ODE, optimization, or fitting helper
    ↓
typed solution objects, diagnostics, or fitted parameters
```

### Pyomo Trajectory Prototype

```text
vial/product/heat-transfer/process dictionaries
    ↓
optional legacy ramp sampling and SciPy trajectory warmstart
    ↓
pyomo_models.trajectory.create_trajectory_model(...)
    ↓
uniform backward-Euler dried-cake dynamics plus nodewise physics constraints
    ↓
solve_trajectory(...) diagnostics and legacy-shaped trajectory table
```

## CI and Test Architecture

The active test and CI lanes are marker-based:

- static analysis: enforced Ruff, advisory mypy
- fast PR lane: excludes `slow`, `notebook`, and `pyomo`
- full non-Pyomo lane: tracked confidence gate with coverage
- notebook lane: explicit Jupyter/papermill validation
- slow non-Pyomo lane: manual optimizer-heavy validation
- Pyomo lane: manual optional lane for environments with Pyomo and IPOPT

The authoritative current testing policy is in `tests/README.md`. The CI
workflow guide is in `docs/CI_WORKFLOW_GUIDE.md`.

## Pyomo Status

Pyomo support is optional and additive. Current facts:

- `lyopronto/pyomo_models/` contains tracked single-step and trajectory models.
- Pyomo tests are marked `pyomo` and require optional Pyomo/IPOPT tooling.
- automatic PR and main-branch workflows exclude Pyomo
- manual Pyomo validation exercises the optional lane when the extra solver
  stack is installed

See `docs/PYOMO_STATUS.md` for the tracked model status, the trajectory
discretization choice, and warmstart hooks.

## Design Constraints

- Preserve legacy dict APIs and output table shapes for existing scripts.
- Keep typed Pint APIs additive rather than replacing legacy workflows.
- Keep `import lyopronto` lightweight.
- Avoid new dependencies for legacy paths unless they are justified by the
  feature being added.
- Keep dated completion reports and old coverage/test-count snapshots out of
  the documentation tree; use GitHub issues, PRs, and git history for that
  historical record.
