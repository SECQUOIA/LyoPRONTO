# Copyright (C) 2026, SECQUOIA

"""Adapters normalizing scipy and Pyomo optimizer outputs.

Each adapter returns a dictionary with standardized keys:
- trajectory: np.ndarray (time, Tsub, Tbot, Tsh, Pch_mTorr, flux, percent_dried)
- success: bool
- message: str
- raw: original solver output or model reference
- solver_stats: dict (iterations, evals, etc.)
"""

from __future__ import annotations

import time
from typing import Any

import numpy as np
from lyopronto import opt_Pch, opt_Pch_Tsh, opt_Tsh

from benchmarks.validate import compare_trajectories

DRYNESS_TARGET = 98.9  # Percentage (0-100)
ACCEPTABLE_PYOMO_TERMINATIONS = {"optimal", "locallyoptimal"}


def _pch_benchmark_controls() -> tuple[dict[str, float], dict[str, Any]]:
    """Return fixed controls shared by SciPy and Pyomo Pch benchmarks."""
    # optimize_Pch_pyomo uses free final time, so fixed shelf profiles must be
    # constant. The -18 C setpoint keeps the baseline -25 C product constraint
    # feasible while allowing the SciPy reference to complete the 3x3 grid.
    return (
        {"min": 0.05, "max": 0.5},
        {
            "init": -18.0,
            "setpt": [-18.0],
            "dt_setpt": [6000.0],
            "ramp_rate": 1.0,
        },
    )


def _load_pyomo_optimizers():
    """Import optional Pyomo optimizers only when a Pyomo method is requested."""
    try:
        from lyopronto.pyomo_models import optimizers as pyomo_opt
    except ImportError as exc:
        raise RuntimeError(
            "Pyomo benchmark methods require optional optimization dependencies. "
            "Install them with `pip install .[optimization]`."
        ) from exc
    return pyomo_opt


def _scipy_task_setup(task: str) -> tuple[Any, dict[str, Any], dict[str, Any]]:
    """Return the legacy scipy runner and controls for a benchmark task."""
    if task == "Tsh":
        Pchamber = {"setpt": [0.1], "dt_setpt": [1800.0], "ramp_rate": 0.5}
        Tshelf = {"min": -45.0, "max": 120.0}
        return opt_Tsh.dry, Pchamber, Tshelf
    if task == "Pch":
        Pchamber, Tshelf = _pch_benchmark_controls()
        return opt_Pch.dry, Pchamber, Tshelf
    if task == "both":
        Pchamber = {"min": 0.05}
        Tshelf = {"min": -45.0, "max": 120.0}
        return opt_Pch_Tsh.dry, Pchamber, Tshelf
    raise ValueError(f"Unknown task '{task}'")


def _acceptable_pyomo_termination(termination_condition: Any) -> bool:
    normalized = str(termination_condition or "").lower().replace(" ", "")
    return normalized in ACCEPTABLE_PYOMO_TERMINATIONS


# Scipy adapters -------------------------------------------------------------


def scipy_adapter(
    task: str,
    vial: dict[str, float],
    product: dict[str, float],
    ht: dict[str, float],
    eq_cap: dict[str, float],
    nVial: int,
    scenario: dict[str, Any],
    dt: float = 0.01,
) -> dict[str, Any]:
    """Run scipy baseline optimizer variant for specified task.

    task 'Tsh': optimize shelf temperature only (pressure schedule fixed)
    task 'Pch': optimize chamber pressure only (shelf temperature schedule fixed)
    task 'both': optimize both pressure and temperature concurrently
    """
    runner, Pchamber, Tshelf = _scipy_task_setup(task)
    args = (vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial)

    start = time.perf_counter()
    out = runner(*args)
    wall = time.perf_counter() - start

    traj = out
    success = traj.size > 0
    message = "scipy run completed"
    objective_time_hr = float(traj[-1, 0]) if success else None

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


