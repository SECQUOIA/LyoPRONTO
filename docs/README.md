# LyoPRONTO Documentation

This directory contains current technical documentation for the LyoPRONTO
repository plus an archive of historical development reports.

## Current Documentation

For users and contributors:

- `GETTING_STARTED.md`: local setup, runnable examples, and current checks
- `ARCHITECTURE.md`: current module boundaries and API layers
- `PHYSICS_REFERENCE.md`: physics equations and model notes
- `TYPED_API_GUIDE.md`: legacy dict APIs versus typed Pint APIs
- `JULIA_PARITY_MATRIX.md`: Julia-parity status for typed APIs
- `CI_SETUP.md`: current CI setup overview
- `CI_WORKFLOW_GUIDE.md`: workflow triggers and lane behavior
- `CI_QUICK_REFERENCE.md`: compact CI command reference
- `SLOW_TEST_STRATEGY.md`: marker lane strategy
- `CI_PERFORMANCE_OPTIMIZATION.md`: CI runtime strategy
- `PYOMO_ROADMAP.md`: short Pyomo status note that redirects roadmap planning
  to GitHub issues
- `COEXISTENCE_PHILOSOPHY.md`: current SciPy/Pyomo boundary note; not a
  roadmap

Pyomo roadmap planning should live in GitHub issues and milestones, starting
from the parent roadmap issue
[#63](https://github.com/SECQUOIA/LyoPRONTO/issues/63). The current repository
status is summarized in `ARCHITECTURE.md`.

For the MkDocs site:

- `index.md`
- `tutorials.md`
- `how-to-guides.md`
- `explanation.md`
- `reference.md`
- `dev.md`
- `examples/`

Historical completion reports, stale coverage snapshots, and old test-count
summaries live in `docs/archive/`. They are retained for context and should
not be treated as current repository status.

## Testing and CI

Current local commands:

```bash
python -m ruff check lyopronto tests examples main.py
python -m mypy lyopronto
pytest tests/ -n auto -v -m "not slow and not notebook and not pyomo"
pytest tests/ -n auto -v -m "not pyomo" --cov=lyopronto --cov-report=xml:coverage.xml --cov-report=term-missing
```

The same lanes are available through:

```bash
./run_local_ci.sh fast
./run_local_ci.sh full
./run_local_ci.sh slow
./run_local_ci.sh notebook
./run_local_ci.sh pyomo
```

The Pyomo lane is manual and optional until tracked Pyomo implementation and
tests exist. See `tests/README.md` for the authoritative marker policy.

## Building the Site

Install documentation dependencies:

```bash
python -m pip install -e ".[docs]"
```

Build locally:

```bash
mkdocs build
```

Serve locally:

```bash
mkdocs serve
```

Docs publishing uses `mike` in `.github/workflows/docs.yml`.

## Archive Policy

Move dated completion reports and obsolete implementation snapshots to
`docs/archive/` instead of deleting them. When doing so, update
`docs/archive/README.md` with the reason they are historical.
