# Agent Instructions for LyoPRONTO

This is the repository-wide instruction file for coding agents. Keep it as the
single source of truth for agent guidance; tool-specific entry points should
point here instead of duplicating these instructions.

## Start Here

- Use source code and tests as implementation truth.
- Use `docs/reference.md` for public API boundaries, package layout, typed-unit
  conventions, and optional Pyomo model status.
- Use `docs/dev.md` for CI lanes, branch-protection guidance, docs builds, and
  contributor commands.
- Use `docs/how-to-guides.md` and `examples/README.md` for runnable examples.
- Use `docs/technical/physics-reference.md` for equations and scientific
  assumptions.
- Use `tests/README.md` for pytest markers, warning policy, and scientific
  reference scenario rules.

## Project Guardrails

- Preserve legacy dictionary APIs and output shapes.
- Keep typed Pint APIs additive; do not break legacy imports such as
  `from lyopronto import calc_knownRp`.
- Treat Pyomo as optional and isolated from default installs. Pyomo code lives
  under `lyopronto.pyomo_models`, requires the `pyomo` extra, and is tested
  with `@pytest.mark.pyomo`.
- Do not add dependencies, broaden CI scope, weaken tests, or change workflow
  gates unless the task explicitly requires it and the docs/tests are updated.
- Keep docs current rather than adding status snapshots or duplicated planning
  notes.

## Domain Checks

Legacy primary-drying output arrays have seven columns:

```text
0 time [hr]
1 sublimation-front temperature [degC]
2 vial-bottom temperature [degC]
3 shelf temperature [degC]
4 chamber pressure [mTorr]
5 sublimation flux [kg/hr/m^2]
6 percent dried [0-100]
```

Common mistakes to avoid:

- Do not treat legacy output pressure as Torr; column 4 is mTorr.
- Do not treat percent dried as a fraction; it is 0-100.
- Do not assume flux monotonically decreases; early shelf-temperature changes
  can increase flux before resistance dominates.
- Keep solver dependencies optional. Missing Pyomo or IPOPT should skip Pyomo
  solver tests with clear installation hints.

## Validation Commands

Run targeted tests for changed behavior plus the relevant CI lane. Common
commands:

```bash
python -m ruff check lyopronto tests examples main.py
pytest tests/ -n auto -v -m "not slow and not notebook and not pyomo"
pytest -n 0 -q tests/test_packaging_config.py
mkdocs build
python -m mypy lyopronto
```

`mypy` is advisory in current CI and may fail on known project type issues.
Report those failures instead of weakening the check.

## Editing Rules

- Prefer existing module patterns and helpers over new abstractions.
- Add or update tests for behavior changes, regressions, or new public
  expectations.
- Keep warning behavior visible; expected warnings should be asserted with
  `pytest.warns` rather than hidden globally.
- Update docs when behavior, usage, public API boundaries, or validation policy
  changes.
- Keep changes scoped to the request; record large follow-up work instead of
  expanding the PR opportunistically.
