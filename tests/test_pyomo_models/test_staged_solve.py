"""Test script for staged solve framework."""

import numpy as np
from lyopronto.pyomo_models.optimizers import optimize_Tsh_pyomo

# Test parameters (matching test fixtures exactly)
vial = {
    'Av': 3.8,
    'Ap': 3.14,
    'Vfill': 2.0
}

product = {
    'T_pr_crit': -5.0,
    'cSolid': 0.05,
    'R0': 1.4,
    'A1': 16.0,
    'A2': 0.0
}

ht = {
    'KC': 0.000275,
    'KP': 0.000893,
    'KD': 0.46
}

Pchamber = {
    'setpt': np.array([0.15]),
    'dt_setpt': np.array([1800]),
    'ramp_rate': 0.5,
    'time': [0]
}

Tshelf = {
    'min': -45.0,
    'max': 120.0,
    'init': -35.0,
    'setpt': np.array([120.0]),
    'dt_setpt': np.array([1800]),
    'ramp_rate': 1.0
}

eq_cap = {
    'a': -0.182,
    'b': 11.7
}

nVial = 398
dt = 0.01

print("="*70)
print("TESTING STAGED SOLVE FRAMEWORK")
print("="*70)

# Run with warmstart and staged solve
print("\n\nRunning optimize_Tsh_pyomo with staged solve...\n")
output = optimize_Tsh_pyomo(
    vial=vial,
    product=product,
    ht=ht,
    Pchamber=Pchamber,
    Tshelf=Tshelf,
    dt=dt,
    eq_cap=eq_cap,
    nVial=nVial,
    n_elements=20,  # More elements to better match scipy resolution (214 points)
    n_collocation=2,
    warmstart_scipy=True,
    solver='ipopt',
    tee=True,  # Show solver output
    simulation_mode=False
)

print("\n" + "="*70)
print("RESULTS SUMMARY")
print("="*70)
print(f"Output shape: {output.shape}")
print(f"Final time: {output[-1, 0]:.3f} hr")
print(f"Final Tsub: {output[-1, 1]:.2f} °C")
print(f"Final fraction dried: {output[-1, 6]:.4f}")
print(f"Max Tsub: {np.max(output[:, 1]):.2f} °C (limit: -5.0 °C)")

# Check key constraints
critical_temp_satisfied = np.all(output[:, 1] <= -4.5)
drying_complete = output[-1, 6] >= 0.99
Pch_fixed = np.allclose(output[:, 4], 150.0, rtol=0.01)  # 150 mTorr

print(f"\n✓ Critical temperature satisfied: {critical_temp_satisfied}")
print(f"✓ Drying complete (≥99%): {drying_complete}")
print(f"✓ Chamber pressure fixed: {Pch_fixed}")

if critical_temp_satisfied and drying_complete:
    print("\n🎉 STAGED SOLVE SUCCESSFUL!")
else:
    print("\n⚠️  Some constraints not satisfied")

print("="*70)
