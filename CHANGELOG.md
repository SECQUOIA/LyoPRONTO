# Changelog

All notable changes to LyoPRONTO will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

#### Pyomo-Based Optimization Framework
- **Multi-period DAE optimization** using orthogonal collocation on finite elements
  - Implements rigorous dynamic optimization for primary drying
  - 4-stage convergence framework for robust solution finding
  - Supports scipy warmstart initialization for improved convergence
- **Three optimization modes**:
  - `optimize_Tsh`: Optimize shelf temperature trajectory at fixed chamber pressure
  - `optimize_Pch`: Optimize chamber pressure trajectory at fixed shelf temperature
  - `optimize_Pch_Tsh`: Simultaneous optimization of both control variables
- **New module structure** (`lyopronto/pyomo_models/`):
  - `optimizer.py`: Main optimizer interface functions
  - `multi_period.py`: Multi-period DAE model with orthogonal collocation (563 lines)
  - `single_step.py`: Single time-step optimization model
  - `utils.py`: Utilities for initialization, scaling, and validation
  - `README.md`: Comprehensive module documentation

#### Benchmarking Infrastructure
- **Grid benchmarking CLI** (`benchmarks/grid_cli.py`): N-dimensional parameter grid generation
- **Adapters** (`benchmarks/adapters.py`): Normalized scipy/Pyomo runners for fair comparison
- **Analysis notebook** (`benchmarks/grid_analysis.ipynb`): Visualization of results
- **Schema v2**: Structured output with trajectories, metadata, and content hashing

#### Documentation
- `docs/PHYSICS_REFERENCE.md`: Physics equations and model documentation
- `examples/example_pyomo_optimizer.py`: Working usage example

#### Testing Infrastructure
- 93% code coverage on Pyomo modules
- Comprehensive test suite in `tests/pyomo/` (12 test files)
- CI/CD workflows for main branch, PRs, and manual slow tests
- Smart PR testing: draft PRs get fast tests, ready PRs get full coverage

#### CI/CD Enhancements
- `.github/workflows/tests.yml`: Main branch full tests with coverage
- `.github/workflows/pr-tests.yml`: Smart PR tests (draft vs. ready modes)
- `.github/workflows/slow-tests.yml`: Manual trigger for slow optimization tests
- `.github/workflows/docs.yml`: Documentation build workflow
- Centralized Python version management via `.github/ci-config/ci-versions.yml`

### Changed

#### Physics Corrections
- **Corrected Kv formula**: Fixed vial heat transfer coefficient calculation
- **Corrected k_ice constant**: Updated ice thermal conductivity value
- **Log-transformed vapor pressure**: Improved numerical stability in Pyomo models

#### Dependencies
- Added optional `optimization` dependency group for Pyomo-based features
- Pyomo ≥6.7.0 and IDAES-PSE ≥2.9.0 now available as optional dependencies
- Core scipy-based functionality remains dependency-free of Pyomo

#### Project Structure
- Reorganized test directory structure for clarity
- Added `benchmarks/` directory for performance comparison
- Enhanced `pyproject.toml` with modern Python packaging standards

### Deprecated
- None

### Removed
- None

### Fixed
- Various numerical stability improvements in optimization models
- Improved convergence behavior with staged solving approach

### Security
- None

---

## Migration Guide

### From scipy-only to Pyomo optimization

The scipy-based optimizers (`opt_Pch.py`, `opt_Tsh.py`, `opt_Pch_Tsh.py`) remain fully functional and are the default. To use Pyomo-based optimization:

1. **Install optional dependencies**:
   ```bash
   pip install lyopronto[optimization]
   # Or manually:
   pip install pyomo>=6.7.0 idaes-pse>=2.9.0
   idaes get-extensions  # Downloads IPOPT solver
   ```

2. **Use Pyomo optimizers**:
   ```python
   from lyopronto.pyomo_models import optimize_Tsh, optimize_Pch, optimize_Pch_Tsh
   
   result = optimize_Tsh(
       vial=vial_params,
       product=product_params,
       Pch_setpoint=0.1,  # Torr
       objective="min_time",
       warmstart=True,  # Use scipy solution as initial guess
   )
   ```

3. **Compare with scipy baseline**:
   ```python
   # Scipy (existing)
   from lyopronto import opt_Tsh
   scipy_result = opt_Tsh.optimize(...)
   
   # Pyomo (new)
   from lyopronto.pyomo_models import optimize_Tsh
   pyomo_result = optimize_Tsh(..., warmstart=True)
   ```

### Coexistence Philosophy

Both scipy and Pyomo optimizers will continue to be maintained:
- **scipy**: Fast, reliable, good for most use cases
- **Pyomo**: Rigorous DAE formulation, extensible, better for research

[Unreleased]: https://github.com/LyoHUB/LyoPRONTO/compare/main...HEAD
