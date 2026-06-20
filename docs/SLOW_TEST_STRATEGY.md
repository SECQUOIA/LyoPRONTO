# Test Lane Strategy

## Purpose

LyoPRONTO separates fast feedback from expensive validation with pytest
markers. The active lanes are documented in `tests/README.md` and mirrored by
GitHub Actions plus `run_local_ci.sh`.

## Lanes

### Fast PR Lane

- **Workflow:** `.github/workflows/pr-tests.yml`
- **Trigger:** Every pull request update
- **Command:** `pytest tests/ -n auto -v -m "not slow and not notebook and not pyomo"`
- **Purpose:** Keep ordinary PR feedback focused on tracked, non-notebook SciPy
  behavior.

### Full Non-Pyomo Lane

- **Workflows:** `.github/workflows/pr-tests.yml`,
  `.github/workflows/tests.yml`
- **Trigger:** Ready/non-draft PRs and pushes to `main`
- **Command:** `pytest tests/ -n auto -v -m "not pyomo" --cov=lyopronto --cov-report=xml:coverage.xml --cov-report=term-missing`
- **Purpose:** Main confidence gate for tracked behavior while Pyomo remains an
  implemented optional stack.

### Slow Non-Pyomo Lane

- **Workflow:** `.github/workflows/slow-tests.yml`
- **Trigger:** Manual workflow dispatch
- **Command:** `pytest tests/ -n auto -v -m "slow and not pyomo" --cov=lyopronto --cov-report=xml:coverage.xml --cov-report=term-missing`
- **Purpose:** Targeted optimizer-heavy validation when a change touches slow
  scientific paths or when a reviewer wants focused evidence.

### Notebook Lane

- **Workflow:** `.github/workflows/rundocs.yml`
- **Trigger:** Ready/non-draft PRs, pushes to `main`, or manual dispatch
- **Command:** `pytest tests/ -n auto -v -m "notebook" --cov=lyopronto --cov-report=xml:coverage.xml --cov-report=term-missing`
- **Purpose:** Execute documentation notebooks separately from ordinary fast
  tests.

### Pyomo Light Lane

- **Workflow:** `.github/workflows/pyomo-tests.yml`
- **Trigger:** Pull requests and pushes to `main` that change
  `lyopronto/pyomo_models/**` or `tests/test_pyomo_models/**`
- **Command:** `pytest tests/test_pyomo_models tests/test_pyomo_solver.py -n auto -v`
- **Purpose:** Required import, model-construction, and missing-solver skip
  validation while keeping Pyomo out of default non-Pyomo PR lanes.

### Pyomo Solver Lane

- **Workflows:** `.github/workflows/pyomo-tests.yml`,
  `.github/workflows/slow-tests.yml`
- **Trigger:** Optional non-blocking path-filtered comparison job or manual
  workflow dispatch
- **Command:** `pytest tests/ -n auto -v -m "pyomo" --cov=lyopronto --cov-report=xml:coverage.xml --cov-report=term-missing`
- **Purpose:** Solver-backed Pyomo/IPOPT validation when the optional solver
  stack is available.

## Marker Policy

- `slow`: Long-running or optimizer-heavy tests excluded from the fast PR lane.
- `notebook`: Papermill/Jupyter tests for documentation examples.
- `pyomo`: Implemented optional Pyomo model and solver tests.
- `main`: Legacy `main.py` and high-level API behavior coverage.
- `serial`: Tests that must be run without xdist, using `pytest -m serial -n 0`.

All lanes inherit `--durations=25`, `--timeout=600`, and
`--timeout-method=thread` from `pyproject.toml`.

## Local Usage

```bash
./run_local_ci.sh fast
./run_local_ci.sh full
./run_local_ci.sh slow
./run_local_ci.sh notebook
./run_local_ci.sh pyomo-light
./run_local_ci.sh pyomo
```

Use the fast lane before pushing routine changes. Use the full lane before
marking a PR ready for review when practical. Use the slow or notebook lanes
when the changed files make those paths relevant.
