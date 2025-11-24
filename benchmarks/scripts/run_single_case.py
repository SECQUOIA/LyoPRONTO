#!/usr/bin/env python
"""Run a single optimization case with full terminal output for debugging.

Purpose
-------
Rapidly inspect one scipy baseline and one Pyomo optimization (Tsh, Pch, or both)
without writing benchmark JSONL artifacts. This is ideal for:
    * Verifying constraint satisfaction (dryness, temperature, ramp rates)
    * Comparing FD vs Collocation discretizations interactively
    * Experimenting with solver timeout settings
    * Diagnosing convergence failures before adding a case to a grid run

Key Behaviors
-------------
* Prints scipy baseline summary (final time, dried fraction, points).
* Prints Pyomo optimization configuration (elements, collocation, warmstart, ramp limits).
* Uses IPOPT `max_cpu_time`, which limits CPU seconds (not wall clock). Long
    wall time may still occur if function evaluations dominate.
* Ramp rate overrides (`--ramp-Tsh-max`, `--ramp-Pch-max`) are passed directly
    into the control dictionaries before solving.
* When `--tee` is provided, full IPOPT output is shown for deeper diagnosis.

Recommended Usage Patterns
--------------------------
        # Joint optimization (both controls) finite differences
        python run_single_case.py --task both --R0 0.4 --A1 20 --method fd --n-elements 1000 \
                --ramp-Tsh-max 40 --ramp-Pch-max 0.05 --solver-timeout 300 --tee

        # Shelf temperature only, collocation with warmstart
        python run_single_case.py --task Tsh --R0 0.8 --A1 12.5 --method colloc \
                --n-elements 64 --n-collocation 3 --warmstart --solver-timeout 180

        # Chamber pressure only, finite differences, shorter timeout
        python run_single_case.py --task Pch --R0 0.6 --A1 5 --method fd \
                --n-elements 128 --solver-timeout 60

Important Notes
---------------
* Solver timeout is CPU time; upgrading to IPOPT >=3.14 adds wall time support.
* Warmstart will attempt staged solve; disable with `--no-warmstart` for raw attempt.
* Use small `--n-elements` first when debugging to reduce iteration cost.
* A failed optimization may still yield a partial trajectory—inspect manually.
"""
import argparse
import sys
from pathlib import Path

# Add benchmarks/src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from scenarios import SCENARIOS
import lyopronto.pyomo_models.optimizers as pyomo_opt
import lyopronto.opt_Pch_Tsh as opt_both
import lyopronto.opt_Tsh as opt_Tsh
import lyopronto.opt_Pch as opt_Pch


def run_scipy_baseline(task, vial, product, ht, eq_cap, nVial, dt=0.01):
    """Run scipy baseline for comparison."""
    print("\n" + "="*70)
    print("SCIPY BASELINE")
    print("="*70)
    
    if task == "Tsh":
        Pchamber = {"setpt": [0.1], "dt_setpt": [180.0]}
        result = opt_Tsh.dry(vial, product, ht, Pchamber, dt, eq_cap, nVial)
    elif task == "Pch":
        Tshelf = {"init": -35.0, "setpt": [-20.0, 120.0], "dt_setpt": [300.0, 5700.0]}
        result = opt_Pch.dry(vial, product, ht, Tshelf, dt, eq_cap, nVial)
    elif task == "both":
        # For scipy opt_Pch_Tsh, need bounds like Pyomo
        Pchamber = {"min": 0.05}
        Tshelf = {"min": -45.0, "max": 120.0}
        result = opt_both.dry(vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial)
    else:
        raise ValueError(f"Unknown task: {task}")
    
    if result.size > 0:
        print(f"✓ Success")
        print(f"  Final time: {result[-1, 0]:.2f} hr")
        print(f"  Final dried fraction: {result[-1, 6]:.4f}")
        print(f"  Trajectory points: {len(result)}")
    else:
        print(f"✗ Failed - empty trajectory")
    
    return result


