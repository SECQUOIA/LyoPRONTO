# LyoPRONTO Documentation Inventory

This file is the top-level inventory for Markdown documentation under `docs/`.
Every retained Markdown page is either listed in `mkdocs.yml`, linked here, or
explicitly identified as internal.

## Naming Policy

The root docs folder keeps only entry-point pages with stable purposes:
`index.md`, `how-to-guides.md`, `reference.md`, and `dev.md`. Long-form domain
references live under `technical/` so the root docs folder does not mix user
tasks with scientific appendices. `README.md` is retained as the directory
inventory and is the only uppercase Markdown filename left under `docs/`.

Do not add status snapshots, dated completion reports, or agent scratch notes
under `docs/`. Source code and tests are the implementation truth. Documentation
should explain the public workflow, stable API boundaries, or scientific
assumptions that are expensive to rediscover from code alone.

## Retained Files

| File | Classification | Discoverability |
| --- | --- | --- |
| `README.md` | Keep as internal docs inventory. | Linked from the repository README. |
| `index.md` | Keep as public landing page. | Listed in `mkdocs.yml`. |
| `how-to-guides.md` | Keep as the practical user guide for setup, examples, tutorials, and local validation. | Listed in `mkdocs.yml`. |
| `reference.md` | Keep as the API, package-layout, typed-unit, and optional Pyomo reference. | Listed in `mkdocs.yml`. |
| `technical/physics-reference.md` | Keep as long-lived scientific equation reference. | Listed in `mkdocs.yml`. |
| `technical/julia-parity.md` | Keep as parity/status reference for typed API exports. | Listed in `mkdocs.yml`; checked by tests. |
| `dev.md` | Keep as the contributor, CI, and docs-build guide. | Listed in `mkdocs.yml`; linked from README, CONTRIBUTING, and `tests/README.md`. |

## Merged Or Removed Files

| File | Classification | Replacement |
| --- | --- | --- |
| `CI_SETUP.md` | Merged/delete. | Current setup, workflow, and maintenance content lives in `dev.md`. |
| `CI_WORKFLOW_GUIDE.md` | Merged/delete. | Workflow behavior lives in `dev.md`. |
| `CI_QUICK_REFERENCE.md` | Merged/delete. | Lane command reference lives in `dev.md`. |
| `SLOW_TEST_STRATEGY.md` | Merged/delete. | Marker lane strategy lives in `dev.md` and `../tests/README.md`. |
| `CI_PERFORMANCE_OPTIMIZATION.md` | Merged/delete. | Current runtime policy and maintenance notes live in `dev.md`; historical planning belongs in GitHub issues. |
| `GETTING_STARTED.md` | Merged/delete. | Setup, examples, validation, and docs-build guidance live in `how-to-guides.md`, `dev.md`, and README. |
| `ARCHITECTURE.md` | Merged/delete. | Current package map, API layers, and optional Pyomo boundaries live in `reference.md` and `dev.md`. |
| `TYPED_API_GUIDE.md` | Merged/delete. | Typed API unit conventions and examples live in `reference.md`; parity-specific status lives in `technical/julia-parity.md`. |
| `explanation.md` | Merged/delete. | Its current `dt_setpt` hold-time note lives in `how-to-guides.md`. |
| `ci-testing.md` | Merged/delete. | CI lane commands, workflow behavior, optional Pyomo setup, and maintenance rules live in `dev.md`. |
| `tutorials.md` | Merged/delete. | Hosted GUI/video links and runnable tutorial snippets live in `how-to-guides.md`. |
| `technical/pyomo-status.md` | Merged/delete. | Implemented Pyomo model status, trajectory discretization, and warmstart notes live in `reference.md`. |

## Current Documentation Map

For package users, start with the MkDocs pages:

- `index.md`
- `how-to-guides.md`
- `reference.md`

For contributors, use:

- `dev.md`
- `../tests/README.md`
- `../examples/README.md`

For technical reference and current status, use:

- `reference.md`
- `technical/physics-reference.md`
- `technical/julia-parity.md`

The completed Pyomo roadmap is tracked in GitHub issue
[#80](https://github.com/SECQUOIA/LyoPRONTO/issues/80) and its child issues.
Use GitHub issues, PRs, and git history for historical records, and open new
scoped issues for future Pyomo work.

## Building The Site

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
