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
sudo apt-get install glpk-utils
```

A conda-managed local environment may instead install IPOPT with:

```bash
conda install -c conda-forge ipopt
conda install -c conda-forge glpk
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
| Full non-Pyomo | `pytest tests/ -n auto -v -m "not notebook and not pyomo" --cov=lyopronto --cov-config=.coveragerc.non-pyomo --cov-report=term-missing` | `.github/workflows/full-validation.yml`, `.github/workflows/tests.yml`, `.github/workflows/slow-tests.yml` |
| Slow non-Pyomo | `pytest tests/ -n auto -v -m "slow and not pyomo" --cov=lyopronto --cov-config=.coveragerc.non-pyomo --cov-report=term-missing` | `.github/workflows/slow-tests.yml` |
| Notebook | `pytest tests/ -n 0 -v -m "notebook" --cov=lyopronto --cov-config=.coveragerc.non-pyomo --cov-report=term-missing` | `.github/workflows/rundocs.yml` |
| Pyomo light | `pytest tests/test_pyomo_models tests/test_pyomo_solver.py -n auto -v` | `.github/workflows/pyomo-tests.yml`, `./run_local_ci.sh pyomo-light` |
| Pyomo solver | `pytest tests/ -n auto -v -m "pyomo" --cov=lyopronto --cov-report=term-missing` | `.github/workflows/pyomo-tests.yml`, `.github/workflows/slow-tests.yml` |

All pytest lanes inherit `--durations=25`, `--timeout=600`,
`--timeout-method=thread`, and `--dist=worksteal` from `pyproject.toml`. Non-Pyomo coverage lanes use
`.coveragerc.non-pyomo` so optional Pyomo modules are omitted from SciPy-only
coverage totals. Codecov uploads are not configured; coverage remains visible
in terminal reports from the coverage lanes.

## Workflow Behavior

Pull requests targeting `main` always run static analysis and the fast PR lane.
The Full Validation workflow is reportable on every PR. Repository maintainers
should require the `Full non-Pyomo validation` job in branch protection because
the job reports success quickly when the validation policy decides the full
lane is not needed. For non-draft PRs that touch validation-sensitive paths the
job runs only the slow-marked complement (`slow and not notebook and not
pyomo`, no coverage), because the fast PR lane already runs every non-slow test
on the same events; together the two lanes execute the whole non-Pyomo suite on
each PR. The full lane with coverage runs for PRs labeled `full-validation`,
nightly scheduled validation, manual dispatch, version tags, and pushes to
`main`.

Notebook tests run serially in `.github/workflows/rundocs.yml` for ready PRs,
pushes to `main`, nightly schedule, version tags, and manual dispatch.

The Pyomo Tests workflow is reportable on every PR so repository maintainers
can require the `Pyomo import and construction lane` job in branch protection.
That job reports success quickly when the Pyomo scope check decides validation
is not needed, and installs `.[dev,pyomo]` without IPOPT only for Pyomo model,
Pyomo test, maintained Pyomo example, Pyomo dependency, or Pyomo workflow
changes. The solver comparison job is job-level non-blocking; inspect its logs
when it runs because install failures and comparison failures leave the PR
status green. Solver-backed lanes add IDAES's solver directory to `PATH` and
install its LAPACK runtime dependency, then verify that IPOPT is both discoverable
and executable before pytest starts. This prevents a green run in which every
solver-backed test was silently skipped.

The solver comparison job also executes reduced one-case versions of the
current-main SciPy/Pyomo shelf-temperature, chamber-pressure, and joint-control
comparison notebooks. Their default 3x3 sweeps and repeated timings remain
local tutorial experiments rather than CI timing gates.

The same job executes the original known-Rp fixed-control replay and the
unknown-Rp hybrid parameter-fit comparison, plus both reader-facing notebooks.
The no-solver lane constructs both models; the solver lane checks the known-Rp
seven-column endpoint against the shared
`examples.original_workflow_parity.KNOWN_RP_ENDPOINT_TOLERANCE_PP`
backward-Euler tolerance and checks the unknown-Rp parameters/objective against
SciPy after shared legacy preprocessing.

The same job executes the Srisuma and Braatz optimal-control replication
notebook on a coarse spatial mesh. That notebook reports wall times against the
timings published with the upstream paper, but those comparisons are narrative
only: they are measured on whatever runner the job lands on and are never
asserted.

The optional lane also runs the coarse multiphase GDP paper benchmark. GDPopt
RIC uses GLPK for the discrete master and the lane's IPOPT 3.13.2 build for
local nonlinear subproblems. Structural tests remain skip-safe in the
no-solver lane; solver tests require both executables and provide separate
installation hints when either is absent.

Validate solver-backed changes against the IPOPT that `idaes get-extensions`
installs, not only against a conda or system build. That lane runs IPOPT 3.13.2
through the AMPL/ASL interface, where an option the build does not recognize is
fatal rather than ignored: IPOPT prints `Unknown keyword` and exits non-zero
before solving, which surfaces as `Solver (ipopt) did not exit normally`. Newer
IPOPT builds accept options that one does not, so keep solver options to the
common subset. To reproduce the lane locally, put IDAES's solver directory first
on `PATH`:

```bash
PATH="$HOME/.idaes/bin:$PATH" pytest tests/ -n 0 -v -m "pyomo"
```

For the same reason, avoid asserting constraint violations tighter than the
relaxation IPOPT is entitled to. With `bound_relax_factor` at 1e-8, a 243 K
bound admits about 2.4e-6 K of reported violation by construction; derive such
tolerances from the factor instead of hard-coding a number that happens to hold
for one build.

`.github/workflows/slow-tests.yml` is manual dispatch for focused slow
non-Pyomo, full non-Pyomo, or optional Pyomo validation.

## Pyomo Test Policy

Default installs and the `dev` extra intentionally exclude Pyomo, IDAES, and
IPOPT. Pyomo-marked tests that need IPOPT should call
`tests.pyomo_solver.require_pyomo_solver("ipopt")` before solving models. That
helper skips with installation hints when Pyomo or IPOPT is missing.

Keep automatic Pyomo validation isolated behind the Pyomo scope check so
default non-Pyomo PRs do not install optional dependencies while the required
branch-protection check still reports on every PR.

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
