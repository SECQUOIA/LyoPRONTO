"""Example demonstrating Pyomo-based single-step optimization.

This script shows how to use the Pyomo single-step optimizer as an alternative
to the scipy-based sequential optimization. The Pyomo approach provides more
flexibility for advanced optimization scenarios.
"""

# LyoPRONTO, a vial-scale lyophilization process simulator
# Copyright (C) 2024, Gayathri Shivkumar, Petr S. Kazarin, Alina A. Alexeenko, Isaac S. Wheeler

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import numpy as np
from lyopronto import functions
from lyopronto.pyomo_models import single_step

# Check if Pyomo is available
try:
    import pyomo.environ as pyo
    PYOMO_AVAILABLE = True
except ImportError:
    print("ERROR: Pyomo is not installed.")
    print("Install with: pip install pyomo")
    print("For IPOPT solver: conda install -c conda-forge ipopt")
    exit(1)


def main():
    """Run Pyomo single-step optimization example."""
    
    print("=" * 70)
    print("LyoPRONTO - Pyomo Single-Step Optimization Example")
    print("=" * 70)
    print()
    
    # ==================== Define Configuration ====================
    print("Setting up problem configuration...")
    
    # Vial geometry
    vial = {
        'Av': 3.80,  # Vial area [cm²]
        'Ap': 3.14,  # Product area [cm²]
        'Vfill': 2.0  # Fill volume [mL]
    }
    
    # Product properties
    product = {
        'cSolid': 0.05,      # Solid concentration
        'R0': 1.4,           # Base resistance [cm²·hr·Torr/g]
        'A1': 16.0,          # Resistance parameter [cm·hr·Torr/g]
        'A2': 0.0,           # Resistance parameter [1/cm]
        'T_pr_crit': -5.0    # Critical temperature [°C]
    }
    
    # Heat transfer parameters
    ht = {
        'KC': 2.75e-4,   # [cal/s/K/cm²]
        'KP': 8.93e-4,   # [cal/s/K/cm²/Torr]
        'KD': 0.46       # [1/Torr]
    }
    
    # Equipment capability (optional)
    eq_cap = {
        'a': -0.182,  # [kg/hr]
        'b': 11.7     # [kg/hr/Torr]
    }
    nVial = 398  # Number of vials
    
    # Calculate initial product length
    Lpr0 = functions.Lpr0_FUN(vial['Vfill'], vial['Ap'], product['cSolid'])
    print(f"Initial product length: {Lpr0:.4f} cm")
    
    # ==================== Solve at Different Drying Stages ====================
    print("\nSolving optimization at different drying stages...")
    print("-" * 70)
    
    # Test at three different dried cake lengths
    drying_stages = [
        (0.0, "Start of drying"),
        (Lpr0 * 0.5, "Half dried"),
        (Lpr0 * 0.9, "Nearly complete")
    ]
    
    results = []
    
    for Lck, stage_name in drying_stages:
        print(f"\n{stage_name} (Lck = {Lck:.4f} cm):")
        print("-" * 70)
        
        # Solve using Pyomo
        try:
            solution = single_step.optimize_single_step(
                vial=vial,
                product=product,
                ht=ht,
                Lpr0=Lpr0,
                Lck=Lck,
                Pch_bounds=(0.05, 0.5),
                Tsh_bounds=(-50, 50),
                eq_cap=eq_cap,
                nVial=nVial,
                solver='ipopt',
                tee=False  # Set to True to see solver output
            )
            
            # Display results
            print(f"  Status: {solution['status']}")
            print(f"  Optimal chamber pressure:    Pch = {solution['Pch']:.4f} Torr "
                  f"({solution['Pch']*1000:.1f} mTorr)")
            print(f"  Optimal shelf temperature:   Tsh = {solution['Tsh']:.2f} °C")
            print(f"  Sublimation temperature:     Tsub = {solution['Tsub']:.2f} °C")
            print(f"  Vial bottom temperature:     Tbot = {solution['Tbot']:.2f} °C")
            print(f"  Vapor pressure:              Psub = {solution['Psub']:.4f} Torr")
            print(f"  Sublimation rate:            dmdt = {solution['dmdt']:.4f} kg/hr")
            print(f"  Product resistance:          Rp = {solution['Rp']:.2f} cm²·hr·Torr/g")
            print(f"  Heat transfer coefficient:   Kv = {solution['Kv']:.6f} cal/s/K/cm²")
            print(f"  Driving force:               ΔP = {solution['Psub']-solution['Pch']:.4f} Torr")
            
            # Validate solution
            from lyopronto.pyomo_models import utils
            is_valid, violations = utils.check_solution_validity(solution)
            
            if is_valid:
                print(f"  ✓ Solution is physically valid")
            else:
                print(f"  ✗ Solution has violations:")
                for v in violations:
                    print(f"    - {v}")
            
            results.append((Lck, solution))
            
        except Exception as e:
            print(f"  ✗ Optimization failed: {e}")
            continue
    
    # ==================== Summary ====================
    print("\n" + "=" * 70)
    print("Summary - Comparison Across Drying Stages")
    print("=" * 70)
    print(f"{'Stage':<20} {'Lck [cm]':<12} {'Pch [Torr]':<12} {'Tsh [°C]':<12} {'dmdt [kg/hr]':<12}")
    print("-" * 70)
    
    for i, (Lck, sol) in enumerate(results):
        stage_name = drying_stages[i][1]
        print(f"{stage_name:<20} {Lck:<12.4f} {sol['Pch']:<12.4f} "
              f"{sol['Tsh']:<12.2f} {sol['dmdt']:<12.4f}")
    
    print("\n" + "=" * 70)
    print("Observations:")
    print("  - As drying progresses (Lck increases), product resistance increases")
    print("  - Higher resistance → lower sublimation rate")
    print("  - Optimizer adjusts Pch and Tsh to maintain process within constraints")
    print("=" * 70)
    
    print("\nExample complete!")
    print("\nNext steps:")
    print("  - Try modifying product properties (R0, A1, A2)")
    print("  - Experiment with different bounds (Pch_bounds, Tsh_bounds)")
    print("  - Compare with scipy results from opt_Pch_Tsh.dry()")
    print("  - Set tee=True to see detailed solver output")


if __name__ == "__main__":
    main()
