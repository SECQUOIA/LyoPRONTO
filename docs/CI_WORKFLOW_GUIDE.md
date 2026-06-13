# CI Workflow Guide

## Overview

LyoPRONTO uses explicit pytest marker lanes instead of a single ambiguous test
suite. The workflows are designed around five lanes:

1. Fast PR feedback
2. Full non-Pyomo validation
3. Manual slow non-Pyomo validation
4. Explicit notebook validation
5. Manual optional Pyomo validation

The marker policy and local commands are also documented in `tests/README.md`.

## Workflows

### `.github/workflows/pr-tests.yml`

Runs on pull requests targeting `main`.

- `fast-scipy` runs on every PR update:
  `pytest tests/ -n auto -v -m "not slow and not notebook and not pyomo"`
- `full-non-pyomo` runs only for ready/non-draft PRs:
  `pytest tests/ -n auto -v -m "not pyomo" --cov=lyopronto --cov-report=xml:coverage.xml --cov-report=term-missing`

### `.github/workflows/tests.yml`

Runs on pushes to `main`.

- `full-non-pyomo` runs the main confidence gate:
  `pytest tests/ -n auto -v -m "not pyomo" --cov=lyopronto --cov-report=xml:coverage.xml --cov-report=term-missing`

### `.github/workflows/rundocs.yml`

Runs notebook validation for ready/non-draft PRs, pushes to `main`, and manual
dispatch.

- `notebook-tests` runs:
  `pytest tests/ -n auto -v -m "notebook" --cov=lyopronto --cov-report=xml:coverage.xml --cov-report=term-missing`

### `.github/workflows/slow-tests.yml`

Manual dispatch workflow with three lane choices:

- `slow-non-pyomo`:
  `pytest tests/ -n auto -v -m "slow and not pyomo" --cov=lyopronto --cov-report=xml:coverage.xml --cov-report=term-missing`
- `full-non-pyomo`:
  `pytest tests/ -n auto -v -m "not pyomo" --cov=lyopronto --cov-report=xml:coverage.xml --cov-report=term-missing`
- `pyomo`:
  `pytest tests/ -n auto -v -m "pyomo" --cov=lyopronto --cov-report=xml:coverage.xml --cov-report=term-missing`

The Pyomo lane installs the optional Pyomo/IDAES stack and treats pytest exit
code 5 as a no-op because the repository does not currently track Pyomo tests.

## Local Equivalents

Use `run_local_ci.sh` to run the same commands locally:

```bash
./run_local_ci.sh fast
./run_local_ci.sh full
./run_local_ci.sh slow
./run_local_ci.sh notebook
./run_local_ci.sh pyomo
```

Set `SKIP_INSTALL=1` when dependencies are already installed:

```bash
SKIP_INSTALL=1 ./run_local_ci.sh fast
```

## Expected Pull Request Flow

1. Open or update a PR: fast lane runs.
2. Convert the PR out of draft: full non-Pyomo lane runs with coverage.
3. Notebook lane runs separately for ready PRs.
4. Reviewers can request manual slow or Pyomo lanes when relevant.
5. Merge to `main`: full non-Pyomo lane runs again.

## Maintenance Notes

- Keep marker expressions synchronized between workflows, `run_local_ci.sh`,
  and `tests/README.md`.
- Do not add Pyomo validation to automatic PR/main workflows until tracked
  Pyomo implementation and tests exist.
- Do not broaden fast PR deselection beyond `slow`, `notebook`, and `pyomo`
  without documenting the reason.
- Ruff formatting and linting are local checks documented in
  `CONTRIBUTING.md`; they are not active CI gates.
