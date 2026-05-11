# Copyright (C) 2026, SECQUOIA

"""Experimental LyoPRONTO-facing policy OCP adapter.

This module keeps the paper-reference OCP separate from LyoPRONTO's production
cm/Torr/degC optimizer model.  It reuses the existing quasi-steady Pyomo
optimizer formulation and adds optional policy-style path caps in LyoPRONTO
units.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

import numpy as np
import pyomo.environ as pyo
from lyopronto import functions, opt_Tsh

from .optimizers import (
    _apply_ipopt_time_limits,
    _ensure_successful_solve,
    _extract_output_array,
    _fix_control_profile,
    _is_successful_termination,
    _solve_optimizer_model,
    _solver_limit_metadata,
    _solver_metadata,
    _warmstart_from_scipy_output,
    create_optimizer_model,
    validate_scipy_residuals,
)
from .utils import cake_length_conversion


def create_lyopronto_policy_ocp_model(
    vial: dict[str, float],
    product: dict[str, float],
    ht: dict[str, float],
    Pchamber: dict[str, Any],
    Tshelf: dict[str, Any],
    eq_cap: dict[str, float],
    nVial: int,
    *,
    n_elements: int = 24,
    n_collocation: int = 3,
    use_finite_differences: bool = True,
    treat_n_elements_as_effective: bool = False,
    control_mode: str = "Tsh",
    sublimation_flux_cap_kg_hr_m2: float | None = None,
    interface_velocity_cap_cm_hr: float | None = None,
    initial_conditions: dict[str, float] | None = None,
    apply_scaling: bool = True,
    use_secant_ramp_constraints: bool = True,
) -> pyo.ConcreteModel:
    """Create an experimental policy OCP model in LyoPRONTO units.

    The base model is the existing quasi-steady ``create_optimizer_model``.
    Optional caps are added as path constraints after discretization:

    - ``sublimation_flux_cap_kg_hr_m2`` limits output-column flux
      ``dmdt / Ap`` in ``kg/hr/m^2``.
    - ``interface_velocity_cap_cm_hr`` limits dried cake growth rate in
      ``cm/hr`` using the same conversion as the legacy optimizers.
    """
    flux_cap = _validate_positive_optional(
        sublimation_flux_cap_kg_hr_m2,
        "sublimation_flux_cap_kg_hr_m2",
    )
    velocity_cap = _validate_positive_optional(
        interface_velocity_cap_cm_hr,
        "interface_velocity_cap_cm_hr",
    )

    model = create_optimizer_model(
        vial,
        product,
        ht,
        vial["Vfill"],
        eq_cap,
        nVial,
        Pchamber=Pchamber,
        Tshelf=Tshelf,
        n_elements=n_elements,
        n_collocation=n_collocation,
        treat_n_elements_as_effective=treat_n_elements_as_effective,
        control_mode=control_mode,
        apply_scaling=apply_scaling,
        initial_conditions=initial_conditions,
        use_finite_differences=use_finite_differences,
        use_secant_ramp_constraints=use_secant_ramp_constraints,
    )

    area_m2 = float(vial["Ap"]) * 0.01**2
    velocity_conversion = cake_length_conversion(vial, product)

    if flux_cap is not None:

        def sublimation_flux_cap_rule(m, t):
            return m.dmdt[t] / area_m2 <= flux_cap

        model.sublimation_flux_cap = pyo.Constraint(
            model.t,
            rule=sublimation_flux_cap_rule,
        )

    if velocity_cap is not None:

        def interface_velocity_cap_rule(m, t):
            return m.dmdt[t] * velocity_conversion <= velocity_cap

        model.interface_velocity_cap = pyo.Constraint(
            model.t,
            rule=interface_velocity_cap_rule,
        )

    model._lyopronto_policy_config = {
        "vial": dict(vial),
        "product": dict(product),
        "heat_transfer": dict(ht),
        "Pchamber": dict(Pchamber),
        "Tshelf": dict(Tshelf),
        "equipment_capability": dict(eq_cap),
        "nVial": int(nVial),
    }
    model._lyopronto_policy_problem = {
        "name": "lyopronto_policy_ocp",
        "control_mode": control_mode,
        "temperature_limit_C": _product_temperature_limit(product),
        "shelf_temperature_min_C": Tshelf.get("min"),
        "shelf_temperature_max_C": Tshelf.get("max"),
        "sublimation_flux_cap_kg_hr_m2": flux_cap,
        "interface_velocity_cap_cm_hr": velocity_cap,
        "terminal_drying_fraction_target": 0.99,
    }
    model._lyopronto_policy_discretization = {
        "method": "fd" if use_finite_differences else "collocation",
        "n_elements_requested": int(n_elements),
        "n_collocation": None if use_finite_differences else int(n_collocation),
        "effective_nfe": bool(treat_n_elements_as_effective)
        if not use_finite_differences
        else False,
    }
    model._lyopronto_policy_area_m2 = area_m2
    model._lyopronto_policy_velocity_conversion_cm_hr_per_kg_hr = velocity_conversion

    return model


def solve_lyopronto_policy_ocp(
    vial: dict[str, float],
    product: dict[str, float],
    ht: dict[str, float],
    Pchamber: dict[str, Any],
    Tshelf: dict[str, Any],
    dt: float,
    eq_cap: dict[str, float],
    nVial: int,
    *,
    n_elements: int = 24,
    n_collocation: int = 3,
    use_finite_differences: bool = True,
    treat_n_elements_as_effective: bool = False,
    sublimation_flux_cap_kg_hr_m2: float | None = None,
    interface_velocity_cap_cm_hr: float | None = None,
    warmstart_scipy: bool = True,
    solver: str = "ipopt",
    solver_options: Mapping[str, Any] | None = None,
    tee: bool = False,
    require_success: bool = True,
    return_model: bool = False,
    use_secant_ramp_constraints: bool = True,
    solver_cpu_time: float | None = None,
    solver_wall_time: float | None = None,
) -> dict[str, Any]:
    """Solve the experimental shelf-temperature policy OCP.

    This is intentionally separate from ``optimize_Tsh_pyomo`` so existing
    optimizer return types and behavior remain unchanged.  The result follows
    the paper-reference benchmark shape: rich ``states``, ``controls``,
    ``metrics``, ``metadata``, ``problem``, and ``policies`` sections, plus the
    legacy 7-column trajectory for comparison.
    """
    model = create_lyopronto_policy_ocp_model(
        vial,
        product,
        ht,
        Pchamber,
        Tshelf,
        eq_cap,
        nVial,
        n_elements=n_elements,
        n_collocation=n_collocation,
        use_finite_differences=use_finite_differences,
        treat_n_elements_as_effective=treat_n_elements_as_effective,
        control_mode="Tsh",
        sublimation_flux_cap_kg_hr_m2=sublimation_flux_cap_kg_hr_m2,
        interface_velocity_cap_cm_hr=interface_velocity_cap_cm_hr,
        use_secant_ramp_constraints=use_secant_ramp_constraints,
    )

    if warmstart_scipy:
        scipy_output = opt_Tsh.dry(
            vial,
            product,
            ht,
            Pchamber,
            Tshelf,
            dt,
            eq_cap,
            nVial,
        )
        _warmstart_from_scipy_output(model, scipy_output, vial, product, ht)
        _fix_control_profile(model, "Pch", Pchamber, t_final=scipy_output[-1, 0])
        validate_scipy_residuals(model, scipy_output, vial, product, ht, verbose=tee)
    else:
        _fix_control_profile(model, "Pch", Pchamber)

    policy_cap_active = (
        model._lyopronto_policy_problem["sublimation_flux_cap_kg_hr_m2"] is not None
        or model._lyopronto_policy_problem["interface_velocity_cap_cm_hr"] is not None
    )
    use_staged_solve = warmstart_scipy and not policy_cap_active
    model._lyopronto_policy_solver_strategy = {
        "warmstart_scipy": bool(warmstart_scipy),
        "staged_solve_used": bool(use_staged_solve),
        "staged_solve_skip_reason": "policy_cap"
        if warmstart_scipy and policy_cap_active
        else None,
    }

    try:
        from idaes.core.solvers import get_solver

        opt = get_solver(solver)
    except Exception:
        opt = pyo.SolverFactory(solver)

    if solver == "ipopt" and hasattr(opt, "options"):
        opt.options.setdefault("max_iter", 5000)
        opt.options.setdefault("tol", 1.0e-6)
        opt.options.setdefault("acceptable_tol", 1.0e-4)
        opt.options.setdefault("print_level", 5 if tee else 0)
        opt.options.setdefault("mu_strategy", "adaptive")
        opt.options.setdefault("bound_relax_factor", 1.0e-8)
        opt.options.setdefault("constr_viol_tol", 1.0e-6)
        if warmstart_scipy:
            opt.options.setdefault("warm_start_init_point", "yes")
            opt.options.setdefault("warm_start_bound_push", 1.0e-8)
            opt.options.setdefault("warm_start_mult_bound_push", 1.0e-8)

    if solver_options:
        for key, value in solver_options.items():
            opt.options[key] = value

    solver_time_options = _apply_ipopt_time_limits(
        opt,
        solver,
        solver_cpu_time=solver_cpu_time,
        solver_wall_time=solver_wall_time,
    )
    results = _solve_optimizer_model(
        model,
        opt,
        context="solve_lyopronto_policy_ocp",
        control_mode="Tsh",
        warmstart_scipy=use_staged_solve,
        simulation_mode=False,
        tee=tee,
    )
    solution = extract_lyopronto_policy_solution(
        model,
        results,
        solver_limit_options=solver_time_options,
    )
    solution["policies"] = classify_lyopronto_policies(solution)
    if return_model:
        solution["model"] = model

    if require_success and not _is_successful_termination(results):
        metadata = solution["metadata"]
        raise RuntimeError(
            "LyoPRONTO policy OCP solve did not converge "
            f"(status={metadata['status']}, "
            f"termination_condition={metadata['termination_condition']})"
        )
    if require_success:
        _ensure_successful_solve(results, "solve_lyopronto_policy_ocp")
    return solution


def extract_lyopronto_policy_solution(
    model: pyo.ConcreteModel,
    results: Any | None = None,
    *,
    solver_limit_options: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Extract a LyoPRONTO policy model into a paper-style rich result."""
    config = model._lyopronto_policy_config
    vial = config["vial"]
    product = config["product"]
    problem = dict(model._lyopronto_policy_problem)
    discretization = dict(model._lyopronto_policy_discretization)
    t_points = sorted(model.t)
    t_final = float(pyo.value(model.t_final))
    tau = np.array([float(t) for t in t_points])
    time_hr = tau * t_final
    time_s = time_hr * 3600.0

    trajectory = _extract_output_array(model, vial, product)
    lpr0 = functions.Lpr0_FUN(vial["Vfill"], vial["Ap"], product["cSolid"])
    area_m2 = model._lyopronto_policy_area_m2
    velocity_conversion = model._lyopronto_policy_velocity_conversion_cm_hr_per_kg_hr

    tsub = np.array([float(pyo.value(model.Tsub[t])) for t in t_points])
    tbot = np.array([float(pyo.value(model.Tbot[t])) for t in t_points])
    tsh = np.array([float(pyo.value(model.Tsh[t])) for t in t_points])
    pch_torr = np.array([float(pyo.value(model.Pch[t])) for t in t_points])
    psub_torr = np.array([float(pyo.value(model.Psub[t])) for t in t_points])
    resistance = np.array([float(pyo.value(model.Rp[t])) for t in t_points])
    dmdt = np.array([float(pyo.value(model.dmdt[t])) for t in t_points])
    interface_position = np.array([float(pyo.value(model.Lck[t])) for t in t_points])
    flux = dmdt / area_m2
    interface_velocity = dmdt * velocity_conversion
    drying_fraction = interface_position / lpr0 if lpr0 > 0 else np.zeros_like(tau)

    temperature_limit = float(problem["temperature_limit_C"])
    shelf_min = problem.get("shelf_temperature_min_C")
    shelf_max = problem.get("shelf_temperature_max_C")
    flux_cap = problem.get("sublimation_flux_cap_kg_hr_m2")
    velocity_cap = problem.get("interface_velocity_cap_cm_hr")

    metrics = {
        "drying_time_hr": t_final,
        "drying_time_s": t_final * 3600.0,
        "terminal_interface_position_cm": float(interface_position[-1]),
        "terminal_drying_fraction": float(drying_fraction[-1]),
        "terminal_percent_dried": float(drying_fraction[-1] * 100.0),
        "max_product_temperature_C": float(tbot.max()),
        "max_temperature_violation_C": max(0.0, float(tbot.max() - temperature_limit)),
        "max_sublimation_flux_kg_hr_m2": float(flux.max()),
        "max_interface_velocity_cm_per_hr": float(interface_velocity.max()),
    }
    if shelf_min is not None:
        metrics["shelf_lower_violation_C"] = max(
            0.0,
            float(float(shelf_min) - tsh.min()),
        )
    if shelf_max is not None:
        metrics["shelf_upper_violation_C"] = max(
            0.0,
            float(tsh.max() - float(shelf_max)),
        )
    if flux_cap is not None:
        metrics["max_sublimation_flux_violation_kg_hr_m2"] = max(
            0.0,
            float(flux.max() - float(flux_cap)),
        )
    if velocity_cap is not None:
        metrics["max_interface_velocity_violation_cm_per_hr"] = max(
            0.0,
            float(interface_velocity.max() - float(velocity_cap)),
        )

    status = None
    termination_condition = None
    if results is not None:
        solver_info = getattr(results, "solver", None)
        status = str(getattr(solver_info, "status", None))
        termination_condition = str(getattr(solver_info, "termination_condition", None))

    metadata = {
        "status": status,
        "termination_condition": termination_condition,
        **discretization,
    }
    metadata.update(getattr(model, "_lyopronto_policy_solver_strategy", {}))
    if results is not None:
        metadata.update(_solver_metadata(results))
    if solver_limit_options:
        metadata.update(_solver_limit_metadata(dict(solver_limit_options)))

    return {
        "states": {
            "tau": tau,
            "time_hr": time_hr,
            "time_s": time_s,
            "sublimation_temperature_C": tsub,
            "product_temperature_C": tbot,
            "vial_bottom_temperature_C": tbot,
            "interface_position_cm": interface_position,
            "interface_velocity_cm_per_hr": interface_velocity,
            "sublimation_flux_kg_hr_m2": flux,
            "sublimation_rate_kg_hr": dmdt,
            "product_resistance_cm2_hr_torr_per_g": resistance,
            "vapor_pressure_Torr": psub_torr,
            "drying_fraction": drying_fraction,
            "percent_dried": drying_fraction * 100.0,
        },
        "controls": {
            "shelf_temperature_C": tsh,
            "chamber_pressure_Torr": pch_torr,
            "chamber_pressure_mTorr": pch_torr * 1000.0,
        },
        "metrics": metrics,
        "metadata": metadata,
        "problem": problem,
        "config": config,
        "trajectory": trajectory,
    }


