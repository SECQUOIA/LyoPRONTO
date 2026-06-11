# GitHub Actions CI Quick Reference

## Local Commands

```bash
./run_local_ci.sh fast
./run_local_ci.sh full
./run_local_ci.sh slow
./run_local_ci.sh notebook
./run_local_ci.sh pyomo
```

Use `SKIP_INSTALL=1` to skip dependency installation when your environment is
already ready:

```bash
SKIP_INSTALL=1 ./run_local_ci.sh fast
```

## CI Lanes

| Lane | Command | Workflow |
| --- | --- | --- |
| Fast PR | `pytest tests/ -n auto -v -m "not slow and not notebook and not pyomo"` | `.github/workflows/pr-tests.yml` |
| Full non-Pyomo | `pytest tests/ -n auto -v -m "not pyomo" --cov=lyopronto --cov-report=xml:coverage.xml --cov-report=term-missing` | `.github/workflows/pr-tests.yml`, `.github/workflows/tests.yml` |
| Slow non-Pyomo | `pytest tests/ -n auto -v -m "slow and not pyomo" --cov=lyopronto --cov-report=xml:coverage.xml --cov-report=term-missing` | `.github/workflows/slow-tests.yml` |
| Notebook | `pytest tests/ -n auto -v -m "notebook" --cov=lyopronto --cov-report=xml:coverage.xml --cov-report=term-missing` | `.github/workflows/rundocs.yml` |
| Pyomo | `pytest tests/ -n auto -v -m "pyomo" --cov=lyopronto --cov-report=xml:coverage.xml --cov-report=term-missing` | `.github/workflows/slow-tests.yml` |

## Triggers

- PR updates targeting `main`: fast lane.
- Ready/non-draft PRs targeting `main`: full non-Pyomo lane with coverage.
- Pushes to `main`: full non-Pyomo lane with coverage.
- Ready/non-draft PRs, pushes to `main`, and manual dispatch: notebook lane.
- Manual dispatch: slow non-Pyomo, full non-Pyomo, or optional Pyomo lane.

## Marker Policy

- `slow`: optimizer-heavy or long-running tests excluded from fast PR feedback.
- `notebook`: papermill/Jupyter documentation tests.
- `pyomo`: optional future Pyomo/IPOPT tests. No collected tests is a no-op in
  the manual Pyomo lane.
- `main`: legacy `main.py` and high-level API behavior coverage.
- `serial`: tests that must run with `pytest -m serial -n 0`.

## References

- Full CI guide: `docs/CI_WORKFLOW_GUIDE.md`
- Test policy: `tests/README.md`
- Local script: `run_local_ci.sh`
- Python version: `.github/ci-config/ci-versions.yml`
