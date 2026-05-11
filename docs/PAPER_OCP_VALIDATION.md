# Paper OCP Validation Benchmark

This benchmark validates whether LyoPRONTO's Pyomo direct-transcription stack
can solve published lyophilization optimal-control problems. It is intentionally
experimental and separate from the production LyoPRONTO primary-drying APIs.

## Current Milestone

The first implemented target is Problem 1 from Srisuma and Braatz,
arXiv:2509.10826v1:

- primary drying only;
- moving-boundary one-dimensional frozen-region model;
- shelf temperature as the optimized control;
- objective: minimize drying time;
- constraints: product temperature at or below 243 K and shelf temperature
  between 228 K and 273 K;
- expected qualitative policy sequence: maximum heat input, then product
  temperature tracking.

The implementation lives in `lyopronto.pyomo_models.paper_ocp` and uses SI
units throughout. The Pyomo benchmark itself does not depend on GEKKO or
MATLAB. GEKKO is available in the repo-local Pixi environment for upstream
policy-segment verification.

Problem 2 is now available as a second paper-reference OCP:

- primary drying only, using the same moving-boundary model;
- shelf temperature as the optimized control;
- objective: minimize drying time;
- constraints: product temperature at or below 240 K, interface velocity at or
  below `2.8e-7 m/s`, and shelf temperature between 228 K and 260 K;
- expected qualitative policy sequence: interface-velocity tracking, maximum
  heat input, then product-temperature tracking.

## Validation Strategy

The benchmark has two layers:

- Fast tests validate parameter translation, equation helpers, model structure,
  collocation discretization, and policy classification.
- Slow tests run both a coarse IPOPT solve and the upstream spatial mesh
  (`n_z=20`) to verify feasibility, terminal drying, path-constraint
  satisfaction, and Policy 1 -> Policy 2 detection.

The IPOPT solve is initialized by default from a policy-based trajectory:
maximum shelf temperature until the product-temperature event, then an
algebraic Policy 2 trajectory that holds the bottom product temperature at the
limit. A MATLAB `.mat` trajectory exported from the upstream implementation can
also be loaded with `load_upstream_matlab_trajectory()` and passed to
`solve_paper_problem1(initialization=trajectory)`.

## Upstream Solve Strategy

The upstream implementation does not solve Problem 1 as a single generic OCP
NLP. It uses a hybrid active-policy procedure:

1. MATLAB integrates the physical primary-drying ODE with `ode15s`.
2. Event functions detect the first violated active constraint.
3. For Policy 1, the shelf temperature is fixed at `Tbmax`.
4. For Policy 2, a GEKKO DAE simulation solves for the algebraic shelf
   temperature profile that keeps the bottom product temperature at `Tmax`.
5. MATLAB re-simulates the physical ODE using that shelf profile until the next
   event or drying completion.

The GEKKO segment uses `IMODE=7`, `NODES=3`, and 30 time points for the
temperature-constrained segment. This is closer to an active-set DAE
decomposition than a one-shot free-final-time transcription.

The current default solve uses a coarse validated spatial mesh (`n_z=5`) with a
near-complete terminal drying fraction. It checks the paper's reported switch
time near 2.4 h and a first-pass drying-time target near 6.2 h. The refined
`n_z=20` spatial mesh now also terminates cleanly with IPOPT when using the
documented acceptable NLP tolerance (`acceptable_tol=1e-3`,
`acceptable_iter=5`). The trajectory-level checks remain tight: terminal drying
within `1e-7 m`, product-temperature violation within `2e-6 K`, drying time near
6.19 h, and switch time near 2.4 h.

As verification against the upstream reference implementation
(`PrakitrSrisuma/simDAE-optimalcontrol-lyo` commit
`5bcfece23128be7e5be51b73693dc6674223ccc6`), the MATLAB Policy 1 segment for
Problem 1 (`Case2`) was reproduced by running
`Code (Conference Version)/Simulations/Sim_1stDrying_OCP.m`. It detected the
product-temperature event at `2.363310733077 h`, which is what the policy
initializer checks against.

The upstream GEKKO Policy 2 script (`pyfun_MaxT.py`) was also executed through
`pixi run python` with inputs built from the paper config and the policy
initializer's switch state. The local Pixi environment resolved GEKKO `1.3.2`
and successfully solved a short temperature-constrained segment with a declining
shelf-temperature profile.

