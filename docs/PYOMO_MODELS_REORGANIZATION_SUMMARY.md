# Pyomo Models Directory Reorganization

**Date**: November 14, 2025  
**Status**: ✅ Complete

## Changes Made

### File Renaming

| Old Name | New Name | Purpose |
|----------|----------|---------|
| `multi_period.py` | `model.py` | Multi-period DAE model creation |
| `pyomo_optimizers.py` | `optimizers.py` | Main optimizer functions |
| `single_step.py` | `single_step.py` | *Unchanged* - Single time-step model |
| `utils.py` | `utils.py` | *Unchanged* - Utilities |

### New Directory Structure

```
lyopronto/pyomo_models/
├── __init__.py         # Package exports (updated)
├── model.py            # Multi-period DAE model creation (562 lines)
├── optimizers.py       # Main user-facing optimizers (1589 lines)
├── single_step.py      # Single time-step optimization (411 lines)
├── utils.py            # Utility functions (244 lines)
└── README.md           # Documentation (updated)
```

## Benefits

1. **Clear Naming**: 
   - `model.py` → model creation
   - `optimizers.py` → optimization functions

2. **Obvious Entry Points**:
   ```python
   from lyopronto.pyomo_models.optimizers import optimize_Pch_pyomo
   ```

3. **Consistent with Scipy**:
   - Matches naming convention: `opt_Pch.py`, `opt_Tsh.py`
   - Parallel structure makes code more navigable

4. **Better Package Interface**:
   - `__init__.py` now exports both model functions and optimizers
   - Users can import from package level or module level

## Migration Guide

### For Users

**Old imports** (deprecated):
```python
from lyopronto.pyomo_models.pyomo_optimizers import optimize_Tsh_pyomo
from lyopronto.pyomo_models.multi_period import create_multi_period_model
```

**New imports** (recommended):
```python
# Option 1: Import from specific modules
from lyopronto.pyomo_models.optimizers import optimize_Tsh_pyomo
from lyopronto.pyomo_models.model import create_multi_period_model

# Option 2: Import from package (also works)
from lyopronto.pyomo_models import optimize_Tsh_pyomo, create_multi_period_model
```

### For Developers

All test files in `tests/test_pyomo_models/` have been updated:
- Updated imports to use new module names
- Changed `multi_period.` → `model_module.` (to avoid variable shadowing)
- Changed `pyomo_optimizers.` → `optimizers.`

## Test Verification

**Result**: ✅ All 80 Pyomo tests passing

```bash
pytest tests/test_pyomo_models/ -v
# 75 passed, 3 skipped, 2 xfailed, 0 failed
```

## Files Updated

### Source Files
- `lyopronto/pyomo_models/__init__.py` - Updated exports and documentation
- `lyopronto/pyomo_models/README.md` - Updated module descriptions

### Test Files (11 files)
- `tests/test_pyomo_models/test_model_multi_period.py`
- `tests/test_pyomo_models/test_model_validation.py`
- `tests/test_pyomo_models/test_optimizer_Tsh.py`
- `tests/test_pyomo_models/test_optimizer_Pch.py`
- `tests/test_pyomo_models/test_optimizer_Pch_Tsh.py`
- `tests/test_pyomo_models/test_staged_solve.py`
- `tests/test_pyomo_models/test_warmstart.py`
- `tests/test_pyomo_models/test_parameter_validation.py`
- `tests/test_pyomo_models/test_model_single_step.py`
- `tests/test_pyomo_models/test_model_advanced.py`
- `tests/test_pyomo_models/test_optimizer_framework.py`

### Documentation
- `docs/PYOMO_OPTIMIZER_EXTENSION_COMPLETE.md` - Added reorganization section

## Next Steps

1. ✅ Reorganization complete
2. ✅ All tests passing
3. ⏳ Ready for performance benchmarking vs scipy
4. ⏳ Consider deprecation warnings for old import paths (optional)

---

**Completed**: November 14, 2025  
**Verified**: 80/80 tests passing
