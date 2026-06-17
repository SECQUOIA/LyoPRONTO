# GitHub Copilot Instructions for LyoPRONTO

## Project Context

LyoPRONTO is a vial-scale lyophilization (freeze-drying) process simulator written in Python. It models the freezing and primary drying phases using heat and mass transfer equations.

### Current State
- **Status**: Current tracked implementation is SciPy-based; Pyomo is planned/manual.
- **Branch**: `main` is the default integration branch.
- **Testing**: Use the marker lanes in `tests/README.md`; do not rely on fixed historical test-count or coverage snapshots.
- **Python Version**: 3.8+
- **Key Principle**: Preserve legacy dict APIs while keeping typed Pint APIs additive.

## Code Style and Conventions

### General Guidelines
- Follow PEP 8 style guide
- Use type hints for function signatures
- Write comprehensive docstrings (NumPy style)
- Keep functions focused and testable
- Prefer explicit over implicit

### Naming Conventions
- Functions: `snake_case` (e.g., `calc_knownRp`, `Vapor_pressure`)
- Classes: `PascalCase` (e.g., `TestVaporPressure`)
- Variables: `snake_case` (e.g., `Pch`, `Tsub`, `dmdt`)
- Constants: `UPPER_CASE` in `constant.py`

### Physics Variables (Use These Names)
```python
# Temperatures [degC]
Tsub  # Sublimation front temperature
Tbot  # Vial bottom temperature
Tsh   # Shelf temperature
Tpr   # Product temperature

# Pressures (Torr unless specified)
Pch   # Chamber pressure
Psub  # Vapor pressure at sublimation front

# Lengths (cm)
Lpr0  # Initial product length
Lck   # Dried cake length

# Product properties
Rp    # Product resistance (cm²-hr-Torr/g)
R0    # Base product resistance
A1, A2  # Product resistance parameters

# Heat transfer
Kv    # Vial heat transfer coefficient [cal/s/K/cm**2])
KC, KP, KD  # Vial heat transfer parameters

# Vial geometry
Av    # Vial area (cm²)
Ap    # Product area (cm²)
Vfill # Fill volume (mL)

# Rates
dmdt  # Sublimation rate (kg/hr)
```

## Key Files and Their Purposes

### Core Physics
- `lyopronto/functions.py` - All physics equations (vapor pressure, heat transfer, mass transfer)
- `lyopronto/constant.py` - Physical constants and unit conversions

### Simulators
- `lyopronto/calc_knownRp.py` - Primary drying with known product resistance
- `lyopronto/calc_unknownRp.py` - Primary drying with unknown resistance
- `lyopronto/freezing.py` - Freezing phase calculations

### Optimizers (SciPy-based)
- `lyopronto/opt_Pch_Tsh.py` - Optimize both pressure and temperature
- `lyopronto/opt_Pch.py` - Optimize pressure only
- `lyopronto/opt_Tsh.py` - Optimize temperature only

### Typed API Modules
- `lyopronto/typed.py` - Pint-aware typed helpers
- `lyopronto/physical_properties.py` - Typed physical-property utilities
- `lyopronto/pikal.py` - Typed Pikal primary-drying workflow
- `lyopronto/rf.py` - Typed RF workflow
- `lyopronto/fitting.py` - SciPy fitting helpers
- `lyopronto/cycle_time.py` - End-of-primary-drying detection
- `lyopronto/eccurt.py` - Equipment capability utilities
- `lyopronto/vials.py` - Vial metadata and geometry helpers

### Pyomo Models
No `lyopronto/pyomo_models/` package is tracked on `main`. Treat Pyomo model
examples as roadmap material until implementation and tests are added.

### Testing
- `tests/test_functions.py` - Unit tests for physics functions
- `tests/test_calculators.py` - Integration tests for simulators
- `tests/test_regression.py` - Regression tests
- `tests/conftest.py` - Shared fixtures

## Output Format (IMPORTANT!)

When working with simulation output, remember:

```python
output = calc_knownRp.dry(...)  # Returns numpy array with 7 columns

# Column indices and units:
output[:, 0]  # time [hr]
output[:, 1]  # Tsub - sublimation temperature [degC]
output[:, 2]  # Tbot - vial bottom temperature [degC]
output[:, 3]  # Tsh - shelf temperature [degC]
output[:, 4]  # Pch - chamber pressure mTorr, NOT Torr!)
output[:, 5]  # flux - sublimation flux [kg/hr/m**2]
output[:, 6]  # percent_dried - percent dried (0-100)
```

## Common Pitfalls to Avoid

1. **Unit Confusion**
   - ❌ Don't assume Pch is in Torr (it's in mTorr in output)
   - ❌ Don't assume dried is a fraction (legacy output uses percent 0-100)
   - ❌ Don't forget flux is normalized by area (kg/hr/m²)

2. **Physics Behavior**
   - ❌ Don't assume flux monotonically decreases (it's non-monotonic)
   - ✅ Flux increases early (shelf temp rising) then decreases (resistance dominant)

3. **Numerical Tolerance**
   - ✅ Mass balance within 2% is acceptable (numerical integration error)
   - ✅ Allow 0.5°C tolerance for temperature constraints

4. **Test Writing**
   - ✅ Use fixtures from `conftest.py`
   - ✅ Check physical reasonableness with `assert_physically_reasonable_output()`
   - ✅ Write descriptive test names and docstrings

