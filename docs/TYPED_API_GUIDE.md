# Typed API Guide

LyoPRONTO exposes two coexisting public API styles. This guide explains the
distinction, the unit conventions, and where to find runnable examples. It
accompanies `docs/JULIA_PARITY_MATRIX.md`, which tracks per-export parity with
the Julia package `LyoHUB/LyoPronto.jl`.

## Legacy dict APIs (unchanged and fully supported)

The original calculators keep their dictionary inputs, plain-float values, and
output table shapes. They are not deprecated and are not changed by the
Julia-parity work:

- `lyopronto.calc_knownRp`, `lyopronto.calc_unknownRp`
- `lyopronto.opt_Pch`, `lyopronto.opt_Tsh`, `lyopronto.opt_Pch_Tsh`
- `lyopronto.design_space`
- `lyopronto.functions`, `lyopronto.constant`
- the web-style I/O in `lyopronto.high_level`

These modules use the established float/unit conventions documented in
`docs/PHYSICS_REFERENCE.md` and the legacy examples under `examples/legacy/`
and `docs/examples/`. The legacy 7-column NumPy output tables are preserved.

The `design_space.dry` equipment-capability input remains backward compatible:
it accepts either legacy `{"a", "b"}` coefficients or ECCURT geometry keys
(`duct_diameter`, `valve_thickness`, `duct_length`, `chamber_volume`).

## Typed Pint APIs (additive)

The typed API uses [Pint](https://pint.readthedocs.io/) as the unit library.
`lyopronto.Q_` is the package quantity constructor and `lyopronto.ureg` is the
shared unit registry. Typed entry points accept Pint quantities where units
matter, and also accept plain floats interpreted in the canonical units below.

Canonical units for plain-float inputs and outputs:

- time: hours
- length / height: centimeters
- temperature: kelvin
- chamber pressure: torr (Pirani/CM traces and ECCURT pressures use millitorr)
- area: square centimeters
- product resistance `Rp`: `cm^2*hr*Torr/g`
- heat-transfer coefficient: `cal/s/K/cm^2`
- concentration: `g/mL`
- mass: grams; RF power: watts (per vial); frequency: hertz
- RF heat diagnostics: watts; integrated RF energies: watt-hours

Typed modules and their primary entry points:

- `lyopronto.typed`: `RpFormFit`, `ConstPhysProp`, `RampedVariable`,
  `PrimaryDryFit`
- `lyopronto.physical_properties`: constants, `calc_psub`/`calc_tsub`, `eppf`
- `lyopronto.vials`: `get_vial_radii`, `get_vial_mass`, `get_vial_shape`,
  `make_outlines`
- `lyopronto.pikal`: `PikalParams`, `solve_pikal`, `RpEstimator`, `calc_hRp_T`
- `lyopronto.rf`: `RFParams`, `solve_rf`, `calc_rf_heat_terms`, `qrf_integrate`
- `lyopronto.fitting`: `RpTransform`/`KTransform`/`KRpTransform`,
  `KBBTransform`/`BoundedKBBTransform`, `fit_primary_drying`,
  `fit_rf_primary_drying`
- `lyopronto.eccurt`: `eq_cap_line`, `eq_cap_pressure`,
  `eq_cap_pressures_new`, `eq_cap_line_new`
- `lyopronto.cycle_time`: `identify_pd_end`

## Runnable examples

`examples/typed_api_examples.py` contains one small function per typed
workflow (conventional simulation, Kv/Rp fitting, direct Rp estimation, RF
simulation, RF energy accounting, RF fitting, vial utilities, ECCURT, and
Pirani end-of-primary-drying detection). Run them all with:

    python -m examples.typed_api_examples

They are also executed as smoke tests in `tests/test_typed_examples.py`, which
run as plain pytest cases (no Jupyter/papermill required). The legacy notebook
smoke tests remain in `tests/test_example_scripts.py`.

## Conventions and status notes

- Percent dried: the legacy calculators and optimizers report percent dried as
  `Lck / Lpr0 * 100`, i.e. dried/cake length over initial product length, in
  percent. The typed solvers instead expose the physical state directly
  (frozen/dried height, frozen mass) rather than a percent field.
- Optimization backend: the shipping optimizers (`opt_Pch`, `opt_Tsh`,
  `opt_Pch_Tsh`) and `fit_primary_drying`/`fit_rf_primary_drying` use SciPy.
  Pyomo-based simultaneous optimization is not tracked on `main`; current
  status is summarized in `docs/ARCHITECTURE.md`, and roadmap planning should
  live in GitHub issues.

## Attribution

Formulas, coefficients, and data tables ported from Julia derive from the
MIT-licensed `LyoHUB/LyoPronto.jl` at commit `f452ad4`. Per-module source-file
and commit attribution lives in the typed module docstrings (for example
`lyopronto/physical_properties.py`, `lyopronto/rf.py`, and
`lyopronto/eccurt.py`), and `docs/JULIA_PARITY_MATRIX.md` carries an
attribution section.
