# API Reference

Top-level `import lyopronto` is intentionally lightweight. It exposes
`lyopronto.__version__` immediately and loads submodules or compatibility
helpers only when they are accessed.

## Public API Boundaries

### Legacy Dict APIs

These modules accept the original dictionary-style inputs and return numeric
arrays or legacy result structures. They remain the stable compatibility layer
for existing scripts:

- `lyopronto.calc_knownRp`
- `lyopronto.calc_unknownRp`
- `lyopronto.freezing`
- `lyopronto.design_space`
- `lyopronto.opt_Pch`
- `lyopronto.opt_Tsh`
- `lyopronto.opt_Pch_Tsh`
- `lyopronto.functions`
- `lyopronto.constant`

Existing imports such as `from lyopronto import calc_knownRp` remain supported.

### Typed Pint API

The typed API uses Pint quantities for unit-aware calculations and fitting.
These names are available from the top-level package and from their defining
modules:

- `lyopronto.typed`: `Q_`, `ureg`, `RpFormFit`, `ConstPhysProp`,
  `RampedVariable`, `PrimaryDryFit`
- `lyopronto.pikal`
- `lyopronto.rf`
- `lyopronto.fitting`
- `lyopronto.cycle_time`
- `lyopronto.eccurt`
- `lyopronto.physical_properties`
- `lyopronto.vials`

### High-Level Compatibility Helpers

`lyopronto.high_level` provides the file-oriented compatibility helpers used by
legacy workflows:

- `read_inputs`
- `save_inputs`
- `save_inputs_legacy`
- `execute_simulation`
- `save_csv`
- `generate_visualizations`

These helpers are also exposed lazily at package level for existing imports
such as `from lyopronto import execute_simulation`.

### Optional Pyomo Models

`lyopronto.pyomo_models` contains optional Pyomo primary-drying prototypes. It
is lazily imported and requires the `pyomo` extra only when requested:

- `lyopronto.pyomo_models.single_step`
- `lyopronto.pyomo_models.trajectory`

See `docs/PYOMO_STATUS.md` for the current Pyomo implementation status,
trajectory discretization, and warmstart hooks.

### Plotting Helpers

Plotting is explicit. `import lyopronto` does not import Matplotlib. Use
`lyopronto.plot_styling` for axis styling helpers, or call
`generate_visualizations` when PDF plots should be created. Matplotlib import
errors are not hidden; they are raised when plotting functionality is requested.

## Full Listing

::: lyopronto
    options:
      show_submodules: true
