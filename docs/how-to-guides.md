# User Guide

This page collects the maintained user workflows: install a checkout, run
examples, use the optional Pyomo prototypes, use the legacy compatibility path,
and validate a local change. For contributor CI policy and branch-protection
details, use `dev.md`.

The hosted web GUI and original video tutorial remain useful orientation:

- Web GUI: <http://lyopronto.geddes.rcac.purdue.edu>
- Video tutorial: <https://www.youtube.com/watch?v=DI-Gz0pBI0w>

## Set Up A Development Checkout

From the repository root:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e ".[dev]"
```

On Windows, activate the virtual environment with:

```bash
.venv\Scripts\activate
```

Verify the editable install:

```bash
python -c "import lyopronto; print(lyopronto.__version__)"
```

## Run Maintained Script Examples

From the repository root:

```bash
python -m pip install -e ".[dev]"
python examples/example_web_interface.py
python examples/example_optimizer.py
python examples/example_freezing.py
python examples/example_design_space.py
python examples/example_parameter_estimation.py
```

Outputs are written to `examples/outputs/`.

Legacy scripts are tracked under `examples/legacy/`, but new work should prefer
the maintained examples above. They are archival provenance rather than CI
execution targets; the original known/unknown-Rp workflows are maintained as
the tested notebooks below.

## Run The File-Oriented Compatibility Path

Edit `main.py` from the repository root, then run:

```bash
python main.py
```

That path uses `lyopronto.high_level` helpers to save inputs, CSV outputs, and
plots from the selected simulation mode.

## Run A Minimal Legacy API Simulation

```python
from lyopronto import calc_knownRp

vial = {"Av": 3.80, "Ap": 3.14, "Vfill": 2.0}
product = {"cSolid": 0.05, "R0": 1.4, "A1": 16.0, "A2": 0.0}
ht = {"KC": 2.75e-4, "KP": 8.93e-4, "KD": 0.46}
Pchamber = {"setpt": [0.15], "dt_setpt": [1800.0], "ramp_rate": 0.5}
Tshelf = {"init": -35.0, "setpt": [20.0], "dt_setpt": [1800.0], "ramp_rate": 1.0}

