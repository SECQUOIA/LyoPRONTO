"""Free-final-time Pyomo.DAE optimization for primary drying.

This module provides simultaneous counterparts to the legacy sequential
``opt_Tsh.dry`` and ``opt_Pch.dry`` workflows.  The physical model has one
differential state, the dried cake length, and quasi-steady algebraic heat-
and mass-transfer relations.  A normalized time domain keeps the mesh
independent of the optimized final drying time.

Both backward finite differences and LAGRANGE-RADAU orthogonal collocation
are available through Pyomo.DAE.  The model remains in the optional Pyomo
dependency boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
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
    optimized_control: _DaeOptimizedControl,
) -> pyo.ConcreteModel:
    """Build either supported free-final-time DAE optimization model."""
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
        initial_pressure = fixed_pressure
        initial_shelf = float(tshelf.get("init", product["T_pr_crit"]))
        fixed_shelf = None
    else:
        _require_keys("pchamber", pchamber, ("min", "max"))
        fixed_shelf = _single_fixed_shelf_temperature(tshelf)
        pressure_bounds = (float(pchamber["min"]), float(pchamber["max"]))
        if pressure_bounds[0] <= 0.0 or pressure_bounds[1] <= pressure_bounds[0]:
            raise ValueError("pchamber bounds must be positive and increasing")
        shelf_bounds = (fixed_shelf, fixed_shelf)
        initial_pressure = float(np.mean(pressure_bounds))
        initial_shelf = fixed_shelf
        fixed_pressure = None

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
        initialize=initial_pressure,
    )
    model.Tsh = pyo.Var(
        model.t,
        domain=pyo.Reals,
        bounds=shelf_bounds,
        initialize=initial_shelf,
    )
    model.Tsub = pyo.Var(model.t, domain=pyo.Reals, bounds=(-80.0, 0.0), initialize=-30.0)
    model.Tbot = pyo.Var(model.t, domain=pyo.Reals, bounds=(-80.0, 80.0), initialize=-25.0)
    model.Psub = pyo.Var(model.t, domain=pyo.PositiveReals, bounds=(1.0e-8, 10.0), initialize=0.2)
    model.log_Psub = pyo.Var(model.t, domain=pyo.Reals, bounds=(-20.0, 3.0), initialize=-1.6)
    model.dmdt = pyo.Var(
        model.t, domain=pyo.NonNegativeReals, bounds=(0.0, None), initialize=1.0e-4
    )
    model.Kv = pyo.Var(model.t, domain=pyo.PositiveReals, bounds=(1.0e-8, None), initialize=3.0e-4)

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

    if optimized_control is _DaeOptimizedControl.CHAMBER_PRESSURE:
        # The control at tau=0 has zero measure in the final-time objective.
        # Select its right-limit value explicitly so exported pressure curves
        # do not contain an arbitrary endpoint jump.
        first = model.t.first()
        model.initial_pressure_continuity = pyo.Constraint(
            expr=model.Pch[first] == model.Pch[model.t.next(first)]
        )

    if initialize is not None:
        _warmstart_from_legacy_table(model, initialize)

    model.obj = pyo.Objective(expr=model.t_final, sense=pyo.minimize)
    model.scaling_factor = pyo.Suffix(direction=pyo.Suffix.EXPORT)
    model.scaling_factor[model.t_final] = 0.1
    for tau in model.t:
        model.scaling_factor[model.Lck[tau]] = 1.0 / lpr0
        model.scaling_factor[model.Tsub[tau]] = 0.1
        model.scaling_factor[model.Tbot[tau]] = 0.1
        model.scaling_factor[model.Tsh[tau]] = 0.05
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


def _solve_dae_optimization_model(
    model: pyo.ConcreteModel,
    *,
    discretization: DaeDiscretizationInput,
    nfe: int,
    ncp: int,
    solver: Union[str, Any],
    tee: bool,
) -> DaeOptimizationResult:
    method = _coerce_discretization(discretization)
    metadata = {
        "optimized_control": model.optimized_control,
        "method": method.value,
        "nfe": int(nfe),
        "ncp": None if method is DaeDiscretization.FINITE_DIFFERENCE else int(ncp),
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
        discretization=discretization,
        nfe=nfe,
        ncp=ncp,
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
        discretization=discretization,
        nfe=nfe,
        ncp=ncp,
        solver=solver,
        tee=tee,
    )


__all__ = [
    "DaeDiscretization",
    "DaeOptimizationResult",
    "create_dae_chamber_pressure_optimization_model",
    "create_dae_shelf_temperature_optimization_model",
    "dae_optimization_values",
    "solve_dae_chamber_pressure_optimization",
    "solve_dae_shelf_temperature_optimization",
]
