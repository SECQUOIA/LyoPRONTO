# SciPy and Planned Pyomo Boundary

## Current Status

LyoPRONTO currently ships SciPy-based simulation, optimization, and fitting
workflows. Pyomo simultaneous optimization is a planned optional direction; it
is not implemented on `main` today.

This file is a boundary/status note, not a roadmap. Pyomo roadmap planning
belongs in GitHub issues and milestones, starting from
[#63](https://github.com/SECQUOIA/LyoPRONTO/issues/63).

Current facts:

- The tracked package has no `lyopronto/pyomo_models/` directory.
- The automatic PR and main-branch CI lanes validate tracked non-Pyomo
  behavior.
- The manual `pyomo` CI lane is reserved for future Pyomo/IPOPT tests and may
  no-op when no tests are collected.
- Roadmap examples in this document are target architecture, not callable
  current APIs.

## Principle

Future Pyomo work should coexist with the current SciPy implementation. It
should not replace the legacy dict APIs, the typed Pint APIs, or the
high-level compatibility helpers.

## Current SciPy Paths

The shipped SciPy-backed workflows are:

- `calc_knownRp.py`: primary drying with known product resistance
- `calc_unknownRp.py`: resistance estimation from temperature data
- `freezing.py`: freezing calculations
- `design_space.py`: design-space calculations
- `opt_Pch.py`: pressure-only optimization
- `opt_Tsh.py`: shelf-temperature optimization
- `opt_Pch_Tsh.py`: joint pressure and shelf-temperature optimization
- `fitting.py`: typed API fitting helpers backed by SciPy optimizers
- `pikal.py` and `rf.py`: typed solver workflows backed by SciPy integration

These workflows remain the supported implementation on `main`.

## Planned Pyomo Boundary

When Pyomo implementation returns, keep it isolated in a dedicated module tree,
for example:

```text
lyopronto/
└── pyomo_models/
    ├── __init__.py
    ├── single_step.py
    ├── multi_period.py
    └── utils.py
```

Expected boundaries:

- Do not rewrite legacy calculators just to support Pyomo.
- Reuse shared physics only where the formulas and units are explicit.
- Add comparison tests against current SciPy behavior.
- Mark Pyomo tests with `@pytest.mark.pyomo`.
- Keep Pyomo/IPOPT dependencies optional.

## User-Facing Shape

Current supported imports:

```python
from lyopronto import calc_knownRp, opt_Tsh
from lyopronto import Q_, PikalParams, solve_pikal
```

Potential future Pyomo imports should be explicit until the API is proven:

```python
from lyopronto.pyomo_models import single_step
```

A unified optimizer selector can be considered only after Pyomo has tracked
tests, stable dependency handling, and documented behavior.

## Validation Expectations

Future Pyomo work should include:

- tests proving that model construction works without hidden global state
- numerical comparisons against SciPy reference scenarios
- tests for infeasible or unsolved model handling
- documentation of solver dependencies and expected local setup
- CI marker policy updates in `tests/README.md`,
  `docs/CI_WORKFLOW_GUIDE.md`, workflows, and `run_local_ci.sh`

The comparison should not assume identical trajectories where solver
formulations differ. It should document tolerances and the physical rationale
for any accepted differences.

## Documentation Expectations

Current docs should use this language:

- "Pyomo is planned."
- "The manual Pyomo lane is optional and may no-op."
- "SciPy is the current tracked implementation."

Until code and tests are tracked, do not write that Pyomo optimizers, Pyomo
models, or dual SciPy/Pyomo implementations are available.

Historical documents in `docs/archive/` may contain older roadmap wording.
Those files are retained for context and should not be treated as current
implementation status.
