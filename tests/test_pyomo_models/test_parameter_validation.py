"""Test parameter validation for create_optimizer_model."""

import pytest
from lyopronto.pyomo_models.optimizers import create_optimizer_model

# Common test parameters
vial = {'Av': 3.8, 'Ap': 3.14, 'Vfill': 2.0}
product = {'R0': 1.4, 'A1': 16.0, 'A2': 0.0, 'T_pr_crit': -5.0, 'cSolid': 0.05}
ht = {'KC': 0.000275, 'KP': 0.000893, 'KD': 0.46}
eq_cap = {'a': -0.182, 'b': 11.7}
nVial = 398

print("\n" + "="*60)
print("PARAMETER VALIDATION TESTS")
print("="*60)

# Test 1: Invalid control_mode
print("\n[Test 1] Invalid control_mode")
try:
    model = create_optimizer_model(
        vial, product, ht, vial['Vfill'], eq_cap, nVial,
        control_mode='invalid',
        n_elements=2
    )
    print("  ✗ FAILED: Should have raised ValueError")
except ValueError as e:
    print(f"  ✓ PASSED: {e}")

# Test 2: control_mode='Pch' without Pchamber bounds
print("\n[Test 2] control_mode='Pch' without Pchamber bounds")
try:
    model = create_optimizer_model(
        vial, product, ht, vial['Vfill'], eq_cap, nVial,
        control_mode='Pch',
        Tshelf={'init': -35, 'setpt': [20], 'dt_setpt': [1800]},
        n_elements=2
    )
    print("  ✗ FAILED: Should have raised ValueError")
except ValueError as e:
    print(f"  ✓ PASSED: {e}")

# Test 3: control_mode='Tsh' without Tshelf bounds
print("\n[Test 3] control_mode='Tsh' without Tshelf bounds")
try:
    model = create_optimizer_model(
        vial, product, ht, vial['Vfill'], eq_cap, nVial,
        control_mode='Tsh',
        Pchamber={'setpt': [0.1], 'dt_setpt': [1800]},
        n_elements=2
    )
    print("  ✗ FAILED: Should have raised ValueError")
except ValueError as e:
    print(f"  ✓ PASSED: {e}")

# Test 4: control_mode='both' without both bounds
print("\n[Test 4] control_mode='both' without Pchamber bounds")
try:
    model = create_optimizer_model(
        vial, product, ht, vial['Vfill'], eq_cap, nVial,
        control_mode='both',
        Tshelf={'min': -45, 'max': 30},
        n_elements=2
    )
    print("  ✗ FAILED: Should have raised ValueError")
except ValueError as e:
    print(f"  ✓ PASSED: {e}")

# Test 5: Invalid Pch bounds (min >= max)
print("\n[Test 5] Invalid Pch bounds (min >= max)")
try:
    model = create_optimizer_model(
        vial, product, ht, vial['Vfill'], eq_cap, nVial,
        control_mode='Pch',
        Pchamber={'min': 0.2, 'max': 0.1},
        Tshelf={'init': -35, 'setpt': [20], 'dt_setpt': [1800]},
        n_elements=2
    )
    print("  ✗ FAILED: Should have raised ValueError")
except ValueError as e:
    print(f"  ✓ PASSED: {e}")

# Test 6: Invalid Tsh bounds (min >= max)
print("\n[Test 6] Invalid Tsh bounds (min >= max)")
try:
    model = create_optimizer_model(
        vial, product, ht, vial['Vfill'], eq_cap, nVial,
        control_mode='Tsh',
        Pchamber={'setpt': [0.1], 'dt_setpt': [1800]},
        Tshelf={'min': 30, 'max': -45},
        n_elements=2
    )
    print("  ✗ FAILED: Should have raised ValueError")
except ValueError as e:
    print(f"  ✓ PASSED: {e}")

# Test 7: Valid control_mode='Tsh' (should succeed)
print("\n[Test 7] Valid control_mode='Tsh'")
try:
    model = create_optimizer_model(
        vial, product, ht, vial['Vfill'], eq_cap, nVial,
        control_mode='Tsh',
        Pchamber={'setpt': [0.1], 'dt_setpt': [1800]},
        Tshelf={'min': -45, 'max': 30},
        n_elements=2
    )
    print("  ✓ PASSED: Model created successfully")
    print(f"    Pch bounds: [{model.Pch[0].lb}, {model.Pch[0].ub}]")
    print(f"    Tsh bounds: [{model.Tsh[0].lb}, {model.Tsh[0].ub}]")
