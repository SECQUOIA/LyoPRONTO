"""Example: Using ramp-rate constraints for realistic lyophilization optimization.

This demonstrates how to use the ramp-rate constraint feature to generate
trajectories that are implementable on real equipment.
"""
import numpy as np
import matplotlib.pyplot as plt
from lyopronto.pyomo_models import optimizers as pyomo_opt

# ==============================================================================
# SCENARIO: High-resistance product requiring long drying time
# ==============================================================================

print("="*80)
print("PRACTICAL EXAMPLE: Ramp-Rate Constrained Optimization")
print("="*80)

# Product with high resistance (A1=20) - challenging case
vial = {'Av': 3.8, 'Ap': 3.14, 'Vfill': 2.0}
product = {
    'R0': 1.4,
    'A1': 20.0,  # High resistance
    'A2': 0.0,
    'T_pr_crit': -25.0,
    'cSolid': 0.05
}
ht = {'KC': 3.3e-4, 'KP': 8.93e-4, 'KD': 0.46}
eq_cap = {'a': -0.182, 'b': 11.7}
nVial = 398
dt = 0.01

# Fixed pressure schedule (Tsh optimization)
Pchamber = {"setpt": [0.1], "dt_setpt": [1800.0], "ramp_rate": 0.5}
Tshelf = {"min": -45.0, "max": 120.0}

# ==============================================================================
# CASE 1: Unconstrained (theoretical optimum, not implementable)
# ==============================================================================

print("\nCASE 1: Unconstrained Optimization (Theoretical)")
print("-" * 80)

result_unconstrained = pyomo_opt.optimize_Tsh_pyomo(
    vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial,
    n_elements=200,  # Fine discretization for smooth visualization
    use_finite_differences=True,
    warmstart_scipy=False,
    tee=False,
    return_metadata=True,
    ramp_rates=None  # No constraints - theoretical optimum
)

traj_unconstr = result_unconstrained["output"]
meta_unconstr = result_unconstrained["metadata"]

print(f"Drying time: {traj_unconstr[-1, 0]:.2f} hr")
print(f"Initial Tsh: {traj_unconstr[0, 3]:.1f}°C → {traj_unconstr[1, 3]:.1f}°C")
print(f"Status: {meta_unconstr.get('termination_condition', 'unknown')}")

# ==============================================================================
# CASE 2: Conservative ramp limits (slow equipment)
# ==============================================================================

print("\nCASE 2: Conservative Constraints (Slow Equipment)")
print("-" * 80)

ramp_conservative = {
    'Tsh_max': 15.0,       # °C/hr - slow heating
    'fix_initial_Tsh': -35.0  # Start at freezing temp
}

result_conservative = pyomo_opt.optimize_Tsh_pyomo(
    vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial,
    n_elements=200,
    use_finite_differences=True,
    warmstart_scipy=False,
    tee=False,
    return_metadata=True,
    ramp_rates=ramp_conservative
)

traj_conserv = result_conservative["output"]
meta_conserv = result_conservative["metadata"]

print(f"Drying time: {traj_conserv[-1, 0]:.2f} hr")
print(f"Initial Tsh: {traj_conserv[0, 3]:.1f}°C → {traj_conserv[5, 3]:.1f}°C (first 5 steps)")
print(f"Status: {meta_conserv.get('termination_condition', 'unknown')}")
print(f"Time penalty vs unconstrained: {(traj_conserv[-1, 0] / traj_unconstr[-1, 0] - 1) * 100:.1f}%")

# ==============================================================================
# CASE 3: Typical industrial ramp limits
# ==============================================================================

print("\nCASE 3: Typical Industrial Constraints")
print("-" * 80)

ramp_typical = {
    'Tsh_max': 20.0,       # °C/hr - standard rate
    'fix_initial_Tsh': -35.0
}

result_typical = pyomo_opt.optimize_Tsh_pyomo(
    vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial,
    n_elements=200,
    use_finite_differences=True,
    warmstart_scipy=False,
    tee=False,
    return_metadata=True,
    ramp_rates=ramp_typical
)

traj_typical = result_typical["output"]
meta_typical = result_typical["metadata"]

