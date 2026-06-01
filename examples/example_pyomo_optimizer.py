"""Example demonstrating Pyomo-based single-step optimization.

This script shows how to use the Pyomo single-step optimizer as an alternative
to the scipy-based sequential optimization. The Pyomo approach provides more
flexibility for advanced optimization scenarios.
"""

# Copyright (C) 2026, SECQUOIA

from importlib.util import find_spec

from lyopronto import functions


def _pyomo_available():
    """Return whether optional Pyomo dependencies are importable."""
    return find_spec("pyomo") is not None


def _ipopt_available():
    """Return whether IPOPT is available through IDAES or Pyomo."""
    if not _pyomo_available():
        return False

    try:
        from idaes.core.solvers import get_solver

        return bool(get_solver("ipopt").available())
    except Exception:
        try:
            import pyomo.environ as pyo

            return bool(pyo.SolverFactory("ipopt").available(exception_flag=False))
        except Exception:
            return False


def _load_pyomo_modules():
    """Import Pyomo modules after optional dependency checks pass."""
    from lyopronto.pyomo_models import single_step, utils

    return single_step, utils


def _print_pyomo_install_help():
    print("ERROR: Pyomo is not installed.")
    print("Install with: pip install lyopronto[optimization]")
    print("For IPOPT solver: conda install -c conda-forge ipopt")


def _print_ipopt_install_help():
    print("ERROR: IPOPT solver is not available.")
    print("Install with: conda install -c conda-forge ipopt")
    print("Or install IDAES solver binaries with: idaes get-extensions")


def main():
    """Run Pyomo single-step optimization example."""
    if not _pyomo_available():
        _print_pyomo_install_help()
        return 1

    if not _ipopt_available():
        _print_ipopt_install_help()
        return 1

    single_step, utils = _load_pyomo_modules()

    print("=" * 70)
    print("LyoPRONTO - Pyomo Single-Step Optimization Example")
    print("=" * 70)
    print()

    # ==================== Define Configuration ====================
    print("Setting up problem configuration...")

    # Vial geometry
    vial = {
        "Av": 3.80,  # Vial area [cm²]
        "Ap": 3.14,  # Product area [cm²]
        "Vfill": 2.0,  # Fill volume [mL]
    }

    # Product properties
    product = {
        "cSolid": 0.05,  # Solid concentration
        "R0": 1.4,  # Base resistance [cm²·hr·Torr/g]
        "A1": 16.0,  # Resistance parameter [cm·hr·Torr/g]
        "A2": 0.0,  # Resistance parameter [1/cm]
        "T_pr_crit": -5.0,  # Critical temperature [°C]
    }

    # Heat transfer parameters
    ht = {
        "KC": 2.75e-4,  # [cal/s/K/cm²]
        "KP": 8.93e-4,  # [cal/s/K/cm²/Torr]
        "KD": 0.46,  # [1/Torr]
    }

    # Equipment capability (optional)
    eq_cap = {
        "a": -0.182,  # [kg/hr]
        "b": 11.7,  # [kg/hr/Torr]
    }
    nVial = 398  # Number of vials

    # Calculate initial product length
    Lpr0 = functions.Lpr0_FUN(vial["Vfill"], vial["Ap"], product["cSolid"])
    print(f"Initial product length: {Lpr0:.4f} cm")

    # ==================== Solve at Different Drying Stages ====================
    print("\nSolving optimization at different drying stages...")
    print("-" * 70)

    # Test at three different dried cake lengths
    drying_stages = [
        (0.0, "Start of drying"),
        (Lpr0 * 0.5, "Half dried"),
        (Lpr0 * 0.9, "Nearly complete"),
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
                solver="ipopt",
                tee=False,  # Set to True to see solver output
            )

            # Display results
            print(f"  Status: {solution['status']}")
            print(
                f"  Optimal chamber pressure:    Pch = {solution['Pch']:.4f} Torr "
                f"({solution['Pch'] * 1000:.1f} mTorr)"
            )
            print(f"  Optimal shelf temperature:   Tsh = {solution['Tsh']:.2f} °C")
            print(f"  Sublimation temperature:     Tsub = {solution['Tsub']:.2f} °C")
            print(f"  Vial bottom temperature:     Tbot = {solution['Tbot']:.2f} °C")
            print(f"  Vapor pressure:              Psub = {solution['Psub']:.4f} Torr")
            print(f"  Sublimation rate:            dmdt = {solution['dmdt']:.4f} kg/hr")
            print(
                f"  Product resistance:          Rp = {solution['Rp']:.2f} cm²·hr·Torr/g"
            )
            print(
                f"  Heat transfer coefficient:   Kv = {solution['Kv']:.6f} cal/s/K/cm²"
            )
            print(
                f"  Driving force:               ΔP = {solution['Psub'] - solution['Pch']:.4f} Torr"
            )

            is_valid, violations = utils.check_solution_validity(solution)

            if is_valid:
                print("  ✓ Solution is physically valid")
            else:
                print("  ✗ Solution has violations:")
                for v in violations:
                    print(f"    - {v}")

            results.append((stage_name, Lck, solution))

        except Exception as e:
            print(f"  ✗ Optimization failed: {e}")
            continue

    if not results:
        print("\nERROR: No optimization stages solved successfully.")
        print(
            "Check IPOPT installation and solver diagnostics, then rerun the example."
        )
        return 1

    # ==================== Summary ====================
    print("\n" + "=" * 70)
    print("Summary - Comparison Across Drying Stages")
    print("=" * 70)
    print(
        f"{'Stage':<20} {'Lck [cm]':<12} {'Pch [Torr]':<12} {'Tsh [°C]':<12} {'dmdt [kg/hr]':<12}"
    )
    print("-" * 70)

    for stage_name, Lck, sol in results:
        print(
            f"{stage_name:<20} {Lck:<12.4f} {sol['Pch']:<12.4f} "
            f"{sol['Tsh']:<12.2f} {sol['dmdt']:<12.4f}"
        )

    print(f"\nSolved optimization stages: {len(results)} of {len(drying_stages)}")
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
