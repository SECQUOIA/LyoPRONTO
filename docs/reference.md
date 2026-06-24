# API Reference

Top-level `import lyopronto` is intentionally lightweight. It exposes
`lyopronto.__version__` immediately and loads submodules or compatibility
helpers only when they are accessed. This page is the compact reference for
current public API layers, package layout, typed-unit conventions, and optional
Pyomo boundaries.

For model equations and scientific assumptions, see
`technical/physics-reference.md`. For Julia parity status, see
`technical/julia-parity.md`.

## Package Map

Core legacy modules:

- `lyopronto.functions`: physics equations and ramp interpolation helpers.
- `lyopronto.constant`: physical constants and unit conversions.
- `lyopronto.calc_knownRp`: primary drying with known product resistance.
- `lyopronto.calc_unknownRp`: resistance estimation from temperature data.
- `lyopronto.freezing`: freezing-phase calculations.
- `lyopronto.design_space`: design-space calculations.
- `lyopronto.opt_Pch`, `lyopronto.opt_Tsh`, `lyopronto.opt_Pch_Tsh`: SciPy
  optimization modes.

Additive typed modules:

- `lyopronto.typed`: Pint-aware data helpers.
- `lyopronto.physical_properties`, `pikal`, `rf`, `fitting`, `cycle_time`,
  `eccurt`, and `vials`: typed workflows and Julia-parity utilities.
- `lyopronto.high_level`: file-oriented compatibility helpers used by
  `main.py`.
- `lyopronto.pyomo_models`: optional Pyomo single-step and trajectory models.

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

