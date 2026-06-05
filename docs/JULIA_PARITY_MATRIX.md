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
| `PrimaryDryFit` | ported | `lyopronto.typed.PrimaryDryFit` | Fitting-data container for product temperature, vial-wall temperature/endpoint, and drying end-time data. |
| `end_drying_callback` | partially ported | `lyopronto.pikal.solve_pikal` | Conventional Pikal terminal event is ported; RF remains planned in Issue #45. |
| `calc_u0` | partially ported | `lyopronto.pikal.calc_pikal_u0` | Pikal initial-state helper is ported; RF remains planned in Issue #45. |
| `get_tstops` | partially ported | `lyopronto.pikal.get_pikal_tstops` | Pikal extracts stops from ramped shelf and pressure controls; RF remains planned in Issue #45. |
| `lyo_1d_dae_f` | ported | `lyopronto.pikal.calc_md_q`, `lyopronto.pikal.solve_pikal` | Python solves the height ODE with the Pikal algebraic temperature balance through SciPy. |
| `ParamObjPikal` | ported | `lyopronto.pikal.PikalParams` | Typed Pikal parameter dataclass. |
| `RpEstimator` | planned | Issue #43 | Direct Rp estimation workflow. |
| `calc_hRp_T` | planned | Issue #43 | Direct Rp-vs-height estimate from temperature data. |
| `lumped_cap_rf!` | planned | Issue #45 | RF/microwave RHS. |
| `ParamObjRF` | planned | Issue #45 | Typed RF parameter dataclass. |
| `gen_sol_pd` | partially ported | `lyopronto.fitting.gen_sol_pd` | Conventional Pikal solution generator is ported; RF remains planned in Issue #46. |
| `obj_pd` | partially ported | `lyopronto.fitting.obj_pd` | Conventional Pikal scalar objective is ported; RF remains planned in Issue #46. |
| `gen_nsol_pd` | ported | `lyopronto.fitting.gen_nsol_pd` | Multi-experiment conventional Pikal fitting helper with shared/separate groups. |
| `objn_pd` | ported | `lyopronto.fitting.objn_pd` | Multi-experiment conventional Pikal scalar objective. |
| `KRp_transform_basic` | ported | `lyopronto.fitting.KRpTransform` | Conventional Kv/Rp log-space transform. |
| `K_transform_basic` | ported | `lyopronto.fitting.KTransform` | Conventional Kv transform. |
| `Rp_transform_basic` | ported | `lyopronto.fitting.RpTransform` | Product-resistance transform. |
| `KBB_transform_basic` | planned | Issue #46 | RF fitting transform. |
| `KBB_transform_bounded` | planned | Issue #46 | RF bounded transform. |
| `obj_expT` | ported | `lyopronto.fitting.obj_expT` | Temperature/end-time scalar objective. |
| `err_expT` | ported | `lyopronto.fitting.err_expT` | Residual vector for SciPy least squares. |
| `err_expT!` | intentionally unsupported | Python residual functions return arrays | Julia mutating API is not a Python public API target. |
| `num_errs` | ported | `lyopronto.fitting.num_errs` | Residual-count helper. |
| `nls_pd` | partially ported | `lyopronto.fitting.err_pd`, `lyopronto.fitting.errn_pd`, `lyopronto.fitting.fit_primary_drying` | Conventional Pikal residual wrappers and SciPy least-squares entry point are ported; RF remains planned in Issue #46. |
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