def run_pyomo_optimization(task, vial, product, ht, eq_cap, nVial, method, 
                          n_elements, n_collocation, warmstart, ramp_rates, 
                          solver_timeout, tee):
    """Run Pyomo optimization with specified settings."""
    print("\n" + "="*70)
    print(f"PYOMO OPTIMIZATION - {method.upper()}")
    print("="*70)
    print(f"Discretization: {n_elements} elements" + 
          (f", {n_collocation} collocation points" if method == "colloc" else ""))
    print(f"Warmstart: {warmstart}")
    print(f"Solver timeout: {solver_timeout}s")
    if ramp_rates:
        if ramp_rates.get('Tsh_max'):
            print(f"Tsh ramp limit: {ramp_rates['Tsh_max']} °C/hr")
        if ramp_rates.get('Pch_max'):
            print(f"Pch ramp limit: {ramp_rates['Pch_max']} Torr/hr")
    print()
    
    # Setup task-specific parameters
    dt = 0.01
    if task == "Tsh":
        Pchamber = {"setpt": [0.1], "dt_setpt": [180.0], "ramp_rate": 0.5}
        Tshelf = {"min": -45.0, "max": 120.0}
        runner = pyomo_opt.optimize_Tsh_pyomo
        args = (vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial)
    elif task == "Pch":
        Pchamber = {"min": 0.05}
        Tshelf = {"init": -35.0, "setpt": [-20.0, 120.0], "dt_setpt": [300.0, 5700.0], "ramp_rate": 1.0}
        runner = pyomo_opt.optimize_Pch_pyomo
        args = (vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial)
    elif task == "both":
        Pchamber = {"min": 0.05, "max": 0.5}
        Tshelf = {"min": -45.0, "max": 120.0, "init": -35.0}
        
        # Apply ramp rate overrides if provided
        if ramp_rates:
            if 'Tsh_max' in ramp_rates:
                Tshelf['ramp_rate'] = ramp_rates['Tsh_max']
            if 'Pch_max' in ramp_rates:
                Pchamber['ramp_rate'] = ramp_rates['Pch_max']
        
        runner = pyomo_opt.optimize_Pch_Tsh_pyomo
        args = (vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial)
    else:
        raise ValueError(f"Unknown task: {task}")
    
    use_fd = method.lower() == "fd"
    
    try:
        result = runner(
            *args,
            n_elements=n_elements,
            n_collocation=n_collocation,
            use_finite_differences=use_fd,
            treat_n_elements_as_effective=True,
            warmstart_scipy=warmstart,
            return_metadata=True,
            tee=tee,
            ramp_rates=ramp_rates,
            solver_timeout=solver_timeout,
        )
        
        if isinstance(result, dict) and "output" in result:
            trajectory = result["output"]
            metadata = result.get("metadata", {})
        else:
            trajectory = result
            metadata = {}
        
        print("\n" + "-"*70)
        print("RESULTS")
        print("-"*70)
        
        if trajectory.size > 0:
            print(f"✓ Success")
            print(f"  Final time: {trajectory[-1, 0]:.2f} hr")
            print(f"  Final dried fraction: {trajectory[-1, 6]:.4f}")
            print(f"  Trajectory points: {len(trajectory)}")
            
            if metadata:
                if metadata.get('status'):
                    print(f"  Solver status: {metadata['status']}")
                if metadata.get('termination_condition'):
                    print(f"  Termination: {metadata['termination_condition']}")
                if metadata.get('ipopt_iterations'):
                    print(f"  IPOPT iterations: {metadata['ipopt_iterations']}")
                if metadata.get('objective_time_hr'):
                    print(f"  Objective value: {metadata['objective_time_hr']:.2f} hr")
        else:
            print(f"✗ Failed - empty trajectory")
            if metadata:
                print(f"  Status: {metadata.get('status')}")
                print(f"  Termination: {metadata.get('termination_condition')}")
        
        return trajectory, metadata
        
    except Exception as e:
        print(f"\n✗ Exception occurred: {e}")
        import traceback
        traceback.print_exc()
        return None, None


