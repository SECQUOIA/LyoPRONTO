# LyoPRONTO Examples

This directory contains maintained scripts that exercise the supported
dictionary-style workflows, the typed Pint API, and the optional Pyomo
optimization prototypes.

## Maintained Scripts

| Script | Purpose | Output |
| --- | --- | --- |
| `example_web_interface.py` | Primary drying with known product resistance, matching the web-interface style. | CSV and `primary_drying_results.png` under `examples/outputs/`. |
| `example_optimizer.py` | Shelf-temperature optimization at fixed chamber pressure. | CSV under `examples/outputs/`. |
| `example_freezing.py` | Freezing-phase simulation. | CSV under `examples/outputs/`. |
| `example_design_space.py` | Design-space sections for shelf temperature, product temperature, and equipment capability. | CSV under `examples/outputs/`. |
| `example_parameter_estimation.py` | Product-resistance estimation from temperature data. | CSV and `parameter_estimation_results.png` under `examples/outputs/`. |
| `typed_api_examples.py` | Typed Pint API examples for simulation, fitting, RF, vial utilities, ECCURT, and Pirani endpoint detection. | Console smoke output. |
| `example_pyomo_optimization.py` | Optional Pyomo construction example for pressure-only, shelf-temperature-only, and joint optimization modes. | Console model summaries. |

Run examples from the repository root:

```bash
python -m pip install -e ".[dev]"
python examples/example_web_interface.py
python examples/example_optimizer.py
python examples/example_freezing.py
python examples/example_design_space.py
python examples/example_parameter_estimation.py
python -m examples.typed_api_examples
```

The maintained examples use reference-style inputs from `test_data/` where
needed and write local outputs to `examples/outputs/`. Generated outputs are
ignored by git.

Run the optional Pyomo example only after installing the Pyomo extra:

```bash
python -m pip install -e ".[dev,pyomo]"
python examples/example_pyomo_optimization.py
```

The Pyomo example builds models without solving them, so it does not require
IPOPT. Solver-backed Pyomo comparisons are covered separately by the optional
Pyomo validation lane.

## Legacy Scripts

`examples/legacy/` contains the original standalone scripts:

- `ex_knownRp_PD.py`
- `ex_unknownRp_PD.py`

They are retained for backward compatibility and smoke-tested by
`tests/test_example_scripts.py`. New examples should follow the maintained
scripts in this directory instead.

## Adding Examples

- Name new scripts `example_<topic>.py`.
- Keep input values explicit and physically meaningful.
- Add a module docstring with purpose, usage, and output summary.
- Write outputs under `examples/outputs/`.
- Add focused smoke or regression coverage under `tests/`.
- Update this README only with a concise row in the maintained scripts table.

## References

- `docs/how-to-guides.md`: setup, examples, notebooks, and local validation.
- `docs/reference.md`: API boundaries and unit conventions.
- `tests/README.md`: test lanes and marker policy.
- `examples/outputs/README.md`: generated-output policy.
- `AGENTS.md`: coding-agent guidance.
