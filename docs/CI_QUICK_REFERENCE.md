# GitHub Actions CI Quick Reference

## Local Commands

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

Use `SKIP_INSTALL=1` to skip dependency installation when your environment is
already ready:

```bash
SKIP_INSTALL=1 ./run_local_ci.sh fast
```

For the optional Pyomo lane, install the documented Pyomo extra and IPOPT
solver extensions:

```bash
python -m pip install -e ".[dev,pyomo]"
idaes get-extensions --extra petsc
```

A conda-managed local environment may instead provide IPOPT with:

```bash
conda install -c conda-forge ipopt
```

## CI Lanes

| Lane | Command | Workflow |
| --- | --- | --- |
| Static analysis | `python -m ruff check lyopronto tests examples main.py`; advisory `python -m mypy lyopronto` | `.github/workflows/pr-tests.yml`, `.github/workflows/tests.yml` |
| Fast PR | `pytest tests/ -n auto -v -m "not slow and not notebook and not pyomo"` | `.github/workflows/pr-tests.yml` |
| Full non-Pyomo PR | `pytest tests/ -n auto -v -m "not pyomo" --cov=lyopronto --cov-config=.coveragerc.non-pyomo --cov-report=term-missing` | `.github/workflows/full-validation.yml` |
| Full non-Pyomo main/local | `pytest tests/ -n auto -v -m "not pyomo" --cov=lyopronto --cov-config=.coveragerc.non-pyomo --cov-report=term-missing` | `.github/workflows/tests.yml`, `run_local_ci.sh` |
| Slow non-Pyomo | `pytest tests/ -n auto -v -m "slow and not pyomo" --cov=lyopronto --cov-config=.coveragerc.non-pyomo --cov-report=term-missing` | `.github/workflows/slow-tests.yml` |
| Notebook | `pytest tests/ -n auto -v -m "notebook" --cov=lyopronto --cov-config=.coveragerc.non-pyomo --cov-report=term-missing` | `.github/workflows/rundocs.yml` |
| Pyomo light | `pytest tests/test_pyomo_models tests/test_pyomo_solver.py -n auto -v` | `.github/workflows/pyomo-tests.yml` |
| Pyomo solver | `pytest tests/ -n auto -v -m "pyomo" --cov=lyopronto --cov-report=term-missing` | `.github/workflows/pyomo-tests.yml`, `.github/workflows/slow-tests.yml` |

All pytest lanes inherit `--durations=25`, `--timeout=600`, and
`--timeout-method=thread` from `pyproject.toml`.
Non-Pyomo coverage uses `.coveragerc.non-pyomo` to keep optional Pyomo modules
out of SciPy-only totals.

## Triggers

- PR updates targeting `main`: static analysis and fast lane.
- Full Validation workflow: full non-Pyomo lane with coverage for
  non-draft PRs touching validation-sensitive code/tests, PRs labeled
  `full-validation`, nightly scheduled validation, manual dispatch, and version
  tags.
- Pushes to `main`: static analysis and full non-Pyomo lane with coverage.
- Ready/non-draft PRs, pushes to `main`, nightly schedule, version tags, and
  manual dispatch: notebook lane.
- PRs or pushes to `main` changing `lyopronto/pyomo_models/**` or
  `tests/test_pyomo_models/**`: required Pyomo light lane and optional
  non-blocking solver comparison.
- Manual dispatch: slow non-Pyomo, full non-Pyomo, or optional Pyomo lane.

Do not add the path-filtered Pyomo light job to branch-protection required
status checks. It does not report on non-Pyomo PRs. The optional solver
comparison job is job-level non-blocking, so review its logs when it runs.
The Full Validation workflow is reportable on every PR and can be used as a
branch-protection required status check; it skips quickly when neither paths nor
labels require the expensive full lane.
Codecov uploads are not configured. Coverage remains visible in terminal
reports from the full, notebook, slow, and Pyomo solver lanes.

## Marker Policy

- `slow`: optimizer-heavy or long-running tests excluded from fast PR feedback.
- `notebook`: papermill/Jupyter documentation tests.
- `pyomo`: implemented optional Pyomo model and IPOPT solver tests.
  Model-construction coverage runs in the path-filtered Pyomo light lane.
  Tests that need IPOPT should use
  `tests.pyomo_solver.require_pyomo_solver("ipopt")` for clear missing-solver
  skips.
- `main`: legacy `main.py` and high-level API behavior coverage.
- `serial`: tests that must run with `pytest -m serial -n 0`.

## References

- Full CI guide: `docs/CI_WORKFLOW_GUIDE.md`
- Test policy: `tests/README.md`
- Local script: `run_local_ci.sh`
- Python version: `.github/ci-config/ci-versions.yml`