## Pyomo Development Guidelines

### When Creating Pyomo Models

1. **Variable Bounds** (use these ranges)
   ```python
   Pch: (0.05, 0.5)      # Torr
   Tsh: (-50, 50)        # °C
   Tsub: (-60, 0)        # °C
   Tbot: (-60, 50)       # °C
   dmdt: (0, None)       # kg/hr (non-negative)
   ```

2. **Avoid Direct Exponentials**
   ```python
   # ❌ Don't do this (numerical issues):
   model.Psub = pyo.Expression(expr=2.698e10 * pyo.exp(-6144.96/(model.Tsub+273.15)))
   
   # ✅ Do this instead (log transform):
   model.log_Psub = pyo.Var()
   model.log_constraint = pyo.Constraint(
       expr=model.log_Psub == log(2.698e10) - 6144.96/(model.Tsub+273.15)
   )
   ```

3. **Handle Conditionals**
   ```python
   # ❌ Don't use if statements in Pyomo expressions
   if dmdt < 0:
       dmdt = 0
   
   # ✅ Use smooth max or complementarity
   model.dmdt_nonneg = pyo.Constraint(expr=model.dmdt >= 0)
   ```

4. **Initialization Strategy**
   - Always initialize with scipy solution for warmstart
   - Use `model.var.set_value()` to set initial guesses

## Testing Requirements

### For New Code
1. Write tests BEFORE implementation (TDD)
2. Ensure at least one unit test per function
3. Add integration test for workflows
4. Include edge case tests
5. Run full test suite: `pytest tests/ -v`

### For Pyomo Code
1. Add comparison test against scipy baseline
2. Test convergence with different initial guesses
3. Test numerical stability
4. Benchmark performance

## Documentation Standards

### Function Docstrings (NumPy Style)
```python
def my_function(arg1, arg2):
    """Brief description of function.
    
    Longer description if needed. Explain physics, assumptions,
    and any important implementation details.
    
    Args:
        arg1 (float): Description with units (e.g., temperature in °C)
        arg2 (dict): Description of dict contents
            
    Returns:
        (float): Description with units
        
    Notes:
        Any important notes about numerical stability, edge cases, etc.
        
    Examples:
        >>> result = my_function(1.0, {'key': 'value'})
        >>> print(result)
        42.0
    """
```

### Comments in Code
- Explain WHY, not WHAT
- Flag physics assumptions
- Note numerical considerations
- Document units in non-obvious places

## Git Workflow

```bash
# Feature development
git checkout -b feature/descriptive-name

# Make changes, write tests
pytest tests/ -v

# Commit with descriptive message
git commit -m "Add feature: brief description

Detailed explanation of what changed and why.
Fixes issue #123."

# Push and create PR
git push origin feature/descriptive-name
```

## Useful Commands

```bash
# Run fast PR-style tests
pytest tests/ -n auto -v -m "not slow and not notebook and not pyomo"

# Run with coverage
pytest tests/ -n auto -v -m "not pyomo" --cov=lyopronto --cov-report=xml:coverage.xml --cov-report=term-missing

# Run specific test
pytest tests/test_functions.py::TestVaporPressure::test_vapor_pressure_at_freezing_point -v

# Run with debugging
pytest tests/ -v --pdb

# Format and lint code
python -m ruff check lyopronto tests examples main.py

# Type checking
python -m mypy lyopronto
```

## Key Physics Equations

### Vapor Pressure (Antoine Equation)
```python
P_sub = 2.698e10 * exp(-6144.96 / (T_sub + 273.15))  # Torr
```

### Product Resistance
```python
Rp = R0 + A1 * Lck / (1 + A2 * Lck)  # cm²-hr-Torr/g
```

### Sublimation Rate
```python
dmdt = Ap / Rp * (P_sub - Pch)  # kg/hr (before area normalization)
```

### Energy Balance
```python
Q_shelf = Kv * Av * (Tsh - Tbot)  # Heat from shelf
Q_sub = dmdt * dHs  # Heat for sublimation
# At steady state: Q_shelf = Q_sub
```

## References

### Core Documentation
- **Architecture**: See `docs/ARCHITECTURE.md` for system design
- **Physics**: See `docs/PHYSICS_REFERENCE.md` for equations and models
- **Getting Started**: See `docs/GETTING_STARTED.md` for developer guide

### Examples and Tests
- **Examples**: See `examples/README.md` for web interface examples (4 modes)
- **Testing**: See `tests/README.md` for current test lanes and marker policy
- **Historical logs**: See `docs/archive/` for development history

### Historical Reference
- **Archive**: See `docs/archive/` for detailed session summaries and historical context

## Questions?

When unsure:
1. Check existing tests in `tests/` for examples
2. Review `lyopronto/functions.py` for physics implementation
3. See `docs/ARCHITECTURE.md` for current module boundaries
4. Run the relevant lane from `tests/README.md` to validate changes
5. Check `examples/` for working code examples

## Current Focus

Current focus:

- Keep legacy dict APIs and typed Pint APIs documented separately.
- Keep CI lane documentation synchronized with workflows and `run_local_ci.sh`.
- Treat Pyomo as planned until tracked implementation and tests are added.
- Use GitHub issues and milestones for Pyomo roadmap planning; keep current
  implementation status in `docs/ARCHITECTURE.md`.