def main():
    parser = argparse.ArgumentParser(
        description="Run single optimization case for debugging",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Test problematic case with full solver output
  python run_single_case.py --task both --R0 0.4 --A1 20 --method fd --tee

  # Test with ramp constraints
  python run_single_case.py --task both --R0 0.6 --A1 12.5 --method colloc \\
      --ramp-Tsh-max 40 --ramp-Pch-max 0.05

  # Test with increased timeout
  python run_single_case.py --task both --R0 0.4 --A1 20 --method fd \\
      --solver-timeout 600 --tee

  # Compare scipy baseline only
  python run_single_case.py --task Tsh --R0 0.8 --A1 5 --scipy-only
        """
    )
    
    # Task and parameters
    parser.add_argument("--task", required=True, choices=["Tsh", "Pch", "both"],
                       help="Optimization task")
    parser.add_argument("--scenario", default="baseline",
                       help="Scenario name (default: baseline)")
    parser.add_argument("--R0", type=float, required=True,
                       help="Product resistance R0 parameter")
    parser.add_argument("--A1", type=float, required=True,
                       help="Product resistance A1 parameter")
    
    # Method selection
    parser.add_argument("--method", default="fd", choices=["fd", "colloc"],
                       help="Pyomo discretization method (default: fd)")
    parser.add_argument("--scipy-only", action="store_true",
                       help="Run only scipy baseline (skip Pyomo)")
    
    # Discretization
    parser.add_argument("--n-elements", type=int, default=1000,
                       help="Number of finite elements (default: 1000)")
    parser.add_argument("--n-collocation", type=int, default=3,
                       help="Collocation points per element (default: 3)")
    
    # Solver options
    parser.add_argument("--warmstart", action="store_true",
                       help="Enable scipy warmstart")
    parser.add_argument("--solver-timeout", type=float, default=180,
                       help="Solver timeout in seconds (default: 180)")
    parser.add_argument("--tee", action="store_true",
                       help="Show solver output (verbose)")
    
    # Ramp constraints
    parser.add_argument("--ramp-Tsh-max", type=float,
                       help="Max shelf temperature ramp rate (°C/hr)")
    parser.add_argument("--ramp-Pch-max", type=float,
                       help="Max chamber pressure ramp rate (Torr/hr)")
    
    args = parser.parse_args()
    
    # Load scenario
    if args.scenario not in SCENARIOS:
        print(f"Error: Unknown scenario '{args.scenario}'")
        print(f"Available: {list(SCENARIOS.keys())}")
        return 1
    
    scenario = SCENARIOS[args.scenario].copy()
    
    # Override product parameters
    scenario['product']['R0'] = args.R0
    scenario['product']['A1'] = args.A1
    
    vial = scenario['vial']
    product = scenario['product']
    ht = scenario['ht']
    eq_cap = scenario['eq_cap']
    nVial = scenario.get('nVial', 400)
    
    # Print configuration
    print("\n" + "="*70)
    print("CONFIGURATION")
    print("="*70)
    print(f"Task: {args.task}")
    print(f"Scenario: {args.scenario}")
    print(f"Product parameters:")
    print(f"  R0 = {args.R0}")
    print(f"  A1 = {args.A1}")
    print(f"  A2 = {product['A2']}")
    print(f"  T_pr_crit = {product['T_pr_crit']} °C")
    
    # Build ramp_rates dict
    ramp_rates = None
    if args.ramp_Tsh_max or args.ramp_Pch_max:
        ramp_rates = {}
        if args.ramp_Tsh_max:
            ramp_rates['Tsh_max'] = args.ramp_Tsh_max
        if args.ramp_Pch_max:
            ramp_rates['Pch_max'] = args.ramp_Pch_max
    
    # Run scipy baseline
    scipy_result = run_scipy_baseline(args.task, vial, product, ht, eq_cap, nVial)
    
    # Run Pyomo if requested
    if not args.scipy_only:
        pyomo_result, metadata = run_pyomo_optimization(
            args.task, vial, product, ht, eq_cap, nVial,
            args.method, args.n_elements, args.n_collocation,
            args.warmstart, ramp_rates, args.solver_timeout, args.tee
        )
        
        # Compare results
        if scipy_result.size > 0 and pyomo_result is not None and pyomo_result.size > 0:
            print("\n" + "="*70)
            print("COMPARISON")
            print("="*70)
            scipy_time = scipy_result[-1, 0]
            pyomo_time = pyomo_result[-1, 0]
            diff = pyomo_time - scipy_time
            speedup = (scipy_time / pyomo_time - 1) * 100
            
            print(f"Scipy time:  {scipy_time:.2f} hr")
            print(f"Pyomo time:  {pyomo_time:.2f} hr")
            print(f"Difference:  {diff:+.2f} hr ({speedup:+.1f}% speedup)")
    
    print("\n" + "="*70)
    print("DONE")
    print("="*70 + "\n")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
