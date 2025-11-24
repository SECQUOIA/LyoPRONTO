# Pyomo Models Test Suite

**Status**: ✅ 88 tests passing (88 passed, 3 skipped, 2 xfailed)  
**Organization**: Reorganized November 14, 2025

## Test Organization

Tests are organized by what they test, following the source code structure:

### Core Model Tests (4 files)

#### `test_model_single_step.py` (4 test classes, ~330 lines)
Tests for single time-step optimization model.
- **TestSingleStepModel**: Model structure and variable creation
- **TestSingleStepSolver**: Solver integration and convergence
- **TestSolutionValidity**: Solution quality and constraint satisfaction
- **TestWarmstartUtilities**: Initialization from scipy solutions

**Purpose**: Single time-step model that replicates one step of scipy sequential approach.

#### `test_model_advanced.py` (4 test classes, ~480 lines)
Advanced structural analysis and numerical debugging.
- **TestStructuralAnalysis**: Incidence analysis and degrees of freedom
- **TestNumericalDebugging**: Constraint residuals and scaling
- **TestScipyComparison**: Validation against scipy baseline
- **TestModelValidation**: Physical consistency checks

**Purpose**: Deep validation of model structure and numerical properties.

#### `test_model_multi_period.py` (5 test classes, ~658 lines)
Tests for multi-period DAE model with orthogonal collocation.
- **TestMultiPeriodModelStructure**: Model creation and variable structure
- **TestMultiPeriodWarmstart**: Scipy warmstart functionality
- **TestMultiPeriodStructuralAnalysis**: Degrees of freedom and block structure
- **TestMultiPeriodNumerics**: Scaling and numerical conditioning
- **TestMultiPeriodOptimization**: Full optimization runs

**Purpose**: Dynamic optimization model using DAE with collocation on finite elements.

#### `test_model_validation.py` (3 test classes, ~350 lines)
Validation tests comparing Pyomo to scipy.
- **TestScipyComparison**: Warmstart and trajectory preservation
- **TestPhysicsConsistency**: Physical constraints (temperature, sublimation rate)
- **TestOptimizationComparison**: Optimization quality vs scipy

**Purpose**: Cross-validation between Pyomo and scipy implementations.

### Optimizer Tests (4 files)

#### `test_optimizer_Tsh.py` (3 test classes, ~294 lines)
Tests for `optimize_Tsh_pyomo()` - shelf temperature optimization.
- **TestPyomoOptTshBasic**: Basic functionality and output format
- **TestPyomoOptTshEquivalence**: Equivalence to scipy opt_Tsh
- **TestPyomoOptTshEdgeCases**: Edge cases and consistency

**Purpose**: Validates Pyomo equivalent of scipy `opt_Tsh.optimize()`.

#### `test_optimizer_Pch.py` (5 test classes, ~374 lines)
Tests for `optimize_Pch_pyomo()` - chamber pressure optimization.
- **TestPyomoOptPchModelStructure**: Model structure for Pch control mode
- **TestPyomoOptPchScipyValidation**: Scipy solution validation
- **TestPyomoOptPchOptimization**: Optimization convergence and quality
- **TestPyomoOptPchStagedSolve**: Staged solve framework
- **TestPyomoOptPchPhysicalConstraints**: Physical constraint satisfaction

**Purpose**: Validates Pyomo equivalent of scipy `opt_Pch.optimize()`.

#### `test_optimizer_Pch_Tsh.py` (5 test classes, ~375 lines)
Tests for `optimize_Pch_Tsh_pyomo()` - joint optimization.
- **TestPyomoOptPchTshModelStructure**: Model structure for both controls
- **TestPyomoOptPchTshScipyValidation**: Scipy solution validation
- **TestPyomoOptPchTshOptimization**: Joint optimization quality
- **TestPyomoOptPchTshStagedSolve**: Staged solve with both controls
- **TestPyomoOptPchTshPhysicalConstraints**: Constraint satisfaction

**Purpose**: Validates Pyomo equivalent of scipy `opt_Pch_Tsh.optimize()`.

#### `test_optimizer_framework.py` (5 test classes, ~411 lines)
Tests for core optimizer infrastructure (`create_optimizer_model`, staged solve).
- **TestPyomoModelStructure**: Model creation and ODE structure
- **TestScipyValidation**: Scipy solution validation on Pyomo mesh
- **TestStagedSolve**: 4-stage convergence framework
- **TestPhysicalConstraints**: Temperature limits and drying progress
- **TestReferenceData**: Validation against reference solutions

**Purpose**: Tests shared infrastructure used by all three optimizers.