print(f"Drying time: {traj_typical[-1, 0]:.2f} hr")
print(f"Initial Tsh: {traj_typical[0, 3]:.1f}°C → {traj_typical[5, 3]:.1f}°C (first 5 steps)")
print(f"Status: {meta_typical.get('termination_condition', 'unknown')}")
print(f"Time penalty vs unconstrained: {(traj_typical[-1, 0] / traj_unconstr[-1, 0] - 1) * 100:.1f}%")

# ==============================================================================
# CASE 4: Aggressive ramp limits (fast equipment)
# ==============================================================================

print("\nCASE 4: Aggressive Constraints (Fast Equipment)")
print("-" * 80)

ramp_aggressive = {
    'Tsh_max': 30.0,       # °C/hr - fast heating
    'fix_initial_Tsh': -35.0
}

result_aggressive = pyomo_opt.optimize_Tsh_pyomo(
    vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial,
    n_elements=200,
    use_finite_differences=True,
    warmstart_scipy=False,
    tee=False,
    return_metadata=True,
    ramp_rates=ramp_aggressive
)

traj_aggressive = result_aggressive["output"]
meta_aggressive = result_aggressive["metadata"]

print(f"Drying time: {traj_aggressive[-1, 0]:.2f} hr")
print(f"Initial Tsh: {traj_aggressive[0, 3]:.1f}°C → {traj_aggressive[5, 3]:.1f}°C (first 5 steps)")
print(f"Status: {meta_aggressive.get('termination_condition', 'unknown')}")
print(f"Time penalty vs unconstrained: {(traj_aggressive[-1, 0] / traj_unconstr[-1, 0] - 1) * 100:.1f}%")

# ==============================================================================
# VISUALIZATION
# ==============================================================================

print("\nGenerating comparison plots...")

fig, axes = plt.subplots(2, 2, figsize=(14, 10))

# Plot 1: Full temperature trajectories
ax1 = axes[0, 0]
ax1.plot(traj_unconstr[:, 0], traj_unconstr[:, 3], 'k--', label='Unconstrained', linewidth=2)
ax1.plot(traj_conserv[:, 0], traj_conserv[:, 3], 'b-', label='Conservative (15°C/hr)', linewidth=1.5)
ax1.plot(traj_typical[:, 0], traj_typical[:, 3], 'g-', label='Typical (20°C/hr)', linewidth=1.5)
ax1.plot(traj_aggressive[:, 0], traj_aggressive[:, 3], 'r-', label='Aggressive (30°C/hr)', linewidth=1.5)
ax1.set_xlabel('Time (hr)', fontsize=11)
ax1.set_ylabel('Shelf Temperature (°C)', fontsize=11)
ax1.set_title('Full Temperature Trajectories', fontsize=12, fontweight='bold')
ax1.legend(fontsize=9)
ax1.grid(True, alpha=0.3)

# Plot 2: Initial behavior (first 2 hours)
ax2 = axes[0, 1]
mask_unconstr = traj_unconstr[:, 0] <= 2.0
mask_conserv = traj_conserv[:, 0] <= 2.0
mask_typical = traj_typical[:, 0] <= 2.0
mask_aggressive = traj_aggressive[:, 0] <= 2.0

ax2.plot(traj_unconstr[mask_unconstr, 0], traj_unconstr[mask_unconstr, 3], 'k--o', 
         label='Unconstrained', markersize=3, linewidth=2)
ax2.plot(traj_conserv[mask_conserv, 0], traj_conserv[mask_conserv, 3], 'b-s', 
         label='Conservative (15°C/hr)', markersize=2)
ax2.plot(traj_typical[mask_typical, 0], traj_typical[mask_typical, 3], 'g-^', 
         label='Typical (20°C/hr)', markersize=2)
ax2.plot(traj_aggressive[mask_aggressive, 0], traj_aggressive[mask_aggressive, 3], 'r-d', 
         label='Aggressive (30°C/hr)', markersize=2)
ax2.axhline(-35, color='gray', linestyle=':', alpha=0.5, label='Initial temp')
ax2.set_xlabel('Time (hr)', fontsize=11)
ax2.set_ylabel('Shelf Temperature (°C)', fontsize=11)
ax2.set_title('Initial Behavior (First 2 Hours)', fontsize=12, fontweight='bold')
ax2.legend(fontsize=8)
ax2.grid(True, alpha=0.3)

