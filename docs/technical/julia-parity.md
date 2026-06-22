# Julia Parity Matrix

This matrix tracks parity with the public exports in Julia `LyoPronto.jl`
at commit `f452ad4`.

The Python package now has an additive typed API foundation for Julia-parity
work. Existing dict-based calculators, optimizers, design-space generation,
and web-style I/O remain supported and keep their legacy float units and
output table shapes.

See `../reference.md` for the legacy-vs-typed API distinction and Pint unit
conventions. Runnable typed examples live in `examples/typed_api_examples.py`.

## Attribution

Formulas, coefficients, and data tables ported here derive from the
MIT-licensed Julia package `LyoHUB/LyoPronto.jl` at commit `f452ad4`. The
relevant Python modules carry source-file and commit attribution in their
module docstrings (for example `lyopronto/physical_properties.py`,
`lyopronto/rf.py`, and `lyopronto/eccurt.py`).

## Status Values

- `ported`: the Python API covers the Julia export's intended public behavior.
- `partially ported`: the conventional Pikal path is available, but RF or
  another Julia mode remains planned.
- `planned`: no Python implementation is present yet; the issue listed in the
  location column owns the port.
- `intentionally unsupported`: the Julia API shape does not map to the Python
  public API, usually because the Julia export is mutating.

| Julia export | Python status | Python location | Notes |
| --- | --- | --- | --- |
| `RpFormFit` | ported | `lyopronto.typed.RpFormFit` | Callable `R0 + A1*x/(1 + A2*x)`. |
| `RampedVariable` | ported | `lyopronto.typed.RampedVariable` | `constant`, `linear`, and `multi` constructors. |
| `ConstPhysProp` | ported | `lyopronto.typed.ConstPhysProp` | Callable constant physical property. |
| `PrimaryDryFit` | ported | `lyopronto.typed.PrimaryDryFit` | Fitting-data container for product temperature, vial-wall temperature/endpoint, and drying end-time data. |
| `end_drying_callback` | ported | `lyopronto.pikal.solve_pikal`, `lyopronto.rf.solve_rf` | Conventional and RF solvers stop at drying completion. |
| `calc_u0` | ported | `lyopronto.pikal.calc_pikal_u0`, `lyopronto.rf.calc_rf_u0` | Initial-state helpers for Pikal and RF typed solvers. |
| `get_tstops` | ported | `lyopronto.pikal.get_pikal_tstops`, `lyopronto.rf.get_rf_tstops` | Pikal and RF extract stops from ramped controls. |
| `lyo_1d_dae_f` | ported | `lyopronto.pikal.calc_md_q`, `lyopronto.pikal.solve_pikal` | Python solves the height ODE with the Pikal algebraic temperature balance through SciPy. |
| `ParamObjPikal` | ported | `lyopronto.pikal.PikalParams` | Typed Pikal parameter dataclass. |
| `RpEstimator` | ported | `lyopronto.pikal.RpEstimator` | Direct Rp estimation input bundle for typed Pikal data. |
| `calc_hRp_T` | ported | `lyopronto.pikal.calc_hRp_T` | Direct Rp-vs-height estimate from temperature data; returns dried height in cm and Rp in `cm^2*hr*Torr/g`. |
| `lumped_cap_rf!` | ported | `lyopronto.rf.rf_rhs`, `lyopronto.rf.calc_rf_diagnostics` | RF/microwave RHS with heat diagnostics in Julia order. |
| `ParamObjRF` | ported | `lyopronto.rf.RFParams` | Typed RF parameter dataclass with tuple-of-tuples constructor. |
| `gen_sol_pd` | ported | `lyopronto.fitting.gen_sol_pd`, `lyopronto.fitting.gen_sol_rf` | Pikal and RF solution generators share the same fitting transform path. |
| `obj_pd` | ported | `lyopronto.fitting.obj_pd`, `lyopronto.fitting.obj_rf` | Pikal and RF scalar objectives both reuse `PrimaryDryFit` and `obj_expT`. |
| `gen_nsol_pd` | ported | `lyopronto.fitting.gen_nsol_pd` | Multi-experiment Pikal/RF fitting helper with shared/separate groups. |
| `objn_pd` | ported | `lyopronto.fitting.objn_pd` | Multi-experiment Pikal/RF scalar objective. |
| `KRp_transform_basic` | ported | `lyopronto.fitting.KRpTransform` | Conventional Kv/Rp log-space transform. |
| `K_transform_basic` | ported | `lyopronto.fitting.KTransform` | Conventional Kv transform. |
| `Rp_transform_basic` | ported | `lyopronto.fitting.RpTransform` | Product-resistance transform. |
| `KBB_transform_basic` | ported | `lyopronto.fitting.KBBTransform` | RF `Kvwf`, `Bf`, and `Bvw` log-space transform. |
| `KBB_transform_bounded` | ported | `lyopronto.fitting.BoundedKBBTransform` | RF bounded logistic transform. |
| `obj_expT` | ported | `lyopronto.fitting.obj_expT` | Temperature/end-time scalar objective. |
| `err_expT` | ported | `lyopronto.fitting.err_expT` | Residual vector for SciPy least squares. |
| `err_expT!` | intentionally unsupported | Python residual functions return arrays | Julia mutating API is not a Python public API target. |
| `num_errs` | ported | `lyopronto.fitting.num_errs` | Residual-count helper. |
| `nls_pd` | ported | `lyopronto.fitting.err_pd`, `lyopronto.fitting.err_rf`, `lyopronto.fitting.errn_pd`, `lyopronto.fitting.fit_primary_drying`, `lyopronto.fitting.fit_rf_primary_drying` | Pikal and RF residual wrappers and SciPy least-squares entry points. |
| `nls_pd!` | intentionally unsupported | Python fitting functions return results | Julia mutating API is not a Python public API target. |
| `qrf_integrate` | ported | `lyopronto.rf.qrf_integrate` | Trapezoidal time-integration of the RF heat-transfer modes over a solved trajectory; returns `Qsub`/`Qshf`/`Qvwf`/`QRFf`/`QRFvw` as Pint energies. |
| `identify_pd_end` | ported | `lyopronto.cycle_time.identify_pd_end` | Pirani-based end-of-primary-drying detection. |
| `get_vial_radii` | ported | `lyopronto.vials.get_vial_radii` | SCHOTT vial metadata utility; module-level public API. |
| `get_vial_mass` | ported | `lyopronto.vials.get_vial_mass` | SCHOTT vial metadata utility; module-level public API. |
| `get_vial_shape` | ported | `lyopronto.vials.get_vial_shape` | SCHOTT vial shape utility; module-level public API. |
| `make_outlines` | ported | `lyopronto.vials.make_outlines` | Vial/fill outline utility; module-level public API. |
| `ECCURT` | ported | `lyopronto.eccurt` | Equipment-capability interpolation module with original/new line methods and pressure interpolation. |