### Infrastructure Tests (3 files)

#### `test_parameter_validation.py` (12 tests, ~199 lines)
Parameter validation for `create_optimizer_model()`.
- Control mode validation (`'Tsh'`, `'Pch'`, `'both'`)
- Pchamber bounds validation (0.01-1.0 Torr)
- Tshelf bounds validation (-50-150 °C)
- Error messages for missing/invalid parameters

**Purpose**: Ensures robust parameter validation for all control modes.

#### `test_warmstart.py` (4 tests, ~219 lines)
Warmstart adapter tests for all scipy optimizers.
- Warmstart from `opt_Tsh` output
- Warmstart from `opt_Pch` output
- Warmstart from `opt_Pch_Tsh` output
- Constraint-consistent initialization

**Purpose**: Validates generic `_warmstart_from_scipy_output()` for all modes.

#### `test_staged_solve.py` (1 test script, ~98 lines)
Staged solve framework validation.
- 4-stage convergence (collocation → trust region → full solve → refinement)
- Error handling and diagnostics
- Integration with all optimizer modes

**Purpose**: Tests the staged solve strategy for robust convergence.

## File Naming Convention

- **`test_model_*.py`**: Tests for model creation (`model.py`, `single_step.py`)
- **`test_optimizer_*.py`**: Tests for optimizer functions (`optimizers.py`)
- **`test_*.py`**: Tests for infrastructure (validation, warmstart, staged solve)

## Running Tests

```bash
# Run all Pyomo tests
pytest tests/test_pyomo_models/ -v

# Run specific test file
pytest tests/test_pyomo_models/test_optimizer_Tsh.py -v

# Run specific test class
pytest tests/test_pyomo_models/test_optimizer_Pch.py::TestPyomoOptPchOptimization -v

# Run with coverage
pytest tests/test_pyomo_models/ --cov=lyopronto.pyomo_models --cov-report=html

# Run in parallel
pytest tests/test_pyomo_models/ -n auto
```

## Test Statistics

| Category | Files | Test Classes | Approx Tests | Lines of Code |
|----------|-------|--------------|--------------|---------------|
| **Model Tests** | 4 | 16 | ~45 | ~1,818 |
| **Optimizer Tests** | 4 | 18 | ~35 | ~1,454 |
| **Infrastructure** | 3 | 3 | ~17 | ~516 |
| **Total** | **11** | **37** | **~97** | **~3,788** |

## Test Markers

Tests use pytest markers for organization:

```python
@pytest.mark.pyomo_serial    # Sequential execution (opt_Tsh tests)
@pytest.mark.xfail           # Known limitations (structural analysis)
@pytest.mark.skipif          # Conditional skipping (solver availability)
```

## Recent Changes

**November 14, 2025 - Test Reorganization**:
- Renamed files for clarity (`test_pyomo_opt_*.py` → `test_optimizer_*.py`)
- Moved misplaced `test_pyomo_optimizers.py` → `test_optimizer_framework.py`
- Removed scratch file (`test_new_optimizers_scratch.py`)
- Organized by function: models vs optimizers vs infrastructure
- All 88 tests passing after reorganization

## Development Guidelines

### Adding New Tests

1. **Choose the right file**:
   - Model structure/behavior → `test_model_*.py`
   - Optimizer function → `test_optimizer_*.py`
   - Infrastructure → `test_*.py`

2. **Follow naming convention**:
   - Test classes: `TestFeatureName`
   - Test methods: `test_specific_behavior`

3. **Use fixtures from `conftest.py`**:
   - `standard_vial`, `standard_product`, `standard_ht`
   - `standard_params` (combines all parameters)

4. **Document what you test**:
   - Clear docstrings for classes and methods
   - Explain expected behavior and edge cases

### Test Quality Standards

- ✅ **Physical reasonableness**: Check temperatures, pressures, rates are realistic
- ✅ **Numerical tolerance**: Use appropriate tolerances for optimization
- ✅ **Error messages**: Clear, actionable error messages
- ✅ **Fixture reuse**: Use shared fixtures from `conftest.py`
- ✅ **Fast execution**: Keep test cases small where possible

## References

- **Source Code**: `lyopronto/pyomo_models/`
- **Documentation**: `docs/PYOMO_OPTIMIZER_EXTENSION_COMPLETE.md`
- **Scipy Baseline**: `lyopronto/opt_Tsh.py`, `opt_Pch.py`, `opt_Pch_Tsh.py`
- **Coexistence Philosophy**: `docs/COEXISTENCE_PHILOSOPHY.md`
