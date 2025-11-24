"""Adapters normalizing scipy and Pyomo optimizer outputs.

Each adapter returns a dictionary with standardized keys:
- trajectory: np.ndarray (time, Tsub, Tbot, Tsh, Pch_mTorr, flux, frac_dried)
- success: bool
- message: str
- raw: original solver output or model reference
- solver_stats: dict (iterations, evals, etc.)
- diagnostics: detailed instrumentation (Pyomo only)
"""
from __future__ import annotations
import time
from typing import Dict, Any, Optional
import numpy as np

from lyopronto import opt_Tsh, opt_Pch, opt_Pch_Tsh, constant
from lyopronto.pyomo_models import optimizers as pyomo_opt
import diagnostics as diag

DRYNESS_TARGET = 0.989

# Scipy adapters -------------------------------------------------------------

def scipy_adapter(task: str, vial: Dict[str,float], product: Dict[str,float], ht: Dict[str,float],
                  eq_cap: Dict[str,float], nVial: int, scenario: Dict[str,Any], dt: float = 0.01) -> Dict[str,Any]:
    """Run scipy baseline optimizer variant for specified task.

    task 'Tsh': optimize shelf temperature only (pressure schedule fixed)
    task 'Pch': optimize chamber pressure only (shelf temperature schedule fixed)
    task 'both': optimize both pressure and temperature concurrently
    """
    if task == "Tsh":
        # Pressure schedule fixed at 0.1 Torr with long hold allowing completion
        Pchamber = {"setpt": [0.1], "dt_setpt": [1800.0], "ramp_rate": 0.5}
        # Shelf temperature optimization bounds
        Tshelf = {"min": -45.0, "max": 120.0}
        runner = opt_Tsh.dry
        args = (vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial)
    elif task == "Pch":
        # Pressure optimization lower bound
        Pchamber = {"min": 0.05}
        # Shelf multi-step schedule with sufficient time for drying completion
        # NOTE: dt_setpt in MINUTES (opt_Pch expects minutes, converts internally)
        # High resistance products (A1=20) need ~86 hours, use 100 hours for margin
        Tshelf = {"init": -35.0, "setpt": [-20.0, 120.0], "dt_setpt": [300.0, 5700.0], "ramp_rate": 1.0}
        runner = opt_Pch.dry
        args = (vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial)
    elif task == "both":
        Pchamber = {"min": 0.05}
        Tshelf = {"min": -45.0, "max": 120.0}
        runner = opt_Pch_Tsh.dry
        args = (vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial)
    else:
        raise ValueError(f"Unknown task '{task}'")

    start = time.perf_counter()
    out = runner(*args)
    wall = time.perf_counter() - start

    traj = out
    success = traj.size > 0
    message = "scipy run completed"
    objective_time_hr = float(traj[-1,0]) if success else None

    return {
        "trajectory": traj,
        "success": success,
        "message": message,
        "wall_time_s": wall,
        "objective_time_hr": objective_time_hr,
        "solver": {"status": "n/a", "termination_condition": "n/a"},
        "solver_stats": {},
        "raw": out,
    }

# Pyomo adapters -------------------------------------------------------------

