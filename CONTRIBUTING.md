# Contributing to LyoPRONTO

This file is a short entry point for contributors. The detailed, current
workflow references are:

- `docs/dev.md`: CI lanes, branch-protection guidance, docs builds, and
  contributor commands.
- `tests/README.md`: pytest markers, warning policy, test-authoring guidance,
  and scientific reference scenario rules.
- `docs/reference.md`: public API boundaries, package layout, typed-unit
  conventions, and optional Pyomo model status.
- `AGENTS.md`: repository-wide coding-agent guidance.

## Setup

```bash
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e ".[dev]"
```

For optional Pyomo development and manual Pyomo validation:

```bash
python -m pip install -e ".[dev,pyomo]"
idaes get-extensions --extra petsc
```

## Local Checks

Run static analysis and the fast PR lane before pushing:

```bash
python -m ruff check lyopronto tests examples main.py
python -m mypy lyopronto
./run_local_ci.sh fast
```

Before marking a validation-sensitive PR ready for review, run the full
non-Pyomo lane when practical:

```bash
./run_local_ci.sh full
```

Use `./run_local_ci.sh slow`, `notebook`, `pyomo-light`, or `pyomo` for focused
manual validation. See `docs/dev.md` for the exact lane commands, coverage
policy, workflow triggers, and branch-protection notes.

## Contributor Policy

- Preserve legacy dictionary APIs and output shapes.
- Keep typed Pint APIs additive.
- Keep Pyomo optional and isolated behind the `pyomo` extra and `pyomo` marker.
- Add or update tests for behavior changes and bug fixes.
- Assert expected project warnings with `pytest.warns`; do not hide warnings
  globally or use broad filters for `lyopronto` modules.
- Keep generated local outputs out of commits. If generated output must become
  a reference fixture, document why and update the allowlist narrowly.
- Update docs when behavior, usage, public API boundaries, or validation policy
  changes.

## Pull Requests

Use clear PR descriptions with:

- what changed;
- why it changed;
- tests run and outcomes;
- documentation updates;
- related issues.

Generated artifacts, local benchmark outputs, executed notebook copies,
coverage reports, and files produced by examples should not be committed unless
the PR intentionally adds a documented reference artifact.

## Questions

Check existing issues on GitHub or open a new issue with the use case, expected
behavior, observed behavior, and the commands needed to reproduce the problem.