def classify_lyopronto_policies(
    result: Mapping[str, Any],
    tolerances: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    """Infer active policies from a LyoPRONTO policy-OCP trajectory.

    Policy 1 is maximum shelf heat input, Policy 2 is product-temperature
    tracking, and Policy 3 is active flux or interface-velocity tracking.
    Product-temperature activity takes precedence when multiple path constraints
    are active at the same time.
    """
    tolerances = dict(tolerances or {})
    temperature_tolerance = tolerances.get("temperature_C", 0.25)
    shelf_tolerance = tolerances.get("shelf_temperature_C", 0.25)
    flux_tolerance = tolerances.get("sublimation_flux_kg_hr_m2", 1.0e-6)
    velocity_tolerance = tolerances.get("interface_velocity_cm_per_hr", 1.0e-6)

    states = result["states"]
    controls = result["controls"]
    problem = result["problem"]
    time_hr = np.asarray(states["time_hr"])
    product_temperature = np.asarray(states["product_temperature_C"])
    shelf_temperature = np.asarray(controls["shelf_temperature_C"])
    flux = np.asarray(
        states.get(
            "sublimation_flux_kg_hr_m2",
            np.full(product_temperature.shape, np.nan, dtype=float),
        )
    )
    velocity = np.asarray(
        states.get(
            "interface_velocity_cm_per_hr",
            np.full(product_temperature.shape, np.nan, dtype=float),
        )
    )

    temperature_limit = float(problem["temperature_limit_C"])
    shelf_max = problem.get("shelf_temperature_max_C")
    flux_cap = problem.get("sublimation_flux_cap_kg_hr_m2")
    velocity_cap = problem.get("interface_velocity_cap_cm_hr")

    labels: list[str] = []
    for temp, shelf, flux_value, velocity_value in zip(
        product_temperature,
        shelf_temperature,
        flux,
        velocity,
    ):
        temp_active = temp >= temperature_limit - temperature_tolerance
        flux_active = (
            flux_cap is not None and flux_value >= float(flux_cap) - flux_tolerance
        )
        velocity_active = (
            velocity_cap is not None
            and velocity_value >= float(velocity_cap) - velocity_tolerance
        )
        shelf_active = (
            shelf_max is not None and abs(shelf - float(shelf_max)) <= shelf_tolerance
        )

        if temp_active:
            labels.append("policy_2_product_temperature_tracking")
        elif flux_active:
            labels.append("policy_3_sublimation_flux_tracking")
        elif velocity_active:
            labels.append("policy_3_interface_velocity_tracking")
        elif shelf_active:
            labels.append("policy_1_max_heat_input")
        else:
            labels.append("unclassified")

    segments = _compress_policy_labels(time_hr, labels)
    switch_times = [segment["start_time_hr"] for segment in segments[1:]]
    return {
        "labels": labels,
        "segments": segments,
        "switch_times_hr": switch_times,
    }


def _validate_positive_optional(value: float | None, name: str) -> float | None:
    if value is None:
        return None
    value = float(value)
    if value <= 0.0:
        raise ValueError(f"{name} must be positive when provided")
    return value


def _product_temperature_limit(product: Mapping[str, float]) -> float:
    return float(product.get("Tpr_max", product.get("T_pr_crit", -25.0)))


def _compress_policy_labels(
    time_hr: Iterable[float],
    labels: Iterable[str],
) -> list[dict[str, Any]]:
    times = list(time_hr)
    label_list = list(labels)
    if not label_list:
        return []

    segments: list[dict[str, Any]] = []
    current = label_list[0]
    start_index = 0
    for index, label in enumerate(label_list[1:], start=1):
        if label != current:
            segments.append(
                {
                    "label": current,
                    "start_time_hr": float(times[start_index]),
                    "end_time_hr": float(times[index - 1]),
                }
            )
            current = label
            start_index = index
    segments.append(
        {
            "label": current,
            "start_time_hr": float(times[start_index]),
            "end_time_hr": float(times[-1]),
        }
    )
    return segments
