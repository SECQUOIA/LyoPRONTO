"""Free-final-time Pyomo.DAE optimization for primary drying.

This module provides simultaneous counterparts to the legacy sequential
``opt_Tsh.dry``, ``opt_Pch.dry``, and ``opt_Pch_Tsh.dry`` workflows.  The
physical model has one differential state, the dried cake length, and
quasi-steady algebraic heat- and mass-transfer relations.  A normalized time
domain keeps the mesh independent of the optimized final drying time.

Both backward finite differences and LAGRANGE-RADAU orthogonal collocation
are available through Pyomo.DAE.  The model remains in the optional Pyomo
dependency boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Optional, Tuple, Union

import numpy as np
import pyomo.dae as dae  # type: ignore[import-untyped]
import pyomo.environ as pyo  # type: ignore[import-untyped]

from .. import constant, functions
from .single_step import _solver_from_arg, _termination_success
from .trajectory import _constraint_violations, _drying_length_factor


class DaeDiscretization(str, Enum):
    """Supported Pyomo.DAE time-domain transformations."""

    FINITE_DIFFERENCE = "finite_difference"
    COLLOCATION = "collocation"


DaeDiscretizationInput = Union[DaeDiscretization, str]


class _DaeOptimizedControl(str, Enum):
    SHELF_TEMPERATURE = "shelf_temperature"
    CHAMBER_PRESSURE = "chamber_pressure"
    JOINT = "joint"


@dataclass(frozen=True)
class DaeOptimizationResult:
    """Solver outcome for a free-final-time Pyomo.DAE optimization."""

    success: bool
    solver_status: str
    termination_condition: str
    message: str
    objective_time_hr: Optional[float]
    values: Mapping[str, np.ndarray]
    constraint_violations: Mapping[str, Optional[float]]
    discretization: Mapping[str, Any]
    shadow_prices: Mapping[str, float] = field(default_factory=dict)
    """Change in optimal drying time [hr] per unit increase in each named limit.

    Populated only for a successful solve, and only for limits the model
    actually defines. A value near zero means the limit is inactive at the
    optimum, so relaxing it buys nothing. Keys and their units are:

    ``product_temperature_limit`` [hr/degC], ``equipment_capability``
    [hr/(kg/hr)], ``final_drying_target`` [hr/cm],
    ``chamber_pressure_lower_bound`` and ``chamber_pressure_upper_bound``
    [hr/Torr], and ``shelf_temperature_lower_bound`` and
    ``shelf_temperature_upper_bound`` [hr/degC].
    """

    def as_table(self) -> np.ndarray:
        """Return values in the legacy seven-column trajectory shape."""
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


def _require_keys(name: str, data: Mapping[str, Any], keys: Tuple[str, ...]) -> None:
    missing = [key for key in keys if key not in data]
    if missing:
        raise KeyError(f"{name} is missing required key(s): {', '.join(missing)}")


def _coerce_discretization(method: DaeDiscretizationInput) -> DaeDiscretization:
    if isinstance(method, DaeDiscretization):
        return method
    normalized = str(method).strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "fd": DaeDiscretization.FINITE_DIFFERENCE,
        "finite_difference": DaeDiscretization.FINITE_DIFFERENCE,
        "backward_euler": DaeDiscretization.FINITE_DIFFERENCE,
        "colloc": DaeDiscretization.COLLOCATION,
        "collocation": DaeDiscretization.COLLOCATION,
        "orthogonal_collocation": DaeDiscretization.COLLOCATION,
    }
    try:
        return aliases[normalized]
    except KeyError as exc:
        raise ValueError("discretization must be 'finite_difference' or 'collocation'") from exc


def _single_fixed_pressure(pchamber: Mapping[str, Any]) -> float:
    _require_keys("pchamber", pchamber, ("setpt",))
    setpoints = np.asarray(pchamber["setpt"], dtype=float).reshape(-1)
    if setpoints.size != 1 or not np.isfinite(setpoints[0]):
        raise ValueError(
            "free-final-time shelf-temperature optimization requires one constant pchamber setpoint"
        )
    if setpoints[0] <= 0.0:
        raise ValueError("pchamber setpoint must be positive")
    return float(setpoints[0])


def _single_fixed_shelf_temperature(tshelf: Mapping[str, Any]) -> float:
    _require_keys("tshelf", tshelf, ("init", "setpt"))
    initial = float(tshelf["init"])
    setpoints = np.asarray(tshelf["setpt"], dtype=float).reshape(-1)
    if (
        not np.isfinite(initial)
        or setpoints.size != 1
        or not np.isfinite(setpoints[0])
        or not np.isclose(setpoints[0], initial)
    ):
        raise ValueError(
            "free-final-time chamber-pressure optimization requires one "
            "constant tshelf setpoint equal to tshelf init"
        )
    return initial


def _warmstart_from_legacy_table(
    model: pyo.ConcreteModel,
    trajectory: np.ndarray,
) -> None:
    table = np.asarray(trajectory, dtype=float)
    if table.ndim != 2 or table.shape[1] != 7 or table.shape[0] < 2:
        raise ValueError("initialize must be a two-dimensional, seven-column trajectory")
    if not np.all(np.isfinite(table)) or table[-1, 0] <= 0.0:
        raise ValueError("initialize must contain a finite positive-time trajectory")

    horizon = float(table[-1, 0])
    model.t_final.set_value(horizon)
    normalized_source_time = table[:, 0] / horizon
    ap = float(pyo.value(model.Ap))
    lpr0 = float(pyo.value(model.Lpr0))
    for tau in model.t:
        coordinate = float(tau)
        model.Lck[tau].set_value(
            np.interp(coordinate, normalized_source_time, table[:, 6]) / 100.0 * lpr0
        )
        model.Tsub[tau].set_value(np.interp(coordinate, normalized_source_time, table[:, 1]))
        model.Tbot[tau].set_value(np.interp(coordinate, normalized_source_time, table[:, 2]))
        model.Tsh[tau].set_value(np.interp(coordinate, normalized_source_time, table[:, 3]))
        model.Pch[tau].set_value(
            np.interp(coordinate, normalized_source_time, table[:, 4]) / constant.Torr_to_mTorr
        )
        dmdt = np.interp(coordinate, normalized_source_time, table[:, 5]) * ap * constant.cm_To_m**2
        model.dmdt[tau].set_value(dmdt)
        psub = float(functions.Vapor_pressure(pyo.value(model.Tsub[tau])))
        model.Psub[tau].set_value(psub)
        model.log_Psub[tau].set_value(np.log(psub))
        model.Kv[tau].set_value(
            functions.Kv_FUN(
                pyo.value(model.KC),
                pyo.value(model.KP),
                pyo.value(model.KD),
                pyo.value(model.Pch[tau]),
            )
        )
        model.dLck_dt[tau].set_value(horizon * dmdt * float(pyo.value(model.drying_length_factor)))


def _create_dae_optimization_model(
    vial: Mapping[str, float],
    product: Mapping[str, float],
    ht: Mapping[str, float],
    pchamber: Mapping[str, Any],
    tshelf: Mapping[str, Any],
    *,
    eq_cap: Mapping[str, float],
    nvial: int,
    nfe: int = 24,
    discretization: DaeDiscretizationInput = DaeDiscretization.FINITE_DIFFERENCE,
    ncp: int = 3,
    final_dried_fraction: float = 1.0,
    t_final_bounds: Tuple[float, float] = (0.1, 50.0),
    initialize: Optional[np.ndarray] = None,
    initial_pressure: Optional[float] = None,
    initial_shelf_temperature: Optional[float] = None,
    pressure_ramp_rate: Optional[float] = None,
    shelf_temperature_ramp_rate: Optional[float] = None,
    optimized_control: _DaeOptimizedControl,
) -> pyo.ConcreteModel:
    """Build either supported free-final-time DAE optimization model."""
    requested_initial_pressure = initial_pressure
    requested_initial_shelf_temperature = initial_shelf_temperature
    _require_keys("vial", vial, ("Av", "Ap", "Vfill"))
    _require_keys("product", product, ("cSolid", "R0", "A1", "A2", "T_pr_crit"))
    _require_keys("ht", ht, ("KC", "KP", "KD"))
    _require_keys("eq_cap", eq_cap, ("a", "b"))
    method = _coerce_discretization(discretization)
    if optimized_control is _DaeOptimizedControl.SHELF_TEMPERATURE:
        _require_keys("tshelf", tshelf, ("min", "max"))
        fixed_pressure = _single_fixed_pressure(pchamber)
        if float(tshelf["max"]) <= float(tshelf["min"]):
            raise ValueError("tshelf max must be greater than tshelf min")
        pressure_bounds = (fixed_pressure, fixed_pressure)
        shelf_bounds = (float(tshelf["min"]), float(tshelf["max"]))
        pressure_initialization = fixed_pressure
        shelf_initialization = float(tshelf.get("init", product["T_pr_crit"]))
        fixed_shelf = None
    elif optimized_control is _DaeOptimizedControl.CHAMBER_PRESSURE:
        _require_keys("pchamber", pchamber, ("min", "max"))
        fixed_shelf = _single_fixed_shelf_temperature(tshelf)
        pressure_bounds = (float(pchamber["min"]), float(pchamber["max"]))
        if pressure_bounds[0] <= 0.0 or pressure_bounds[1] <= pressure_bounds[0]:
            raise ValueError("pchamber bounds must be positive and increasing")
        shelf_bounds = (fixed_shelf, fixed_shelf)
        pressure_initialization = float(np.mean(pressure_bounds))
        shelf_initialization = fixed_shelf
        fixed_pressure = None
    else:
        _require_keys("pchamber", pchamber, ("min", "max"))
        _require_keys("tshelf", tshelf, ("min", "max"))
        pressure_bounds = (float(pchamber["min"]), float(pchamber["max"]))
        if pressure_bounds[0] <= 0.0 or pressure_bounds[1] <= pressure_bounds[0]:
            raise ValueError("pchamber bounds must be positive and increasing")
        shelf_bounds = (float(tshelf["min"]), float(tshelf["max"]))
        if shelf_bounds[1] <= shelf_bounds[0]:
            raise ValueError("tshelf max must be greater than tshelf min")
        pressure_initialization = (
            float(requested_initial_pressure)
            if requested_initial_pressure is not None
            else float(np.mean(pressure_bounds))
        )
        shelf_initialization = (
            float(requested_initial_shelf_temperature)
            if requested_initial_shelf_temperature is not None
            else float(tshelf.get("init", product["T_pr_crit"]))
        )
        fixed_pressure = None
        fixed_shelf = None

    if nfe < 1:
        raise ValueError("nfe must be at least one")
    if ncp < 1:
        raise ValueError("ncp must be at least one")
    if nvial < 1:
        raise ValueError("nvial must be at least one")
    if not 0.0 < final_dried_fraction <= 1.0:
        raise ValueError("final_dried_fraction must satisfy 0 < value <= 1")
    if t_final_bounds[0] <= 0.0 or t_final_bounds[1] <= t_final_bounds[0]:
        raise ValueError("t_final_bounds must be positive and increasing")
    if requested_initial_pressure is not None and not (
        pressure_bounds[0] <= float(requested_initial_pressure) <= pressure_bounds[1]
    ):
        raise ValueError("initial_pressure must be within the chamber-pressure bounds")
    if requested_initial_shelf_temperature is not None and not (
        shelf_bounds[0] <= float(requested_initial_shelf_temperature) <= shelf_bounds[1]
    ):
        raise ValueError("initial_shelf_temperature must be within the shelf-temperature bounds")
    if pressure_ramp_rate is not None:
        if float(pressure_ramp_rate) <= 0.0:
            raise ValueError("pressure_ramp_rate must be positive")
        if requested_initial_pressure is None:
            raise ValueError("initial_pressure is required when pressure_ramp_rate is set")
    if shelf_temperature_ramp_rate is not None:
        if float(shelf_temperature_ramp_rate) <= 0.0:
            raise ValueError("shelf_temperature_ramp_rate must be positive")
        if requested_initial_shelf_temperature is None:
            raise ValueError(
                "initial_shelf_temperature is required when shelf_temperature_ramp_rate is set"
            )
    lpr0 = float(functions.Lpr0_FUN(vial["Vfill"], vial["Ap"], product["cSolid"]))
    drying_length_factor = _drying_length_factor(product, vial["Ap"])
    initial_horizon = (
        float(np.asarray(initialize)[-1, 0])
        if initialize is not None
        else min(max(12.0, t_final_bounds[0]), t_final_bounds[1])
    )

    model = pyo.ConcreteModel()
    model.optimized_control = optimized_control.value
    model.discretization_method = method.value
    model.nfe = int(nfe)
    model.ncp = None if method is DaeDiscretization.FINITE_DIFFERENCE else int(ncp)
    model.t = dae.ContinuousSet(bounds=(0.0, 1.0))

    model.Lpr0 = pyo.Param(initialize=lpr0)
    model.Av = pyo.Param(initialize=float(vial["Av"]))
    model.Ap = pyo.Param(initialize=float(vial["Ap"]))
    model.R0 = pyo.Param(initialize=float(product["R0"]))
    model.A1 = pyo.Param(initialize=float(product["A1"]))
    model.A2 = pyo.Param(initialize=float(product["A2"]))
    model.T_crit = pyo.Param(initialize=float(product["T_pr_crit"]))
    model.KC = pyo.Param(initialize=float(ht["KC"]))
    model.KP = pyo.Param(initialize=float(ht["KP"]))
    model.KD = pyo.Param(initialize=float(ht["KD"]))
    model.kg_To_g = pyo.Param(initialize=constant.kg_To_g)
    model.hr_To_s = pyo.Param(initialize=constant.hr_To_s)
    model.k_ice = pyo.Param(initialize=constant.k_ice)
    model.dHs = pyo.Param(initialize=constant.dHs)
    model.drying_length_factor = pyo.Param(initialize=drying_length_factor)
    model.final_dried_fraction = pyo.Param(initialize=float(final_dried_fraction))
    model.eq_cap_a = pyo.Param(initialize=float(eq_cap["a"]))
    model.eq_cap_b = pyo.Param(initialize=float(eq_cap["b"]))
    model.nvial = pyo.Param(initialize=int(nvial))
    if fixed_pressure is not None:
        model.fixed_Pch = pyo.Param(initialize=fixed_pressure)
    if fixed_shelf is not None:
        model.fixed_Tsh = pyo.Param(initialize=fixed_shelf)

    model.t_final = pyo.Var(bounds=t_final_bounds, initialize=initial_horizon)
    model.Lck = pyo.Var(
        model.t,
        domain=pyo.NonNegativeReals,
        bounds=(0.0, lpr0),
        initialize=lambda _m, tau: lpr0 * float(tau),
    )
    model.dLck_dt = dae.DerivativeVar(model.Lck, wrt=model.t)
    model.Pch = pyo.Var(
        model.t,
        domain=pyo.PositiveReals,
        bounds=pressure_bounds,
        initialize=pressure_initialization,
    )
    model.Tsh = pyo.Var(
        model.t,
        domain=pyo.Reals,
        bounds=shelf_bounds,
        initialize=shelf_initialization,
    )
    model.Tsub = pyo.Var(model.t, domain=pyo.Reals, bounds=(-80.0, 0.0), initialize=-30.0)
    model.Tbot = pyo.Var(model.t, domain=pyo.Reals, bounds=(-80.0, 80.0), initialize=-25.0)
    model.Psub = pyo.Var(model.t, domain=pyo.PositiveReals, bounds=(1.0e-8, 10.0), initialize=0.2)
    model.log_Psub = pyo.Var(model.t, domain=pyo.Reals, bounds=(-20.0, 3.0), initialize=-1.6)
    model.dmdt = pyo.Var(
        model.t, domain=pyo.NonNegativeReals, bounds=(0.0, None), initialize=1.0e-4
    )
    model.Kv = pyo.Var(model.t, domain=pyo.PositiveReals, bounds=(1.0e-8, None), initialize=3.0e-4)
    first = model.t.first()

    model.Rp = pyo.Expression(
        model.t,
        rule=lambda m, tau: m.R0 + m.A1 * m.Lck[tau] / (1.0 + m.A2 * m.Lck[tau]),
    )
    model.length_rate = pyo.Expression(
        model.t, rule=lambda m, tau: m.dmdt[tau] * m.drying_length_factor
    )
    model.percent_dried = pyo.Expression(model.t, rule=lambda m, tau: 100.0 * m.Lck[tau] / m.Lpr0)

    model.initial_dried_cake = pyo.Constraint(expr=model.Lck[model.t.first()] == 0.0)
    model.drying_front_dynamics = pyo.Constraint(
        model.t,
        rule=lambda m, tau: m.dLck_dt[tau] == m.t_final * m.length_rate[tau],
    )
    model.final_drying_target = pyo.Constraint(
        expr=model.Lck[model.t.last()] >= model.final_dried_fraction * model.Lpr0
    )
    model.vapor_pressure_log = pyo.Constraint(
        model.t,
        rule=lambda m, tau: (
            m.log_Psub[tau]
            == pyo.log(functions.VAPOR_PRESSURE_PREEXPONENTIAL)
            - functions.VAPOR_PRESSURE_TEMPERATURE_COEFFICIENT / (273.15 + m.Tsub[tau])
        ),
    )
    model.vapor_pressure_exp = pyo.Constraint(
        model.t, rule=lambda m, tau: m.Psub[tau] == pyo.exp(m.log_Psub[tau])
    )
    model.mass_transfer = pyo.Constraint(
        model.t,
        rule=lambda m, tau: (
            m.dmdt[tau] == m.Ap / m.Rp[tau] / m.kg_To_g * (m.Psub[tau] - m.Pch[tau])
        ),
    )
    model.frozen_layer_heat_balance = pyo.Constraint(
        model.t,
        rule=lambda m, tau: (
            (m.Tsh[tau] - m.Tbot[tau]) * m.Av * m.Kv[tau] * (m.Lpr0 - m.Lck[tau])
            == m.Ap * (m.Tbot[tau] - m.Tsub[tau]) * m.k_ice
        ),
    )
    model.energy_balance = pyo.Constraint(
        model.t,
        rule=lambda m, tau: (
            m.Tsh[tau]
            == m.dmdt[tau] * m.kg_To_g / m.hr_To_s * m.dHs / m.Av / m.Kv[tau] + m.Tbot[tau]
        ),
    )
    model.vial_heat_transfer = pyo.Constraint(
        model.t,
        rule=lambda m, tau: m.Kv[tau] == m.KC + m.KP * m.Pch[tau] / (1.0 + m.KD * m.Pch[tau]),
    )
    model.product_temperature_limit = pyo.Constraint(
        model.t, rule=lambda m, tau: m.Tbot[tau] <= m.T_crit
    )
    model.equipment_capability = pyo.Constraint(
        model.t,
        rule=lambda m, tau: m.eq_cap_a + m.eq_cap_b * m.Pch[tau] - m.nvial * m.dmdt[tau] >= 0.0,
    )

    if method is DaeDiscretization.FINITE_DIFFERENCE:
        pyo.TransformationFactory("dae.finite_difference").apply_to(
            model, wrt=model.t, nfe=int(nfe), scheme="BACKWARD"
        )
    else:
        pyo.TransformationFactory("dae.collocation").apply_to(
            model,
            wrt=model.t,
            nfe=int(nfe),
            ncp=int(ncp),
            scheme="LAGRANGE-RADAU",
        )

    points = sorted(model.t)
    if pressure_ramp_rate is not None:
        pressure_rate = float(pressure_ramp_rate)  # [Torr/hr]
        model.chamber_pressure_ramp_up = pyo.ConstraintList()
        model.chamber_pressure_ramp_down = pyo.ConstraintList()
        for previous, current in zip(points, points[1:]):
            normalized_interval = float(current - previous)  # [-]
            maximum_change = pressure_rate * normalized_interval * model.t_final
            model.chamber_pressure_ramp_up.add(
                model.Pch[current] - model.Pch[previous] <= maximum_change
            )
            model.chamber_pressure_ramp_down.add(
                model.Pch[previous] - model.Pch[current] <= maximum_change
            )
    if shelf_temperature_ramp_rate is not None:
        shelf_rate = float(shelf_temperature_ramp_rate)  # [degC/hr]
        model.shelf_temperature_ramp_up = pyo.ConstraintList()
        model.shelf_temperature_ramp_down = pyo.ConstraintList()
        for previous, current in zip(points, points[1:]):
            normalized_interval = float(current - previous)  # [-]
            maximum_change = shelf_rate * normalized_interval * model.t_final
            model.shelf_temperature_ramp_up.add(
                model.Tsh[current] - model.Tsh[previous] <= maximum_change
            )
            model.shelf_temperature_ramp_down.add(
                model.Tsh[previous] - model.Tsh[current] <= maximum_change
            )

    if (
        optimized_control
        in (
            _DaeOptimizedControl.CHAMBER_PRESSURE,
            _DaeOptimizedControl.JOINT,
        )
        and requested_initial_pressure is None
    ):
        # The control at tau=0 has zero measure in the final-time objective.
        # Select its right-limit value explicitly so exported pressure curves
        # do not contain an arbitrary endpoint jump.
        model.initial_pressure_continuity = pyo.Constraint(
            expr=model.Pch[first] == model.Pch[model.t.next(first)]
        )
    if (
        optimized_control is _DaeOptimizedControl.JOINT
        and requested_initial_shelf_temperature is None
    ):
        # Shelf temperature at tau=0 is likewise an isolated control value.
        # Match its first right-limit value so the exported joint-control
        # trajectory contains no arbitrary endpoint jump.
        model.initial_shelf_temperature_continuity = pyo.Constraint(
            expr=model.Tsh[first] == model.Tsh[model.t.next(first)]
        )

    if initialize is not None:
        _warmstart_from_legacy_table(model, initialize)
    # Explicit physical initial conditions take precedence over an optional
    # trajectory warm start, including its zero-time control values.
    if requested_initial_pressure is not None:
        model.Pch[first].fix(float(requested_initial_pressure))
    if requested_initial_shelf_temperature is not None:
        model.Tsh[first].fix(float(requested_initial_shelf_temperature))

    model.obj = pyo.Objective(expr=model.t_final, sense=pyo.minimize)
    # Import constraint and bound multipliers so a solved model can report how
    # many hours each active limit is worth. IPOPT populates the bound suffixes;
    # other solvers simply leave them empty.
    model.dual = pyo.Suffix(direction=pyo.Suffix.IMPORT)
    model.ipopt_zL_out = pyo.Suffix(direction=pyo.Suffix.IMPORT)
    model.ipopt_zU_out = pyo.Suffix(direction=pyo.Suffix.IMPORT)
    model.scaling_factor = pyo.Suffix(direction=pyo.Suffix.EXPORT)
    model.scaling_factor[model.t_final] = 0.1
    for tau in model.t:
        model.scaling_factor[model.Lck[tau]] = 1.0 / lpr0
        model.scaling_factor[model.Tsub[tau]] = 0.1
        model.scaling_factor[model.Tbot[tau]] = 0.1
        if not model.Tsh[tau].fixed:
            model.scaling_factor[model.Tsh[tau]] = 0.05
        if not model.Pch[tau].fixed:
            model.scaling_factor[model.Pch[tau]] = 5.0
        model.scaling_factor[model.Psub[tau]] = 5.0
        model.scaling_factor[model.dmdt[tau]] = 1.0e4
        model.scaling_factor[model.Kv[tau]] = 1.0e4
    return model


def create_dae_shelf_temperature_optimization_model(
    vial: Mapping[str, float],
    product: Mapping[str, float],
    ht: Mapping[str, float],
    pchamber: Mapping[str, Any],
    tshelf: Mapping[str, Any],
    *,
    eq_cap: Mapping[str, float],
    nvial: int,
    nfe: int = 24,
    discretization: DaeDiscretizationInput = DaeDiscretization.FINITE_DIFFERENCE,
    ncp: int = 3,
    final_dried_fraction: float = 1.0,
    t_final_bounds: Tuple[float, float] = (0.1, 50.0),
    initialize: Optional[np.ndarray] = None,
) -> pyo.ConcreteModel:
    """Build the free-final-time DAE counterpart to ``opt_Tsh.dry``.

    Chamber pressure is one fixed setpoint and shelf temperature is the
    bounded time-dependent control. The objective minimizes final drying
    time. ``nfe`` is passed directly to the selected Pyomo.DAE transformation;
    collocation additionally uses ``ncp`` Radau points per finite element.

    ``initialize`` may be a legacy seven-column trajectory with time [hr],
    temperatures [degC], pressure [mTorr], flux [kg/hr/m^2], and percent dried
    [0-100].
    """
    return _create_dae_optimization_model(
        vial,
        product,
        ht,
        pchamber,
        tshelf,
        eq_cap=eq_cap,
        nvial=nvial,
        nfe=nfe,
        discretization=discretization,
        ncp=ncp,
        final_dried_fraction=final_dried_fraction,
        t_final_bounds=t_final_bounds,
        initialize=initialize,
        optimized_control=_DaeOptimizedControl.SHELF_TEMPERATURE,
    )


def create_dae_chamber_pressure_optimization_model(
    vial: Mapping[str, float],
    product: Mapping[str, float],
    ht: Mapping[str, float],
    pchamber: Mapping[str, Any],
    tshelf: Mapping[str, Any],
    *,
    eq_cap: Mapping[str, float],
    nvial: int,
    nfe: int = 24,
    discretization: DaeDiscretizationInput = DaeDiscretization.FINITE_DIFFERENCE,
    ncp: int = 3,
    final_dried_fraction: float = 1.0,
    t_final_bounds: Tuple[float, float] = (0.1, 50.0),
    initialize: Optional[np.ndarray] = None,
) -> pyo.ConcreteModel:
    """Build the free-final-time DAE counterpart to ``opt_Pch.dry``.

    Shelf temperature must be one constant setpoint, and chamber pressure is
    the bounded time-dependent control in Torr. The objective minimizes final
    drying time under the same physics and constraints as the sequential
    optimizer. ``nfe`` is passed directly to the selected Pyomo.DAE
    transformation; collocation additionally uses ``ncp`` Radau points per
    finite element.

    ``initialize`` may be a legacy seven-column trajectory with time [hr],
    temperatures [degC], pressure [mTorr], flux [kg/hr/m^2], and percent dried
    [0-100].
    """
    return _create_dae_optimization_model(
        vial,
        product,
        ht,
        pchamber,
        tshelf,
        eq_cap=eq_cap,
        nvial=nvial,
        nfe=nfe,
        discretization=discretization,
        ncp=ncp,
        final_dried_fraction=final_dried_fraction,
        t_final_bounds=t_final_bounds,
        initialize=initialize,
        optimized_control=_DaeOptimizedControl.CHAMBER_PRESSURE,
    )


def create_dae_joint_optimization_model(
    vial: Mapping[str, float],
    product: Mapping[str, float],
    ht: Mapping[str, float],
    pchamber: Mapping[str, Any],
    tshelf: Mapping[str, Any],
    *,
    eq_cap: Mapping[str, float],
    nvial: int,
    nfe: int = 24,
    discretization: DaeDiscretizationInput = DaeDiscretization.FINITE_DIFFERENCE,
    ncp: int = 3,
    final_dried_fraction: float = 1.0,
    t_final_bounds: Tuple[float, float] = (0.1, 50.0),
    initialize: Optional[np.ndarray] = None,
    initial_pressure: Optional[float] = None,
    initial_shelf_temperature: Optional[float] = None,
    pressure_ramp_rate: Optional[float] = None,
    shelf_temperature_ramp_rate: Optional[float] = None,
) -> pyo.ConcreteModel:
    """Build the free-final-time DAE counterpart to ``opt_Pch_Tsh.dry``.

    Chamber pressure and shelf temperature are bounded time-dependent
    controls. The objective minimizes final drying time under the same
    quasi-steady physics, product-temperature limit, equipment constraint,
    and completion target as the sequential optimizer.

    ``initial_pressure`` [Torr] and ``initial_shelf_temperature`` [degC]
    optionally fix the two controls at physical time zero. The corresponding
    ramp rates are expressed in Torr/hr and degC/hr and constrain every pair
    of adjacent transcription nodes using the optimized physical-time
    interval. Ramp-rate options require their matching initial value. Leaving
    these options unset preserves the rate-unlimited legacy comparison.
    """
    return _create_dae_optimization_model(
        vial,
        product,
        ht,
        pchamber,
        tshelf,
        eq_cap=eq_cap,
        nvial=nvial,
        nfe=nfe,
        discretization=discretization,
        ncp=ncp,
        final_dried_fraction=final_dried_fraction,
        t_final_bounds=t_final_bounds,
        initialize=initialize,
        initial_pressure=initial_pressure,
        initial_shelf_temperature=initial_shelf_temperature,
        pressure_ramp_rate=pressure_ramp_rate,
        shelf_temperature_ramp_rate=shelf_temperature_ramp_rate,
        optimized_control=_DaeOptimizedControl.JOINT,
    )


def dae_optimization_values(model: pyo.ConcreteModel) -> dict[str, np.ndarray]:
    """Extract a solved normalized-time DAE model into physical-time arrays."""
    coordinates = sorted(model.t)
    final_time = pyo.value(model.t_final, exception=False)
    scale = np.nan if final_time is None else float(final_time)
    values: dict[str, np.ndarray] = {
        "time": np.asarray([float(tau) * scale for tau in coordinates], dtype=float),
        "Ap": np.full(len(coordinates), float(pyo.value(model.Ap)), dtype=float),
        "Lpr0": np.full(len(coordinates), float(pyo.value(model.Lpr0)), dtype=float),
    }
    for name in ("Lck", "Pch", "Tsh", "Tsub", "Tbot", "Psub", "log_Psub", "dmdt", "Kv"):
        component = getattr(model, name)
        raw = [pyo.value(component[tau], exception=False) for tau in coordinates]
        values[name] = np.asarray(
            [np.nan if value is None else float(value) for value in raw], dtype=float
        )
    values["Rp"] = np.asarray([float(pyo.value(model.Rp[tau])) for tau in coordinates], dtype=float)
    values["length_rate"] = np.asarray(
        [float(pyo.value(model.length_rate[tau])) for tau in coordinates], dtype=float
    )
    values["percent_dried"] = values["Lck"] / values["Lpr0"] * 100.0
    return values


def _shadow_prices(model: pyo.ConcreteModel) -> dict[str, float]:
    """Return the drying-time sensitivity [hr] of each active limit.

    Every entry is the change in the optimal final drying time per unit
    increase in the named limit, so the sign convention is uniform across
    constraint multipliers and variable-bound multipliers. Values are summed
    over the time domain because a limit expressed as a model parameter (the
    critical product temperature, a control bound) is relaxed simultaneously
    at every transcription node.
    """

    def _suffix_total(suffix_name: str, components: Any) -> Optional[float]:
        suffix = getattr(model, suffix_name, None)
        if suffix is None:
            return None
        values = [suffix.get(component, None) for component in components]
        present = [float(value) for value in values if value is not None]
        return float(sum(present)) if present else None

    prices: dict[str, float] = {}
    for key, component_name in (
        ("product_temperature_limit", "product_temperature_limit"),
        ("equipment_capability", "equipment_capability"),
    ):
        component = getattr(model, component_name, None)
        if component is not None:
            total = _suffix_total("dual", list(component.values()))
            if total is not None:
                prices[key] = total
    target = getattr(model, "final_drying_target", None)
    if target is not None:
        total = _suffix_total("dual", [target])
        if total is not None:
            prices["final_drying_target"] = total
    for key, variable, suffix_name in (
        ("chamber_pressure_lower_bound", model.Pch, "ipopt_zL_out"),
        ("chamber_pressure_upper_bound", model.Pch, "ipopt_zU_out"),
        ("shelf_temperature_lower_bound", model.Tsh, "ipopt_zL_out"),
        ("shelf_temperature_upper_bound", model.Tsh, "ipopt_zU_out"),
    ):
        total = _suffix_total(suffix_name, [variable[tau] for tau in model.t])
        if total is not None:
            prices[key] = total
    return prices


def _solve_dae_optimization_model(
    model: pyo.ConcreteModel,
    *,
    solver: Union[str, Any],
    tee: bool,
) -> DaeOptimizationResult:
    method = _coerce_discretization(model.discretization_method)
    metadata = {
        "optimized_control": model.optimized_control,
        "method": method.value,
        "nfe": int(model.nfe),
        "ncp": None if method is DaeDiscretization.FINITE_DIFFERENCE else int(model.ncp),
        "n_time_points": len(model.t),
        "n_variables": sum(1 for _ in model.component_data_objects(pyo.Var, descend_into=True)),
        "n_constraints": sum(
            1 for _ in model.component_data_objects(pyo.Constraint, active=True, descend_into=True)
        ),
        "solver_iterations": None,
    }
    try:
        opt, solver_name = _solver_from_arg(solver, tee)
        options = getattr(opt, "options", None)
        if solver_name == "ipopt" and options is not None:
            # IPOPT otherwise ignores the model's exported scaling_factor
            # suffix. Keep this option local to the DAE model, which defines
            # the suffix, and preserve an explicit caller override.
            options.setdefault("nlp_scaling_method", "user-scaling")
        results = opt.solve(model, tee=tee)
    except Exception as exc:  # pragma: no cover - environment-specific solver failures
        return DaeOptimizationResult(
            success=False,
            solver_status="not_available",
            termination_condition="not_available",
            message=f"Pyomo.DAE solve failed before returning results: {exc}",
            objective_time_hr=None,
            values=dae_optimization_values(model),
            constraint_violations=_constraint_violations(model),
            discretization=metadata,
        )

    try:
        metadata["solver_iterations"] = int(results.solver.iterations)
    except (AttributeError, TypeError, ValueError):
        pass

    status = results.solver.status
    termination = results.solver.termination_condition
    success = _termination_success(termination)
    violations = _constraint_violations(model)
    finite_violations = [value for value in violations.values() if value is not None]
    max_violation = max(finite_violations, default=0.0)
    objective = pyo.value(model.t_final, exception=False)
    message = (
        f"Pyomo.DAE solve reached {termination}; maximum constraint violation {max_violation:.3e}."
        if success
        else "Pyomo.DAE solve did not reach an optimal solution "
        f"(status={status}, termination_condition={termination}); maximum "
        f"constraint violation {max_violation:.3e}."
    )
    return DaeOptimizationResult(
        success=success,
        solver_status=str(status),
        termination_condition=str(termination),
        message=message,
        objective_time_hr=None if objective is None else float(objective),
        values=dae_optimization_values(model),
        constraint_violations=violations,
        discretization=metadata,
        # Multipliers describe the optimum, so they are meaningless for a
        # solve that did not reach one.
        shadow_prices=_shadow_prices(model) if success else {},
    )


def solve_dae_shelf_temperature_optimization(
    vial: Mapping[str, float],
    product: Mapping[str, float],
    ht: Mapping[str, float],
    pchamber: Mapping[str, Any],
    tshelf: Mapping[str, Any],
    *,
    eq_cap: Mapping[str, float],
    nvial: int,
    nfe: int = 24,
    discretization: DaeDiscretizationInput = DaeDiscretization.FINITE_DIFFERENCE,
    ncp: int = 3,
    final_dried_fraction: float = 1.0,
    t_final_bounds: Tuple[float, float] = (0.1, 50.0),
    initialize: Optional[np.ndarray] = None,
    solver: Union[str, Any] = "ipopt",
    tee: bool = False,
) -> DaeOptimizationResult:
    """Build and solve the free-final-time DAE shelf-temperature problem.

    Parameters
    ----------
    vial, product, ht, pchamber, tshelf, eq_cap, nvial, nfe, discretization, ncp
        Model inputs described by
        :func:`create_dae_shelf_temperature_optimization_model`.
    final_dried_fraction
        Dimensionless terminal dried fraction on the interval (0, 1].
    t_final_bounds
        Lower and upper bounds for the free final drying time, in hours.
    initialize
        Optional legacy seven-column trajectory using time [hr], temperatures
        [degC], pressure [mTorr], sublimation flux [kg/hr/m^2], and percent
        dried [0-100].
    solver
        Pyomo solver name or solver object.
    tee
        Whether to stream solver output [-].

    Returns
    -------
    DaeOptimizationResult
        Solver status, final-time objective [hr], physical trajectories, and
        constraint violations.
    """
    model = create_dae_shelf_temperature_optimization_model(
        vial,
        product,
        ht,
        pchamber,
        tshelf,
        eq_cap=eq_cap,
        nvial=nvial,
        nfe=nfe,
        discretization=discretization,
        ncp=ncp,
        final_dried_fraction=final_dried_fraction,
        t_final_bounds=t_final_bounds,
        initialize=initialize,
    )
    return _solve_dae_optimization_model(
        model,
        solver=solver,
        tee=tee,
    )


def solve_dae_chamber_pressure_optimization(
    vial: Mapping[str, float],
    product: Mapping[str, float],
    ht: Mapping[str, float],
    pchamber: Mapping[str, Any],
    tshelf: Mapping[str, Any],
    *,
    eq_cap: Mapping[str, float],
    nvial: int,
    nfe: int = 24,
    discretization: DaeDiscretizationInput = DaeDiscretization.FINITE_DIFFERENCE,
    ncp: int = 3,
    final_dried_fraction: float = 1.0,
    t_final_bounds: Tuple[float, float] = (0.1, 50.0),
    initialize: Optional[np.ndarray] = None,
    solver: Union[str, Any] = "ipopt",
    tee: bool = False,
) -> DaeOptimizationResult:
    """Build and solve the free-final-time DAE chamber-pressure problem.

    Inputs follow :func:`create_dae_chamber_pressure_optimization_model`.
    The result contains solver status, the final-time objective [hr], physical
    trajectories in package units, discretization size, and constraint
    violations.
    """
    model = create_dae_chamber_pressure_optimization_model(
        vial,
        product,
        ht,
        pchamber,
        tshelf,
        eq_cap=eq_cap,
        nvial=nvial,
        nfe=nfe,
        discretization=discretization,
        ncp=ncp,
        final_dried_fraction=final_dried_fraction,
        t_final_bounds=t_final_bounds,
        initialize=initialize,
    )
    return _solve_dae_optimization_model(
        model,
        solver=solver,
        tee=tee,
    )


def solve_dae_joint_optimization(
    vial: Mapping[str, float],
    product: Mapping[str, float],
    ht: Mapping[str, float],
    pchamber: Mapping[str, Any],
    tshelf: Mapping[str, Any],
    *,
    eq_cap: Mapping[str, float],
    nvial: int,
    nfe: int = 24,
    discretization: DaeDiscretizationInput = DaeDiscretization.FINITE_DIFFERENCE,
    ncp: int = 3,
    final_dried_fraction: float = 1.0,
    t_final_bounds: Tuple[float, float] = (0.1, 50.0),
    initialize: Optional[np.ndarray] = None,
    initial_pressure: Optional[float] = None,
    initial_shelf_temperature: Optional[float] = None,
    pressure_ramp_rate: Optional[float] = None,
    shelf_temperature_ramp_rate: Optional[float] = None,
    solver: Union[str, Any] = "ipopt",
    tee: bool = False,
) -> DaeOptimizationResult:
    """Build and solve the joint pressure/temperature DAE optimization."""
    model = create_dae_joint_optimization_model(
        vial,
        product,
        ht,
        pchamber,
        tshelf,
        eq_cap=eq_cap,
        nvial=nvial,
        nfe=nfe,
        discretization=discretization,
        ncp=ncp,
        final_dried_fraction=final_dried_fraction,
        t_final_bounds=t_final_bounds,
        initialize=initialize,
        initial_pressure=initial_pressure,
        initial_shelf_temperature=initial_shelf_temperature,
        pressure_ramp_rate=pressure_ramp_rate,
        shelf_temperature_ramp_rate=shelf_temperature_ramp_rate,
    )
    return _solve_dae_optimization_model(
        model,
        solver=solver,
        tee=tee,
    )


__all__ = [
    "DaeDiscretization",
    "DaeOptimizationResult",
    "create_dae_chamber_pressure_optimization_model",
    "create_dae_joint_optimization_model",
    "create_dae_shelf_temperature_optimization_model",
    "dae_optimization_values",
    "solve_dae_chamber_pressure_optimization",
    "solve_dae_joint_optimization",
    "solve_dae_shelf_temperature_optimization",
]
