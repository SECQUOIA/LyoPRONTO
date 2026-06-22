# Contributor Guide

This is the single contributor reference for LyoPRONTO setup, CI lanes,
documentation builds, and static checks. Keep GitHub workflows,
`run_local_ci.sh`, tests that assert CI policy, and this page synchronized.

For user-facing examples, see `how-to-guides.md`. For test-authoring rules,
marker details, warning policy, and scientific reference scenarios, see
`../tests/README.md`.

## Setup

Install development dependencies from the repository root:

```bash
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e ".[dev]"
```

Optional Pyomo work uses a separate extra so default development environments
stay non-Pyomo:

```bash
python -m pip install -e ".[dev,pyomo]"
idaes get-extensions --extra petsc
```

A conda-managed local environment may instead install IPOPT with:

```bash
conda install -c conda-forge ipopt
```

## Local Validation

Run static analysis and the fast PR lane before pushing:

```bash
python -m ruff check lyopronto tests examples main.py
python -m mypy lyopronto
./run_local_ci.sh fast
```

Ruff linting is enforced in CI with the scoped Pyflakes rule set in
`pyproject.toml`. mypy is advisory in CI while remaining project type issues
are handled in follow-up work.

Use `SKIP_INSTALL=1` to reuse an existing environment:

```bash
SKIP_INSTALL=1 ./run_local_ci.sh fast
```

Before marking a validation-sensitive PR ready for review, run the full
non-Pyomo lane when practical:

```bash
./run_local_ci.sh full
```

## CI Lane Reference

| Lane | Command | Workflow |
| --- | --- | --- |
| Static analysis | `python -m ruff check lyopronto tests examples main.py`; advisory `python -m mypy lyopronto` | `.github/workflows/pr-tests.yml`, `.github/workflows/tests.yml` |
| Fast PR | `pytest tests/ -n auto -v -m "not slow and not notebook and not pyomo"` | `.github/workflows/pr-tests.yml` |
| Full non-Pyomo | `pytest tests/ -n auto -v -m "not pyomo" --cov=lyopronto --cov-config=.coveragerc.non-pyomo --cov-report=term-missing` | `.github/workflows/full-validation.yml`, `.github/workflows/tests.yml`, `.github/workflows/slow-tests.yml` |
| Slow non-Pyomo | `pytest tests/ -n auto -v -m "slow and not pyomo" --cov=lyopronto --cov-config=.coveragerc.non-pyomo --cov-report=term-missing` | `.github/workflows/slow-tests.yml` |
| Notebook | `pytest tests/ -n auto -v -m "notebook" --cov=lyopronto --cov-config=.coveragerc.non-pyomo --cov-report=term-missing` | `.github/workflows/rundocs.yml` |
| Pyomo light | `pytest tests/test_pyomo_models tests/test_pyomo_solver.py -n auto -v` | `.github/workflows/pyomo-tests.yml`, `./run_local_ci.sh pyomo-light` |
| Pyomo solver | `pytest tests/ -n auto -v -m "pyomo" --cov=lyopronto --cov-report=term-missing` | `.github/workflows/pyomo-tests.yml`, `.github/workflows/slow-tests.yml` |

All pytest lanes inherit `--durations=25`, `--timeout=600`, and
`--timeout-method=thread` from `pyproject.toml`. Non-Pyomo coverage lanes use
`.coveragerc.non-pyomo` so optional Pyomo modules are omitted from SciPy-only
coverage totals. Codecov uploads are not configured; coverage remains visible
in terminal reports from the coverage lanes.

## Workflow Behavior

Pull requests targeting `main` always run static analysis and the fast PR lane.
The Full Validation workflow is reportable on every PR. Repository maintainers
should require the `Full non-Pyomo validation` job in branch protection because
the job reports success quickly when the validation policy decides the full
lane is not needed. The full lane runs for non-draft PRs that touch
validation-sensitive paths, PRs labeled `full-validation`, nightly scheduled
validation, manual dispatch, version tags, and pushes to `main`.

Notebook tests run in `.github/workflows/rundocs.yml` for ready PRs, pushes to
`main`, nightly schedule, version tags, and manual dispatch.

Pyomo model and test changes run `.github/workflows/pyomo-tests.yml`. The
`pyomo-no-solver` job installs `.[dev,pyomo]` without IPOPT and runs the Pyomo
light lane. The solver comparison job is job-level non-blocking; inspect its
logs when it runs because install failures and comparison failures leave the PR
status green.

Do not configure path-filtered Pyomo jobs as branch-protection required status checks
while `.github/workflows/pyomo-tests.yml` uses `paths`, because those jobs do
not report on non-Pyomo PRs. If Pyomo status must be required
repository-wide, add an always-running gate job first.

`.github/workflows/slow-tests.yml` is manual dispatch for focused slow
non-Pyomo, full non-Pyomo, or optional Pyomo validation.

## Pyomo Test Policy

Default installs and the `dev` extra intentionally exclude Pyomo, IDAES, and
IPOPT. Pyomo-marked tests that need IPOPT should call
`tests.pyomo_solver.require_pyomo_solver("ipopt")` before solving models. That
helper skips with installation hints when Pyomo or IPOPT is missing.

Keep automatic Pyomo validation isolated behind the Pyomo path filter so
default non-Pyomo PRs do not install optional dependencies.

## Documentation

Install documentation dependencies:

```bash
python -m pip install -e ".[docs]"
```

Build and preview locally:

```bash
mkdocs build
mkdocs serve
```

Docs publishing uses `mike` in `.github/workflows/docs.yml`. Pull requests
build a `pr-<number>` docs version, pushes to `main` deploy `dev`, and
published releases deploy the release version plus `latest`.

If a published documentation version needs to be replaced, update it from the
branch with the desired docs:

```bash
git fetch
git switch [branch with desired docs]
mike delete [broken docs version]
mike deploy [new docs version]
git switch gh-pages
git push origin gh-pages
```

## Maintenance Notes

- Keep marker expressions synchronized between workflows, `run_local_ci.sh`,
  this page, and tests that assert CI policy.
- Keep `.coveragerc.non-pyomo` on SciPy-only coverage commands.
- Keep notebook tests in the explicit notebook lane.
- Keep slow optimizer-heavy tests out of the fast PR lane.
- Do not broaden fast PR deselection beyond `slow`, `notebook`, and `pyomo`
  without documenting the reason here.
