# LyoPRONTO

LyoPRONTO is an open-source Python package for vial-scale lyophilization
simulation and optimization. It models freezing and primary drying with heat
and mass transfer equations, SciPy-based solvers, legacy web-interface
compatibility helpers, and an additive typed Pint API.

A hosted web GUI is available at <http://lyopronto.geddes.rcac.purdue.edu>.
The original video tutorial remains available on
[LyoHUB's YouTube channel](https://youtu.be/DI-Gz0pBI0w).

## Install

From the repository root:

```bash
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e .
```

For development and tests:

```bash
python -m pip install -e ".[dev]"
```

For documentation builds:

```bash
python -m pip install -e ".[docs]"
```

For optional Pyomo development and manual Pyomo validation:

```bash
python -m pip install -e ".[dev,pyomo]"
idaes get-extensions --extra petsc
```

The package metadata supports Python 3.8 and newer. GitHub Actions reads its
active CI Python version from `.github/ci-config/ci-versions.yml`.

## Run Examples

The recommended executable examples live in `examples/`:

```bash
python examples/example_web_interface.py
python examples/example_optimizer.py
python examples/example_freezing.py
python examples/example_design_space.py
python examples/example_parameter_estimation.py
python -m examples.typed_api_examples
```

Generated CSV and plot outputs are written under `examples/outputs/` for the
modern examples. Historical scripts are preserved in `examples/legacy/` for
backward compatibility.

For the file-oriented legacy workflow, edit `main.py` from the repository root
and run:

```bash
python main.py
```

That path uses `lyopronto.high_level` helpers to save inputs, CSV outputs, and
plots from the selected simulation mode.

## Public APIs

LyoPRONTO currently exposes three supported API layers:

- Legacy dict APIs: `calc_knownRp`, `calc_unknownRp`, `freezing`,
  `design_space`, `opt_Pch`, `opt_Tsh`, `opt_Pch_Tsh`, `functions`, and
  `constant`.
- Typed Pint APIs: `typed`, `physical_properties`, `pikal`, `rf`, `fitting`,
  `cycle_time`, `eccurt`, and `vials`.
- High-level compatibility helpers: `read_inputs`, `save_inputs`,
  `execute_simulation`, `save_csv`, and `generate_visualizations`.
- Optional Pyomo prototypes: `lyopronto.pyomo_models.single_step` and
  `lyopronto.pyomo_models.trajectory`.

See `docs/ARCHITECTURE.md`, `docs/reference.md`, and
`docs/TYPED_API_GUIDE.md` for current module boundaries and unit conventions.
See `docs/PYOMO_STATUS.md` for optional Pyomo model status and trajectory
discretization notes.

## Tests and CI

Run static analysis and the fast PR lane locally with:

```bash
python -m ruff check lyopronto tests examples main.py
python -m mypy lyopronto
pytest tests/ -n auto -v -m "not slow and not notebook and not pyomo"
```

The full tracked validation lane is:

```bash
pytest tests/ -n auto -v -m "not pyomo" --cov=lyopronto --cov-config=.coveragerc.non-pyomo --cov-report=term-missing
```

`./run_local_ci.sh fast`, `./run_local_ci.sh full`,
`./run_local_ci.sh slow`, `./run_local_ci.sh notebook`,
`./run_local_ci.sh pyomo-light`, and `./run_local_ci.sh pyomo` mirror the
documented GitHub Actions lanes. Pyomo remains optional: the path-filtered
automatic Pyomo lane installs `.[dev,pyomo]` without IPOPT, while
solver-backed Pyomo validation stays optional.

All pytest lanes inherit `--durations=25`, `--timeout=600`, and
`--timeout-method=thread` from the shared pytest configuration through
`pytest-timeout` from the `dev` extra so hung tests fail clearly.

## Documentation

Build the documentation site with:

```bash
mkdocs build
```

For contributor orientation, start with:

- `docs/GETTING_STARTED.md`
- `docs/ARCHITECTURE.md`
- `docs/CI_WORKFLOW_GUIDE.md`
- `tests/README.md`
- `examples/README.md`

## Citation

G. Shivkumar, P. S. Kazarin, A. D. Strongrich, and A. A. Alexeenko,
"LyoPRONTO: An Open-Source Lyophilization PRocess OptimizatioN TOol",
AAPS PharmSciTech (2019) 20: 328.

The paper is open access:
<https://link.springer.com/article/10.1208/s12249-019-1532-7>.

## Authors

Original authors: Gayathri Shivkumar, Petr S. Kazarin, and Alina A. Alexeenko.
Maintained and updated by Isaac S. Wheeler.

## Licensing

Copyright (C) 2019, Gayathri Shivkumar, Petr S. Kazarin, and Alina A.
Alexeenko.

This program is free software: you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later
version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY
WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A
PARTICULAR PURPOSE. See the GNU General Public License for more details.

By request, this software may also be distributed under the terms of the GNU
Lesser General Public License (LGPL); for permission, contact the authors or
maintainer.
