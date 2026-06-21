# CI Workflow Guide

## Overview

LyoPRONTO uses explicit pytest marker lanes instead of a single ambiguous test
suite. The workflows are designed around seven lanes:

1. Static analysis
2. Fast PR feedback
3. Conditional full non-Pyomo validation
4. Manual slow non-Pyomo validation
5. Explicit notebook validation
6. Automatic Pyomo no-solver validation
7. Optional Pyomo solver comparison

The marker policy and local commands are also documented in `tests/README.md`.
Each pytest lane inherits `--durations=25`, `--timeout=600`, and
`--timeout-method=thread` from the shared pytest configuration.

## Workflows

### `.github/workflows/pr-tests.yml`

Runs on pull requests targeting `main`.

- `static-analysis` runs on every PR update:
  `python -m ruff check lyopronto tests examples main.py`
  and advisory `python -m mypy lyopronto`
- `fast-scipy` runs on every PR update:
  `pytest tests/ -n auto -v -m "not slow and not notebook and not pyomo"`

Ordinary PR feedback intentionally stops at these fast checks. Use the Full
Validation workflow for the expensive full lane.

### `.github/workflows/full-validation.yml`

Runs on pull requests targeting `main`, nightly schedule, version tags, and
manual dispatch. The `Validation scope` job keeps the workflow reportable on
all PRs; `Full non-Pyomo validation` skips quickly unless full validation is
required.

The full lane runs for:

- non-draft PRs labeled `full-validation`
- non-draft PRs changing validation-sensitive code, top-level tests and shared
  test helpers, examples, test data, or dependency metadata
- nightly scheduled validation
- version tags and manual dispatch

The full lane command is:

  `pytest tests/ -n auto -v -m "not pyomo" --cov=lyopronto --cov-config=.coveragerc.non-pyomo --cov-report=term-missing`

Because this marker expression selects all non-Pyomo tests, it includes the
slow-marked optimizer, fitting, and scientific reference checks. The notebook
workflow still runs separately so notebook status remains visible.

Repository maintainers should require the `Full non-Pyomo validation` job in
branch protection. The job reports success quickly when the validation policy
decides the full lane is not needed, so requiring it does not deadlock ordinary
PRs.

### `.github/workflows/tests.yml`

Runs on pushes to `main`.

- `static-analysis` runs the enforced Ruff lint gate:
  `python -m ruff check lyopronto tests examples main.py`
  and advisory `python -m mypy lyopronto`
- `full-non-pyomo` runs the main confidence gate:
  `pytest tests/ -n auto -v -m "not pyomo" --cov=lyopronto --cov-config=.coveragerc.non-pyomo --cov-report=term-missing`

### `.github/workflows/rundocs.yml`

Runs notebook validation for ready/non-draft PRs, pushes to `main`, version
tags, nightly schedule, and manual dispatch.

- `notebook-tests` runs:
  `pytest tests/ -n auto -v -m "notebook" --cov=lyopronto --cov-config=.coveragerc.non-pyomo --cov-report=term-missing`

### `.github/workflows/slow-tests.yml`

Manual dispatch workflow with three lane choices:

- `slow-non-pyomo`:
  `pytest tests/ -n auto -v -m "slow and not pyomo" --cov=lyopronto --cov-config=.coveragerc.non-pyomo --cov-report=term-missing`
- `full-non-pyomo`:
  `pytest tests/ -n auto -v -m "not pyomo" --cov=lyopronto --cov-config=.coveragerc.non-pyomo --cov-report=term-missing`
- `pyomo`:
  `pytest tests/ -n auto -v -m "pyomo" --cov=lyopronto --cov-report=term-missing`

The Pyomo lane installs the optional Pyomo/IDAES stack and treats pytest exit
code 5 as a no-op for manual compatibility.

Non-Pyomo coverage commands use `.coveragerc.non-pyomo` so optional Pyomo
source files are not reported as 0% in SciPy-only lanes. Pyomo coverage uses
the default configuration in the optional Pyomo lane.

