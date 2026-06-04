# Julia Parity Matrix

This matrix tracks parity with the public exports in Julia `LyoPronto.jl`
at commit `f452ad4`.

The Python package now has an additive typed API foundation for Julia-parity
work. Existing dict-based calculators, optimizers, design-space generation,
and web-style I/O remain supported and keep their legacy float units and
output table shapes.

| Julia export | Python status | Python location | Notes |
| --- | --- | --- | --- |
| `RpFormFit` | ported | `lyopronto.typed.RpFormFit` | Callable `R0 + A1*x/(1 + A2*x)`. |
| `RampedVariable` | ported | `lyopronto.typed.RampedVariable` | `constant`, `linear`, and `multi` constructors. |
| `ConstPhysProp` | ported | `lyopronto.typed.ConstPhysProp` | Callable constant physical property. |
| `PrimaryDryFit` | planned | Issue #41 | Fitting-data container belongs to the residual/objective PR. |
| `end_drying_callback` | planned | Issues #40, #45 | Python will implement solver terminal events. |
| `calc_u0` | planned | Issues #40, #45 | Initial-state construction belongs with solver PRs. |
| `get_tstops` | planned | Issues #40, #45 | `RampedVariable.timestops` is available; solver-specific handling remains planned. |
| `lyo_1d_dae_f` | planned | Issue #40 | Conventional Pikal RHS/solver. |
| `ParamObjPikal` | planned | Issue #40 | Typed Pikal parameter dataclass. |
| `RpEstimator` | planned | Issue #43 | Direct Rp estimation workflow. |
| `calc_hRp_T` | planned | Issue #43 | Direct Rp-vs-height estimate from temperature data. |
| `lumped_cap_rf!` | planned | Issue #45 | RF/microwave RHS. |
| `ParamObjRF` | planned | Issue #45 | Typed RF parameter dataclass. |
| `gen_sol_pd` | planned | Issues #42, #46 | Conventional/RF solution generators for fitting. |
| `obj_pd` | planned | Issues #42, #46 | Scalar fitting objective. |
| `gen_nsol_pd` | planned | Issue #42 | Multi-experiment fitting helper. |
| `objn_pd` | planned | Issue #42 | Multi-experiment scalar objective. |
| `KRp_transform_basic` | planned | Issue #42 | Conventional Kv/Rp log-space transform. |
| `K_transform_basic` | planned | Issue #42 | Conventional Kv transform. |
| `Rp_transform_basic` | planned | Issue #42 | Product-resistance transform. |
| `KBB_transform_basic` | planned | Issue #46 | RF fitting transform. |
| `KBB_transform_bounded` | planned | Issue #46 | RF bounded transform. |
| `obj_expT` | planned | Issue #41 | Temperature/end-time objective. |
| `err_expT` | planned | Issue #41 | Residual vector for SciPy least squares. |
| `err_expT!` | intentionally unsupported | Python residual functions return arrays | Julia mutating API is not a Python public API target. |
| `num_errs` | planned | Issue #41 | Residual-count helper. |
| `nls_pd` | planned | Issues #42, #46 | SciPy least-squares wrappers. |
| `nls_pd!` | intentionally unsupported | Python fitting functions return results | Julia mutating API is not a Python public API target. |
| `qrf_integrate` | planned | Issue #45 | RF heat-term integration helper. |
| `identify_pd_end` | planned | Issue #44 | Pirani-based end-of-primary-drying detection. |
| `get_vial_radii` | planned | Issue #39 | SCHOTT vial metadata utility. |
| `get_vial_mass` | planned | Issue #39 | SCHOTT vial metadata utility. |
| `get_vial_shape` | planned | Issue #39 | SCHOTT vial shape utility. |
| `make_outlines` | planned | Issue #39 | Vial/fill outline utility. |
| `ECCURT` | planned | Issue #47 | Equipment-capability interpolation module. |

## Non-Exported Julia Helpers

These helpers are not public exports from Julia `LyoPronto.jl`, but they are
tracked here because downstream typed APIs depend on them.

| Julia helper | Python status | Python location | Notes |
| --- | --- | --- | --- |
| `physical_properties.jl` constants | ported | `lyopronto.physical_properties` | Unitful constants are represented as Pint quantities. |
| `calc_psub` | ported | `lyopronto.physical_properties.calc_psub` | Plain floats use kelvin and pascal; Pint inputs are converted. |
| `calc_Tsub` | ported | `lyopronto.physical_properties.calc_tsub` | Python also provides `calc_Tsub` as an alias. |
| `eppf` dielectric helper | ported | `lyopronto.physical_properties.eppf` | Ice dielectric-loss correlation with Julia reference interpolation arrays. |
