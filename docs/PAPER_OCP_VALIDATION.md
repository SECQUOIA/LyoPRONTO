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

The current supported validation target is the paper-reported behavior rather
than an exact upstream trajectory artifact: Policy 1 -> Policy 2, a switch time
near 2.4 h, path-constraint satisfaction, and a first-pass drying-time target
near 6.2 h. The default solve uses a coarse validated spatial mesh (`n_z=5`)
with a near-complete terminal drying fraction. The refined `n_z=20` spatial
mesh now also terminates cleanly with IPOPT when using the documented acceptable
NLP tolerance (`acceptable_tol=1e-3`, `acceptable_iter=5`). The trajectory-level
checks remain tight: terminal drying within `1e-7 m`, product-temperature
violation within `2e-6 K`, drying time near 6.19 h, and switch time near 2.4 h.

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

`benchmarks/paper_problem1_reference.py` provides best-effort diagnostic tooling
for the upstream reference-generation path tracked in #27. It keeps the upstream
clone read-only: it writes temporary MATLAB wrappers for `SimPy_MaxT` and
`SimPy_MaxFlux` that use the known upstream `Python/` folder instead of
`matlab.desktop.editor.getActiveFilename`, then runs `Sim_1stDrying_OCP` for
`Case2` and saves:

- `t`
- `T`
- `S`
- `Tb`
- `dSdt`
- `policy`
- `tsw`

This is an environment-dependent diagnostic path, not the primary validation
gate. The upstream `.mat` generation depends on an exact MATLAB/Python/GEKKO
solver stack compatible with the upstream repository. The paper reports MATLAB
R2024b, Python 3.10, GEKKO, and 64-bit Windows 11, but it does not pin the
GEKKO/APMonitor solver version. The generator may fail on modern MATLAB/Python
or GEKKO setups even when MATLAB Python can import GEKKO; use the paper-reported
scalar behavior above as the supported validation target unless a known-good
upstream reference artifact is available. A future `--matlab-python` option
could make interpreter selection easier, but it would not by itself address
GEKKO/APMonitor solver crashes.

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

## Future Work

Next steps are tracked in GitHub issues:

1. #27 - Pin or provide a known-good upstream MATLAB/Python/GEKKO environment or
   reference artifact for reproducible trajectory generation.
2. #28 - Prepare the first Paper Problem 1 validation PR.
3. #29 - Add Problem 2 with the interface-velocity constraint and expected
   Policy 3 -> Policy 1 -> Policy 2 sequence.
4. #30 - Compare the paper-reference transcription against LyoPRONTO's existing
   quasi-steady Pyomo and scipy optimizers.
5. #31 - If the benchmark is credible, add a LyoPRONTO-facing experimental
   policy API with the same rich result format.

#26 is addressed by the bottom-node temperature constraint alignment, the
smaller expression-based NLP for vapor pressure/resistance/flux/interface
velocity, constraint scaling, and the `n_z=20` slow validation test.