def pyomo_adapter(
    task: str,
    vial: Dict[str, float],
    product: Dict[str, float],
    ht: Dict[str, float],
    eq_cap: Dict[str, float],
    nVial: int,
    scenario: Dict[str, Any],
    dt: float = 0.01,
    warmstart: bool = False,
    method: str = "fd",  # 'fd' or 'colloc'
    n_elements: int = 24,
    n_collocation: int = 3,
    effective_nfe: bool = True,
    ramp_rates: Optional[Dict[str, float]] = None,
    solver_timeout: float = 180,
) -> Dict[str, Any]:
    """Run Pyomo optimizer counterpart for specified task with discretization controls.

    Parameters
    ----------
    method : str
        'fd' for finite differences, 'colloc' for orthogonal collocation.
    n_elements : int
        Base number of finite elements requested.
    n_collocation : int
        Number of collocation points per element (only if method == 'colloc').
    effective_nfe : bool
        If True (collocation only), treat n_elements as effective (parity with FD) for reporting.
    warmstart : bool
        Use staged solve with scipy warmstart trajectory. Default False for robustness benchmarking.
    """
    if task == "Tsh":
        Pchamber = {"setpt": [0.1], "dt_setpt": [180.0], "ramp_rate": 0.5}
        Tshelf = {"min": -45.0, "max": 120.0}
        runner = pyomo_opt.optimize_Tsh_pyomo
        args = (vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial)
    elif task == "Pch":
        Pchamber = {"min": 0.05}
        # Shelf multi-step schedule with sufficient time for drying completion
        # NOTE: dt_setpt in MINUTES (Pyomo internally uses same convention as scipy)
        # High resistance products (A1=20) need ~86 hours, use 100 hours for margin
        Tshelf = {"init": -35.0, "setpt": [-20.0, 120.0], "dt_setpt": [300.0, 5700.0], "ramp_rate": 1.0}
        runner = pyomo_opt.optimize_Pch_pyomo
        args = (vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial)
    elif task == "both":
        Pchamber = {"min": 0.05, "max": 0.5}
        Tshelf = {"min": -45.0, "max": 120.0, "init": -35.0}
        runner = pyomo_opt.optimize_Pch_Tsh_pyomo
        args = (vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial)
    else:
        raise ValueError(f"Unknown task '{task}'")
    
    # Apply ramp rate overrides from CLI if provided
    if ramp_rates is not None:
        if 'Tsh_max' in ramp_rates:
            Tshelf['ramp_rate'] = ramp_rates['Tsh_max']
        if 'Pch_max' in ramp_rates:
            Pchamber['ramp_rate'] = ramp_rates['Pch_max']
    
    # Extract ramp constraints for metadata (AFTER applying CLI overrides)
    if task == "Tsh":
        ramp_constraints = {"Pch": Pchamber.get("ramp_rate"), "Tsh": None}  # Tsh has no ramp constraint
    elif task == "Pch":
        ramp_constraints = {"Pch": None, "Tsh": Tshelf.get("ramp_rate")}
    elif task == "both":
        ramp_constraints = {"Pch": Pchamber.get("ramp_rate"), "Tsh": Tshelf.get("ramp_rate")}
    else:
        ramp_constraints = {"Pch": None, "Tsh": None}

    use_fd = method.lower() == "fd"
    treat_eff = (not use_fd) and bool(effective_nfe)

    start = time.perf_counter()
    meta: Dict[str, Any] = {}
    model_ref = None
    results_ref = None
    solver_opts = {}
    
    try:
        res = runner(
            *args,
            n_elements=int(n_elements),
            n_collocation=int(n_collocation),
            use_finite_differences=use_fd,
            treat_n_elements_as_effective=treat_eff,
            warmstart_scipy=warmstart,
            return_metadata=True,
            tee=False,
            ramp_rates=ramp_rates,
            solver_timeout=solver_timeout,
        )
        if isinstance(res, dict) and "output" in res:
            traj = res["output"]
            meta = res.get("metadata", {})
            # Try to extract model and results from metadata if available
            model_ref = meta.get("model")
            results_ref = meta.get("results")
        else:
            traj = res
        success = True
        message = "pyomo run completed"
    except Exception as e:
        traj = np.empty((0, 7))
        success = False
        message = f"pyomo failure: {e.__class__.__name__}: {e}"[:300]
    wall = time.perf_counter() - start

    if success and isinstance(traj, np.ndarray) and traj.size:
        default_t = float(traj[-1, 0])
    else:
        default_t = None
    objective_time_hr = float(meta.get("objective_time_hr", default_t)) if success else None

    solver_info = {
        "status": meta.get("status"),
        "termination_condition": meta.get("termination_condition"),
        "ipopt_iterations": meta.get("ipopt_iterations"),
        "n_points": meta.get("n_points"),
        "staged_solve_success": meta.get("staged_solve_success"),
    }

    # Discretization reporting
    # Get actual applied nfe from mesh_info if available
    mesh_info = meta.get("mesh_info")
    nfe_applied = n_elements  # default to requested
    if isinstance(mesh_info, dict) and "nfe_applied" in mesh_info:
        nfe_applied = mesh_info["nfe_applied"]
    
    if use_fd:
        total_mesh_points = int(nfe_applied) + 1  # simple FD time mesh
    else:
        # For collocation, total interior points per element is n_collocation
        total_mesh_points = int(nfe_applied) * int(n_collocation) + 1
    
    discretization = {
        "method": "fd" if use_fd else "colloc",
        "n_elements_requested": int(n_elements),
        "n_elements_applied": int(nfe_applied),
        "n_collocation": int(n_collocation) if not use_fd else None,
        "effective_nfe": bool(treat_eff) if not use_fd else False,
        "total_mesh_points": total_mesh_points,
    }
    # Merge any remaining mesh_info from metadata if present
    if isinstance(mesh_info, dict):
        discretization.update({k: v for k, v in mesh_info.items() if k not in discretization})

    # Collect full diagnostics if Pyomo solve was attempted
    detailed_diagnostics = {}
    if model_ref is not None and results_ref is not None:
        # Default IPOPT solver options used in optimizers
        default_solver_options = {
            'max_iter': 5000,
            'tol': 1e-6,
            'acceptable_tol': 1e-4,
            'print_level': 0,
            'mu_strategy': 'adaptive',
            'bound_relax_factor': 1e-8,
            'constr_viol_tol': 1e-6,
        }
        if warmstart:
            default_solver_options.update({
                'warm_start_init_point': 'yes',
                'warm_start_bound_push': 1e-8,
                'warm_start_mult_bound_push': 1e-8,
            })
        
        detailed_diagnostics = diag.collect_full_diagnostics(
            model=model_ref,
            results=results_ref,
            solver_options=default_solver_options,
            warmstart_source=None,  # TODO: add scipy baseline hash when warmstart enabled
            warmstart_ratio=None
        )
    
    return {
        "trajectory": traj,
        "success": success,
        "message": message,
        "wall_time_s": wall,
        "objective_time_hr": objective_time_hr,
        "solver": solver_info,
        "solver_stats": {},
        "raw": traj,
        "warmstart_used": warmstart,
        "discretization": discretization,
        "diagnostics": detailed_diagnostics if detailed_diagnostics else None,
        "ramp_constraints": ramp_constraints,
    }