## Public API Export Policy

The package exposes both stable module namespaces and selected direct
top-level imports from `lyopronto`.

- Module namespaces imported by `lyopronto.__init__`, such as
  `lyopronto.typed`, `lyopronto.pikal`, `lyopronto.fitting`,
  `lyopronto.cycle_time`, `lyopronto.physical_properties`, and
  `lyopronto.vials`, are public entry points.
- Direct top-level imports are reserved for stable typed workflow objects and
  functions that are expected to be common end-user imports, for example
  `PikalParams`, `PikalSolution`, `PrimaryDryFit`, `solve_pikal`,
  fitting transforms, and `identify_pd_end`.
- Domain utility families with several related helpers remain module-level
  public APIs. The vial helpers are intentionally used as
  `lyopronto.vials.get_vial_radii(...)` or `from lyopronto import vials`;
  their exported names are governed by `lyopronto.vials.__all__`, not by
  `lyopronto.__all__`.
- `physical_properties` follows the same module-level policy because it
  contains constants, aliases, and correlations that are easier to keep
  coherent as one namespace.
- RF names start in `lyopronto.rf` and RF fitting names start in
  `lyopronto.fitting`. The primary workflow objects, solver, and fitting entry
  points are also available as direct top-level imports: `RFParams`,
  `RFSolution`, `RFDiagnostics`, `solve_rf`, `KBBTransform`,
  `BoundedKBBTransform`, `fit_rf_primary_drying`, and `qrf_integrate`.
  Lower-level RF heat diagnostics remain module-level unless they become
  broadly used user-facing APIs.

## Parity Test Categories

The existing tests mix three parity categories. New Julia-parity tests should
make the category clear in the test name or assertion comments.

- Exact Julia parity checks assert reference constants, formulas, table values,
  and direct API behavior that should not drift. Current examples include
  `test_rpformfit_matches_julia_formula_with_quantities`,
  `test_constant_ramped_variable_matches_julia_cases`,
  `test_get_vial_radii_matches_julia_table_for_6r`,
  `test_get_vial_mass_and_thickness_match_julia_table_for_6r`, and
  `test_physical_property_constants_match_julia_units_and_values`.
- Bounded parity checks assert numerical behavior within tolerances where
  SciPy solvers, interpolation, or fitting optimizers can differ slightly from
  Julia. Current examples include the Pikal sucrose benchmark, direct
  `calc_hRp_T` recovery tests, primary-drying fit recovery tests, and residual
  weighting tests.
- Intentional Python divergences cover safer Python API behavior and should
  stay documented in tests. Current examples include corrected absolute-index
  handling in `identify_pd_end`, explicit input validation for Pirani traces,
  quantity-aware inputs and outputs, and non-mutating fitting functions in
  place of Julia `!` APIs.

## Non-Exported Julia Helpers

These helpers are not public exports from Julia `LyoPronto.jl`, but they are
tracked here because downstream typed APIs depend on them.

| Julia helper | Python status | Python location | Notes |
| --- | --- | --- | --- |
| `physical_properties.jl` constants | ported | `lyopronto.physical_properties` | Unitful constants are represented as Pint quantities. |
| `calc_psub` | ported | `lyopronto.physical_properties.calc_psub` | Plain floats use kelvin and pascal; Pint inputs are converted. |
| `calc_Tsub` | ported | `lyopronto.physical_properties.calc_tsub` | Python also provides `calc_Tsub` as an alias. |
| `eppf` dielectric helper | ported | `lyopronto.physical_properties.eppf` | Ice dielectric-loss correlation with Julia reference interpolation arrays. |
