# Pyomo Branch Merge - PR Implementation Plan

**Date**: January 2025  
**Target**: Merge `pyomo` branch into SECQUOIA/LyoPRONTO `main`  
**Ground Truth**: LyoHUB/LyoPRONTO (upstream)

## Executive Summary

The `pyomo` branch contains comprehensive Pyomo optimization framework additions. This document outlines a staged PR strategy to merge this work into SECQUOIA main.

### Key Finding: Branch State Analysis

| Branch | Base | Status |
|--------|------|--------|
| **upstream/main** (LyoHUB) | - | Ground truth, has recent scipy improvements |
| **origin/main** (SECQUOIA) | Older fork | Missing upstream improvements in `functions.py`, `opt_*.py` |
| **pyomo** (current) | upstream/main | Has ALL upstream improvements + Pyomo additions + formatting |

**Important**: The `pyomo` branch was based on upstream/main and already includes:
1. Correct `k_ice = 0.0059` value  
2. Improved `Kv_FUN` formula
3. `RampInterpolator` class
4. Better error handling in optimizers
5. PCHIP interpolation in `fill_output()`

## Strategic Options

### Option A: Staged Merge (Recommended)
1. **PR 0**: Sync SECQUOIA main with upstream (get scipy improvements first)
2. **PRs 1-7**: Add Pyomo work on top

**Pros**: Clean separation, easier code review, clear provenance  
**Cons**: More PRs, potential merge conflicts

### Option B: Direct Split of Pyomo Branch
Split pyomo branch changes directly into logical PRs

**Pros**: Less work, already tested together  
**Cons**: PRs mix upstream improvements with Pyomo additions

---

## PR Implementation Details

### PR 0: Sync with Upstream (Foundation)

**Purpose**: Bring SECQUOIA main up to date with LyoHUB upstream

**Files Changed** (from upstream → origin/main diff):
- `lyopronto/functions.py` - Major improvements:
  - `RampInterpolator` class
  - `lumped_cap_Tpr_abstract`, `lumped_cap_Tpr_ice`, `lumped_cap_Tpr_sol`
  - `crystallization_time_FUN` with Tsh_func parameter
  - `fill_output()` with PCHIP interpolation
  - Better dmdt<0 handling
- `lyopronto/opt_Pch.py` - Error handling, bounds improvements
- `lyopronto/opt_Tsh.py` - Warning imports, ramp_rate handling
- `lyopronto/opt_Pch_Tsh.py` - Code formatting

**Command to create**:
```bash
git checkout origin/main
git checkout -b pr/sync-upstream
git merge upstream/main --no-commit
# Resolve conflicts if any
git commit -m "Sync with upstream LyoHUB/LyoPRONTO"
```

---

### PR 1: CI/CD Infrastructure for Pyomo

**Purpose**: Enable Pyomo testing in GitHub Actions

**Files**:
- `.github/workflows/tests.yml` - Add test-pyomo job
- `.github/workflows/pr-tests.yml` - Add pyomo marker handling
- `.github/workflows/slow-tests.yml` - Add include_pyomo option
- `.github/workflows/rundocs.yml` - Update for notebook tests
- `.github/workflows/docs.yml` - Update docs deployment

