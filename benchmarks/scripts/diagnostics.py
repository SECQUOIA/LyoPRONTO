"""Diagnostics collection for Pyomo benchmark runs.

Captures:
- Model size (variables, constraints, objectives)
- IPOPT solver diagnostics (iterations, times, infeasibilities, KKT metrics)
- Termination details (return status code)
- Option fingerprint (hash + key values)
- Data provenance (code version, environment)
- Solver invocation flags
"""

import hashlib
import json
import subprocess
import sys
from typing import Dict, Any, Optional
import pyomo
import pyomo.environ as pyo


def get_model_size(model: pyo.ConcreteModel) -> Dict[str, int]:
    """Extract model size statistics.
    
    Args:
        model: Pyomo ConcreteModel instance
        
    Returns:
        Dictionary with n_variables, n_constraints, n_objectives
    """
    n_vars = sum(1 for _ in model.component_data_objects(pyo.Var, active=True))
    n_cons = sum(1 for _ in model.component_data_objects(pyo.Constraint, active=True))
    n_objs = sum(1 for _ in model.component_data_objects(pyo.Objective, active=True))
    
    return {
        "n_variables": n_vars,
        "n_constraints": n_cons,
        "n_objectives": n_objs
    }


def parse_ipopt_diagnostics(results) -> Dict[str, Any]:
    """Parse IPOPT solver diagnostics from Pyomo results object.
    
    Args:
        results: Pyomo solver results object
        
    Returns:
        Dictionary with IPOPT metrics (iterations, cpu_time_s, objective_final,
        primal_infeasibility, dual_infeasibility, complementarity, kkt_error,
        barrier_parameter, barrier_objective)
    """
    diagnostics = {
        "iterations": None,
        "cpu_time_s": None,
        "objective_final": None,
        "primal_infeasibility": None,
        "dual_infeasibility": None,
        "complementarity": None,
        "kkt_error": None,
        "barrier_parameter": None,
        "barrier_objective": None
    }
    
    # Try to extract from solver statistics
    if hasattr(results, 'solver'):
        solver_info = results.solver
        
        # Number of iterations
        if hasattr(solver_info, 'statistics'):
            stats = solver_info.statistics
            if hasattr(stats, 'number_of_iterations'):
                diagnostics["iterations"] = stats.number_of_iterations
        
        # CPU time
        if hasattr(solver_info, 'time'):
            diagnostics["cpu_time_s"] = solver_info.time
        elif hasattr(solver_info, 'wall_time'):
            diagnostics["cpu_time_s"] = solver_info.wall_time
    
    # Try to extract from problem info
    if hasattr(results, 'problem'):
        prob_info = results.problem
        
        # Objective value
        if hasattr(prob_info, 'lower_bound'):
            diagnostics["objective_final"] = prob_info.lower_bound
        elif hasattr(prob_info, 'upper_bound'):
            diagnostics["objective_final"] = prob_info.upper_bound
    
    # Try to extract from solution
    if hasattr(results, 'solution') and len(results.solution) > 0:
        sol = results.solution(0)
        if hasattr(sol, 'gap'):
            # IPOPT doesn't always populate these, but check
            pass
    
    # Parse from solver message/log if available
    if hasattr(results, 'solver') and hasattr(results.solver, 'message'):
        msg = results.solver.message
        if msg:
            diagnostics.update(_parse_ipopt_message(msg))
    
    return diagnostics


