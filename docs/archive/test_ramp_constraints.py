"""Test ramp-rate constraints implementation.

This script tests the adaptive ramp-rate constraints by running a single
optimization case with and without ramp constraints, comparing trajectories.
"""
import numpy as np
import matplotlib.pyplot as plt
from lyopronto.pyomo_models import optimizers as pyomo_opt

# Test parameters (baseline case from benchmarks)
vial = {'Av': 3.8, 'Ap': 3.14, 'Vfill': 2.0}
product = {'R0': 1.4, 'A1': 18.0, 'A2': 0.0, 'T_pr_crit': -25.0, 'cSolid': 0.05}
ht = {'KC': 3.3e-4, 'KP': 8.93e-4, 'KD': 0.46}
eq_cap = {'a': -0.182, 'b': 11.7}
nVial = 398
dt = 0.01

# Fixed pressure for Tsh optimization
Pchamber = {"setpt": [0.1], "dt_setpt": [1800.0], "ramp_rate": 0.5}
Tshelf = {"min": -45.0, "max": 120.0}

print("="*80)
print("RAMP-RATE CONSTRAINT TEST")
print("="*80)

# Test 1: Run WITHOUT ramp constraints (baseline)
print("\n1. Running Tsh optimization WITHOUT ramp constraints...")
result_no_ramp = pyomo_opt.optimize_Tsh_pyomo(
    vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial,
    n_elements=100,
    use_finite_differences=True,
    warmstart_scipy=False,
    tee=False,
    return_metadata=True,
    ramp_rates=None  # No constraints
)

if isinstance(result_no_ramp, dict):
    traj_no_ramp = result_no_ramp["output"]
    meta_no_ramp = result_no_ramp["metadata"]
else:
    traj_no_ramp = result_no_ramp
    meta_no_ramp = {}

print(f"   ✓ Objective time: {traj_no_ramp[-1, 0]:.2f} hr")
print(f"   ✓ Status: {meta_no_ramp.get('termination_condition', 'unknown')}")

# Test 2: Run WITH ramp constraints
print("\n2. Running Tsh optimization WITH ramp constraints (20°C/hr, initial=-35°C)...")
ramp_config = {
    'Tsh_max': 20.0,  # Maximum 20°C/hr heating/cooling rate
    'fix_initial_Tsh': -35.0  # Start at -35°C (prevent jump at t=0)
}

result_with_ramp = pyomo_opt.optimize_Tsh_pyomo(
    vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial,
    n_elements=100,
    use_finite_differences=True,
    warmstart_scipy=False,
    tee=False,
    return_metadata=True,
    ramp_rates=ramp_config
)

if isinstance(result_with_ramp, dict):
    traj_with_ramp = result_with_ramp["output"]
    meta_with_ramp = result_with_ramp["metadata"]
else:
    traj_with_ramp = result_with_ramp
    meta_with_ramp = {}

print(f"   ✓ Objective time: {traj_with_ramp[-1, 0]:.2f} hr")
print(f"   ✓ Status: {meta_with_ramp.get('termination_condition', 'unknown')}")

# Test 3: Verify ramp-rate compliance
print("\n3. Verifying ramp-rate compliance...")

time_with_ramp = traj_with_ramp[:, 0]  # hr
Tsh_with_ramp = traj_with_ramp[:, 3]   # °C

# Compute actual ramp rates
dt_values = np.diff(time_with_ramp)
dTsh_values = np.diff(Tsh_with_ramp)
actual_ramp_rates = dTsh_values / dt_values  # °C/hr

max_ramp_rate = np.max(np.abs(actual_ramp_rates))
print(f"   Maximum ramp rate: {max_ramp_rate:.2f} °C/hr")
print(f"   Specified limit: {ramp_config['Tsh_max']:.2f} °C/hr")

# Allow small numerical tolerance (1%)
if max_ramp_rate <= ramp_config['Tsh_max'] * 1.01:
    print(f"   ✓ Ramp constraint SATISFIED")
else:
    print(f"   ✗ Ramp constraint VIOLATED")

# Check initial condition
print(f"   Initial Tsh: {Tsh_with_ramp[0]:.2f} °C")
print(f"   Expected: {ramp_config['fix_initial_Tsh']:.2f} °C")
if abs(Tsh_with_ramp[0] - ramp_config['fix_initial_Tsh']) < 0.1:
    print(f"   ✓ Initial condition SATISFIED")
else:
    print(f"   ✗ Initial condition VIOLATED")

# Test 4: Compare trajectories
print("\n4. Trajectory comparison:")
print(f"   Without ramp: Initial Tsh jump = {traj_no_ramp[1, 3] - traj_no_ramp[0, 3]:.2f} °C")
print(f"   With ramp:    Initial Tsh jump = {traj_with_ramp[1, 3] - traj_with_ramp[0, 3]:.2f} °C")
print(f"   Time penalty: {(traj_with_ramp[-1, 0] - traj_no_ramp[-1, 0]) / traj_no_ramp[-1, 0] * 100:.1f}%")

# Plot comparison
print("\n5. Generating comparison plot...")
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8))

# Temperature trajectories
ax1.plot(traj_no_ramp[:, 0], traj_no_ramp[:, 3], 'b-o', label='No ramp constraint', markersize=3)
ax1.plot(traj_with_ramp[:, 0], traj_with_ramp[:, 3], 'r-^', label=f'With ramp (≤20°C/hr)', markersize=3)
ax1.axhline(-35, color='gray', linestyle='--', alpha=0.5, label='Initial Tsh')
ax1.set_xlabel('Time (hr)')
ax1.set_ylabel('Shelf Temperature (°C)')
ax1.set_title('Effect of Ramp-Rate Constraints on Temperature Trajectory')
ax1.legend()
ax1.grid(True, alpha=0.3)

# Ramp rates
if len(actual_ramp_rates) > 0:
    ax2.plot(time_with_ramp[1:], actual_ramp_rates, 'g-', label='Actual ramp rate')
    ax2.axhline(20, color='r', linestyle='--', label='Limit (20°C/hr)')
    ax2.axhline(-20, color='r', linestyle='--')
    ax2.axhline(0, color='gray', linestyle='-', alpha=0.3)
    ax2.set_xlabel('Time (hr)')
    ax2.set_ylabel('Heating Rate (°C/hr)')
    ax2.set_title('Heating Rate Compliance Check')
    ax2.legend()
    ax2.grid(True, alpha=0.3)

plt.tight_layout()
plt.savefig('ramp_constraint_test.png', dpi=150)
print(f"   ✓ Saved to: ramp_constraint_test.png")

print("\n" + "="*80)
print("TEST COMPLETE")
print("="*80)