**Key Changes**:
- Separate scipy and pyomo test jobs
- IPOPT installation via `idaes get-extensions --extra petsc`
- `continue-on-error: true` for pyomo tests (don't block PRs)
- Pyomo test marker: `@pytest.mark.pyomo`

---

### PR 2: Pyomo Dependencies and Module Structure

**Purpose**: Add optional Pyomo dependencies, create empty module

**Files**:
- `pyproject.toml` - Add `[project.optional-dependencies.optimization]`
- `lyopronto/pyomo_models/__init__.py` - Create with placeholder
- `tests/test_pyomo_models/__init__.py` - Create test directory

**Dependencies to add**:
```toml
[project.optional-dependencies]
optimization = [
    "pyomo>=6.7.0",
    "idaes-pse>=2.9.0",
]
```

---

### PR 3: Single-Step Optimization + Utilities

**Purpose**: Core utilities and single time-step optimization

**Files**:
- `lyopronto/pyomo_models/utils.py` (254 lines)
  - Warmstart utilities
  - Scaling functions
  - Validation helpers
- `lyopronto/pyomo_models/single_step.py` (427 lines)
  - Single time-point optimization
  - Building block for multi-period
- `tests/test_pyomo_models/test_utils.py`
- `tests/test_pyomo_models/test_single_step.py`

---

### PR 4: Multi-Period DAE Model

**Purpose**: Core multi-period model with orthogonal collocation

**Files**:
- `lyopronto/pyomo_models/model.py` (640 lines)
  - Multi-period DAE formulation
  - Orthogonal collocation discretization
  - Physics constraints
- `tests/test_pyomo_models/test_model_*.py`
- `tests/test_pyomo_models/test_physics_equations.py`

---

### PR 5: Pyomo Optimizers

**Purpose**: Main optimizer functions matching scipy API

**Files**:
- `lyopronto/pyomo_models/optimizers.py` (2017 lines)
  - `optimize_Tsh_pyomo()`
  - `optimize_Pch_pyomo()`
  - `optimize_Pch_Tsh_pyomo()`
- `lyopronto/pyomo_models/__init__.py` - Update exports
- `tests/test_pyomo_models/test_optimizer_*.py`
- `tests/test_pyomo_models/test_warmstart.py`

---

### PR 6: Benchmarking Infrastructure

**Purpose**: Grid comparison of scipy vs Pyomo

**Files**:
- `benchmarks/adapters.py` - Adapter classes for both solvers
- `benchmarks/grid_cli.py` - CLI for grid runs
- `benchmarks/scenarios.py` - Test scenarios
- `benchmarks/schema.py` - Result schema
- `benchmarks/validate.py` - Validation utilities
- `benchmarks/grid_analysis.ipynb` - Analysis notebook
- `benchmarks/README.md`
- `benchmarks/results/` - Baseline results

---

### PR 7: Documentation and Examples

**Purpose**: User-facing documentation and examples

**Files**:
- `examples/example_pyomo_optimizer.py` - Pyomo usage example
- `lyopronto/pyomo_models/README.md` - Module documentation
- `docs/PHYSICS_REFERENCE.md` - Fix Kv formula documentation
- `CHANGELOG.md` - Document additions
- `README.md` - Update with Pyomo info

---

## Implementation Commands

### Setup Remotes (if not done)
```bash
git remote add upstream https://github.com/LyoHUB/LyoPRONTO.git
git fetch upstream
git fetch origin
```

### Create PR Branches

For each PR:
```bash
# After PR 0 is merged
git checkout origin/main
git pull origin main
git checkout -b pr/ci-cd-pyomo  # For PR 1

# Cherry-pick or copy files from pyomo branch
git checkout pyomo -- .github/workflows/

# Commit and push
git add .
git commit -m "Add CI/CD infrastructure for Pyomo testing"
git push origin pr/ci-cd-pyomo
```

---

## Testing Strategy

### Before Each PR
```bash
ruff check --fix lyopronto/ tests/ benchmarks/
ruff format lyopronto/ tests/ benchmarks/
pytest tests/ -v -m "not slow and not pyomo"  # For non-Pyomo PRs
pytest tests/ -v  # For Pyomo PRs (with optimization extras installed)
```

### Coverage Requirements
- Maintain 32%+ code coverage (current baseline)
- Each PR should include tests for new code
- Pyomo tests marked with `@pytest.mark.pyomo`

---

## Risk Assessment

| Risk | Mitigation |
|------|------------|
| Merge conflicts with SECQUOIA main | PR 0 syncs first, reducing conflicts |
| Pyomo tests flaky | `continue-on-error: true` in CI |
| IPOPT installation issues | IDAES extensions with fallback |
| Breaking scipy functionality | Separate test jobs, regression tests |

---

## Timeline Estimate

| PR | Effort | Dependencies |
|----|--------|--------------|
| PR 0 | 1 hour | None |
| PR 1 | 30 min | PR 0 merged |
| PR 2 | 15 min | PR 1 merged |
| PR 3 | 1 hour | PR 2 merged |
| PR 4 | 2 hours | PR 3 merged |
| PR 5 | 2 hours | PR 4 merged |
| PR 6 | 1 hour | PR 5 merged |
| PR 7 | 30 min | PR 6 merged |

**Total**: ~8 hours of implementation work, plus review time

---

## Branches Created

All PR branches have been created locally:

| PR | Branch | Commit | Description |
|----|--------|--------|-------------|
| 0 | `pr/sync-upstream` | 9f23cbe | Sync with upstream LyoHUB/LyoPRONTO |
| 1 | `pr/ci-cd-pyomo` | 87c0054 | Add CI/CD infrastructure for Pyomo testing |
| 2 | `pr/pyomo-dependencies` | 6f3a59b | Add Pyomo optional dependencies and module structure |
| 3 | `pr/pyomo-utils-singlestep` | 0a902ef | Add Pyomo utilities and single-step optimization |
| 4 | `pr/pyomo-model` | 64bc983 | Add Pyomo multi-period DAE model |
| 5 | `pr/pyomo-optimizers` | 337dd24 | Add Pyomo optimizer functions |
| 6 | `pr/benchmarks` | 3cc18a4 | Add benchmarking infrastructure for scipy vs Pyomo |
| 7 | `pr/docs-examples` | 6097d80 | Add Pyomo documentation, examples, and CHANGELOG |

## Next Steps

1. Push PR 0 and open PR against SECQUOIA/LyoPRONTO main
2. After PR 0 merges, push PR 1 and open PR
3. Continue sequentially through PR 7
4. Each PR should target the previously merged PR's result

### Push Commands

```bash
# PR 0 - targets origin/main
git push origin pr/sync-upstream
# Then create PR on GitHub

# After PR 0 merges, rebase and push PR 1
git checkout pr/ci-cd-pyomo
git rebase origin/main
git push origin pr/ci-cd-pyomo
# Create PR on GitHub

# Continue pattern for PRs 2-7
```