def _parse_ipopt_message(message: str) -> Dict[str, Any]:
    """Parse IPOPT solver message for detailed diagnostics.
    
    Args:
        message: IPOPT solver output message string
        
    Returns:
        Dictionary with extracted metrics
    """
    metrics = {}
    
    # Common IPOPT message patterns
    # Example: "Number of Iterations....: 42"
    import re
    
    iter_match = re.search(r'Number of Iterations[.\s]*:\s*(\d+)', message)
    if iter_match:
        metrics["iterations"] = int(iter_match.group(1))
    
    # CPU time pattern: "Total CPU secs in IPOPT (w/o function evaluations)   =      1.234"
    cpu_match = re.search(r'Total (?:CPU|Wall) secs[^=]*=\s*([\d.]+)', message)
    if cpu_match:
        metrics["cpu_time_s"] = float(cpu_match.group(1))
    
    # Objective value: "Objective...............:   1.234567890123456e+01"
    obj_match = re.search(r'Objective[.\s]*:\s*([-+]?[\d.]+(?:e[-+]?\d+)?)', message)
    if obj_match:
        metrics["objective_final"] = float(obj_match.group(1))
    
    # Infeasibilities at final iteration
    # "Dual infeasibility......:   1.234567890123456e-08"
    dual_match = re.search(r'Dual infeasibility[.\s]*:\s*([-+]?[\d.]+(?:e[-+]?\d+)?)', message)
    if dual_match:
        metrics["dual_infeasibility"] = float(dual_match.group(1))
    
    # "Constraint violation....:   2.345678901234567e-09"
    primal_match = re.search(r'Constraint violation[.\s]*:\s*([-+]?[\d.]+(?:e[-+]?\d+)?)', message)
    if primal_match:
        metrics["primal_infeasibility"] = float(primal_match.group(1))
    
    # "Complementarity.........:   3.456789012345678e-09"
    comp_match = re.search(r'Complementarity[.\s]*:\s*([-+]?[\d.]+(?:e[-+]?\d+)?)', message)
    if comp_match:
        metrics["complementarity"] = float(comp_match.group(1))
    
    # "Overall NLP error.......:   4.567890123456789e-09"
    kkt_match = re.search(r'Overall NLP error[.\s]*:\s*([-+]?[\d.]+(?:e[-+]?\d+)?)', message)
    if kkt_match:
        metrics["kkt_error"] = float(kkt_match.group(1))
    
    return metrics


def get_termination_detail(results) -> Optional[int]:
    """Extract IPOPT return status code.
    
    Args:
        results: Pyomo solver results object
        
    Returns:
        Integer return status code (0=optimal, 1=iteration/time limit, 2=infeasible, 3=unbounded, -1=other)
    """
    if hasattr(results, 'solver'):
        solver_info = results.solver
        
        # Check for return code (but watch for UndefinedData placeholder)
        if hasattr(solver_info, 'return_code'):
            rc = solver_info.return_code
            # Check if it's actually a value (not undefined)
            if rc is not None and str(rc) != "<undefined>":
                try:
                    return int(rc)
                except (ValueError, TypeError):
                    pass
        
        # Fall back to mapping termination_condition
        if hasattr(solver_info, 'termination_condition'):
            tc = solver_info.termination_condition
            # Handle both string and enum representations
            tc_str = str(tc).lower()
            
            if "optimal" in tc_str:
                return 0
            elif "infeasible" in tc_str:
                return 2
            elif "unbounded" in tc_str:
                return 3
            elif "iteration" in tc_str or "time" in tc_str or "limit" in tc_str:
                return 1
            else:
                return -1
    
    return None


def compute_option_fingerprint(solver_options: Dict[str, Any]) -> Dict[str, Any]:
    """Compute hash and extract key solver options.
    
    Args:
        solver_options: Dictionary of solver options
        
    Returns:
        Dictionary with option_hash and key option values
        (linear_solver, tol, constr_viol_tol, mu_strategy)
    """
    # Sort options for consistent hashing
    sorted_opts = json.dumps(solver_options, sort_keys=True)
    opt_hash = hashlib.sha256(sorted_opts.encode()).hexdigest()[:16]
    
    # Extract key options
    key_options = {
        "linear_solver": solver_options.get("linear_solver"),
        "tol": solver_options.get("tol"),
        "constr_viol_tol": solver_options.get("constr_viol_tol"),
        "mu_strategy": solver_options.get("mu_strategy"),
        "max_iter": solver_options.get("max_iter")
    }
    
    return {
        "option_hash": opt_hash,
        "key_options": key_options
    }


