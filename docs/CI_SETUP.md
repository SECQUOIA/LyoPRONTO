# Continuous Integration Setup

## Overview

LyoPRONTO uses GitHub Actions with explicit pytest marker lanes. The active CI
configuration is:

- Platform: Ubuntu latest
- Python: read from `.github/ci-config/ci-versions.yml`
- Dependency install: default lanes use `pip install -e ".[dev]"`; Pyomo lanes
  use `pip install -e ".[dev,pyomo]"`
- Coverage config: non-Pyomo coverage uses `.coveragerc.non-pyomo`
- Coverage upload: none; Codecov uploads are not configured

The detailed workflow behavior is documented in `docs/CI_WORKFLOW_GUIDE.md`.

## Workflows

| Workflow | Trigger | Lane |
| --- | --- | --- |
| `.github/workflows/pr-tests.yml` | Pull requests to `main` | Static analysis and fast PR lane for all PR updates |
| `.github/workflows/full-validation.yml` | Pull requests to `main`, nightly schedule, version tags, manual dispatch | Full non-Pyomo lane for validation-sensitive paths or `full-validation` label; scheduled/tag/manual full validation |
| `.github/workflows/tests.yml` | Pushes to `main` | Static analysis and full non-Pyomo lane |
| `.github/workflows/rundocs.yml` | Ready PRs, pushes to `main`, nightly schedule, version tags, manual dispatch | Notebook lane |
| `.github/workflows/pyomo-tests.yml` | PRs and pushes to `main` changing `lyopronto/pyomo_models/**` or `tests/test_pyomo_models/**`; manual dispatch | Required Pyomo no-solver lane plus optional non-blocking solver comparison |
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
./run_local_ci.sh pyomo-light
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
pytest tests/ -n auto -v -m "not pyomo" --cov=lyopronto --cov-config=.coveragerc.non-pyomo --cov-report=term-missing
pytest tests/ -n auto -v -m "slow and not pyomo" --cov=lyopronto --cov-config=.coveragerc.non-pyomo --cov-report=term-missing
pytest tests/ -n auto -v -m "notebook" --cov=lyopronto --cov-config=.coveragerc.non-pyomo --cov-report=term-missing
pytest tests/test_pyomo_models tests/test_pyomo_solver.py -n auto -v
pytest tests/ -n auto -v -m "pyomo" --cov=lyopronto --cov-report=term-missing
```

All pytest lanes inherit `--durations=25`, `--timeout=600`, and
`--timeout-method=thread` from the shared pytest configuration through
`pytest-timeout` from the `dev` extra, including Pyomo lanes that install
`.[dev,pyomo]`.

The automatic Pyomo lane installs optional Pyomo/IDAES dependencies without
IPOPT and relies on solver-backed tests to skip with installation hints. The
optional solver comparison lane and manual Pyomo lane install IPOPT extensions
when that deeper validation is needed.

Codecov uploads are not configured. Coverage remains visible in terminal
reports from the coverage lanes.

Do not configure the path-filtered Pyomo light job as a branch-protection
required status check. Non-Pyomo PRs do not trigger `.github/workflows/pyomo-tests.yml`,
so that check would never report for those PRs. If Pyomo status must become a
repository-wide required check, add an always-running gate job first.
Repository maintainers should require the `Full non-Pyomo validation` job in
branch protection. The Full Validation workflow is reportable on every PR; its
full lane runs only for ready PRs that touch validation-sensitive paths, PRs
labeled `full-validation`, nightly scheduled validation, manual dispatch, and
version tags.

## Optional Pyomo Setup

Normal runtime and development installs intentionally exclude Pyomo and IPOPT.
For Pyomo development, the automatic Pyomo lane, or the manual Pyomo lane,
install the optional stack with:

```bash
python -m pip install -e ".[dev,pyomo]"
idaes get-extensions --extra petsc
```

The same package extra is used by `./run_local_ci.sh pyomo-light`. Solver-backed
validation through `./run_local_ci.sh pyomo` and the optional CI comparison job
also installs IPOPT with `idaes get-extensions --extra petsc`. A conda-managed
local environment may instead install IPOPT with:

```bash
conda install -c conda-forge ipopt
```

Pyomo-marked tests that need IPOPT should use
`tests.pyomo_solver.require_pyomo_solver("ipopt")` so missing Pyomo or IPOPT
skips with a clear installation hint.

## Maintenance Checklist

- Keep marker expressions synchronized across workflows, `run_local_ci.sh`,
  `tests/README.md`, and this document.
- Keep automatic Pyomo coverage path-filtered to Pyomo code and tests so
  default non-Pyomo PRs do not install optional Pyomo dependencies.
- Keep `.coveragerc.non-pyomo` on SciPy-only coverage commands so optional
  Pyomo modules are not counted as unexecuted in non-Pyomo totals.
- Monitor the optional solver comparison logs when they run. The job is
  job-level non-blocking, so install failures and comparison failures do not
  fail the PR status.
- Keep notebook tests in the explicit notebook lane.
- Keep slow optimizer-heavy tests out of the fast PR lane.
- Ruff linting is enforced in CI with the narrow Pyflakes rule set configured
  in `pyproject.toml`.
- mypy is advisory in CI until the remaining real project type errors are fixed;
  do not add blanket package-wide ignores to silence those errors.
