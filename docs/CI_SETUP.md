# Continuous Integration Setup

## Overview

LyoPRONTO uses GitHub Actions with explicit pytest marker lanes. The active CI
configuration is:

- Platform: Ubuntu latest
- Python: read from `.github/ci-config/ci-versions.yml`
- Dependency install: `pip install -e ".[dev]"`
- Coverage upload: Codecov, non-blocking when configured

The detailed workflow behavior is documented in `docs/CI_WORKFLOW_GUIDE.md`.

## Workflows

| Workflow | Trigger | Lane |
| --- | --- | --- |
| `.github/workflows/pr-tests.yml` | Pull requests to `main` | Static analysis and fast PR lane for all PR updates; full non-Pyomo lane for ready/non-draft PRs |
| `.github/workflows/tests.yml` | Pushes to `main` | Static analysis and full non-Pyomo lane |
| `.github/workflows/rundocs.yml` | Ready PRs, pushes to `main`, manual dispatch | Notebook lane |
| `.github/workflows/slow-tests.yml` | Manual dispatch | Slow non-Pyomo, full non-Pyomo, or optional Pyomo lane |
| `.github/workflows/docs.yml` | Docs publish events | Documentation deployment |

## Local Setup

Install development dependencies from the project root:

```bash
python -m pip install --upgrade pip setuptools wheel
pip install -e ".[dev]"
```

Run CI-equivalent lanes locally with:

```bash
./run_local_ci.sh fast
./run_local_ci.sh full
./run_local_ci.sh slow
./run_local_ci.sh notebook
./run_local_ci.sh pyomo
```

Set `SKIP_INSTALL=1` to reuse an existing environment:

```bash
SKIP_INSTALL=1 ./run_local_ci.sh fast
```

## Lane Commands

```bash
python -m ruff check lyopronto tests examples main.py
python -m mypy lyopronto
pytest tests/ -n auto -v -m "not slow and not notebook and not pyomo"
pytest tests/ -n auto -v -m "not pyomo" --cov=lyopronto --cov-report=xml:coverage.xml --cov-report=term-missing
pytest tests/ -n auto -v -m "slow and not pyomo" --cov=lyopronto --cov-report=xml:coverage.xml --cov-report=term-missing
pytest tests/ -n auto -v -m "notebook" --cov=lyopronto --cov-report=xml:coverage.xml --cov-report=term-missing
pytest tests/ -n auto -v -m "pyomo" --cov=lyopronto --cov-report=xml:coverage.xml --cov-report=term-missing
```

The manual Pyomo lane installs optional Pyomo/IDAES dependencies and treats
pytest exit code 5 as a no-op until tracked Pyomo tests exist.

## Optional Pyomo Setup

Normal runtime and development installs intentionally exclude Pyomo and IPOPT.
For Pyomo development or the manual Pyomo lane, install the optional stack with:

```bash
python -m pip install -e ".[dev,pyomo]"
idaes get-extensions --extra petsc
```

The same setup is used by `./run_local_ci.sh pyomo` and the manual validation
workflow. A conda-managed local environment may instead install IPOPT with:

```bash
conda install -c conda-forge ipopt
```

Pyomo-marked tests that need IPOPT should use
`tests.pyomo_solver.require_pyomo_solver("ipopt")` so missing Pyomo or IPOPT
skips with a clear installation hint.

## Maintenance Checklist

- Keep marker expressions synchronized across workflows, `run_local_ci.sh`,
  `tests/README.md`, and this document.
- Do not add automatic Pyomo jobs until tracked Pyomo implementation/tests
  exist.
- Keep notebook tests in the explicit notebook lane.
- Keep slow optimizer-heavy tests out of the fast PR lane.
- Ruff linting is enforced in CI with the narrow Pyflakes rule set configured
  in `pyproject.toml`.
- mypy is advisory in CI until the remaining real project type errors are fixed;
  do not add blanket package-wide ignores to silence those errors.
