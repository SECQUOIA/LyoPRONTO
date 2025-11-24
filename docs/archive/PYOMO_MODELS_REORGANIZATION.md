# Pyomo Models Directory Reorganization

## Current Structure (Confusing)
- `single_step.py` - Single time-step model (411 lines) - Not actively used
- `multi_period.py` - Multi-period DAE model (562 lines) - Core model creation
- `pyomo_optimizers.py` - Main optimizer functions (1589 lines) - What users call
- `utils.py` - Utilities (244 lines)

## Proposed Structure (Clear)
- `model.py` - Multi-period model creation (renamed from multi_period.py)
- `optimizers.py` - User-facing optimizer functions (renamed from pyomo_optimizers.py)
- `utils.py` - Keep as is
- `single_step/` - Move to subdirectory (optional/deprecated)

## Benefits
1. Clear naming: `model.py` = model creation, `optimizers.py` = optimization
2. Main entry point is obvious: `from lyopronto.pyomo_models.optimizers import optimize_Pch_pyomo`
3. Matches scipy structure better (opt_Pch.py, opt_Tsh.py, etc.)
4. Reduces confusion about what "multi_period" and "pyomo_optimizers" mean

## Migration
1. Rename files
2. Update imports in optimizers.py
3. Update __init__.py exports
4. Update all test imports
5. Update documentation