A longer GEKKO Policy 2 segment, initialized at the Problem 1 switch state and
run over the remaining Pyomo `n_z=20` drying time, gives the same shelf-control
shape as the direct-transcription result. At equal fractions of the Policy 2
segment, Pyomo shelf temperatures were within `0.26 K` at the switch and within
`0.11 K` after the first quarter of the segment. The Pyomo switch time was
`2.3946 h` versus the policy initializer's upstream event time of `2.3633 h`;
that offset explains the small interface-position differences in the GEKKO
segment comparison.

## Regenerating The Upstream Reference

Issue #27 is handled by `benchmarks/paper_problem1_reference.py`. The generator
keeps the upstream clone read-only: it writes temporary MATLAB wrappers for
`SimPy_MaxT` and `SimPy_MaxFlux` that use the known upstream `Python/` folder
instead of `matlab.desktop.editor.getActiveFilename`, then runs
`Sim_1stDrying_OCP` for `Case2` and saves:

- `t`
- `T`
- `S`
- `Tb`
- `dSdt`
- `policy`
- `tsw`

The MATLAB Python environment must be able to import GEKKO because the upstream
Policy 2 segment calls `pyfun_MaxT.py`.

```bash
python benchmarks/paper_problem1_reference.py generate \
  --upstream-root /home/bernalde/repos/simDAE-optimalcontrol-lyo \
  --output benchmarks/results/paper_problem1_upstream_reference.mat
```

Use `--runner-only --work-dir /tmp/lyopronto-paper-problem1` to inspect the
generated MATLAB files and exact `matlab -batch` command without running
MATLAB.

The exported artifact can seed the Pyomo solve and report Pyomo-vs-upstream
deviations for drying time, first switch time, terminal interface position, peak
temperature, and max-temperature profile:

```bash
python benchmarks/paper_problem1_reference.py compare-pyomo \
  benchmarks/results/paper_problem1_upstream_reference.mat \
  --n-z 20 --nfe 12 --ncp 3
```

## Mesh Diagnostics

All rows use `nfe=12`, `ncp=3`, `LAGRANGE-RADAU`, the policy initializer, and a
99.5% terminal drying target.

| Spatial nodes | IPOPT status | Drying time | Policy status |
| --- | --- | --- | --- |
| `n_z=5` | optimal | ~6.19 h | Policy 1 -> Policy 2 |
| `n_z=20` | optimal/acceptable | ~6.19 h | Policy 1 -> Policy 2 |

## Paper-vs-LyoPRONTO Baseline Comparison

Issue #30 compares the paper-reference direct transcription against current
LyoPRONTO baselines before adding any LyoPRONTO-facing policy OCP API. The
closest comparable LyoPRONTO case is the `Tsh` benchmark: shelf temperature is
optimized while chamber pressure is fixed. The committed baseline data were
generated with the current SciPy optimizer and quasi-steady Pyomo FD/collocation
optimizers over the `baseline` 3x3 grid:

```bash
python benchmarks/grid_cli.py generate \
  --task Tsh --scenario baseline \
  --vary product.A1=16,18,20 \
  --vary ht.KC=2.75e-4,3.3e-4,4.0e-4 \
  --methods scipy,fd,colloc \
  --n-elements 24 --n-collocation 3 \
  --out benchmarks/results/baseline_Tsh_3x3_summary.jsonl
```

`Pch` data in `benchmarks/results/baseline_Pch_3x3_summary.jsonl` were also
checked as a non-comparable optimizer sanity run. They use chamber pressure as
the manipulated variable with a fixed shelf profile, so they should not be used
as a paper OCP comparison point. Their drying-time ranges were 18.12-23.67 h
for SciPy, 18.15-23.71 h for Pyomo FD, and 17.90-23.37 h for Pyomo collocation.

