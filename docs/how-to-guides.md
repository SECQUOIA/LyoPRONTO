# User Guide

This page collects the maintained user workflows: install a checkout, run
examples, use the legacy compatibility path, and validate a local change. For
contributor CI policy and branch-protection details, use `dev.md`.

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

## Run Notebook Examples

The MkDocs notebook examples are tracked under `docs/examples/`:

- [known Rp](examples/knownRp_PD.ipynb)
- [unknown Rp](examples/unknownRp_PD.ipynb)

Notebook execution is validated through the explicit notebook CI lane.

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
