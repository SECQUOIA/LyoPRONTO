"""Multi-period Pyomo trajectory model for primary drying.

This module implements the first trajectory discretization for the optional
Pyomo path. The grid is uniform in time and advances dried cake length with a
backward-Euler step:

``Lck[t] = Lck[t - 1] + dt * dLdt[t]``

The algebraic heat-transfer, mass-transfer, vapor-pressure, and process-bound
constraints are enforced at every time node. Units match the legacy SciPy
primary-drying code: pressure in Torr, temperature in degC, length in cm,
time in hours, heat-transfer coefficients in cal/s/K/cm^2, product resistance
in cm^2-hr-Torr/g, and sublimation rate in kg/hr/vial.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple, Union

import numpy as np
import pyomo.environ as pyo  # type: ignore[import-untyped]

from .. import constant, functions
from .single_step import _solver_from_arg, _termination_success


VariableBounds = Tuple[Optional[float], Optional[float]]
ProfileInput = Union[Sequence[float], Mapping[int, float]]
WarmstartValue = Union[float, Sequence[float], Mapping[int, float], np.ndarray]
WarmstartInput = Mapping[str, WarmstartValue]


@dataclass(frozen=True)
class TrajectoryResult:
    """Solver outcome and diagnostics for a Pyomo primary-drying trajectory."""

    success: bool
    solver_status: str
    termination_condition: str
    message: str
    values: Mapping[str, np.ndarray]
    constraint_violations: Mapping[str, Optional[float]]

    def as_table(self) -> np.ndarray:
        """Return trajectory values in the legacy seven-column output shape."""
        return np.column_stack(
            (
                self.values["time"],
                self.values["Tsub"],
                self.values["Tbot"],
                self.values["Tsh"],
                self.values["Pch"] * constant.Torr_to_mTorr,
                self.values["dmdt"] / (self.values["Ap"] * constant.cm_To_m**2),
                self.values["percent_dried"],
            )
        )


def _require_keys(name: str, data: Mapping[str, float], keys: Tuple[str, ...]) -> None:
    missing = [key for key in keys if key not in data]
    if missing:
        joined = ", ".join(missing)
        raise KeyError(f"{name} is missing required key(s): {joined}")


def _normalize_profile(name: str, profile: ProfileInput, n_steps: int) -> Dict[int, float]:
    if isinstance(profile, Mapping):
        values = {int(index): float(value) for index, value in profile.items()}
    else:
        if len(profile) != n_steps + 1:
            raise ValueError(f"{name} must have n_steps + 1 values")
        values = {index: float(value) for index, value in enumerate(profile)}

    missing = [index for index in range(n_steps + 1) if index not in values]
    if missing:
        joined = ", ".join(str(index) for index in missing)
        raise ValueError(f"{name} is missing value(s) for time index: {joined}")
    return values


def _profile_or_default(
    profile: Optional[ProfileInput],
    n_steps: int,
    default: float,
    name: str,
) -> Dict[int, float]:
    if profile is not None:
        return _normalize_profile(name, profile, n_steps)
    return {index: float(default) for index in range(n_steps + 1)}


def _midpoint(bounds: VariableBounds, fallback_lower: float, fallback_upper: float) -> float:
    lower = fallback_lower if bounds[0] is None else bounds[0]
    upper = fallback_upper if bounds[1] is None else bounds[1]
    return (float(lower) + float(upper)) / 2.0


def _inverse_vapor_pressure(pressure: float) -> float:
    safe_pressure = max(float(pressure), 1.0e-8)
    return (
        -functions.VAPOR_PRESSURE_TEMPERATURE_COEFFICIENT
        / np.log(safe_pressure / functions.VAPOR_PRESSURE_PREEXPONENTIAL)
        - 273.15
    )


def _drying_length_factor(product: Mapping[str, float], ap: float) -> float:
    c_solid = float(product["cSolid"])
    unfrozen_solution_factor = 1.0 - c_solid * constant.rho_solution / constant.rho_solute
    dried_volume_factor = (
        1.0 - c_solid * (constant.rho_solution - constant.rho_ice) / constant.rho_solute
    )
    return (
        constant.kg_To_g
        / unfrozen_solution_factor
        / (float(ap) * constant.rho_ice)
        * dried_volume_factor
    )


def _default_initialization(
    vial: Mapping[str, float],
    product: Mapping[str, float],
    ht: Mapping[str, float],
    lpr0: float,
    n_steps: int,
    final_dried_fraction: float,
    pch_profile: Mapping[int, float],
    tsh_profile: Mapping[int, float],
) -> Dict[str, Dict[int, float]]:
    tbot_ceiling = float(product.get("T_pr_crit", 50.0))
    values: Dict[str, Dict[int, float]] = {
        "Lck": {},
        "Pch": {},
        "Tsh": {},
        "Tbot": {},
        "Tsub": {},
        "Psub": {},
        "log_Psub": {},
        "dmdt": {},
        "Kv": {},
    }

    for index in range(n_steps + 1):
        dried_fraction = final_dried_fraction * index / max(n_steps, 1)
        lck = min(float(lpr0) * dried_fraction, float(lpr0) * 0.999)
        pch = float(pch_profile[index])
        tsh = float(tsh_profile[index])
        tbot = min(tsh - 0.1, tbot_ceiling - 0.1)
        target_psub = max(pch * 1.2, 1.0e-6)
        tsub = min(tbot - 0.5, _inverse_vapor_pressure(target_psub))
        tsub = max(-80.0, min(-1.0e-6, tsub))
        psub = float(functions.Vapor_pressure(tsub))
        rp = float(functions.Rp_FUN(lck, product["R0"], product["A1"], product["A2"]))
        dmdt = max(float(vial["Ap"]) / rp / constant.kg_To_g * (psub - pch), 1.0e-8)

        values["Lck"][index] = lck
        values["Pch"][index] = pch
        values["Tsh"][index] = tsh
        values["Tbot"][index] = tbot
        values["Tsub"][index] = tsub
        values["Psub"][index] = psub
        values["log_Psub"][index] = float(np.log(psub))
        values["dmdt"][index] = dmdt
        values["Kv"][index] = float(functions.Kv_FUN(ht["KC"], ht["KP"], ht["KD"], pch))

    return values


def _values_for_time_index(
    values: WarmstartValue,
    time_index: int,
) -> float:
    if isinstance(values, Mapping):
        return float(values[time_index])
    if isinstance(values, (str, bytes)):
        raise TypeError("Warmstart values must be numeric")
    if isinstance(values, (int, float, np.floating)):
        return float(values)
    return float(values[time_index])


def apply_trajectory_warmstart(
    model: pyo.ConcreteModel,
    initialize: WarmstartInput,
) -> None:
    """Set indexed variable initial values from a trajectory warmstart mapping."""
    for name, values in initialize.items():
        component = getattr(model, name, None)
        if component is None or not component.is_indexed():
            continue
        for time_index in model.TIME:
            component[time_index].set_value(
                _values_for_time_index(values, int(time_index)),
                skip_validation=True,
            )


def sample_ramp_profile(rampspec: Mapping[str, Any], time_points: Sequence[float]) -> np.ndarray:
    """Sample a legacy ramp specification at trajectory node times."""
    ramp = functions.RampInterpolator(rampspec)
    return np.array([float(ramp(float(time))) for time in time_points], dtype=float)


def trajectory_initialization_from_scipy_output(
    output: np.ndarray,
    lpr0: float,
    ap: float,
    ht: Optional[Mapping[str, float]] = None,
    time_points: Optional[Sequence[float]] = None,
) -> Dict[str, np.ndarray]:
    """Build a Pyomo warmstart mapping from a legacy SciPy output table.

    The input table uses the seven-column legacy format returned by
    ``calc_knownRp.dry``. Pressure is converted from mTorr to Torr, sublimation
    flux from kg/hr/m^2 to kg/hr/vial, and percent dried to dried cake length.
    """
    output_array = np.asarray(output, dtype=float)
    if output_array.ndim != 2 or output_array.shape[1] < 7:
        raise ValueError("output must be a two-dimensional legacy trajectory table")

    source_time = output_array[:, 0]
    target_time = np.asarray(source_time if time_points is None else time_points, dtype=float)

    tsub = np.interp(target_time, source_time, output_array[:, 1])
    tbot = np.interp(target_time, source_time, output_array[:, 2])
    tsh = np.interp(target_time, source_time, output_array[:, 3])
    pch = np.interp(target_time, source_time, output_array[:, 4]) / constant.Torr_to_mTorr
    flux = np.interp(target_time, source_time, output_array[:, 5])
    percent_dried = np.interp(target_time, source_time, output_array[:, 6])
    psub = np.asarray(functions.Vapor_pressure(tsub), dtype=float)

    initialization = {
        "Lck": np.clip(percent_dried / 100.0 * float(lpr0), 0.0, float(lpr0) * 0.999),
        "Tsub": tsub,
        "Tbot": tbot,
        "Tsh": tsh,
        "Pch": pch,
        "dmdt": flux * float(ap) * constant.cm_To_m**2,
        "Psub": psub,
        "log_Psub": np.log(psub),
    }
    if ht is not None:
        initialization["Kv"] = np.asarray(
            [functions.Kv_FUN(ht["KC"], ht["KP"], ht["KD"], pressure) for pressure in pch],
            dtype=float,
        )
    return initialization


def create_trajectory_model(
    vial: Mapping[str, float],
    product: Mapping[str, float],
    ht: Mapping[str, float],
    n_steps: int,
    dt: float,
    pch_bounds: VariableBounds = (0.05, 0.5),
    tsh_bounds: VariableBounds = (-50.0, 50.0),
    final_dried_fraction: float = 0.995,
    fixed_pch_profile: Optional[ProfileInput] = None,
    fixed_tsh_profile: Optional[ProfileInput] = None,
    pch_ramp_rate: Optional[float] = None,
    tsh_ramp_rate: Optional[float] = None,
    eq_cap: Optional[Mapping[str, float]] = None,
    nvial: Optional[int] = None,
    tbot_upper: Optional[float] = None,
    lpr0: Optional[float] = None,
    initialize: Optional[WarmstartInput] = None,
) -> pyo.ConcreteModel:
    """Create a backward-Euler Pyomo trajectory model for primary drying.

    ``n_steps`` is the number of backward-Euler intervals and ``dt`` is the
    uniform interval length in hours. ``final_dried_fraction`` is constrained at
    the last node and must be less than 1.0 because the frozen-layer heat
    balance is singular when no frozen layer remains.

    When ``product["T_pr_crit"]`` or ``tbot_upper`` is provided, the model
    constrains ``Tbot`` at every node. This also applies when chamber-pressure
    and shelf-temperature profiles are fixed, so fixed-profile use is a
    constrained feasibility replay rather than an unconstrained legacy
    simulation.
    """
    _require_keys("vial", vial, ("Av", "Ap"))
    if lpr0 is None:
        _require_keys("vial", vial, ("Vfill",))
    _require_keys("product", product, ("cSolid", "R0", "A1", "A2"))
    _require_keys("ht", ht, ("KC", "KP", "KD"))
    if eq_cap is not None:
        _require_keys("eq_cap", eq_cap, ("a", "b"))
        if nvial is None:
            raise ValueError("nvial is required when eq_cap is provided")
    if n_steps < 1:
        raise ValueError("n_steps must be at least 1")
    if dt <= 0:
        raise ValueError("dt must be positive")
    if not 0.0 < final_dried_fraction < 1.0:
        raise ValueError("final_dried_fraction must satisfy 0 < final_dried_fraction < 1")

    lpr0_value = (
        float(lpr0)
        if lpr0 is not None
        else float(functions.Lpr0_FUN(vial["Vfill"], vial["Ap"], product["cSolid"]))
    )
    if lpr0_value <= 0:
        raise ValueError("lpr0 must be positive")

    pch_default = _midpoint(pch_bounds, 0.05, 0.5)
    tsh_default = _midpoint(tsh_bounds, -45.0, 20.0)
    pch_profile = _profile_or_default(fixed_pch_profile, n_steps, pch_default, "fixed_pch_profile")
    tsh_profile = _profile_or_default(fixed_tsh_profile, n_steps, tsh_default, "fixed_tsh_profile")
    defaults = _default_initialization(
        vial,
        product,
        ht,
        lpr0_value,
        n_steps,
        final_dried_fraction,
        pch_profile,
        tsh_profile,
    )
    if initialize is not None:
        for name, values in initialize.items():
            if name not in defaults:
                continue
            for index in range(n_steps + 1):
                defaults[name][index] = _values_for_time_index(values, index)

    model = pyo.ConcreteModel()
    model.discretization_method = "backward_euler"
    model.n_steps = pyo.Param(initialize=int(n_steps))
    model.dt = pyo.Param(initialize=float(dt))
    model.Lpr0 = pyo.Param(initialize=lpr0_value)
    model.Av = pyo.Param(initialize=float(vial["Av"]))
    model.Ap = pyo.Param(initialize=float(vial["Ap"]))
    model.R0 = pyo.Param(initialize=float(product["R0"]))
    model.A1 = pyo.Param(initialize=float(product["A1"]))
    model.A2 = pyo.Param(initialize=float(product["A2"]))
    model.KC = pyo.Param(initialize=float(ht["KC"]))
    model.KP = pyo.Param(initialize=float(ht["KP"]))
    model.KD = pyo.Param(initialize=float(ht["KD"]))
    model.kg_To_g = pyo.Param(initialize=constant.kg_To_g)
    model.hr_To_s = pyo.Param(initialize=constant.hr_To_s)
    model.k_ice = pyo.Param(initialize=constant.k_ice)
    model.dHs = pyo.Param(initialize=constant.dHs)
    model.drying_length_factor = pyo.Param(initialize=_drying_length_factor(product, vial["Ap"]))
    model.final_dried_fraction = pyo.Param(initialize=float(final_dried_fraction))

    model.TIME = pyo.RangeSet(0, n_steps)
    model.STEPS = pyo.RangeSet(1, n_steps)
    model.time = pyo.Param(
        model.TIME, initialize={index: float(index) * float(dt) for index in range(n_steps + 1)}
    )

    model.Lck = pyo.Var(
        model.TIME,
        domain=pyo.NonNegativeReals,
        bounds=(0.0, lpr0_value * 0.999999),
        initialize=defaults["Lck"],
    )
    model.Pch = pyo.Var(
        model.TIME,
        domain=pyo.NonNegativeReals,
        bounds=pch_bounds,
        initialize=defaults["Pch"],
    )
    model.Tsh = pyo.Var(
        model.TIME, domain=pyo.Reals, bounds=tsh_bounds, initialize=defaults["Tsh"]
    )
    model.Tsub = pyo.Var(
        model.TIME, domain=pyo.Reals, bounds=(-80.0, 0.0), initialize=defaults["Tsub"]
    )
    model.Tbot = pyo.Var(
        model.TIME, domain=pyo.Reals, bounds=(-80.0, 80.0), initialize=defaults["Tbot"]
    )
    model.Psub = pyo.Var(
        model.TIME,
        domain=pyo.NonNegativeReals,
        bounds=(1.0e-8, 10.0),
        initialize=defaults["Psub"],
    )
    model.log_Psub = pyo.Var(
        model.TIME, domain=pyo.Reals, bounds=(-20.0, 3.0), initialize=defaults["log_Psub"]
    )
    model.dmdt = pyo.Var(
        model.TIME,
        domain=pyo.NonNegativeReals,
        bounds=(0.0, None),
        initialize=defaults["dmdt"],
    )
    model.Kv = pyo.Var(
        model.TIME,
        domain=pyo.PositiveReals,
        bounds=(1.0e-8, None),
        initialize=defaults["Kv"],
    )

    model.Rp = pyo.Expression(
        model.TIME,
        rule=lambda m, t: m.R0 + m.A1 * m.Lck[t] / (1.0 + m.A2 * m.Lck[t]),
    )
    model.length_rate = pyo.Expression(
        model.TIME, rule=lambda m, t: m.dmdt[t] * m.drying_length_factor
    )
    model.percent_dried = pyo.Expression(
        model.TIME, rule=lambda m, t: 100.0 * m.Lck[t] / m.Lpr0
    )

    model.initial_dried_cake = pyo.Constraint(expr=model.Lck[0] == 0.0)
    model.drying_front_dynamics = pyo.Constraint(
        model.STEPS,
        rule=lambda m, t: m.Lck[t] == m.Lck[t - 1] + m.dt * m.length_rate[t],
    )
    model.final_drying_target = pyo.Constraint(
        expr=model.Lck[n_steps] >= model.final_dried_fraction * model.Lpr0
    )
    model.vapor_pressure_log = pyo.Constraint(
        model.TIME,
        rule=lambda m, t: m.log_Psub[t]
        == pyo.log(functions.VAPOR_PRESSURE_PREEXPONENTIAL)
        - functions.VAPOR_PRESSURE_TEMPERATURE_COEFFICIENT / (273.15 + m.Tsub[t]),
    )
    model.vapor_pressure_exp = pyo.Constraint(
        model.TIME, rule=lambda m, t: m.Psub[t] == pyo.exp(m.log_Psub[t])
    )
    model.mass_transfer = pyo.Constraint(
        model.TIME,
        rule=lambda m, t: m.dmdt[t] == m.Ap / m.Rp[t] / m.kg_To_g * (m.Psub[t] - m.Pch[t]),
    )
    model.frozen_layer_heat_balance = pyo.Constraint(
        model.TIME,
        rule=lambda m, t: (m.Tsh[t] - m.Tbot[t]) * m.Av * m.Kv[t] * (m.Lpr0 - m.Lck[t])
        == m.Ap * (m.Tbot[t] - m.Tsub[t]) * m.k_ice,
    )
    model.energy_balance = pyo.Constraint(
        model.TIME,
        rule=lambda m, t: m.Tsh[t]
        == m.dmdt[t] * m.kg_To_g / m.hr_To_s * m.dHs / m.Av / m.Kv[t] + m.Tbot[t],
    )
    model.vial_heat_transfer = pyo.Constraint(
        model.TIME,
        rule=lambda m, t: m.Kv[t] == m.KC + m.KP * m.Pch[t] / (1.0 + m.KD * m.Pch[t]),
    )

    if fixed_pch_profile is not None:
        model.fixed_Pch = pyo.Param(model.TIME, initialize=pch_profile)
        model.fixed_chamber_pressure_profile = pyo.Constraint(
            model.TIME, rule=lambda m, t: m.Pch[t] == m.fixed_Pch[t]
        )
    if fixed_tsh_profile is not None:
        model.fixed_Tsh = pyo.Param(model.TIME, initialize=tsh_profile)
        model.fixed_shelf_temperature_profile = pyo.Constraint(
            model.TIME, rule=lambda m, t: m.Tsh[t] == m.fixed_Tsh[t]
        )
    if pch_ramp_rate is not None:
        ramp = float(pch_ramp_rate)
        model.chamber_pressure_ramp_up = pyo.Constraint(
            model.STEPS, rule=lambda m, t: m.Pch[t] - m.Pch[t - 1] <= ramp * m.dt
        )
        model.chamber_pressure_ramp_down = pyo.Constraint(
            model.STEPS, rule=lambda m, t: m.Pch[t - 1] - m.Pch[t] <= ramp * m.dt
        )
    if tsh_ramp_rate is not None:
        ramp = float(tsh_ramp_rate)
        model.shelf_temperature_ramp_up = pyo.Constraint(
            model.STEPS, rule=lambda m, t: m.Tsh[t] - m.Tsh[t - 1] <= ramp * m.dt
        )
        model.shelf_temperature_ramp_down = pyo.Constraint(
            model.STEPS, rule=lambda m, t: m.Tsh[t - 1] - m.Tsh[t] <= ramp * m.dt
        )

    temperature_limit = tbot_upper if tbot_upper is not None else product.get("T_pr_crit")
    if temperature_limit is not None:
        model.T_crit = pyo.Param(initialize=float(temperature_limit))
        model.product_temperature_limit = pyo.Constraint(
            model.TIME, rule=lambda m, t: m.Tbot[t] <= m.T_crit
        )
    if eq_cap is not None and nvial is not None:
        model.eq_cap_a = pyo.Param(initialize=float(eq_cap["a"]))
        model.eq_cap_b = pyo.Param(initialize=float(eq_cap["b"]))
        model.nvial = pyo.Param(initialize=int(nvial))
        model.equipment_capability = pyo.Constraint(
            model.TIME,
            rule=lambda m, t: m.eq_cap_a + m.eq_cap_b * m.Pch[t] - m.nvial * m.dmdt[t] >= 0,
        )

    model.obj = pyo.Objective(
        expr=sum(model.Pch[t] - model.Psub[t] for t in model.TIME),
        sense=pyo.minimize,
    )
    return model


def _constraint_violations(model: pyo.ConcreteModel) -> Dict[str, Optional[float]]:
    violations: Dict[str, Optional[float]] = {}
    for constraint in model.component_data_objects(pyo.Constraint, active=True):
        body = pyo.value(constraint.body, exception=False)
        if body is None:
            violations[constraint.name] = None
            continue

        violation = 0.0
        if constraint.has_lb():
            lower = pyo.value(constraint.lower, exception=False)
            if lower is not None:
                violation = max(violation, float(lower) - float(body))
        if constraint.has_ub():
            upper = pyo.value(constraint.upper, exception=False)
            if upper is not None:
                violation = max(violation, float(body) - float(upper))
        violations[constraint.name] = max(0.0, violation)
    return violations


def trajectory_values(model: pyo.ConcreteModel) -> Dict[str, np.ndarray]:
    """Extract model values as NumPy arrays keyed by trajectory state name."""
    time_indices = [int(index) for index in model.TIME]
    values: Dict[str, np.ndarray] = {
        "time": np.array([pyo.value(model.time[index]) for index in time_indices], dtype=float),
        "Ap": np.full(len(time_indices), float(pyo.value(model.Ap)), dtype=float),
        "Lpr0": np.full(len(time_indices), float(pyo.value(model.Lpr0)), dtype=float),
    }

    for name in ("Lck", "Pch", "Tsh", "Tsub", "Tbot", "Psub", "log_Psub", "dmdt", "Kv"):
        component = getattr(model, name)
        raw_values = [pyo.value(component[index], exception=False) for index in time_indices]
        values[name] = np.array(
            [np.nan if value is None else float(value) for value in raw_values],
            dtype=float,
        )

    values["Rp"] = np.array(
        [float(pyo.value(model.Rp[index], exception=False)) for index in time_indices],
        dtype=float,
    )
    values["length_rate"] = np.array(
        [float(pyo.value(model.length_rate[index], exception=False)) for index in time_indices],
        dtype=float,
    )
    values["percent_dried"] = values["Lck"] / values["Lpr0"] * 100.0
    return values


def solve_trajectory(
    model: pyo.ConcreteModel,
    solver: Union[str, Any] = "ipopt",
    tee: bool = False,
) -> TrajectoryResult:
    """Solve a trajectory model and return values plus clear diagnostics."""
    try:
        opt, _solver_name = _solver_from_arg(solver, tee)
        results = opt.solve(model, tee=tee)
    except Exception as exc:  # pragma: no cover - exact solver failures are environment specific
        return TrajectoryResult(
            success=False,
            solver_status="not_available",
            termination_condition="not_available",
            message=f"Pyomo solve failed before returning results: {exc}",
            values=trajectory_values(model),
            constraint_violations=_constraint_violations(model),
        )

    solver_info = results.solver
    termination = solver_info.termination_condition
    status = solver_info.status
    success = _termination_success(termination)
    violations = _constraint_violations(model)
    finite_violations = [value for value in violations.values() if value is not None]
    max_violation = max(finite_violations, default=0.0)
    if success:
        message = (
            f"Pyomo trajectory solve reached {termination}; maximum constraint "
            f"violation {max_violation:.3e}."
        )
    else:
        message = (
            "Pyomo trajectory solve did not reach an optimal solution "
            f"(status={status}, termination_condition={termination}); maximum "
            f"constraint violation {max_violation:.3e}."
        )

    return TrajectoryResult(
        success=success,
        solver_status=str(status),
        termination_condition=str(termination),
        message=message,
        values=trajectory_values(model),
        constraint_violations=violations,
    )
