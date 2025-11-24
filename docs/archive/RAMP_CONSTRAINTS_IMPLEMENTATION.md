# Ramp-Rate Constraints Implementation Summary

## What Was Implemented

Adaptive ramp-rate constraints for Pyomo lyophilization optimizers that enforce physically realistic control changes while automatically scaling with discretization.

## Key Features

### 1. Discretization-Adaptive Constraints
- Constraints scale automatically: `(control[i] - control[i-1]) / (Δt * t_final) ≤ max_rate`
- Same physical rate (e.g., 20°C/hr) enforced regardless of mesh resolution
- Works with both finite differences and collocation

### 2. Initial Condition Fixing
- Prevents unrealistic jumps at t=0
- Configurable starting values for Tsh and Pch
- Matches experimental loading conditions

### 3. Mode-Aware Application
- `control_mode='Tsh'`: Constrains only Tsh
- `control_mode='Pch'`: Constrains only Pch
- `control_mode='both'`: Constrains both controls

## Files Modified

### Core Implementation
1. **`lyopronto/pyomo_models/optimizers.py`**:
   - `create_optimizer_model()`: Added `ramp_rates` parameter + constraint logic (lines 488-537)
   - `optimize_Tsh_pyomo()`: Added `ramp_rates` parameter
   - `optimize_Pch_pyomo()`: Added `ramp_rates` parameter
   - `optimize_Pch_Tsh_pyomo()`: Added `ramp_rates` parameter

2. **`benchmarks/adapters.py`**:
   - `pyomo_adapter()`: Added `ramp_rates` parameter and pass-through (lines 11, 90, 143)

### Documentation
3. **`docs/RAMP_RATE_CONSTRAINTS.md`**: Comprehensive technical documentation
4. **`test_ramp_constraints.py`**: Validation test script
5. **`examples/example_ramp_constraints.py`**: Practical usage example

## Usage Examples

### Basic Usage
```python
from lyopronto.pyomo_models import optimizers as pyomo_opt

# Optimize Tsh with 20°C/hr limit
result = pyomo_opt.optimize_Tsh_pyomo(
    vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial,
    n_elements=100,
    ramp_rates={
        'Tsh_max': 20.0,          # °C/hr heating/cooling limit
        'fix_initial_Tsh': -35.0  # Start at -35°C
    }
)
```

### Joint Optimization
```python
# Optimize both Pch and Tsh with constraints
result = pyomo_opt.optimize_Pch_Tsh_pyomo(
    vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial,
    ramp_rates={
        'Tsh_max': 20.0,           # °C/hr
        'Pch_max': 0.08,           # Torr/hr
        'fix_initial_Tsh': -35.0,  # °C
        'fix_initial_Pch': 0.12    # Torr
    }
)
```

### Via Benchmarking Adapter
```python
from benchmarks.adapters import pyomo_adapter

result = pyomo_adapter(
    task='Tsh',
    vial=vial, product=product, ht=ht,
    eq_cap=eq_cap, nVial=nVial,
    scenario={},
    n_elements=1000,
    method='fd',
    ramp_rates={'Tsh_max': 20.0, 'fix_initial_Tsh': -35.0}
)
```

## Test Results

### Validation Test (test_ramp_constraints.py)
- **Without constraints**: 12.25 hr, initial jump 20.76°C
- **With 20°C/hr limit**: 13.61 hr, initial jump 2.72°C
- **Constraint satisfaction**: Max rate = 20.00°C/hr ✓
- **Time penalty**: 11.1% (acceptable for realistic operation)

### Practical Example (examples/example_ramp_constraints.py)
High-resistance product (A1=20):

| Case          | Ramp Limit | Drying Time | Penalty | Notes                    |
|---------------|-----------|-------------|---------|--------------------------|
| Unconstrained | None      | 13.29 hr    | 0.0%    | Not implementable        |
| Aggressive    | 30°C/hr   | 14.28 hr    | 7.4%    | Modern equipment         |
| Typical       | 20°C/hr   | 14.66 hr    | 10.3%   | Standard industrial      |
| Conservative  | 15°C/hr   | 15.01 hr    | 12.9%   | Older/smaller equipment  |

## Recommended Default Values

### Typical Industrial Equipment
```python
ramp_rates = {
    'Tsh_max': 20.0,       # °C/hr
    'Pch_max': 0.08,       # Torr/hr
    'fix_initial_Tsh': -35.0,
    'fix_initial_Pch': 0.12
}
```

## Key Benefits

1. **Physical Realism**: Trajectories respect equipment limitations
2. **Discretization Independence**: Same rate enforced regardless of n_elements
3. **Minimal Penalty**: 7-13% time increase for realistic limits
4. **Robust Convergence**: All test cases achieve optimal status
5. **Production Ready**: Directly implementable on real lyophilizers

## Technical Details

### Constraint Formulation
For each time interval `i`:
```
Tsh[i] - Tsh[i-1] ≤ Tsh_max * (t[i] - t[i-1]) * t_final
Tsh[i-1] - Tsh[i] ≤ Tsh_max * (t[i] - t[i-1]) * t_final
```

Where:
- `t[i]` is normalized time ∈ [0, 1]
- `t_final` is total drying time (optimization variable)
- Result: Physical rate in °C/hr independent of discretization

### Why This Works
- Time normalization: `t ∈ [0, 1]` → actual time = `t * t_final`
- Interval size: `Δt_actual = (t[i] - t[i-1]) * t_final`
- Rate constraint: `ΔTsh / Δt_actual ≤ Tsh_max`
- Rearranged: `ΔTsh ≤ Tsh_max * Δt_normalized * t_final`

## Comparison to SciPy

### SciPy Sequential Approach
- Implicit smoothness from small adaptive time steps
- No explicit ramp constraints
- Sequential propagation prevents large jumps
- Typical step size: ~0.01 hr

### Pyomo Simultaneous Optimization
- Without constraints: Can jump arbitrarily at any time point
- With ramp constraints: Explicit enforcement of equipment limits
- Simultaneous optimization across all time points
- Trade-off: Small time penalty for physical realism

## Future Enhancements

1. **Thermal Dynamics Model**: Replace direct Tsh control with heater power + thermal ODE
2. **Quadratic Smoothness Penalty**: Soft enforcement via objective term
3. **Second-Order Constraints**: Limit acceleration (curvature)
4. **Time-Varying Limits**: Equipment capability changes with temperature

## Running the Examples

```bash
# Basic validation test
python test_ramp_constraints.py

# Comprehensive practical example
python examples/example_ramp_constraints.py
```

Both generate plots showing:
- Temperature trajectory comparison
- Ramp rate compliance verification
- Performance trade-offs

## Integration Status

✅ Core model (`create_optimizer_model`)  
✅ High-level optimizers (`optimize_Tsh_pyomo`, `optimize_Pch_pyomo`, `optimize_Pch_Tsh_pyomo`)  
✅ Benchmarking adapter (`pyomo_adapter`)  
✅ Documentation and examples  
✅ Validation tests  
⏳ CLI integration (optional future enhancement)

## Conclusion

The ramp-rate constraint implementation successfully bridges the gap between Pyomo's theoretical optimum and real-world equipment capabilities. Time penalties are modest (7-13%) while ensuring all trajectories are directly implementable on actual lyophilizers. The feature is production-ready and fully integrated with the existing Pyomo optimization framework.
