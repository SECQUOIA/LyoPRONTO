"""Advanced optional Pyomo workflow builders for primary drying.

The functions in this module compose the lower-level trajectory and
optimization builders into validation-oriented workflows. They remain explicit
Pyomo entry points and do not affect the legacy SciPy calculators.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

import numpy as np
import pyomo.environ as pyo  # type: ignore[import-untyped]

from .. import constant, functions
from .optimization import ModeInput, create_primary_drying_optimization_model
from .trajectory import (
    ProfileInput,
    VariableBounds,
    WarmstartInput,
    create_trajectory_model,
)


ParameterBounds = Mapping[str, VariableBounds]
ObservationInput = Mapping[str, float]
SensitivityModelKey = Tuple[str, float]
SensitivityPerturbations = Mapping[str, Sequence[float]]
ScenarioOverrides = Mapping[str, Mapping[str, float]]
RobustScenarios = Mapping[str, ScenarioOverrides]

_PRODUCT_PARAMETER_NAMES = ("R0", "A1", "A2")
_HEAT_TRANSFER_PARAMETER_NAMES = ("KC", "KP", "KD")
_PARAMETER_NAMES = _PRODUCT_PARAMETER_NAMES + _HEAT_TRANSFER_PARAMETER_NAMES
_BASELINE_SENSITIVITY_LABEL = "baseline"
_SCENARIO_GROUPS = ("vial", "product", "ht", "eq_cap")

_DEFAULT_PARAMETER_BOUNDS: Dict[str, VariableBounds] = {
    "R0": (0.0, None),
    "A1": (0.0, None),
    "A2": (0.0, None),
    "KC": (0.0, None),
    "KP": (0.0, None),
    "KD": (0.0, None),
}


def _require_keys(name: str, data: Mapping[str, float], keys: Sequence[str]) -> None:
    missing = [key for key in keys if key not in data]
    if missing:
        joined = ", ".join(missing)
        raise KeyError(f"{name} is missing required key(s): {joined}")


def _normalize_observations(observations: Sequence[ObservationInput]) -> Tuple[Dict[str, float], ...]:
    if not observations:
        raise ValueError("observations must contain at least one point")

    normalized = []
    for index, observation in enumerate(observations):
        _require_keys(f"observations[{index}]", observation, ("Lck", "Pch"))
        normalized.append({key: float(value) for key, value in observation.items()})
    return tuple(normalized)


def _parameter_bounds(
    name: str,
    parameter_bounds: Optional[ParameterBounds],
) -> VariableBounds:
    if parameter_bounds is not None and name in parameter_bounds:
        lower, upper = parameter_bounds[name]
        return (
            None if lower is None else float(lower),
            None if upper is None else float(upper),
        )
    return _DEFAULT_PARAMETER_BOUNDS[name]


def _add_parameter(
    model: pyo.ConcreteModel,
    name: str,
    initial_value: float,
    estimate: bool,
    parameter_bounds: Optional[ParameterBounds],
) -> None:
    if estimate:
        setattr(
            model,
            name,
            pyo.Var(
                domain=pyo.NonNegativeReals,
                bounds=_parameter_bounds(name, parameter_bounds),
                initialize=float(initial_value),
            ),
        )
    else:
        setattr(model, name, pyo.Param(initialize=float(initial_value)))


def _profile_bounds(name: str, profile: ProfileInput) -> VariableBounds:
    values = np.asarray(list(profile.values()) if isinstance(profile, Mapping) else profile, dtype=float)
    if values.size == 0 or not np.all(np.isfinite(values)):
        raise ValueError(f"{name} must contain finite values")
    return float(np.min(values)), float(np.max(values))


def _constant_profile(value: float, n_steps: int) -> Tuple[float, ...]:
    return tuple(float(value) for _ in range(int(n_steps) + 1))


def _float_dict(data: Mapping[str, float]) -> Dict[str, float]:
    return {key: float(value) for key, value in data.items()}


def _copy_case_inputs(
    vial: Mapping[str, float],
    product: Mapping[str, float],
    ht: Mapping[str, float],
) -> Tuple[Dict[str, float], Dict[str, float], Dict[str, float]]:
    return _float_dict(vial), _float_dict(product), _float_dict(ht)


def _apply_parameter_perturbation(
    vial: Mapping[str, float],
    product: Mapping[str, float],
    ht: Mapping[str, float],
    parameter_name: str,
    perturbation_fraction: float,
) -> Tuple[Dict[str, float], Dict[str, float], Dict[str, float], float, float]:
    vial_case, product_case, ht_case = _copy_case_inputs(vial, product, ht)
    groups = (("vial", vial_case), ("product", product_case), ("ht", ht_case))
    try:
        _group_name, target = next(group for group in groups if parameter_name in group[1])
    except StopIteration as exc:
        raise KeyError(
            f"parameter_perturbations contains unknown parameter: {parameter_name}"
        ) from exc

    base_value = float(target[parameter_name])
    perturbed_value = base_value * (1.0 + float(perturbation_fraction))
    if not np.isfinite(perturbed_value):
        raise ValueError(f"perturbed value for {parameter_name} must be finite")
    if parameter_name in _PARAMETER_NAMES and perturbed_value < 0.0:
        raise ValueError(f"perturbed value for {parameter_name} must be nonnegative")

    target[parameter_name] = perturbed_value
    return vial_case, product_case, ht_case, base_value, perturbed_value


def _tag_sensitivity_model(
    model: pyo.ConcreteModel,
    parameter_name: str,
    perturbation_fraction: float,
    base_value: Optional[float],
    perturbed_value: Optional[float],
) -> pyo.ConcreteModel:
    model.advanced_workflow = "sensitivity_analysis"
    model.validation_scenario = (
        "local finite-difference parameter perturbation around fixed "
        "pressure/shelf-temperature controls"
    )
    model.sensitivity_parameter = parameter_name
    model.sensitivity_perturbation_fraction = float(perturbation_fraction)
    model.sensitivity_base_value = base_value
    model.sensitivity_perturbed_value = perturbed_value
    model.sensitivity_difference_denominator = (
        None if base_value is None or perturbed_value is None else perturbed_value - base_value
    )
    return model


def _scenario_case_inputs(
    vial: Mapping[str, float],
    product: Mapping[str, float],
    ht: Mapping[str, float],
    eq_cap: Optional[Mapping[str, float]],
    overrides: ScenarioOverrides,
    scenario_label: str,
    nvial: Optional[int],
) -> Tuple[Dict[str, float], Dict[str, float], Dict[str, float], Optional[Dict[str, float]]]:
    unknown_groups = [name for name in overrides if name not in _SCENARIO_GROUPS]
    if unknown_groups:
        joined = ", ".join(unknown_groups)
        raise KeyError(f"scenario '{scenario_label}' override contains unknown group(s): {joined}")

    vial_case, product_case, ht_case = _copy_case_inputs(vial, product, ht)
    eq_cap_case = None if eq_cap is None else _float_dict(eq_cap)
    cases = {
        "vial": vial_case,
        "product": product_case,
        "ht": ht_case,
        "eq_cap": eq_cap_case,
    }

    for group_name, group_overrides in overrides.items():
        if group_name == "eq_cap" and cases[group_name] is None:
            if nvial is None or any(key not in group_overrides for key in ("a", "b")):
                raise ValueError(
                    f"scenario '{scenario_label}' overrides eq_cap but no base eq_cap/nvial "
                    "was provided; supply both 'a' and 'b' and a nvial"
                )
            cases[group_name] = {}
            eq_cap_case = cases[group_name]
        target = cases[group_name]
        if target is None:
            raise ValueError(
                f"scenario '{scenario_label}' group {group_name} cannot be overridden "
                "without inputs"
            )
        target.update(_float_dict(group_overrides))

    if eq_cap_case is not None:
        missing = [key for key in ("a", "b") if key not in eq_cap_case]
        if missing:
            joined = ", ".join(missing)
            raise KeyError(
                f"scenario '{scenario_label}' eq_cap is missing required key(s): {joined}"
            )
        if nvial is None:
            raise ValueError(f"scenario '{scenario_label}' includes eq_cap but nvial is required")

    return vial_case, product_case, ht_case, eq_cap_case


def _normalize_scenarios(scenarios: RobustScenarios) -> Tuple[Tuple[str, ScenarioOverrides], ...]:
    if len(scenarios) == 0:
        raise ValueError("scenarios must contain at least one scenario")

    normalized = []
    seen = set()
    for label, overrides in scenarios.items():
        scenario_label = str(label)
        if scenario_label in seen:
            raise ValueError(f"duplicate scenario label after string conversion: {scenario_label}")
        seen.add(scenario_label)
        normalized.append((scenario_label, overrides))
    return tuple(normalized)


def _add_batch_capacity_diagnostics(model: pyo.ConcreteModel) -> None:
    if not all(hasattr(model, name) for name in ("eq_cap_a", "eq_cap_b", "nvial")):
        return
    if hasattr(model, "total_sublimation_rate"):
        return

    model.batch_capacity_basis = "nvial*dmdt <= eq_cap.a + eq_cap.b*Pch"
    model.total_sublimation_rate = pyo.Expression(
        model.TIME, rule=lambda m, t: m.nvial * m.dmdt[t]
    )
    model.equipment_capacity_limit = pyo.Expression(
        model.TIME, rule=lambda m, t: m.eq_cap_a + m.eq_cap_b * m.Pch[t]
    )
    model.capacity_margin = pyo.Expression(
        model.TIME, rule=lambda m, t: m.equipment_capacity_limit[t] - m.total_sublimation_rate[t]
    )


def create_parameter_estimation_model(
    vial: Mapping[str, float],
    product: Mapping[str, float],
    ht: Mapping[str, float],
    observations: Sequence[ObservationInput],
    *,
    estimate_product_resistance: bool = True,
    estimate_heat_transfer: bool = True,
    parameter_bounds: Optional[ParameterBounds] = None,
    residual_weights: Optional[Mapping[str, float]] = None,
) -> pyo.ConcreteModel:
    """Create a Pyomo least-squares model for Rp and Kv parameter estimation.

    Observations use legacy units: dried cake length in cm, pressure in Torr,
    sublimation rate in kg/hr/vial, heat-transfer coefficient in cal/s/K/cm^2,
    and temperature in degC. Each point must include ``Lck`` and ``Pch``.
    Optional targets are:

    - ``Rp`` for direct product-resistance fitting;
    - ``dmdt`` with ``Tsub`` for mass-transfer fitting;
    - ``Kv`` for direct heat-transfer fitting.

    The objective is the sum of weighted squared residuals over the provided
    targets. Parameters outside the selected families are fixed at the supplied
    ``product`` or ``ht`` values.
    """
    _require_keys("vial", vial, ("Ap",))
    _require_keys("product", product, _PRODUCT_PARAMETER_NAMES)
    _require_keys("ht", ht, _HEAT_TRANSFER_PARAMETER_NAMES)
    normalized = _normalize_observations(observations)
    weights = {key: float(value) for key, value in (residual_weights or {}).items()}

    model = pyo.ConcreteModel()
    model.advanced_workflow = "parameter_estimation"
    model.validation_scenario = (
        "synthetic fixed-time observations with known product-resistance and "
        "heat-transfer targets"
    )
    model.estimated_parameters = tuple(
        name
        for names, enabled in (
            (_PRODUCT_PARAMETER_NAMES, estimate_product_resistance),
            (_HEAT_TRANSFER_PARAMETER_NAMES, estimate_heat_transfer),
        )
        if enabled
        for name in names
    )
    model.OBS = pyo.RangeSet(0, len(normalized) - 1)
    model.Ap = pyo.Param(initialize=float(vial["Ap"]))
    model.kg_To_g = pyo.Param(initialize=constant.kg_To_g)

    for name in _PRODUCT_PARAMETER_NAMES:
        _add_parameter(
            model,
            name,
            float(product[name]),
            estimate_product_resistance,
            parameter_bounds,
        )
    for name in _HEAT_TRANSFER_PARAMETER_NAMES:
        _add_parameter(
            model,
            name,
            float(ht[name]),
            estimate_heat_transfer,
            parameter_bounds,
        )

    model.Lck_obs = pyo.Param(
        model.OBS, initialize={index: point["Lck"] for index, point in enumerate(normalized)}
    )
    model.Pch_obs = pyo.Param(
        model.OBS, initialize={index: point["Pch"] for index, point in enumerate(normalized)}
    )
    model.Rp_model = pyo.Expression(
        model.OBS,
        rule=lambda m, i: functions.Rp_FUN(m.Lck_obs[i], m.R0, m.A1, m.A2),
    )
    model.Kv_model = pyo.Expression(
        model.OBS,
        rule=lambda m, i: functions.Kv_FUN(m.KC, m.KP, m.KD, m.Pch_obs[i]),
    )

    residual_terms = []
    residual_labels = []
    for index, point in enumerate(normalized):
        if "Rp" in point:
            residual_terms.append(weights.get("Rp", 1.0) * (model.Rp_model[index] - point["Rp"]) ** 2)
            residual_labels.append(f"Rp[{index}]")
        if "dmdt" in point and "Tsub" in point:
            psub = float(functions.Vapor_pressure(point["Tsub"]))
            predicted_dmdt = model.Ap / model.Rp_model[index] / model.kg_To_g * (
                psub - point["Pch"]
            )
            residual_terms.append(
                weights.get("dmdt", 1.0) * (predicted_dmdt - point["dmdt"]) ** 2
            )
            residual_labels.append(f"dmdt[{index}]")
        if "Kv" in point:
            residual_terms.append(weights.get("Kv", 1.0) * (model.Kv_model[index] - point["Kv"]) ** 2)
            residual_labels.append(f"Kv[{index}]")

    if not residual_terms:
        raise ValueError(
            "observations must include at least one target: Rp, Kv, or dmdt with Tsub"
        )

    model.residual_targets = tuple(residual_labels)
    model.obj = pyo.Objective(expr=sum(residual_terms), sense=pyo.minimize)
    return model


def create_design_space_feasibility_model(
    vial: Mapping[str, float],
    product: Mapping[str, float],
    ht: Mapping[str, float],
    pch_profile: ProfileInput,
    tsh_profile: ProfileInput,
    *,
    n_steps: int,
    dt: float,
    eq_cap: Optional[Mapping[str, float]] = None,
    nvial: Optional[int] = None,
    final_dried_fraction: float = 0.995,
    tbot_upper: Optional[float] = None,
    lpr0: Optional[float] = None,
    initialize: Optional[WarmstartInput] = None,
) -> pyo.ConcreteModel:
    """Create a fixed-control Pyomo feasibility replay for one design point."""
    model = create_trajectory_model(
        vial,
        product,
        ht,
        n_steps=n_steps,
        dt=dt,
        pch_bounds=_profile_bounds("pch_profile", pch_profile),
        tsh_bounds=_profile_bounds("tsh_profile", tsh_profile),
        final_dried_fraction=final_dried_fraction,
        fixed_pch_profile=pch_profile,
        fixed_tsh_profile=tsh_profile,
        eq_cap=eq_cap,
        nvial=nvial,
        tbot_upper=tbot_upper,
        lpr0=lpr0,
        initialize=initialize,
    )
    model.obj.deactivate()
    model.feasibility_objective = pyo.Objective(expr=0.0, sense=pyo.minimize)
    model.advanced_workflow = "design_space_feasibility"
    model.fixed_controls = ("Pch", "Tsh")
    model.validation_scenario = (
        "fixed pressure/shelf-temperature design point with product-temperature "
        "and optional equipment-capacity constraints"
    )
    return model


def create_design_space_grid_models(
    vial: Mapping[str, float],
    product: Mapping[str, float],
    ht: Mapping[str, float],
    pressure_values: Sequence[float],
    shelf_temperature_values: Sequence[float],
    *,
    n_steps: int,
    dt: float,
    eq_cap: Optional[Mapping[str, float]] = None,
    nvial: Optional[int] = None,
    final_dried_fraction: float = 0.995,
    tbot_upper: Optional[float] = None,
    lpr0: Optional[float] = None,
) -> Dict[Tuple[float, float], pyo.ConcreteModel]:
    """Create fixed-control feasibility models over a pressure/temperature grid."""
    if len(pressure_values) == 0:
        raise ValueError("pressure_values must contain at least one value")
    if len(shelf_temperature_values) == 0:
        raise ValueError("shelf_temperature_values must contain at least one value")

    models = {}
    for pressure in pressure_values:
        for shelf_temperature in shelf_temperature_values:
            point = (float(pressure), float(shelf_temperature))
            model = create_design_space_feasibility_model(
                vial,
                product,
                ht,
                _constant_profile(point[0], n_steps),
                _constant_profile(point[1], n_steps),
                n_steps=n_steps,
                dt=dt,
                eq_cap=eq_cap,
                nvial=nvial,
                final_dried_fraction=final_dried_fraction,
                tbot_upper=tbot_upper,
                lpr0=lpr0,
            )
            model.design_space_point = point
            models[point] = model
    return models


def create_sensitivity_analysis_models(
    vial: Mapping[str, float],
    product: Mapping[str, float],
    ht: Mapping[str, float],
    pch_profile: ProfileInput,
    tsh_profile: ProfileInput,
    parameter_perturbations: SensitivityPerturbations,
    *,
    n_steps: int,
    dt: float,
    eq_cap: Optional[Mapping[str, float]] = None,
    nvial: Optional[int] = None,
    final_dried_fraction: float = 0.995,
    tbot_upper: Optional[float] = None,
    lpr0: Optional[float] = None,
    include_baseline: bool = True,
) -> Dict[SensitivityModelKey, pyo.ConcreteModel]:
    """Create fixed-control perturbation models for local sensitivity analysis.

    ``parameter_perturbations`` maps a vial, product, or heat-transfer
    parameter name to fractional perturbations, for example
    ``{"R0": [-0.1, 0.1], "KC": [0.05]}``. Each returned model is a
    feasibility replay with metadata needed to finite-difference solved
    trajectory outputs against the optional baseline model.
    """
    if len(parameter_perturbations) == 0:
        raise ValueError("parameter_perturbations must contain at least one parameter")

    models: Dict[SensitivityModelKey, pyo.ConcreteModel] = {}
    if include_baseline:
        baseline = create_design_space_feasibility_model(
            vial,
            product,
            ht,
            pch_profile,
            tsh_profile,
            n_steps=n_steps,
            dt=dt,
            eq_cap=eq_cap,
            nvial=nvial,
            final_dried_fraction=final_dried_fraction,
            tbot_upper=tbot_upper,
            lpr0=lpr0,
        )
        models[(_BASELINE_SENSITIVITY_LABEL, 0.0)] = _tag_sensitivity_model(
            baseline,
            _BASELINE_SENSITIVITY_LABEL,
            0.0,
            None,
            None,
        )

    for parameter_name, perturbations in parameter_perturbations.items():
        if len(perturbations) == 0:
            raise ValueError(f"perturbations for {parameter_name} must not be empty")
        for perturbation_fraction in perturbations:
            fraction = float(perturbation_fraction)
            if not np.isfinite(fraction):
                raise ValueError(f"perturbation for {parameter_name} must be finite")
            vial_case, product_case, ht_case, base_value, perturbed_value = (
                _apply_parameter_perturbation(vial, product, ht, parameter_name, fraction)
            )
            model = create_design_space_feasibility_model(
                vial_case,
                product_case,
                ht_case,
                pch_profile,
                tsh_profile,
                n_steps=n_steps,
                dt=dt,
                eq_cap=eq_cap,
                nvial=nvial,
                final_dried_fraction=final_dried_fraction,
                tbot_upper=tbot_upper,
                lpr0=lpr0,
            )
            key = (str(parameter_name), fraction)
            models[key] = _tag_sensitivity_model(
                model,
                str(parameter_name),
                fraction,
                base_value,
                perturbed_value,
            )

    return models


def create_multivial_optimization_model(
    vial: Mapping[str, float],
    product: Mapping[str, float],
    ht: Mapping[str, float],
    pchamber: Mapping[str, Any],
    tshelf: Mapping[str, Any],
    *,
    n_steps: int,
    dt: float,
    mode: ModeInput,
    eq_cap: Mapping[str, float],
    nvial: int,
    final_dried_fraction: float = 0.995,
    enforce_ramp_rates: bool = False,
    pch_ramp_rate: Optional[float] = None,
    tsh_ramp_rate: Optional[float] = None,
    tbot_upper: Optional[float] = None,
    lpr0: Optional[float] = None,
    initialize: Optional[WarmstartInput] = None,
) -> pyo.ConcreteModel:
    """Create a Pyomo optimization model with explicit batch-capacity tracking.

    This builder uses the trajectory model's existing equipment-capability
    constraint and requires ``eq_cap``/``nvial`` so batch scope is explicit. It
    adds named diagnostic expressions for total sublimation rate, capacity
    limit, and margin; it does not introduce independent per-vial decision
    variables.
    """
    if int(nvial) <= 0:
        raise ValueError("nvial must be positive")

    model = create_primary_drying_optimization_model(
        vial,
        product,
        ht,
        pchamber,
        tshelf,
        n_steps=n_steps,
        dt=dt,
        mode=mode,
        eq_cap=eq_cap,
        nvial=int(nvial),
        final_dried_fraction=final_dried_fraction,
        enforce_ramp_rates=enforce_ramp_rates,
        pch_ramp_rate=pch_ramp_rate,
        tsh_ramp_rate=tsh_ramp_rate,
        tbot_upper=tbot_upper,
        lpr0=lpr0,
        initialize=initialize,
    )
    model.advanced_workflow = "multi_vial_optimization"
    model.validation_scenario = (
        "batch-level sublimation-rate constraint with total rate nvial*dmdt "
        "bounded by a + b*Pch"
    )
    _add_batch_capacity_diagnostics(model)
    return model


def create_robust_optimization_model(
    vial: Mapping[str, float],
    product: Mapping[str, float],
    ht: Mapping[str, float],
    pchamber: Mapping[str, Any],
    tshelf: Mapping[str, Any],
    scenarios: RobustScenarios,
    *,
    n_steps: int,
    dt: float,
    mode: ModeInput,
    eq_cap: Optional[Mapping[str, float]] = None,
    nvial: Optional[int] = None,
    final_dried_fraction: float = 0.995,
    enforce_ramp_rates: bool = False,
    pch_ramp_rate: Optional[float] = None,
    tsh_ramp_rate: Optional[float] = None,
    tbot_upper: Optional[float] = None,
    lpr0: Optional[float] = None,
    initialize: Optional[WarmstartInput] = None,
) -> pyo.ConcreteModel:
    """Create a scenario-based robust optimization model.

    Each scenario is a deterministic Pyomo optimization block built from the
    existing optimizer with optional overrides for ``vial``, ``product``,
    ``ht``, and ``eq_cap`` dictionaries. The optimized control profiles are
    shared across scenarios, and the top-level objective minimizes the worst
    scenario value of the existing driving-force objective.
    """
    normalized_scenarios = _normalize_scenarios(scenarios)
    scenario_labels = tuple(label for label, _overrides in normalized_scenarios)
    reference_label = scenario_labels[0]

    model = pyo.ConcreteModel()
    model.advanced_workflow = "robust_optimization"
    model.validation_scenario = (
        "scenario-based robust optimization with shared control profiles across "
        "product, heat-transfer, vial, or equipment-capacity uncertainty cases"
    )
    model.robust_objective = "minimize_worst_case_sum_Pch_minus_Psub"
    model.reference_scenario = reference_label
    model.scenario_overrides = dict(normalized_scenarios)
    model.SCENARIOS = pyo.Set(initialize=scenario_labels, ordered=True)
    model.TIME = pyo.RangeSet(0, int(n_steps))
    model.scenario_blocks = pyo.Block(model.SCENARIOS)

    for scenario_label, overrides in normalized_scenarios:
        vial_case, product_case, ht_case, eq_cap_case = _scenario_case_inputs(
            vial,
            product,
            ht,
            eq_cap,
            overrides,
            scenario_label,
            nvial,
        )
        scenario_model = create_primary_drying_optimization_model(
            vial_case,
            product_case,
            ht_case,
            pchamber,
            tshelf,
            n_steps=n_steps,
            dt=dt,
            mode=mode,
            eq_cap=eq_cap_case,
            nvial=nvial,
            final_dried_fraction=final_dried_fraction,
            enforce_ramp_rates=enforce_ramp_rates,
            pch_ramp_rate=pch_ramp_rate,
            tsh_ramp_rate=tsh_ramp_rate,
            tbot_upper=tbot_upper,
            lpr0=lpr0,
            initialize=initialize,
        )
        block = model.scenario_blocks[scenario_label]
        block.transfer_attributes_from(scenario_model)
        block.robust_scenario = scenario_label
        block.robust_overrides = overrides
        block.obj.deactivate()
        _add_batch_capacity_diagnostics(block)

    reference_block = model.scenario_blocks[reference_label]
    optimized_controls = reference_block.optimized_controls
    model.optimized_controls = optimized_controls
    model.fixed_controls = reference_block.fixed_controls

    if "Pch" in optimized_controls:
        model.shared_chamber_pressure = pyo.Constraint(
            model.SCENARIOS,
            model.TIME,
            rule=lambda m, s, t: pyo.Constraint.Skip
            if s == reference_label
            else m.scenario_blocks[s].Pch[t] == m.scenario_blocks[reference_label].Pch[t],
        )
    if "Tsh" in optimized_controls:
        model.shared_shelf_temperature = pyo.Constraint(
            model.SCENARIOS,
            model.TIME,
            rule=lambda m, s, t: pyo.Constraint.Skip
            if s == reference_label
            else m.scenario_blocks[s].Tsh[t] == m.scenario_blocks[reference_label].Tsh[t],
        )

    model.scenario_objective = pyo.Expression(
        model.SCENARIOS,
        rule=lambda m, s: sum(
            m.scenario_blocks[s].Pch[t] - m.scenario_blocks[s].Psub[t] for t in m.TIME
        ),
    )
    model.worst_case_objective = pyo.Var(domain=pyo.Reals, initialize=0.0)
    model.worst_case_objective_bound = pyo.Constraint(
        model.SCENARIOS,
        rule=lambda m, s: m.worst_case_objective >= m.scenario_objective[s],
    )
    model.obj = pyo.Objective(expr=model.worst_case_objective, sense=pyo.minimize)
    return model


__all__ = [
    "create_design_space_feasibility_model",
    "create_design_space_grid_models",
    "create_multivial_optimization_model",
    "create_parameter_estimation_model",
    "create_robust_optimization_model",
    "create_sensitivity_analysis_models",
]