Codecov uploads are not configured. Coverage remains visible in terminal
reports from the Full Validation workflow, pushes to `main`, the notebook
workflow, and manual validation lanes.

### `.github/workflows/pyomo-tests.yml`

Runs when PRs or pushes to `main` change `lyopronto/pyomo_models/**` or
`tests/test_pyomo_models/**`, and can also be started manually.

- `pyomo-no-solver` installs `.[dev,pyomo]` without IPOPT and runs:
  `pytest tests/test_pyomo_models tests/test_pyomo_solver.py -n auto -v`
- `pyomo-solver-comparison` is non-blocking, attempts
  `idaes get-extensions --extra petsc`, and runs the Pyomo SciPy comparison
  tests when the optional solver stack installs.

The Pyomo workflow is path-filtered. Do not add `pyomo-no-solver` or
`pyomo-solver-comparison` as branch-protection required status checks while the
workflow uses `paths`, because they do not report on non-Pyomo PRs. If Pyomo
status must be required repository-wide, add an always-running gate job first.
The solver comparison job is job-level non-blocking; monitor its logs because
both install failures and comparison test failures leave the PR status green.

## Optional Pyomo Setup

Default installs and the normal development extra do not include Pyomo, IDAES,
or IPOPT. Use the Pyomo extra only when developing or validating Pyomo work:

```bash
python -m pip install -e ".[dev,pyomo]"
idaes get-extensions --extra petsc
```

The automatic Pyomo light workflow and `./run_local_ci.sh pyomo-light` use the
package extra without installing IPOPT. The optional solver comparison workflow
and `./run_local_ci.sh pyomo` also use the IDAES extension command. If you
manage solvers through conda instead, install IPOPT into the active environment
and ensure it is on PATH:

```bash
conda install -c conda-forge ipopt
```

Pyomo-marked tests that need IPOPT should call
`tests.pyomo_solver.require_pyomo_solver("ipopt")` before solving models. That
helper skips with these install hints when Pyomo or IPOPT is missing, instead of
failing later with an opaque solver error.

## Local Equivalents

Use `run_local_ci.sh` to run the same commands locally:

```bash
python -m ruff check lyopronto tests examples main.py
python -m mypy lyopronto
./run_local_ci.sh fast
./run_local_ci.sh full
./run_local_ci.sh slow
./run_local_ci.sh notebook
./run_local_ci.sh pyomo-light
./run_local_ci.sh pyomo
```

Set `SKIP_INSTALL=1` when dependencies are already installed:

```bash
SKIP_INSTALL=1 ./run_local_ci.sh fast
```

## Expected Pull Request Flow

1. Open or update a PR: static analysis and the fast lane run.
2. If the PR touches validation-sensitive code/tests or needs deeper evidence,
   the Full Validation workflow runs the full non-Pyomo lane automatically or
   through the `full-validation` label.
3. Notebook lane runs separately for ready PRs.
4. If the PR changes Pyomo model code or tests, the Pyomo light lane runs
   automatically; the optional solver comparison runs for ready PRs.
5. Reviewers can request manual slow, full, or Pyomo lanes when relevant.
6. Merge to `main`: static analysis and the full non-Pyomo lane run again, with
   Pyomo lanes also path-filtered on Pyomo changes.

## Maintenance Notes

- Keep marker expressions synchronized between workflows, `run_local_ci.sh`,
  and `tests/README.md`.
- Keep the Full Validation workflow's path list aligned with validation-
  sensitive modules and tests, and use the `full-validation` label for PRs that
  need deeper evidence without touching those paths.
- Keep automatic Pyomo validation isolated behind the Pyomo path filter so
  default non-Pyomo PRs do not install optional Pyomo dependencies.
- Do not configure path-filtered Pyomo jobs as branch-protection required status
  checks unless an always-running gate job is added.
- Do not broaden fast PR deselection beyond `slow`, `notebook`, and `pyomo`
  without documenting the reason.
- Ruff linting is enforced in CI with the narrow Pyflakes rule set configured
  in `pyproject.toml`.
- mypy is advisory in CI until the remaining real project type errors are fixed;
  do not add blanket package-wide ignores to silence those errors.