def ipopt_replay_adapter(
    task: str,
    vial: dict[str, float],
    product: dict[str, float],
    ht: dict[str, float],
    eq_cap: dict[str, float],
    nVial: int,
    scenario: dict[str, Any],
    scipy_result: dict[str, Any],
    method: str = "fd",
    n_elements: int = 24,
    n_collocation: int = 3,
    effective_nfe: bool = True,
    residual_tol: float = 1e-4,
) -> dict[str, Any]:
    """Replay a SciPy trajectory with controls fixed and solve Pyomo with IPOPT."""
    pyomo_opt = _load_pyomo_optimizers()
    _, Pchamber, Tshelf = _scipy_task_setup(task)

    use_fd = method.lower() == "fd"
    treat_eff = (not use_fd) and bool(effective_nfe)
    scipy_traj = scipy_result["trajectory"]

    start = time.perf_counter()
    meta: dict[str, Any] = {}
    try:
        res = pyomo_opt.replay_scipy_controls_with_ipopt(
            scipy_traj,
            vial,
            product,
            ht,
            Pchamber,
            Tshelf,
            eq_cap,
            nVial,
            n_elements=int(n_elements),
            n_collocation=int(n_collocation),
            use_finite_differences=use_fd,
            treat_n_elements_as_effective=treat_eff,
            return_metadata=True,
            tee=False,
        )
        traj = res["output"]
        meta = res.get("metadata", {})
        comparison = compare_trajectories(scipy_traj, traj)
        termination = meta.get("termination_condition")
        max_residual = float(meta.get("max_constraint_residual", float("inf")))
        success = (
            isinstance(traj, np.ndarray)
            and traj.size > 0
            and _acceptable_pyomo_termination(termination)
            and max_residual <= residual_tol
        )
        message = (
            "ipopt replay completed"
            if success
            else f"ipopt replay validation failed: termination={termination}, max_residual={max_residual:.2e}"
        )
    except Exception as e:
        traj = np.empty((0, 7))
        comparison = {}
        success = False
        message = f"ipopt replay failure: {e.__class__.__name__}: {e}"[:300]
    wall = time.perf_counter() - start

    if use_fd:
        total_mesh_points = int(n_elements) + 1
    else:
        total_mesh_points = int(n_elements) * int(n_collocation) + 1
    discretization = {
        "method": "replay-fd" if use_fd else "replay-colloc",
        "n_elements_requested": int(n_elements),
        "n_elements_applied": int(n_elements),
        "n_collocation": int(n_collocation) if not use_fd else None,
        "effective_nfe": bool(treat_eff) if not use_fd else False,
        "total_mesh_points": total_mesh_points,
    }

    return {
        "trajectory": traj,
        "success": success,
        "message": message,
        "wall_time_s": wall,
        "objective_time_hr": float(meta["objective_time_hr"]) if success else None,
        "solver": {
            "status": meta.get("status"),
            "termination_condition": meta.get("termination_condition"),
            "ipopt_iterations": meta.get("ipopt_iterations"),
            "n_points": meta.get("n_points"),
            "staged_solve_success": None,
        },
        "solver_stats": {},
        "raw": traj,
        "warmstart_used": True,
        "discretization": discretization,
        "validation": {
            "kind": "scipy_control_replay",
            "residual_tol": residual_tol,
            "max_constraint_residual": meta.get("max_constraint_residual"),
            "residuals": meta.get("residuals"),
            "max_scipy_trajectory_residual": meta.get(
                "max_scipy_trajectory_residual"
            ),
            "scipy_trajectory_residuals": meta.get("scipy_trajectory_residuals"),
            "max_replay_solution_residual": meta.get(
                "max_replay_solution_residual"
            ),
            "replay_solution_residuals": meta.get("replay_solution_residuals"),
            "trajectory_comparison": comparison,
        },
    }


# Pyomo adapters -------------------------------------------------------------


