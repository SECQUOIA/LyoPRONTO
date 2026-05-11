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