| Model/case | Comparable scope | Drying time | Active constraints/control behavior | Temperature behavior | Interpretation |
| --- | --- | --- | --- | --- | --- |
| Paper Problem 1 direct transcription | Shelf-only OCP, fixed chamber pressure, SI/Kelvin moving-boundary model | ~6.19 h | Policy 1 max heat input, then Policy 2 product-temperature tracking near 2.4 h | Max product temperature tracks 243 K after the switch; shelf temperature backs away from 273 K | Useful validation target for direct transcription and policy classification, but not a drop-in LyoPRONTO baseline |
| LyoPRONTO `Tsh` SciPy baseline | Shelf-only quasi-steady optimizer, fixed 0.1 Torr chamber pressure, cm/Torr/degC model | 12.19-14.47 h across the 3x3 grid; mean 13.33 h | Shelf profile optimizer with product-temperature limit as the active path constraint | Bottom product temperature tracks -25 degC at the constraint | Closest current control-space comparison; drying-time gap is dominated by formulation, units, scenario, and constraint differences |
| LyoPRONTO `Tsh` Pyomo FD | Same quasi-steady benchmark as SciPy, finite-difference transcription, 24 elements | 12.40-14.76 h; mean 13.58 h | Same active product-temperature constraint; no warm start in committed grid | Tracks the same -25 degC limit with 98.9% terminal drying target | Matches the SciPy baseline closely enough for LyoPRONTO regression use, but does not exercise paper Policy 3/Policy 2 structure |
| LyoPRONTO `Tsh` Pyomo collocation | Same quasi-steady benchmark as SciPy, collocation with effective mesh parity | 12.00-14.23 h; mean 13.11 h | Same active product-temperature constraint on a collocation mesh | Tracks the same -25 degC limit with small objective shifts versus SciPy | Confirms transcription effects are modest inside the LyoPRONTO model, separate from paper-vs-LyoPRONTO physics differences |
| Paper Problem 2 direct transcription | Shelf-only OCP with an interface-velocity path constraint | ~8.9 h first-pass coarse validation | Policy 3 interface-velocity tracking, then Policy 1 max heat input, then Policy 2 temperature tracking | Product temperature stays below 240 K after the velocity-limited phase | No current LyoPRONTO optimizer is directly comparable because the public quasi-steady APIs do not expose a flux or interface-velocity cap |

Recommendation: keep the paper-reference model validation-only and adapt the
policy constraints into LyoPRONTO instead of exposing the SI/Kelvin paper model
as a public optimizer. The paper model should remain in
`lyopronto.pyomo_models.paper_ocp` for upstream validation, convergence checks,
and policy-classification tests. The LyoPRONTO-facing work should proceed
through #31, which already converts the adapter requirements into an
implementation issue: add an optional flux/interface-velocity cap in LyoPRONTO
units, reuse the existing quasi-steady Pyomo optimizer infrastructure, return a
rich result object, classify active policies from LyoPRONTO trajectories, and
avoid changing existing SciPy or Pyomo optimizer behavior.

## Problem 2 First-Pass Tolerances

The Problem 2 validation is intentionally coarse at this stage. The paper
reports switch times near 2.0 h and 3.9 h, with drying complete around 8.9 h.
The slow test therefore accepts broad first-pass tolerances on the coarse
`n_z=5`, `nfe=12`, `ncp=3` mesh:

- terminal interface gap at or below `1e-7 m`;
- product-temperature violation at or below `1e-3 K`;
- post-initial interface-velocity violation at or below `5e-10 m/s`;
- shelf-temperature bound violations at or below `1e-6 K`;
- drying time within `0.7 h` of the paper value;
- first two policy switches within `0.8 h` of the paper values.

The velocity constraint is skipped at the initial collocation point because the
paper explicitly reports an initial velocity excursion before Policy 3 quickly
brings `dS/dt` to its setpoint. Metrics still report the initial velocity
separately, while path-constraint checks use the post-initial trajectory.

Known limitations:

- The Problem 2 initializer is a deterministic policy-sequenced warm start, not
  a full reproduction of the upstream high-index GEKKO Policy 3 solve.
- The first validated solve is coarse. A refined `n_z=20` Problem 2 solve and a
  MATLAB/GEKKO upstream export should be added once the upstream reference
  tooling is extended beyond Problem 1.

## Future Work

Next steps are tracked in GitHub issues:

1. #28 - Prepare the first Paper Problem 1 validation PR.
2. #30 - Compare the paper-reference transcription against LyoPRONTO's existing
   quasi-steady Pyomo and scipy optimizers.
3. #31 - If the benchmark is credible, add a LyoPRONTO-facing experimental
   policy API with the same rich result format.

#26 is addressed by the bottom-node temperature constraint alignment, the
smaller expression-based NLP for vapor pressure/resistance/flux/interface
velocity, constraint scaling, and the `n_z=20` slow validation test.

#29 is addressed by the Problem 2 config defaults, velocity path constraint,
Policy 3 classifier support, policy-sequenced initializer, coarse slow solve,
and first-pass tolerance documentation.
