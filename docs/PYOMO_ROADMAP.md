# Pyomo Status

This document is a short status note. It is not the Pyomo roadmap. Project
planning should happen in GitHub issues and milestones, starting from roadmap
issue [#63](https://github.com/SECQUOIA/LyoPRONTO/issues/63), where tasks can
be assigned, linked to implementation PRs, and closed.

## Current Status

Current repository facts:

- No `lyopronto/pyomo_models/` package is tracked on `main`.
- No Pyomo-marked tests are collected from the repository.
- Automatic PR and main-branch CI lanes validate non-Pyomo behavior.
- The manual Pyomo validation lane is optional and may no-op until future
  Pyomo tests exist.

Current implementation boundaries are documented in `ARCHITECTURE.md`. Do not
describe Pyomo as implemented in user or contributor docs unless the same PR
adds tracked implementation, optional dependency handling, runnable examples,
and Pyomo-marked tests.

## Documentation Rule

Keep Pyomo references in user and contributor docs limited to current status
until implementation returns. A PR that adds Pyomo should also add optional
dependency documentation, runnable examples where appropriate, Pyomo-marked
tests, and CI lane updates.
