# Test Directory Reorganization Plan

## Current Issues

1. **File outside directory**: `tests/test_pyomo_optimizers.py` should be in `tests/test_pyomo_models/`
2. **Inconsistent naming**: Mix of old module names and new ones
3. **Unclear purpose**: File names don't clearly indicate what they test
4. **Scratch/temporary files**: `test_new_optimizers_scratch.py` is a scratch file

## Proposed Organization

### By Function (Recommended)

```
tests/test_pyomo_models/
├── __init__.py
│
# Core Model Tests
├── test_model_single_step.py          # Single time-step model (from test_single_step.py)
├── test_model_multi_period.py         # Multi-period DAE model (from test_multi_period.py)
│
# Optimizer Tests (user-facing functions)
├── test_optimizer_Tsh.py              # optimize_Tsh_pyomo tests (from test_pyomo_opt_Tsh.py)
├── test_optimizer_Pch.py              # optimize_Pch_pyomo tests (from test_pyomo_opt_Pch.py)
├── test_optimizer_Pch_Tsh.py          # optimize_Pch_Tsh_pyomo tests (from test_pyomo_opt_Pch_Tsh.py)
│
# Infrastructure Tests
├── test_parameter_validation.py       # Parameter validation (keep as is)
├── test_warmstart.py                  # Warmstart adapters (from test_warmstart_adapters.py)
├── test_staged_solve.py               # Staged solve framework (keep as is)
│
# Advanced/Validation Tests
├── test_model_validation.py           # Model validation (from test_multi_period_validation.py)
├── test_model_advanced.py             # Advanced tests (from test_single_step_advanced.py)
│
# Legacy/Scratch (to remove or consolidate)
├── test_new_optimizers_scratch.py     # DELETE (scratch file)
└── ../test_pyomo_optimizers.py        # MOVE HERE and rename
```

## File Mapping

| Current File | New Name | Reason |
|-------------|----------|--------|
| `test_single_step.py` | `test_model_single_step.py` | Clear it tests single-step model |
| `test_single_step_advanced.py` | `test_model_advanced.py` | Consolidate advanced tests |
| `test_multi_period.py` | `test_model_multi_period.py` | Clear it tests multi-period model |
| `test_multi_period_validation.py` | `test_model_validation.py` | Shorter, clearer |
| `test_pyomo_opt_Tsh.py` | `test_optimizer_Tsh.py` | Match function name |
| `test_pyomo_opt_Pch.py` | `test_optimizer_Pch.py` | Match function name |
| `test_pyomo_opt_Pch_Tsh.py` | `test_optimizer_Pch_Tsh.py` | Match function name |
| `test_warmstart_adapters.py` | `test_warmstart.py` | Shorter |
| `test_parameter_validation.py` | *(keep)* | Already clear |
| `test_staged_solve.py` | *(keep)* | Already clear |
| `test_new_optimizers_scratch.py` | *(DELETE)* | Scratch file |
| `../test_pyomo_optimizers.py` | `test_optimizer_framework.py` | Tests create_optimizer_model |

## Benefits

1. **Clear naming**: `test_model_*` vs `test_optimizer_*` vs `test_*` (infrastructure)
2. **Consistent with source**: Matches `model.py` and `optimizers.py`
3. **Easy navigation**: Find tests by what they test
4. **No scratch files**: Clean up temporary test files
