# CI Performance Optimization

## Current Approach

CI performance is managed with marker-based lanes:

- Fast PR feedback excludes `slow`, `notebook`, and `pyomo`.
- Ready/non-draft PRs and `main` runs execute the full non-Pyomo lane with
  coverage.
- Slow optimizer-heavy validation is available through manual dispatch.
- Notebook tests run in their own explicit workflow.
- Pyomo light validation runs automatically only when Pyomo model or test paths
  change; solver-backed Pyomo validation remains optional.

## Commands

```bash
# Fast PR feedback
pytest tests/ -n auto -v -m "not slow and not notebook and not pyomo" --durations=25

# Full non-Pyomo validation with coverage
pytest tests/ -n auto -v -m "not pyomo" --cov=lyopronto --cov-report=xml:coverage.xml --cov-report=term-missing --durations=25

# Manual slow validation
pytest tests/ -n auto -v -m "slow and not pyomo" --cov=lyopronto --cov-report=xml:coverage.xml --cov-report=term-missing --durations=25

# Explicit notebook validation
pytest tests/ -n auto -v -m "notebook" --cov=lyopronto --cov-report=xml:coverage.xml --cov-report=term-missing --durations=25

# Automatic Pyomo light validation after installing .[dev,pyomo]
pytest tests/test_pyomo_models tests/test_pyomo_solver.py -n auto -v --durations=25

# Optional solver-backed Pyomo validation after installing .[dev,pyomo] and IPOPT
pytest tests/ -n auto -v -m "pyomo" --cov=lyopronto --cov-report=xml:coverage.xml --cov-report=term-missing --durations=25
```

## Why This Helps

- PR updates get quick signal from tracked non-notebook SciPy behavior.
- Coverage work is reserved for ready PRs and `main`.
- Optimizer-heavy slow tests remain available without forcing every draft PR to
  pay that cost.
- Notebook execution is visible as its own lane instead of being hidden inside
  ordinary fast tests.
- Each pytest lane reports the 25 slowest tests and uses the shared
  `--timeout=600 --timeout-method=thread` configuration so hangs fail clearly.
- The Pyomo light lane is path-filtered so default non-Pyomo PRs do not install
  optional Pyomo dependencies. Solver-backed Pyomo tests should use
  `tests.pyomo_solver.require_pyomo_solver("ipopt")` so missing IPOPT setup is
  reported as a clear skip.

## Maintenance Notes

- Prefer changing marker expressions in one focused PR with matching updates to
  workflows, `run_local_ci.sh`, and `tests/README.md`.
- Keep `-n auto` explicit in CI lane commands so parallel execution remains a
  deliberate workflow choice.
- Do not use `--dist loadgroup` unless tests are grouped with xdist group
  markers and the behavior has been measured.
- If fast PR runtime grows unexpectedly, first inspect newly added `slow` or
  `notebook` candidates before broadening the fast lane exclusions.
