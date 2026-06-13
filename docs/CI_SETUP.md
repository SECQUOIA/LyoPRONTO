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
| `.github/workflows/pr-tests.yml` | Pull requests to `main` | Fast PR lane for all PR updates; full non-Pyomo lane for ready/non-draft PRs |
| `.github/workflows/tests.yml` | Pushes to `main` | Full non-Pyomo lane |
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
pytest tests/ -n auto -v -m "not slow and not notebook and not pyomo"
pytest tests/ -n auto -v -m "not pyomo" --cov=lyopronto --cov-report=xml:coverage.xml --cov-report=term-missing
pytest tests/ -n auto -v -m "slow and not pyomo" --cov=lyopronto --cov-report=xml:coverage.xml --cov-report=term-missing
pytest tests/ -n auto -v -m "notebook" --cov=lyopronto --cov-report=xml:coverage.xml --cov-report=term-missing
pytest tests/ -n auto -v -m "pyomo" --cov=lyopronto --cov-report=xml:coverage.xml --cov-report=term-missing
```

The manual Pyomo lane installs optional Pyomo/IDAES dependencies and treats
pytest exit code 5 as a no-op until tracked Pyomo tests exist.

## Maintenance Checklist

- Keep marker expressions synchronized across workflows, `run_local_ci.sh`,
  `tests/README.md`, and this document.
- Do not add automatic Pyomo jobs until tracked Pyomo implementation/tests
  exist.
- Keep notebook tests in the explicit notebook lane.
- Keep slow optimizer-heavy tests out of the fast PR lane.
- Ruff formatting and linting are documented local checks in
  `CONTRIBUTING.md`; they are not active CI gates.
