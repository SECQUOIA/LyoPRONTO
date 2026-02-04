# Pyomo Models Test Suite

Tests for the Pyomo-based optimization models in `lyopronto/pyomo_models/`.

## Test Organization

| Category | Files | Purpose |
|----------|-------|---------|
| **Model Tests** | `test_model_*.py` | Model creation, structure, warmstart |
| **Optimizer Tests** | `test_optimizer_*.py` | Optimizer functions (Tsh, Pch, Pch_Tsh) |
| **Infrastructure** | `test_parameter_validation.py`, `test_warmstart.py`, `test_staged_solve.py` | Validation, warmstart, staged solve |

## Running Tests

```bash
# Run all Pyomo tests
pytest tests/test_pyomo_models/ -v

# Run with coverage
pytest tests/test_pyomo_models/ --cov=lyopronto.pyomo_models

# Skip if Pyomo not installed
pytest tests/test_pyomo_models/ -v  # Tests auto-skip if Pyomo unavailable
```

## Known Limitations

- `test_block_triangularization` in `test_model_multi_period.py` is xfailed due to DOF from initial conditions (structural analysis limitation, not a functional bug)
- Some tests require optional dependencies (PyNumero, incidence_analysis)
