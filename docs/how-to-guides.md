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
the maintained examples above.

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
  scenarios;
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

## Run Notebook Examples

The MkDocs notebook examples are tracked under `docs/examples/`:

- [known Rp](examples/knownRp_PD.ipynb)
- [unknown Rp](examples/unknownRp_PD.ipynb)
- [SciPy and Pyomo on the LyoPRONTO paper optimizer cases](examples/current_main_joint_optimizer_comparison.ipynb)
- [Replicating the Srisuma and Braatz optimal-control cases](examples/paper_optimal_control_replication.ipynb)

Notebook execution is validated through the explicit notebook CI lane.
The optimizer-comparison and optimal-control replication notebooks require
`.[dev,pyomo]` and IPOPT, so their solver-backed smoke executions also run in the
optional Pyomo comparison lane.
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