output = calc_knownRp.dry(vial, product, ht, Pchamber, Tshelf, dt=0.01)
print(f"Drying time: {output[-1, 0]:.2f} hr")
print(f"Final dried: {output[-1, 6]:.1f}%")
```

## Run Typed API Examples

```bash
python -m examples.typed_api_examples
```

These examples are also covered by `tests/test_typed_examples.py`.

## Run Optional Pyomo Optimization Examples

Pyomo support is optional. Default installs and `.[dev]` do not install Pyomo,
IDAES, or IPOPT. Install the optional Pyomo stack before importing
`lyopronto.pyomo_models` or running Pyomo examples:

```bash
python -m pip install -e ".[dev,pyomo]"
```

The maintained Pyomo example builds the three experimental optimization modes
without solving them:

```bash
python examples/example_pyomo_optimization.py
```

It constructs:

- pressure-only optimization with a fixed shelf-temperature profile;
- shelf-temperature-only optimization with a fixed chamber-pressure profile;
- joint pressure and shelf-temperature optimization.

Advanced Pyomo workflow builders are also available under
`lyopronto.pyomo_models`:

- `create_parameter_estimation_model` for optional Rp/Kv parameter-estimation
  scenarios, paired with `solve_parameter_estimation` and its
  `ParameterEstimationResult` diagnostics;
- `create_design_space_feasibility_model` and `create_design_space_grid_models`
  for fixed-control feasibility checks;
- `create_sensitivity_analysis_models` for local finite-difference
  perturbation studies around fixed controls;
- `create_robust_optimization_model` for scenario-based minimax optimization
  with shared pressure and/or shelf-temperature controls;
- `create_multivial_optimization_model` for optimization with explicit
  batch-capacity diagnostics built on the trajectory model's equipment
  capability constraint.

Model construction does not require IPOPT. Solver-backed runs require an NLP
solver such as IPOPT:

```bash
idaes get-extensions --extra petsc
```

The Pyomo APIs intentionally remain explicit under `lyopronto.pyomo_models`.
Use `lyopronto.opt_Pch`, `lyopronto.opt_Tsh`, and `lyopronto.opt_Pch_Tsh` for
the shipped SciPy optimizer workflows. For an equivalent simultaneous
completion-time problem, use `solve_dae_shelf_temperature_optimization` or
`solve_dae_chamber_pressure_optimization`, or use
`solve_dae_joint_optimization` to release both controls, and select either
`finite_difference` or `collocation`. The older fixed-horizon builders remain
available for validation and advanced workflow composition. A unified selector
is not provided while those formulations have different objectives and solver
requirements.

For an implementability diagnostic, the joint solver also accepts
`initial_pressure` [Torr], `initial_shelf_temperature` [degC],
`pressure_ramp_rate` [Torr/hr], and `shelf_temperature_ramp_rate` [degC/hr].
The fixed-horizon trajectory builder names the same per-hour quantities
`pch_ramp_rate` and `tsh_ramp_rate`; in contrast, legacy dictionary keys such
as `Tshelf["ramp_rate"]` are expressed in degC/min.
Ramp limits act between adjacent transcription nodes and require the matching
initial value. They are disabled by default so the exact rate-unlimited legacy
comparison remains available. This extension constrains control movement but
does not introduce thermal-capacitance dynamics.

### Validate paper policy selection with GDP

`examples/paper_gdp_validation.py` compares the published Srisuma--Braatz
results with two switching routes over the same SI-unit physical equations:
the continuous `paper_ocp` NLP classifies active constraints after the solve,
while `paper_gdp` selects each phase's policy from free GDP indicators. Install
GLPK in addition to the Pyomo/IPOPT setup above:

```bash
sudo apt-get install glpk-utils
python -m examples.paper_gdp_validation
```

Conda environments may use `conda install -c conda-forge glpk` instead. The
example records GDPopt RIC, GLPK, IPOPT, tolerances, and initialization in its
result metadata. It reports indicator-derived sequences, free switch times and
collocation intervals, trajectories, path feasibility, the solver endpoint,
and an extrapolation to the paper's `S = H` endpoint. Because IPOPT solves the
nonlinear subproblems locally, the result is not a global optimality
certificate. Agreement checks the GDP switching formulation independently;
it does not independently validate the shared physical equations.

### Compare the transient and pseudosteady frozen-region models

`examples/pseudosteady_limit_study.py` walks the paper-reference models from
their transient frozen-region PDE toward the pseudosteady formulation that the
production LyoPRONTO path uses. Scaling the frozen heat capacity by `f` scales
the layer's thermal inertia relative to conduction and the surface fluxes, so in
fixed coordinates `f rho Cp dT/dt|_z = k d2T/dz2 + Q` and `f -> 0` recovers the
pseudosteady balance.

The transformed right-hand side does not scale uniformly: the Landau
moving-coordinate term is kinematic and independent of the heat capacity, so
`f * rhs(scaled) = rhs(base) + (f - 1) * convection`. Setting `dS/dt = 0` makes
the relation exact, which the tests pin. For this vial the moving-front term is
about 1e-5 of the right-hand side, and the `f -> 0` limit is unaffected.

```bash
python -m examples.pseudosteady_limit_study
```

Each rung warm starts from the previous solution because cold starts fail below
`f = 1`. A rung that does not converge is recorded and ends that problem's
ladder, since where the ladder stops is part of the result.

The same ladder serves as a solver-comparison instance set. `--solver-executable`
selects the NLP binary without changing model code, for any solver following the
AMPL `<solver> <stub> -AMPL` convention:

```bash
python -m examples.pseudosteady_limit_study --solver-executable /path/to/pounce
```

The study records the termination condition, solver status, and solver message
for every rung including the one that stops the ladder, because solvers differ
in what they call success: a result accepted at an acceptable-level tolerance
and one converged to full tolerance both arrive as `optimal` through Pyomo, and
only the message separates them (see issue #142).

Feasibility is judged from `max_constraint_violation`, which covers every active
constraint and every variable bound. The companion
`ode_residual_times_thickness_squared_K_m2` is a diagnostic for how much of that
number is the Landau transform rather than solution quality; it is dimensionful
and covers one constraint family, so it carries no verdict of its own.

Configuration and execution failures, such as a missing solver binary, propagate
rather than being recorded as a non-converged rung, so a broken run produces no
baseline. Recorded baselines and regeneration instructions are in
`benchmarks/README.md`.

## Run Notebook Examples

The MkDocs notebook examples are tracked under `docs/examples/`:

- [known Rp: original SciPy calculation and fixed-horizon Pyomo replay](examples/knownRp_PD.ipynb)
- [unknown Rp: shared legacy preprocessing with SciPy/Pyomo fitting](examples/unknownRp_PD.ipynb)
- [SciPy and Pyomo on the LyoPRONTO paper optimizer cases](examples/current_main_joint_optimizer_comparison.ipynb)
- [Replicating the Srisuma and Braatz optimal-control cases](examples/paper_optimal_control_replication.ipynb)
- [How the DAE optimizer is built and checked](examples/dae_optimizer_walkthrough.ipynb)

The first two notebooks import canonical computation from
`examples/original_workflow_parity.py`; `docs/examples/` owns only narrative,
comparison checks, plots, and committed rendered results. They retain the
original temperature, chamber-pressure/sublimation-flux, percent-dried, and
product-resistance diagnostics while adding SciPy/Pyomo overlays. They also
report single-run, environment-dependent wall times with shared preprocessing,
model construction, and solver work separated; these diagnostics are not
formal benchmarks. The known-Rp Pyomo
path uses a 6.5 hr backward-Euler horizon and a 95% terminal target. The
unknown-Rp Pyomo path is hybrid: the legacy calculator infers `(Lck, Rp)` from
measured `Tbot(t)`, then Pyomo fits `R0`, `A1`, and `A2`. It is not a direct
Pyomo inverse-temperature model.

Notebook execution is validated through the explicit notebook CI lane. When
Pyomo or IPOPT is absent, the original-workflow notebooks still execute the
SciPy path and print the installation command for the optional comparison.
Their full parity checks also run in the Pyomo solver lane.
The optimizer-comparison, optimal-control replication, and DAE walkthrough
notebooks require `.[dev,pyomo]` and IPOPT, so their solver-backed smoke
executions also run in the Pyomo solver lane.
The former shelf-only and pressure-only comparisons remain solver-backed
regression fixtures under `tests/`, rather than separate reader-facing tutorials.

## Run Local Validation

```bash
python -m ruff check lyopronto tests examples main.py
pytest tests/ -n auto -v -m "not slow and not notebook and not pyomo"
```

Use `./run_local_ci.sh fast`, `full`, `slow`, `notebook`, `pyomo-light`, or
`pyomo` to run the CI-equivalent wrappers. See `dev.md` for lane commands and
`../tests/README.md` for marker details.

## Interpret Legacy Hold Times

For legacy process dictionaries, temperature or pressure hold times set with
the `dt_setpt` key include ramp time. This applies to `Tshelf` and `Pchamber`
dictionaries.

## Build Documentation

```bash
python -m pip install -e ".[docs]"
mkdocs build
mkdocs serve
```
