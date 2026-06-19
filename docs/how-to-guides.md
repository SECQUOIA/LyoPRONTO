# How-to Guide

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
pytest tests/ -n auto -v -m "not slow and not notebook and not pyomo" --durations=25
```

See `tests/README.md` for marker details.