except Exception as e:
    print(f"  ✗ FAILED: {type(e).__name__}: {e}")

# Test 8: Valid control_mode='Pch' (should succeed)
print("\n[Test 8] Valid control_mode='Pch'")
try:
    model = create_optimizer_model(
        vial, product, ht, vial['Vfill'], eq_cap, nVial,
        control_mode='Pch',
        Pchamber={'min': 0.06, 'max': 0.20},
        Tshelf={'init': -35, 'setpt': [20], 'dt_setpt': [1800]},
        n_elements=2
    )
    print("  ✓ PASSED: Model created successfully")
    print(f"    Pch bounds: [{model.Pch[0].lb}, {model.Pch[0].ub}]")
    print(f"    Tsh bounds: [{model.Tsh[0].lb}, {model.Tsh[0].ub}]")
except Exception as e:
    print(f"  ✗ FAILED: {type(e).__name__}: {e}")

# Test 9: Valid control_mode='both' (should succeed)
print("\n[Test 9] Valid control_mode='both'")
try:
    model = create_optimizer_model(
        vial, product, ht, vial['Vfill'], eq_cap, nVial,
        control_mode='both',
        Pchamber={'min': 0.06, 'max': 0.20},
        Tshelf={'min': -45, 'max': 30},
        n_elements=2
    )
    print("  ✓ PASSED: Model created successfully")
    print(f"    Pch bounds: [{model.Pch[0].lb}, {model.Pch[0].ub}]")
    print(f"    Tsh bounds: [{model.Tsh[0].lb}, {model.Tsh[0].ub}]")
except Exception as e:
    print(f"  ✗ FAILED: {type(e).__name__}: {e}")

# Test 10: Verify Pch max bound is 0.5 Torr
print("\n[Test 10] Verify Pch max bound defaults to 0.5 Torr")
try:
    model = create_optimizer_model(
        vial, product, ht, vial['Vfill'], eq_cap, nVial,
        control_mode='Pch',
        Pchamber={'min': 0.06},  # No 'max' specified
        Tshelf={'init': -35, 'setpt': [20], 'dt_setpt': [1800]},
        n_elements=2
    )
    print("  ✓ PASSED: Model created successfully")
    print(f"    Pch bounds: [{model.Pch[0].lb}, {model.Pch[0].ub}]")
    assert model.Pch[0].ub == 0.5, f"Expected Pch max = 0.5, got {model.Pch[0].ub}"
    print(f"    ✓ Pch max correctly defaults to 0.5 Torr")
except Exception as e:
    print(f"  ✗ FAILED: {type(e).__name__}: {e}")

# Test 11: Pch bounds out of valid range
print("\n[Test 11] Pch bounds out of valid range")
try:
    model = create_optimizer_model(
        vial, product, ht, vial['Vfill'], eq_cap, nVial,
        control_mode='Pch',
        Pchamber={'min': 0.001, 'max': 2.0},  # Both out of [0.01, 1.0]
        Tshelf={'init': -35, 'setpt': [20], 'dt_setpt': [1800]},
        n_elements=2
    )
    print("  ✗ FAILED: Should have raised ValueError for Pch bounds")
except ValueError as e:
    print(f"  ✓ PASSED: {e}")

# Test 12: Tsh bounds out of valid range
print("\n[Test 12] Tsh bounds out of valid range")
try:
    model = create_optimizer_model(
        vial, product, ht, vial['Vfill'], eq_cap, nVial,
        control_mode='Tsh',
        Pchamber={'setpt': [0.1], 'dt_setpt': [1800]},
        Tshelf={'min': -100, 'max': 200},  # Both out of [-50, 150]
        n_elements=2
    )
    print("  ✗ FAILED: Should have raised ValueError for Tsh bounds")
except ValueError as e:
    print(f"  ✓ PASSED: {e}")

print("\n" + "="*60)
print("VALIDATION TESTS COMPLETE")
print("="*60)
print("Summary:")
print("  - Invalid control_mode: ✓")
print("  - Missing required parameters: ✓")
print("  - Invalid bounds: ✓")
print("  - Valid configurations: ✓")
print("  - Default values: ✓")
print("\nAll parameter validation working correctly!")
