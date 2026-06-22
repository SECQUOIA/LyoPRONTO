# Example Outputs

Example scripts write generated CSV and plot files here during local
development. The directory is tracked only through this README and `.gitkeep`;
generated outputs are ignored by git and should not be committed.

Common generated patterns:

- `lyopronto_primary_drying_*.csv`
- `lyopronto_design_space_*.csv`
- `lyopronto_freezing_*.csv`
- `lyopronto_parameter_estimation_*.csv`
- `lyopronto_optimizer_*.csv`
- `*_results.png`

Run examples from the repository root:

```bash
python examples/example_web_interface.py
python examples/example_design_space.py
python examples/example_freezing.py
python examples/example_parameter_estimation.py
python examples/example_optimizer.py
```

Tests run examples in temporary directories, so the test suite should not leave
files here. If this directory contains generated files, inspect them before
removing them and keep only `README.md` and `.gitkeep` in commits.
