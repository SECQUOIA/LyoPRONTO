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

_PRODUCT_PARAMETER_NAMES = ("R0", "A1", "A2")
_HEAT_TRANSFER_PARAMETER_NAMES = ("KC", "KP", "KD")
_PARAMETER_NAMES = _PRODUCT_PARAMETER_NAMES + _HEAT_TRANSFER_PARAMETER_NAMES

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
        rule=lambda m, i: m.R0 + m.A1 * m.Lck_obs[i] / (1.0 + m.A2 * m.Lck_obs[i]),
    )
    model.Kv_model = pyo.Expression(
        model.OBS,
        rule=lambda m, i: m.KC + m.KP * m.Pch_obs[i] / (1.0 + m.KD * m.Pch_obs[i]),
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
    """Create a Pyomo optimization model with explicit batch-capacity tracking."""
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
    return model


__all__ = [
    "create_design_space_feasibility_model",
    "create_design_space_grid_models",
    "create_multivial_optimization_model",
    "create_parameter_estimation_model",
]
