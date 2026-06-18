# LyoPRONTO Documentation

This directory contains current technical documentation for the LyoPRONTO
repository.

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

Pyomo roadmap planning lives in GitHub issue
[#80](https://github.com/SECQUOIA/LyoPRONTO/issues/80) and its child issues.
The current repository status is summarized in `ARCHITECTURE.md`.

For the MkDocs site:

- `index.md`
- `tutorials.md`
- `how-to-guides.md`
- `explanation.md`
- `reference.md`
- `dev.md`
- `examples/`

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

## Stale Report Policy

Do not keep dated completion reports, obsolete implementation snapshots, or
old coverage/test-count summaries in the documentation tree. Use GitHub issues,
PRs, and git history for that historical record.