def get_environment_metadata() -> Dict[str, str]:
    """Collect environment metadata (Python, Pyomo, IPOPT versions).
    
    Returns:
        Dictionary with python_version, pyomo_version, ipopt_version
    """
    metadata = {
        "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "pyomo_version": pyomo.__version__
    }
    
    # Try to get IPOPT version by running ipopt --version
    try:
        result = subprocess.run(
            ["ipopt", "--version"],
            capture_output=True,
            text=True,
            timeout=2
        )
        if result.returncode == 0:
            # Parse version from output (usually first line)
            version_line = result.stdout.strip().split('\n')[0]
            # Extract version number pattern like "3.14.11"
            import re
            match = re.search(r'(\d+\.\d+\.\d+)', version_line)
            if match:
                metadata["ipopt_version"] = match.group(1)
            else:
                metadata["ipopt_version"] = version_line
        else:
            metadata["ipopt_version"] = "unknown"
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
        metadata["ipopt_version"] = "unknown"
    
    return metadata


def get_code_version() -> Optional[str]:
    """Get current git commit SHA.
    
    Returns:
        Commit SHA string, or None if not in git repo
    """
    import os
    try:
        # Get directory of this file and go up to repo root
        module_dir = os.path.dirname(os.path.abspath(__file__))
        repo_root = os.path.dirname(module_dir)  # One level up from benchmarks/
        
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2,
            cwd=repo_root
        )
        if result.returncode == 0:
            return result.stdout.strip()[:12]  # Short SHA
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
        pass
    
    return None


def create_warmstart_metadata(
    source_hash: Optional[str] = None,
    variable_match_ratio: Optional[float] = None
) -> Dict[str, Any]:
    """Create warmstart metadata dictionary.
    
    Args:
        source_hash: Hash of warmstart source (e.g., scipy baseline)
        variable_match_ratio: Fraction of variables successfully initialized
        
    Returns:
        Dictionary with warmstart metadata
    """
    return {
        "warmstart_enabled": source_hash is not None,
        "source_hash": source_hash,
        "variable_match_ratio": variable_match_ratio
    }


def collect_full_diagnostics(
    model: pyo.ConcreteModel,
    results,
    solver_options: Dict[str, Any],
    warmstart_source: Optional[str] = None,
    warmstart_ratio: Optional[float] = None
) -> Dict[str, Any]:
    """Collect all diagnostics in one call.
    
    Args:
        model: Pyomo model instance
        results: Pyomo solver results object (or None if solve failed)
        solver_options: Dictionary of solver options used
        warmstart_source: Optional hash of warmstart source
        warmstart_ratio: Optional variable match ratio
        
    Returns:
        Complete diagnostics dictionary
    """
    diagnostics = {
        "solver_invoked": True,
        "solver_returned": results is not None,
        "model_size": get_model_size(model),
        "environment": get_environment_metadata(),
        "code_version": get_code_version(),
        "option_fingerprint": compute_option_fingerprint(solver_options),
        "warmstart": create_warmstart_metadata(warmstart_source, warmstart_ratio)
    }
    
    # Only collect IPOPT diagnostics if solver returned
    if results is not None:
        diagnostics["ipopt"] = parse_ipopt_diagnostics(results)
        diagnostics["return_status_code"] = get_termination_detail(results)
    else:
        diagnostics["ipopt"] = {
            "iterations": None,
            "cpu_time_s": None,
            "objective_final": None,
            "primal_infeasibility": None,
            "dual_infeasibility": None,
            "complementarity": None,
            "kkt_error": None,
            "barrier_parameter": None,
            "barrier_objective": None
        }
        diagnostics["return_status_code"] = None
    
    return diagnostics
