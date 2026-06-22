"""Experimental Pyomo optimization mode builders for primary drying.

The mode builders intentionally share the legacy driving-force objective.
Mode-specific behavior comes from the free/fixed controls, fixed-profile
constraints, bounds, and optional ramp-rate constraints.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, List, Mapping, Optional, Sequence, Tuple, Union

import numpy as np
import pyomo.environ as pyo  # type: ignore[import-untyped]

from .. import constant
from .trajectory import (
    ProfileInput,
    TrajectoryResult,
    VariableBounds,
    WarmstartInput,
    create_trajectory_model,
    sample_ramp_profile,
    solve_trajectory,
)


class OptimizationMode(str, Enum):
    """Supported experimental Pyomo optimizer modes."""

    PRESSURE = "pressure"
    SHELF_TEMPERATURE = "shelf_temperature"
    JOINT = "joint"


ModeInput = Union[OptimizationMode, str]

_MODE_ALIASES = {
    "pressure": OptimizationMode.PRESSURE,
    "pch": OptimizationMode.PRESSURE,
    "variable_pressure": OptimizationMode.PRESSURE,
    "shelf_temperature": OptimizationMode.SHELF_TEMPERATURE,
    "temperature": OptimizationMode.SHELF_TEMPERATURE,
    "tsh": OptimizationMode.SHELF_TEMPERATURE,
    "variable_shelf_temperature": OptimizationMode.SHELF_TEMPERATURE,
    "joint": OptimizationMode.JOINT,
    "both": OptimizationMode.JOINT,
    "pressure_and_shelf_temperature": OptimizationMode.JOINT,
}

_OBJECTIVE_DESCRIPTIONS = {
    OptimizationMode.PRESSURE: (
        "intentionally shared objective: minimize sum(Pch[t] - Psub[t]) "
        "with chamber pressure variable and the shelf-temperature profile fixed"
    ),
    OptimizationMode.SHELF_TEMPERATURE: (
        "intentionally shared objective: minimize sum(Pch[t] - Psub[t]) "
        "with shelf temperature variable and the chamber-pressure profile fixed"
    ),
    OptimizationMode.JOINT: (
        "intentionally shared objective: minimize sum(Pch[t] - Psub[t]) "
        "with chamber pressure and shelf temperature both variable"
    ),
}


def _coerce_mode(mode: ModeInput) -> OptimizationMode:
    if isinstance(mode, OptimizationMode):
        return mode

    normalized = str(mode).strip().lower().replace("-", "_").replace(" ", "_")
    try:
        return _MODE_ALIASES[normalized]
    except KeyError as exc:
        choices = ", ".join(mode.value for mode in OptimizationMode)
        raise ValueError(f"mode must be one of: {choices}") from exc


def _require_keys(name: str, data: Mapping[str, Any], keys: Sequence[str]) -> None:
    missing = [key for key in keys if key not in data]
    if missing:
        joined = ", ".join(missing)
        raise KeyError(f"{name} is missing required key(s): {joined}")


def _time_points(n_steps: int, dt: float) -> List[float]:
    return [float(index) * float(dt) for index in range(int(n_steps) + 1)]


def _variable_pressure_bounds(pchamber: Mapping[str, Any]) -> VariableBounds:
    _require_keys("pchamber", pchamber, ("min",))
    lower = float(pchamber["min"])
    upper = float(pchamber["max"]) if "max" in pchamber else None
    if lower < 0.0:
        raise ValueError("pchamber min must be nonnegative")
    if upper is not None and upper < lower:
        raise ValueError("pchamber max must be greater than or equal to min")
    return lower, upper


def _variable_shelf_bounds(tshelf: Mapping[str, Any]) -> VariableBounds:
    _require_keys("tshelf", tshelf, ("min", "max"))
    lower = float(tshelf["min"])
    upper = float(tshelf["max"])
    if upper < lower:
        raise ValueError("tshelf max must be greater than or equal to min")
    return lower, upper


def _fixed_profile_bounds(name: str, profile: ProfileInput) -> VariableBounds:
    values = np.asarray(profile, dtype=float)
    if values.size == 0 or not np.all(np.isfinite(values)):
        raise ValueError(f"{name} fixed profile must contain finite values")
    return float(np.min(values)), float(np.max(values))


def _fixed_pressure_profile(
    pchamber: Mapping[str, Any],
    time_points: Sequence[float],
) -> List[float]:
    _require_keys("pchamber", pchamber, ("setpt", "dt_setpt", "ramp_rate"))
    return sample_ramp_profile(pchamber, time_points).tolist()


def _fixed_shelf_profile(
    tshelf: Mapping[str, Any],
    time_points: Sequence[float],
) -> List[float]:
    _require_keys("tshelf", tshelf, ("init", "setpt", "dt_setpt", "ramp_rate"))
    return sample_ramp_profile(tshelf, time_points).tolist()


def _resolve_ramp_rate(
    spec: Mapping[str, Any],
    explicit_rate: Optional[float],
    enforce_spec_rate: bool,
) -> Optional[float]:
    if explicit_rate is not None:
        return float(explicit_rate)
    if enforce_spec_rate and "ramp_rate" in spec:
        return float(spec["ramp_rate"]) * constant.hr_To_min
    return None


def _mode_ramp_rates(
    mode: OptimizationMode,
    pchamber: Mapping[str, Any],
    tshelf: Mapping[str, Any],
    enforce_ramp_rates: bool,
    pch_ramp_rate: Optional[float],
    tsh_ramp_rate: Optional[float],
) -> Tuple[Optional[float], Optional[float]]:
    pressure_rate = None
    shelf_rate = None
    if mode in (OptimizationMode.PRESSURE, OptimizationMode.JOINT):
        pressure_rate = _resolve_ramp_rate(pchamber, pch_ramp_rate, enforce_ramp_rates)
    if mode in (OptimizationMode.SHELF_TEMPERATURE, OptimizationMode.JOINT):
        shelf_rate = _resolve_ramp_rate(tshelf, tsh_ramp_rate, enforce_ramp_rates)
    return pressure_rate, shelf_rate


def _mode_profiles_and_bounds(
    mode: OptimizationMode,
    pchamber: Mapping[str, Any],
    tshelf: Mapping[str, Any],
    time_points: Sequence[float],
) -> Tuple[VariableBounds, VariableBounds, Optional[ProfileInput], Optional[ProfileInput]]:
    fixed_pch_profile = None
    fixed_tsh_profile = None

    if mode is OptimizationMode.PRESSURE:
        fixed_tsh_profile = _fixed_shelf_profile(tshelf, time_points)
        pch_bounds = _variable_pressure_bounds(pchamber)
        tsh_bounds = _fixed_profile_bounds("tshelf", fixed_tsh_profile)
    elif mode is OptimizationMode.SHELF_TEMPERATURE:
        fixed_pch_profile = _fixed_pressure_profile(pchamber, time_points)
        pch_bounds = _fixed_profile_bounds("pchamber", fixed_pch_profile)
        tsh_bounds = _variable_shelf_bounds(tshelf)
    else:
        pch_bounds = _variable_pressure_bounds(pchamber)
        tsh_bounds = _variable_shelf_bounds(tshelf)

    return pch_bounds, tsh_bounds, fixed_pch_profile, fixed_tsh_profile


def _tag_model(
    model: pyo.ConcreteModel,
    mode: OptimizationMode,
) -> pyo.ConcreteModel:
    optimized_controls: Tuple[str, ...]
    fixed_controls: Tuple[str, ...]
    if mode is OptimizationMode.PRESSURE:
        optimized_controls = ("Pch",)
        fixed_controls = ("Tsh",)
    elif mode is OptimizationMode.SHELF_TEMPERATURE:
        optimized_controls = ("Tsh",)
        fixed_controls = ("Pch",)
    else:
        optimized_controls = ("Pch", "Tsh")
        fixed_controls = ()

    model.optimization_mode = mode.value
    model.optimized_controls = optimized_controls
    model.fixed_controls = fixed_controls
    model.optimization_objective = "sum_Pch_minus_Psub"
    model.optimization_objective_description = _OBJECTIVE_DESCRIPTIONS[mode]
    return model


def create_primary_drying_optimization_model(
    vial: Mapping[str, float],
    product: Mapping[str, float],
    ht: Mapping[str, float],
    pchamber: Mapping[str, Any],
    tshelf: Mapping[str, Any],
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
    """Create an experimental Pyomo trajectory optimizer for one control mode.

    The input dictionaries mirror the legacy SciPy optimizer dictionaries:
    pressure-only mode uses ``pchamber["min"]`` and optional ``"max"`` while
    fixing the sampled ``tshelf`` schedule; shelf-temperature mode fixes the
    sampled ``pchamber`` schedule and uses ``tshelf["min"]``/``"max"``; joint
    mode uses both sets of variable bounds.

    ``n_steps`` and ``dt`` define a fixed uniform Pyomo time grid. This is a
    validation prototype, not a drop-in replacement for the sequential SciPy
    ``dry`` functions that run until complete drying.
    """
    optimization_mode = _coerce_mode(mode)
    grid = _time_points(n_steps, dt)
    pch_bounds, tsh_bounds, fixed_pch_profile, fixed_tsh_profile = _mode_profiles_and_bounds(
        optimization_mode,
        pchamber,
        tshelf,
        grid,
    )
    resolved_pch_ramp_rate, resolved_tsh_ramp_rate = _mode_ramp_rates(
        optimization_mode,
        pchamber,
        tshelf,
        enforce_ramp_rates,
        pch_ramp_rate,
        tsh_ramp_rate,
    )

    model = create_trajectory_model(
        vial,
        product,
        ht,
        n_steps=n_steps,
        dt=dt,
        pch_bounds=pch_bounds,
        tsh_bounds=tsh_bounds,
        final_dried_fraction=final_dried_fraction,
        fixed_pch_profile=fixed_pch_profile,
        fixed_tsh_profile=fixed_tsh_profile,
        pch_ramp_rate=resolved_pch_ramp_rate,
        tsh_ramp_rate=resolved_tsh_ramp_rate,
        eq_cap=eq_cap,
        nvial=nvial,
        tbot_upper=tbot_upper,
        lpr0=lpr0,
        initialize=initialize,
    )
    return _tag_model(model, optimization_mode)


def create_pressure_optimization_model(
    vial: Mapping[str, float],
    product: Mapping[str, float],
    ht: Mapping[str, float],
    pchamber: Mapping[str, Any],
    tshelf: Mapping[str, Any],
    *,
    n_steps: int,
    dt: float,
    eq_cap: Optional[Mapping[str, float]] = None,
    nvial: Optional[int] = None,
    final_dried_fraction: float = 0.995,
    enforce_ramp_rates: bool = False,
    pch_ramp_rate: Optional[float] = None,
    tbot_upper: Optional[float] = None,
    lpr0: Optional[float] = None,
    initialize: Optional[WarmstartInput] = None,
) -> pyo.ConcreteModel:
    """Create the fixed-shelf-temperature, variable-pressure Pyomo mode."""
    return create_primary_drying_optimization_model(
        vial,
        product,
        ht,
        pchamber,
        tshelf,
        n_steps=n_steps,
        dt=dt,
        mode=OptimizationMode.PRESSURE,
        eq_cap=eq_cap,
        nvial=nvial,
        final_dried_fraction=final_dried_fraction,
        enforce_ramp_rates=enforce_ramp_rates,
        pch_ramp_rate=pch_ramp_rate,
        tbot_upper=tbot_upper,
        lpr0=lpr0,
        initialize=initialize,
    )


def create_shelf_temperature_optimization_model(
    vial: Mapping[str, float],
    product: Mapping[str, float],
    ht: Mapping[str, float],
    pchamber: Mapping[str, Any],
    tshelf: Mapping[str, Any],
    *,
    n_steps: int,
    dt: float,
    eq_cap: Optional[Mapping[str, float]] = None,
    nvial: Optional[int] = None,
    final_dried_fraction: float = 0.995,
    enforce_ramp_rates: bool = False,
    tsh_ramp_rate: Optional[float] = None,
    tbot_upper: Optional[float] = None,
    lpr0: Optional[float] = None,
    initialize: Optional[WarmstartInput] = None,
) -> pyo.ConcreteModel:
    """Create the fixed-pressure, variable-shelf-temperature Pyomo mode."""
    return create_primary_drying_optimization_model(
        vial,
        product,
        ht,
        pchamber,
        tshelf,
        n_steps=n_steps,
        dt=dt,
        mode=OptimizationMode.SHELF_TEMPERATURE,
        eq_cap=eq_cap,
        nvial=nvial,
        final_dried_fraction=final_dried_fraction,
        enforce_ramp_rates=enforce_ramp_rates,
        tsh_ramp_rate=tsh_ramp_rate,
        tbot_upper=tbot_upper,
        lpr0=lpr0,
        initialize=initialize,
    )


def create_joint_optimization_model(
    vial: Mapping[str, float],
    product: Mapping[str, float],
    ht: Mapping[str, float],
    pchamber: Mapping[str, Any],
    tshelf: Mapping[str, Any],
    *,
    n_steps: int,
    dt: float,
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
    """Create the joint variable-pressure and variable-shelf-temperature mode."""
    return create_primary_drying_optimization_model(
        vial,
        product,
        ht,
        pchamber,
        tshelf,
        n_steps=n_steps,
        dt=dt,
        mode=OptimizationMode.JOINT,
        eq_cap=eq_cap,
        nvial=nvial,
        final_dried_fraction=final_dried_fraction,
        enforce_ramp_rates=enforce_ramp_rates,
        pch_ramp_rate=pch_ramp_rate,
        tsh_ramp_rate=tsh_ramp_rate,
        tbot_upper=tbot_upper,
        lpr0=lpr0,
        initialize=initialize,
    )


def solve_primary_drying_optimization(
    vial: Mapping[str, float],
    product: Mapping[str, float],
    ht: Mapping[str, float],
    pchamber: Mapping[str, Any],
    tshelf: Mapping[str, Any],
    *,
    n_steps: int,
    dt: float,
    mode: ModeInput,
    solver: Union[str, Any] = "ipopt",
    tee: bool = False,
    eq_cap: Optional[Mapping[str, float]] = None,
    nvial: Optional[int] = None,
    final_dried_fraction: float = 0.995,
    enforce_ramp_rates: bool = False,
    pch_ramp_rate: Optional[float] = None,
    tsh_ramp_rate: Optional[float] = None,
    tbot_upper: Optional[float] = None,
    lpr0: Optional[float] = None,
    initialize: Optional[WarmstartInput] = None,
) -> TrajectoryResult:
    """Build and solve an experimental Pyomo optimization mode."""
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
        nvial=nvial,
        final_dried_fraction=final_dried_fraction,
        enforce_ramp_rates=enforce_ramp_rates,
        pch_ramp_rate=pch_ramp_rate,
        tsh_ramp_rate=tsh_ramp_rate,
        tbot_upper=tbot_upper,
        lpr0=lpr0,
        initialize=initialize,
    )
    return solve_trajectory(model, solver=solver, tee=tee)


__all__ = [
    "OptimizationMode",
    "create_joint_optimization_model",
    "create_pressure_optimization_model",
    "create_primary_drying_optimization_model",
    "create_shelf_temperature_optimization_model",
    "solve_primary_drying_optimization",
]