The typed API is additive. It uses [Pint](https://pint.readthedocs.io/) for
unit-aware calculations and fitting. `lyopronto.Q_` is the package quantity
constructor and `lyopronto.ureg` is the shared unit registry. Typed entry points
accept Pint quantities where units matter and also accept plain floats in these
canonical units:

- time: hours
- length and height: centimeters
- temperature: kelvin
- chamber pressure: torr; Pirani/CM traces and ECCURT pressures use millitorr
- area: square centimeters
- product resistance `Rp`: `cm^2*hr*Torr/g`
- heat-transfer coefficient: `cal/s/K/cm^2`
- concentration: `g/mL`
- mass: grams
- RF power: watts per vial
- RF frequency: hertz
- RF heat diagnostics: watts
- integrated RF energies: watt-hours

These names are available from the top-level package and from their defining
modules:

- `lyopronto.typed`: `Q_`, `ureg`, `RpFormFit`, `ConstPhysProp`,
  `RampedVariable`, `PrimaryDryFit`, `extract_ts`
- `lyopronto.pikal`
- `lyopronto.rf`
- `lyopronto.fitting`
- `lyopronto.cycle_time`
- `lyopronto.eccurt`
- `lyopronto.physical_properties`
- `lyopronto.vials`

`extract_ts(control, unit="hour")` returns typed-control stop times as float
magnitudes. Ramped controls expose raw stop times, interpolation-like controls
may expose `t` or `times`, and unrecognized controls are treated as constant
from time zero. Raw stop times may include `math.inf` for an unbounded hold;
callers building finite grids should filter non-finite values, as
`get_pikal_tstops` and `get_rf_tstops` do.

Runnable typed examples live in `examples/typed_api_examples.py` and are
covered by `tests/test_typed_examples.py`.

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
is lazily imported and requires the `pyomo` extra only when requested. Pyomo
support does not change the legacy SciPy calculators or their public output
arrays.

Implemented modules:

- `lyopronto.pyomo_models.single_step` builds and solves one primary-drying
  optimization point with the legacy heat-transfer and mass-transfer
  equations.
- `lyopronto.pyomo_models.trajectory` builds a multi-period primary-drying
  trajectory model over a fixed uniform time grid.
- `lyopronto.pyomo_models.optimization` exposes experimental trajectory
  optimization builders for pressure-only, shelf-temperature-only, and joint
  pressure/shelf-temperature modes.
- `lyopronto.pyomo_models.advanced` composes the trajectory and optimization
  builders into optional parameter-estimation, design-space feasibility,
  sensitivity-analysis, robust-optimization, and multi-vial capacity workflows.

Pyomo tests are marked `pyomo` and are skip-safe when Pyomo or IPOPT is not
installed. See `dev.md` for optional solver setup and CI lane policy.
The maintained construction example lives in
`examples/example_pyomo_optimization.py` and is covered by the optional Pyomo
test lane.

The trajectory model uses backward Euler for dried cake length:

```text
Lck[t] = Lck[t - 1] + dt * dLdt[t]
```

The model enforces the algebraic primary-drying physics at every time node:

- vapor pressure from sublimation-front temperature
- sublimation mass transfer
- frozen-layer heat balance
- shelf-to-vial energy balance
- pressure-dependent vial heat transfer
- optional product-temperature and equipment-capability limits

Chamber pressure, shelf temperature, dried cake length, temperatures,
sublimation rate, vapor pressure, and heat-transfer coefficient are time-indexed
Pyomo variables. Chamber-pressure and shelf-temperature profiles can be fixed
from legacy ramp schedules, or bounded and constrained by per-hour ramp limits.

The optimization mode builders use the same legacy dictionary conventions as
the SciPy optimizers:

- `create_pressure_optimization_model`: fixed shelf-temperature profile,
  variable chamber pressure.
- `create_shelf_temperature_optimization_model`: fixed chamber-pressure
  profile, variable shelf temperature.
- `create_joint_optimization_model`: chamber pressure and shelf temperature
  both variable.

All three modes intentionally share the trajectory objective
`sum(Pch[t] - Psub[t])`, a driving-force proxy inherited from the legacy
optimizers. Mode-specific behavior comes from the free/fixed controls, fixed
profiles, bounds, product-temperature limit, optional equipment capability, and
optional ramp-rate constraints. These Pyomo APIs are validation prototypes and
should not be treated as stable replacements for `opt_Pch.dry`,
`opt_Tsh.dry`, or `opt_Pch_Tsh.dry`.

There is intentionally no unified SciPy/Pyomo optimizer selector. Call the
legacy SciPy optimizer modules or the explicit Pyomo builders directly so
solver requirements, formulation differences, and failure modes remain visible.

The final dried target is represented as a lower bound on the final dried cake
fraction. Targets must remain below 100% because the frozen-layer heat balance
is singular when no frozen layer remains.

`trajectory_initialization_from_scipy_output` converts a legacy SciPy trajectory
table into Pyomo initial values. It converts pressure from mTorr to Torr,
sublimation flux to kg/hr/vial, and percent dried to cake length.
`apply_trajectory_warmstart` can apply that mapping, or any compatible indexed
mapping, to an existing trajectory model.

Comparison to SciPy optimizer results is direct for variable bounds, fixed
profiles, output columns, and algebraic constraints. Full trajectories can
diverge because the Pyomo optimizer solves a simultaneous fixed-horizon
backward-Euler problem with a final dried-fraction target, while the SciPy
optimizers solve sequential point problems and advance until complete drying.

Advanced workflow builders remain explicit optional Pyomo prototypes:

- `create_parameter_estimation_model` builds a least-squares model for fitting
  product-resistance parameters (`R0`, `A1`, `A2`) and heat-transfer parameters
  (`KC`, `KP`, `KD`) from fixed-time synthetic or experimental observations.
  Observation units follow the legacy primary-drying conventions: pressure in
  Torr, dried cake length in cm, sublimation rate in kg/hr/vial, and
  heat-transfer coefficient in cal/s/K/cm^2.
- `create_design_space_feasibility_model` fixes chamber-pressure and
  shelf-temperature profiles and turns the trajectory model into a pure
  feasibility replay with product-temperature and optional equipment-capacity
  constraints. `create_design_space_grid_models` applies that replay over a
  pressure/shelf-temperature grid.
- `create_multivial_optimization_model` wraps the existing optimization modes
  with required batch-capacity inputs and explicit batch-level diagnostics. It
  uses the trajectory model's existing equipment-capability constraint rather
  than adding independent per-vial decision variables. The capacity convention
  is `nvial * dmdt <= eq_cap["a"] + eq_cap["b"] * Pch`, where `dmdt` is the
  per-vial sublimation rate in kg/hr/vial and `Pch` is in Torr.
- `create_sensitivity_analysis_models` creates fixed-control feasibility
  replays for fractional perturbations of vial, product, or heat-transfer
  parameters. Returned models carry finite-difference metadata such as the
  perturbed parameter, base value, perturbed value, and difference
  denominator.
- `create_robust_optimization_model` builds a scenario-based minimax Pyomo
  model. Each scenario is a deterministic optimization block with optional
  overrides for `vial`, `product`, `ht`, or `eq_cap`; optimized controls are
  shared across scenarios, and the top-level objective minimizes the worst
  scenario value of the existing driving-force objective. Scenario capacity
  diagnostics use the same `nvial * dmdt <= eq_cap["a"] + eq_cap["b"] * Pch`
  convention as the multi-vial builder.

The completed Pyomo implementation roadmap is tracked in GitHub issue
[#80](https://github.com/SECQUOIA/LyoPRONTO/issues/80) and its child issues.
Keep this reference focused on implemented behavior and current usage notes;
track future Pyomo work in new, scoped GitHub issues.

### Plotting Helpers

Plotting is explicit. `import lyopronto` does not import Matplotlib. Use
`lyopronto.plot_styling` for axis styling helpers, or call
`generate_visualizations` when PDF plots should be created. Matplotlib import
errors are not hidden; they are raised when plotting functionality is requested.

## Full Listing

::: lyopronto
    options:
      show_submodules: true
