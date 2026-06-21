# Getting Started

This guide is for contributors working from a local checkout. For the shortest
user-facing path, see the root `README.md` and `examples/README.md`.

## Set Up

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

## Run Working Examples

Start with the web-interface parity example or the typed API smoke examples:

```bash
python examples/example_web_interface.py
python -m examples.typed_api_examples
```

Other maintained examples:

```bash
python examples/example_optimizer.py
python examples/example_freezing.py
python examples/example_design_space.py
python examples/example_parameter_estimation.py
```

Legacy scripts are still tracked under `examples/legacy/`, but new work should
prefer the maintained examples above.

## Run Checks

Use the same lane commands that CI documents:

```bash
python -m ruff check lyopronto tests examples main.py
python -m mypy lyopronto
pytest tests/ -n auto -v -m "not slow and not notebook and not pyomo"
```

Before marking a validation-sensitive PR ready when practical:

```bash
pytest tests/ -n auto -v -m "not pyomo" --cov=lyopronto --cov-config=.coveragerc.non-pyomo --cov-report=term-missing
```

The wrapper script mirrors CI lanes:

```bash
./run_local_ci.sh fast
./run_local_ci.sh full
./run_local_ci.sh slow
./run_local_ci.sh notebook
./run_local_ci.sh pyomo-light
./run_local_ci.sh pyomo
```

The Pyomo light lane mirrors the automatic path-filtered CI job for Pyomo model
and test changes. Solver-backed Pyomo validation remains optional. See
`tests/README.md` and `docs/CI_WORKFLOW_GUIDE.md` for the current marker policy
and workflow triggers.

## Build Documentation

Install docs dependencies and build:

```bash
python -m pip install -e ".[docs]"
mkdocs build
```

For a local preview:

```bash
mkdocs serve
```

## Current Code Map

Core legacy modules:

- `lyopronto/functions.py`: physics equations and ramp interpolation helpers.
- `lyopronto/constant.py`: physical constants and unit conversions.
- `lyopronto/calc_knownRp.py`: primary drying with known product resistance.
- `lyopronto/calc_unknownRp.py`: resistance estimation from temperature data.
- `lyopronto/freezing.py`: freezing-phase calculations.
- `lyopronto/design_space.py`: design-space calculations.
- `lyopronto/opt_Pch.py`, `lyopronto/opt_Tsh.py`,
  `lyopronto/opt_Pch_Tsh.py`: SciPy-based optimization modes.

Current additive API modules:

- `lyopronto/typed.py`: Pint-aware data helpers.
- `lyopronto/physical_properties.py`, `pikal.py`, `rf.py`, `fitting.py`,
  `cycle_time.py`, `eccurt.py`, and `vials.py`: typed workflows and
  Julia-parity utilities.
- `lyopronto/high_level.py`: file-oriented compatibility helpers used by
  `main.py`.

`import lyopronto` is intentionally lightweight. Submodules and selected
compatibility helpers are loaded lazily when accessed.

## Minimal Legacy Simulation

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

Legacy output columns are:

1. time in hours
2. sublimation front temperature in degC
3. vial bottom temperature in degC
4. shelf temperature in degC
5. chamber pressure in mTorr
6. sublimation flux in kg/hr/m^2
7. percent dried from 0 to 100

## Development Notes

- Keep code behavior changes separate from documentation-only PRs.
- Add or update tests for behavior changes.
- Assert expected project warnings with `pytest.warns`; do not hide them with
  broad filters.
- Keep Pyomo references marked as planned unless tracked implementation and
  tests are present.
- Do not add stale completion reports or old coverage/test-count snapshots to
  the documentation tree.

## Troubleshooting

### Import Errors

```bash
# Make sure package is installed in development mode
python -m pip install -e ".[dev]"

# Check Python path
python -c "import sys; print('\n'.join(sys.path))"
```

### Test Failures

```bash
# Re-run the fast lane with verbose output
pytest tests/ -n auto -v -m "not slow and not notebook and not pyomo"

# Check if issue is with one specific test
pytest tests/test_functions.py::TestVaporPressure -v
```

### Simulation Issues

```python
# Check intermediate values
print(f"Lpr0: {Lpr0:.4f} cm")
print(f"Rp: {Rp:.4f} cm^2-hr-Torr/g")
print(f"Kv: {Kv:.6f} cal/s/K/cm^2")

# Verify physical reasonableness
assert Lpr0 > 0, "Initial product length must be positive"
assert Rp > 0, "Product resistance must be positive"
```

## Resources

- Current test policy: `../tests/README.md`
- Current CI workflow guide: `CI_WORKFLOW_GUIDE.md`
- Current architecture: `ARCHITECTURE.md`
- Current examples: `../examples/README.md`
