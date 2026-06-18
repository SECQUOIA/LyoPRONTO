# LyoPRONTO Test Suite

This document describes the supported pytest markers, local commands, and CI
lanes for LyoPRONTO.

## Test Lanes

| Lane | Marker expression | Where it runs | Purpose |
| --- | --- | --- | --- |
| Fast PR | `not slow and not notebook and not pyomo` | Every PR update in `.github/workflows/pr-tests.yml` | Quick contributor feedback without solver-heavy, notebook, or future Pyomo tests. |
| Full non-Pyomo | `not pyomo` | Ready/non-draft PRs and pushes to `main` | Main confidence gate with coverage for the tracked SciPy implementation. |
| Slow non-Pyomo | `slow and not pyomo` | Manual validation workflow | Targeted optimizer-heavy validation. |
| Notebook | `notebook` | Explicit notebook workflow | Executes documentation notebooks separately from ordinary fast tests. |
| Pyomo | `pyomo` | Manual validation workflow | Optional future lane. No collected tests is treated as a no-op until tracked Pyomo tests exist. |

## Marker Policy

- `slow`: Long-running or optimizer-heavy tests. These are excluded from the
  fast PR lane and covered by full/manual validation.
- `notebook`: Papermill or Jupyter execution tests for documentation examples.
  Keep these in the explicit notebook lane.
- `pyomo`: Tests that require Pyomo, IPOPT, or the Pyomo optimization stack.
  There are currently no tracked Pyomo tests; the manual lane may no-op. Tests
  that need IPOPT should call `tests.pyomo_solver.require_pyomo_solver("ipopt")`
  so missing solver setup skips with an installation hint.
- `main`: Tests covering behavior that was historically reachable through
  `main.py` or the high-level API. This is a coverage label, not a CI lane.
- `serial`: Tests that must not run under xdist parallelism. Run them with
  `pytest -m serial -n 0`.

## Scientific Reference Scenarios

`tests/scientific_reference_scenarios.py` records the pinned scientific
reference cases used by `tests/test_scientific_references.py`. Each case names
its workflow category, input units, output units, expected summary values,
explicit tolerances, tolerance rationale, and provenance. These tests are
regression guards for future numerical refactors; they should not be updated
without documenting why the scientific reference changed.

## Running Tests Locally

Run static analysis before the pytest lanes when preparing a PR:

```bash
python -m ruff check lyopronto tests examples main.py
python -m mypy lyopronto
```

Ruff linting is enforced in CI with the narrow Pyflakes rule set in
`pyproject.toml`. mypy is advisory in CI while remaining project type errors
are fixed in staged follow-up work.

Use the local CI wrapper when you want the same commands used by GitHub Actions:

```bash
./run_local_ci.sh fast
./run_local_ci.sh full
./run_local_ci.sh slow
./run_local_ci.sh notebook
./run_local_ci.sh pyomo
```

The underlying pytest commands are:

```bash
pytest tests/ -n auto -v -m "not slow and not notebook and not pyomo"
pytest tests/ -n auto -v -m "not pyomo" --cov=lyopronto --cov-report=xml:coverage.xml --cov-report=term-missing
pytest tests/ -n auto -v -m "slow and not pyomo" --cov=lyopronto --cov-report=xml:coverage.xml --cov-report=term-missing
pytest tests/ -n auto -v -m "notebook" --cov=lyopronto --cov-report=xml:coverage.xml --cov-report=term-missing
pytest tests/ -n auto -v -m "pyomo" --cov=lyopronto --cov-report=xml:coverage.xml --cov-report=term-missing
```

## Optional Pyomo Setup

Default package installs and `.[dev]` do not include Pyomo, IDAES, or IPOPT.
Install the optional Pyomo test stack with:

```bash
python -m pip install -e ".[dev,pyomo]"
idaes get-extensions --extra petsc
```

If your local environment manages solvers with conda, install IPOPT there and
keep it on PATH:

```bash
conda install -c conda-forge ipopt
```

For quick debugging, it is still fine to run a single file or test directly:

```bash
pytest tests/test_functions.py -v
pytest tests/test_functions.py::TestClassName::test_case_name -v
```

## Warning Policy

The shared pytest configuration keeps warnings visible by default and does not
use `--disable-warnings`. Expected scientific or runtime warnings should be
asserted in the tests that intentionally exercise those paths, normally with
`pytest.warns` plus a message check. Do not add a global warning ignore for
`lyopronto` modules.

Only add `filterwarnings` entries for understood third-party noise, and scope
them as narrowly as possible by warning type, message, and module. Document the
reason when adding a new filter.

The current top warning sources audited for this policy are:

- `calc_unknownRp`: expected "No sublimation" warnings in experimental and
  short-series edge-case coverage tests.
- `design_space`: infeasible sublimation, too-low shelf temperature, and
  single-timestep completion warnings from edge-case coverage tests.
- `opt_Pch`: total-time-exceeded and narrow-pressure optimization failure
  warnings from optimizer edge-case coverage tests.
- `calc_knownRp`: low-temperature chamber-pressure feasibility warnings from
  edge-case calculator tests.

## CI Integration

- Static analysis runs in PR and main-branch workflows. Ruff linting is an
  enforced gate; mypy is advisory.
- `.github/workflows/pr-tests.yml` runs the fast lane for all PR updates and
  the full non-Pyomo lane with coverage once the PR is ready for review.
- `.github/workflows/tests.yml` runs the full non-Pyomo lane with coverage on
  pushes to `main`.
- `.github/workflows/rundocs.yml` runs notebook-marked tests as an explicit
  notebook lane for ready PRs, `main`, and manual dispatch.
- `.github/workflows/slow-tests.yml` provides manual `slow-non-pyomo`,
  `full-non-pyomo`, and `pyomo` lanes.
- Python version is read from `.github/ci-config/ci-versions.yml`.

## Best Practices

- Mark optimizer-heavy or long-running tests with `@pytest.mark.slow`.
- Mark papermill/Jupyter execution tests with `@pytest.mark.notebook`.
- Mark future Pyomo/IPOPT tests with `@pytest.mark.pyomo`.
- Mark tests that cannot run under xdist with `@pytest.mark.serial`.
- Do not use broad marker deselection to hide a failure. If a lane excludes a
  marker, document the reason in this file and in the workflow command.
- Keep test output and error messages clear and physically meaningful.
- Use fixtures and helper functions from `conftest.py` for consistency.