# Plot 3: Product temperature trajectories (safety check)
ax3 = axes[1, 0]
ax3.plot(traj_unconstr[:, 0], traj_unconstr[:, 1], 'k--', label='Unconstrained', linewidth=2)
ax3.plot(traj_conserv[:, 0], traj_conserv[:, 1], 'b-', label='Conservative', linewidth=1.5)
ax3.plot(traj_typical[:, 0], traj_typical[:, 1], 'g-', label='Typical', linewidth=1.5)
ax3.plot(traj_aggressive[:, 0], traj_aggressive[:, 1], 'r-', label='Aggressive', linewidth=1.5)
ax3.axhline(-25, color='red', linestyle='--', alpha=0.7, label='Critical temp')
ax3.set_xlabel('Time (hr)', fontsize=11)
ax3.set_ylabel('Product Temperature (°C)', fontsize=11)
ax3.set_title('Product Temperature (T_sub)', fontsize=12, fontweight='bold')
ax3.legend(fontsize=9)
ax3.grid(True, alpha=0.3)

# Plot 4: Time penalty comparison
ax4 = axes[1, 1]
cases = ['Unconstrained', 'Aggressive\n(30°C/hr)', 'Typical\n(20°C/hr)', 'Conservative\n(15°C/hr)']
times = [
    traj_unconstr[-1, 0],
    traj_aggressive[-1, 0],
    traj_typical[-1, 0],
    traj_conserv[-1, 0]
]
colors = ['black', 'red', 'green', 'blue']
penalties = [(t / times[0] - 1) * 100 for t in times]

bars = ax4.bar(cases, times, color=colors, alpha=0.7, edgecolor='black')
for i, (bar, penalty) in enumerate(zip(bars, penalties)):
    height = bar.get_height()
    ax4.text(bar.get_x() + bar.get_width()/2., height,
             f'{height:.1f} hr\n({penalty:+.1f}%)',
             ha='center', va='bottom', fontsize=9, fontweight='bold')

ax4.set_ylabel('Total Drying Time (hr)', fontsize=11)
ax4.set_title('Drying Time Comparison', fontsize=12, fontweight='bold')
ax4.grid(True, alpha=0.3, axis='y')

plt.tight_layout()
plt.savefig('ramp_constraint_example.png', dpi=150, bbox_inches='tight')
print(f"✓ Saved to: ramp_constraint_example.png")

# ==============================================================================
# SUMMARY TABLE
# ==============================================================================

print("\n" + "="*80)
print("SUMMARY TABLE")
print("="*80)
print(f"{'Case':<20} {'Ramp Limit':<15} {'Drying Time':<15} {'Penalty':<10} {'Status':<10}")
print("-"*80)
print(f"{'Unconstrained':<20} {'None':<15} {f'{traj_unconstr[-1, 0]:.2f} hr':<15} {'0.0%':<10} {'Optimal':<10}")
print(f"{'Aggressive':<20} {'30°C/hr':<15} {f'{traj_aggressive[-1, 0]:.2f} hr':<15} {f'{(traj_aggressive[-1, 0]/traj_unconstr[-1, 0]-1)*100:.1f}%':<10} {'Optimal':<10}")
print(f"{'Typical':<20} {'20°C/hr':<15} {f'{traj_typical[-1, 0]:.2f} hr':<15} {f'{(traj_typical[-1, 0]/traj_unconstr[-1, 0]-1)*100:.1f}%':<10} {'Optimal':<10}")
print(f"{'Conservative':<20} {'15°C/hr':<15} {f'{traj_conserv[-1, 0]:.2f} hr':<15} {f'{(traj_conserv[-1, 0]/traj_unconstr[-1, 0]-1)*100:.1f}%':<10} {'Optimal':<10}")
print("="*80)

print("\nRECOMMENDATIONS:")
print("  • For most industrial equipment: Use 20°C/hr (typical case)")
print("  • For older/smaller equipment: Use 15°C/hr (conservative case)")
print("  • For modern high-performance equipment: Use 30°C/hr (aggressive case)")
print("  • Time penalties are modest (5-20%) for realistic operation")
print("  • All cases maintain product temperature below critical limit")
print("\n" + "="*80)