def pyomo_adapter(
    task: str,
    vial: dict[str, float],
    product: dict[str, float],
    ht: dict[str, float],
    eq_cap: dict[str, float],
    nVial: int,
    scenario: dict[str, Any],
    dt: float = 0.01,
    warmstart: bool = False,
    method: str = "fd",  # 'fd' or 'colloc'
    n_elements: int = 24,
    n_collocation: int = 3,
    effective_nfe: bool = True,
    tsh_ramp_rate: float | None = None,  # Max Tsh ramp rate [°C/hr]
    pch_ramp_rate: float | None = None,  # Max Pch ramp rate [Torr/hr]
    use_secant_ramp_constraints: bool = True,  # Add secant slope constraints for collocation
) -> dict[str, Any]:
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
    use_secant_ramp_constraints : bool
        When using collocation with ramp constraints, add explicit secant slope constraints.
        Default True. If False, only polynomial derivative constraints are used, which may
        allow numerical derivatives between mesh points to exceed the ramp limit (by ~15%).
    """
    pyomo_opt = _load_pyomo_optimizers()

    if task == "Tsh":
        Pchamber = {"setpt": [0.1], "dt_setpt": [180.0], "ramp_rate": 0.5}
        Tshelf = {"min": -45.0, "max": 120.0}
        if tsh_ramp_rate is not None:
            Tshelf["max_ramp_rate"] = tsh_ramp_rate
        runner = pyomo_opt.optimize_Tsh_pyomo
        args = (vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial)
    elif task == "Pch":
        Pchamber, Tshelf = _pch_benchmark_controls()
        if pch_ramp_rate is not None:
            Pchamber["max_ramp_rate"] = pch_ramp_rate
        runner = pyomo_opt.optimize_Pch_pyomo
        args = (vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial)
    elif task == "both":
        Pchamber = {"min": 0.05, "max": 0.5}
        if pch_ramp_rate is not None:
            Pchamber["max_ramp_rate"] = pch_ramp_rate
        Tshelf = {"min": -45.0, "max": 120.0, "init": -35.0}
        if tsh_ramp_rate is not None:
            Tshelf["max_ramp_rate"] = tsh_ramp_rate
        runner = pyomo_opt.optimize_Pch_Tsh_pyomo
        args = (vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial)
    else:
        raise ValueError(f"Unknown task '{task}'")

    use_fd = method.lower() == "fd"
    treat_eff = (not use_fd) and bool(effective_nfe)

    start = time.perf_counter()
    meta: dict[str, Any] = {}
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
            use_secant_ramp_constraints=use_secant_ramp_constraints,
        )
        if isinstance(res, dict) and "output" in res:
            traj = res["output"]
            meta = res.get("metadata", {})
        else:
            traj = res
        termination = meta.get("termination_condition")
        success = (
            isinstance(traj, np.ndarray)
            and traj.size > 0
            and _acceptable_pyomo_termination(termination)
        )
        if success:
            message = "pyomo run completed"
        else:
            message = f"pyomo non-optimal termination: {termination}"
    except Exception as e:
        traj = np.empty((0, 7))
        success = False
        message = f"pyomo failure: {e.__class__.__name__}: {e}"[:300]
    wall = time.perf_counter() - start

    if success and isinstance(traj, np.ndarray) and traj.size:
        default_t = float(traj[-1, 0])
    else:
        default_t = None
    objective_time_hr = (
        float(meta.get("objective_time_hr", default_t)) if success else None
    )

    solver_info = {
        "status": meta.get("status"),
        "termination_condition": meta.get("termination_condition"),
        "ipopt_iterations": meta.get("ipopt_iterations"),
        "n_points": meta.get("n_points"),
        "staged_solve_success": meta.get("staged_solve_success"),
    }

    # Discretization reporting
    if use_fd:
        total_mesh_points = int(n_elements) + 1  # simple FD time mesh
    else:
        # For collocation, total interior points per element is n_collocation
        # Effective parity: treat effective_nfe True => report n_elements as comparable to FD
        total_mesh_points = int(n_elements) * int(n_collocation) + 1
    discretization = {
        "method": "fd" if use_fd else "colloc",
        "n_elements_requested": int(n_elements),
        "n_elements_applied": int(n_elements),  # could differ if transformation adjusts
        "n_collocation": int(n_collocation) if not use_fd else None,
        "effective_nfe": bool(treat_eff) if not use_fd else False,
        "total_mesh_points": total_mesh_points,
    }
    # Merge any mesh_info from metadata if present
    mesh_info = meta.get("mesh_info")
    if isinstance(mesh_info, dict):
        discretization.update(
            {k: v for k, v in mesh_info.items() if k not in discretization}
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
    }
