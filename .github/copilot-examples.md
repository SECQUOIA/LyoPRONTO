# Code Examples for AI Assistants

This file provides concrete code examples to help AI coding assistants understand common patterns in LyoPRONTO.

## Table of Contents
1. [Running Simulations](#running-simulations)
2. [Writing Tests](#writing-tests)
3. [Parsing Output](#parsing-output)
4. [Pyomo Roadmap Work](#pyomo-roadmap-work)
5. [Common Workflows](#common-workflows)

---

## Running Simulations

### Basic Primary Drying Simulation (Known Rp)

```python
from lyopronto import calc_knownRp

# Define vial and product properties
vial = {
    'Av': 3.14,      # Vial cross-sectional area (cm²)
    'Ap': 2.86,      # Product area (cm²)
    'Vfill': 3.0,    # Fill volume (mL)
}

product = {
    'R0': 1.0,       # Base resistance (cm²-hr-Torr/g)
    'A1': 20.0,      # Resistance parameter A1
    'A2': 0.5,       # Resistance parameter A2 (cm⁻¹)
    'rho_solid': 0.05,  # Solid density (g/mL)
}

# Define process parameters
Pch = 0.15       # Chamber pressure [Torr]
Tsh = -10.0      # Shelf temperature [degC]

# Run simulation
output = calc_knownRp.dry(vial, product, Pch, Tsh, Tstep=100)

# output is a numpy array with shape (n_timepoints, 7)
print(f"Drying completed in {output[-1, 0]:.2f} hours")
```

### Primary Drying with Unknown Rp

```python
from lyopronto import calc_unknownRp

# Same vial setup as above
vial = {'Av': 3.14, 'Ap': 2.86, 'Vfill': 3.0}

# Define heat transfer parameters (instead of Rp parameters)
KC = 2.5e-4      # Heat transfer constant
KP = 0.0         # Pressure-dependent term
KD = 0.0         # Distance-dependent term

# Run with unknown resistance
output = calc_unknownRp.dry(vial, KC, KP, KD, Pch, Tsh, Tstep=100)
```

### Optimization Example (scipy-based)

```python
from lyopronto import opt_Pch_Tsh

# Define constraints
constraints = {
    'T_max': -15.0,     # Maximum product temperature [degC]
    'Pch_min': 0.05,    # Minimum chamber pressure [Torr]
    'Pch_max': 0.5,     # Maximum chamber pressure [Torr]
    'Tsh_min': -50.0,   # Minimum shelf temperature [degC]
    'Tsh_max': 30.0,    # Maximum shelf temperature [degC]
}

# Run optimization
result = opt_Pch_Tsh.optimize(vial, product, constraints)

# Extract optimal conditions
Pch_opt = result['Pch']    # Optimal pressure [Torr]
Tsh_opt = result['Tsh']    # Optimal shelf temperature [degC]
t_dry = result['time']     # Drying time [hr]
```

---

## Writing Tests

### Unit Test for Physics Function

```python
import pytest
from lyopronto.functions import Vapor_pressure

class TestVaporPressure:
    """Tests for vapor pressure calculations."""
    
    def test_vapor_pressure_at_freezing_point(self):
        """Test vapor pressure at water's freezing point (0°C).
        
        At 0°C, water vapor pressure should be approximately 4.58 Torr.
        """
        T = 0.0
        P = Vapor_pressure(T)
        
        assert P == pytest.approx(4.58, rel=0.01), \
            f"Expected ~4.58 Torr at 0°C, got {P:.2f}"
    
    def test_vapor_pressure_increases_with_temperature(self):
        """Test that vapor pressure increases monotonically with temperature."""
        temperatures = [-40, -30, -20, -10, 0]
        pressures = [Vapor_pressure(T) for T in temperatures]
        
        # Check monotonic increase
        for i in range(len(pressures) - 1):
            assert pressures[i+1] > pressures[i], \
                f"Pressure not monotonic: P({temperatures[i]})={pressures[i]:.3f}, " \
                f"P({temperatures[i+1]})={pressures[i+1]:.3f}"
```

### Integration Test Using Fixtures

```python
import pytest
import numpy as np
from lyopronto import calc_knownRp
from tests.conftest import assert_physically_reasonable_output

class TestPrimaryDrying:
    """Integration tests for primary drying calculator."""
    
    def test_standard_case(self, standard_setup):
        """Test primary drying with standard parameters.
        
        Uses the standard_setup fixture from conftest.py.
        """
        vial, product, Pch, Tsh = standard_setup
        
        # Run simulation
        output = calc_knownRp.dry(vial, product, Pch, Tsh)
        
        # Validate output structure
        assert output.shape[1] == 7, "Output should have 7 columns"
        assert len(output) > 0, "Output should not be empty"
        
        # Check physical reasonableness
        assert_physically_reasonable_output(output)
        
        # Check drying completion
        final_dried = output[-1, 6]  # percent dried at end
        assert final_dried >= 99, \
            f"Expected at least 99% dried, got {final_dried:.1f}%"
    
    def test_mass_balance(self, standard_setup):
        """Verify mass balance between sublimation and product consumption."""
        vial, product, Pch, Tsh = standard_setup
        output = calc_knownRp.dry(vial, product, Pch, Tsh)
        
        # Calculate initial mass
        from lyopronto.constant import rho_ice
        from lyopronto.functions import Lpr0_FUN
        Lpr0 = Lpr0_FUN(vial['Vfill'], vial['Ap'], product['rho_solid'])
        m_initial = rho_ice * vial['Ap'] * Lpr0  # grams
        
        # Integrate sublimation flux (convert kg/hr/m² to g)
        time = output[:, 0]
        flux = output[:, 5]  # kg/hr/m²
        total_sublimed = np.trapz(flux, time) * vial['Ap'] * 1e4 * 1000  # g
        
        # Check balance (within 2% tolerance)
        error = abs(total_sublimed - m_initial) / m_initial
        assert error < 0.02, \
            f"Mass balance error {error*100:.1f}% exceeds 2% tolerance"
```

### Parametric Test

```python
import pytest
from lyopronto import calc_knownRp

class TestParametricStudy:
    """Test behavior across parameter ranges."""
    
    @pytest.mark.parametrize("Pch,expected_range", [
        (0.08, (8, 12)),   # Low pressure → longer drying
        (0.15, (5, 8)),    # Medium pressure
        (0.30, (3, 6)),    # High pressure → shorter drying
    ])
    def test_pressure_effect_on_drying_time(self, standard_setup, Pch, expected_range):
        """Test that drying time decreases with increasing pressure."""
        vial, product, _, Tsh = standard_setup
        
        output = calc_knownRp.dry(vial, product, Pch, Tsh)
        drying_time = output[-1, 0]
        
        min_time, max_time = expected_range
        assert min_time <= drying_time <= max_time, \
            f"At Pch={Pch} Torr, expected drying time in [{min_time}, {max_time}] hr, " \
            f"got {drying_time:.1f} hr"
```

---

## Parsing Output

### Extract and Plot Results

```python
import numpy as np
import matplotlib.pyplot as plt
from lyopronto import calc_knownRp

# Run simulation
vial = {'Av': 3.14, 'Ap': 2.86, 'Vfill': 3.0}
product = {'R0': 1.0, 'A1': 20.0, 'A2': 0.5, 'rho_solid': 0.05}
output = calc_knownRp.dry(vial, product, Pch=0.15, Tsh=-10)

# Extract columns (REMEMBER UNITS!)
time = output[:, 0]           # hours
Tsub = output[:, 1]           # °C
Tbot = output[:, 2]           # °C
Tsh = output[:, 3]            # °C (shelf setpoint)
Pch = output[:, 4]            # mTorr (NOT Torr!)
flux = output[:, 5]           # kg/hr/m²
percent_dried = output[:, 6]  # percent dried, 0-100

# Convert units for plotting
Pch_torr = Pch / 1000         # Convert mTorr to Torr

# Create plots
fig, axes = plt.subplots(2, 2, figsize=(12, 8))

# Temperature profile
axes[0, 0].plot(time, Tsub, label='Sublimation Front')
axes[0, 0].plot(time, Tbot, label='Vial Bottom')
axes[0, 0].set_xlabel('Time (hr)')
axes[0, 0].set_ylabel('Temperature (°C)')
axes[0, 0].legend()
axes[0, 0].grid(True)

# Flux profile (note: non-monotonic!)
axes[0, 1].plot(time, flux)
axes[0, 1].set_xlabel('Time (hr)')
axes[0, 1].set_ylabel('Sublimation Flux (kg/hr/m²)')
axes[0, 1].grid(True)

# Drying progress
axes[1, 0].plot(time, percent_dried)
axes[1, 0].set_xlabel('Time (hr)')
axes[1, 0].set_ylabel('% Dried')
axes[1, 0].set_ylim([0, 105])
axes[1, 0].grid(True)

# Pressure (converted to Torr)
axes[1, 1].plot(time, Pch_torr)
axes[1, 1].set_xlabel('Time (hr)')
axes[1, 1].set_ylabel('Chamber Pressure (Torr)')
axes[1, 1].grid(True)

plt.tight_layout()
plt.savefig('drying_profile.png', dpi=300)
```

### Calculate Key Metrics

```python
def analyze_drying_output(output):
    """Extract key metrics from simulation output.
    
    Args:
        output (np.ndarray): Simulation output array (n, 7)
        
    Returns:
        dict: Dictionary of key metrics
    """
    metrics = {}
    
    # Time metrics
    metrics['total_time'] = output[-1, 0]  # hours
    time_90 = np.interp(90.0, output[:, 6], output[:, 0])
    metrics['time_to_90pct'] = time_90
    
    # Temperature metrics
    metrics['min_Tsub'] = np.min(output[:, 1])  # °C
    metrics['max_Tsub'] = np.max(output[:, 1])  # °C
    metrics['final_Tbot'] = output[-1, 2]       # °C
    
    # Flux metrics (remember: non-monotonic!)
    metrics['max_flux'] = np.max(output[:, 5])  # kg/hr/m²
    metrics['avg_flux'] = np.mean(output[:, 5])  # kg/hr/m²
    
    # Find when flux peaks
    idx_max_flux = np.argmax(output[:, 5])
    metrics['time_peak_flux'] = output[idx_max_flux, 0]  # hours
    metrics['percent_dried_at_peak_flux'] = output[idx_max_flux, 6]
    
    return metrics

# Usage
metrics = analyze_drying_output(output)
print(f"Drying completed in {metrics['total_time']:.2f} hours")
print(f"Peak flux: {metrics['max_flux']:.2f} kg/hr/m² at {metrics['time_peak_flux']:.2f} hr")
print(f"Temperature range: {metrics['min_Tsub']:.1f} to {metrics['max_Tsub']:.1f} °C")
```

---

## Pyomo Roadmap Work

No `lyopronto/pyomo_models/` package is tracked on `main`. Do not generate
Pyomo implementation docs or examples unless the same PR adds tracked code,
optional dependency handling, runnable examples, and Pyomo-marked tests.

Use GitHub issue #80 and its child issues for Pyomo planning. Current shipped
examples should continue to use the SciPy-backed APIs shown in this file.

---

## Common Workflows

### Complete Workflow: Simulate → Optimize → Re-simulate

```python
from lyopronto import calc_knownRp, opt_Pch_Tsh
import numpy as np

# 1. Baseline simulation with nominal conditions
print("Running baseline simulation...")
vial = {'Av': 3.14, 'Ap': 2.86, 'Vfill': 3.0}
product = {'R0': 1.0, 'A1': 20.0, 'A2': 0.5, 'rho_solid': 0.05}
Pch_nominal = 0.15
Tsh_nominal = -10.0

baseline = calc_knownRp.dry(vial, product, Pch_nominal, Tsh_nominal)
baseline_time = baseline[-1, 0]
print(f"Baseline drying time: {baseline_time:.2f} hours")

# 2. Optimize process conditions
print("\nOptimizing process...")
constraints = {
    'T_max': -15.0,
    'Pch_min': 0.05,
    'Pch_max': 0.5,
    'Tsh_min': -50.0,
    'Tsh_max': 30.0,
}

result = opt_Pch_Tsh.optimize(vial, product, constraints)
Pch_opt = result['Pch']
Tsh_opt = result['Tsh']
print(f"Optimal conditions: Pch={Pch_opt:.3f} Torr, Tsh={Tsh_opt:.2f} °C")

# 3. Re-simulate with optimized conditions
print("\nRe-simulating with optimized conditions...")
optimized = calc_knownRp.dry(vial, product, Pch_opt, Tsh_opt)
optimized_time = optimized[-1, 0]
print(f"Optimized drying time: {optimized_time:.2f} hours")

# 4. Calculate improvement
improvement = (baseline_time - optimized_time) / baseline_time * 100
print(f"\nTime reduction: {improvement:.1f}%")

# 5. Verify constraints were satisfied
max_Tsub = np.max(optimized[:, 1])
print(f"Maximum product temperature: {max_Tsub:.2f} °C (limit: {constraints['T_max']:.2f} °C)")
assert max_Tsub <= constraints['T_max'] + 0.5, "Temperature constraint violated!"
```

### Parametric Study Workflow

```python
import numpy as np
import pandas as pd
from lyopronto import calc_knownRp

# Define parameter ranges
pressures = [0.08, 0.12, 0.15, 0.20, 0.30]
temperatures = [-20, -15, -10, -5, 0]

# Run parametric study
results = []
for Pch in pressures:
    for Tsh in temperatures:
        output = calc_knownRp.dry(vial, product, Pch, Tsh)
        
        results.append({
            'Pch_torr': Pch,
            'Tsh_C': Tsh,
            'drying_time_hr': output[-1, 0],
            'max_flux_kg_hr_m2': np.max(output[:, 5]),
            'min_Tsub_C': np.min(output[:, 1]),
        })

# Convert to DataFrame for analysis
df = pd.DataFrame(results)
print(df.to_string(index=False))

# Find optimal (shortest time with Tsub > -20°C)
df_filtered = df[df['min_Tsub_C'] > -20]
optimal = df_filtered.loc[df_filtered['drying_time_hr'].idxmin()]
print(f"\nOptimal conditions: Pch={optimal['Pch_torr']} Torr, Tsh={optimal['Tsh_C']} °C")
```

---

## Notes for AI Assistants

### When Writing New Code:
1. **Always check units** - See the Output Format section
2. **Use fixtures** - Check `conftest.py` for available fixtures
3. **Follow naming** - Use physics variable names from copilot-instructions.md
4. **Test first** - Write tests before implementation (TDD)
5. **Handle edge cases** - Very low temps can cause Tbot < Tsub

### When Debugging:
1. **Check output shape** - Should be (n, 7) with n >= 1
2. **Check units** - Pch in mTorr (not Torr), dried as percent from 0 to 100
3. **Check tolerances** - Mass balance within 2% is acceptable
4. **Check flux** - Non-monotonic is expected, not a bug
5. **Run tests** - `pytest tests/ -v` to validate changes

### When Optimizing:
1. **Use current APIs** - `opt_Pch.py`, `opt_Tsh.py`, and `opt_Pch_Tsh.py`
   are the tracked optimization implementations.
2. **Set bounds** - All optimizer inputs need physically meaningful bounds.
3. **Validate** - Compare optimized trajectories against regression fixtures
   and physical constraints.
