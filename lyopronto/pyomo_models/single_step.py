"""Single-step Pyomo model for primary-drying optimization."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional, Tuple, Union

import pyomo.environ as pyo  # type: ignore[import-untyped]

from .. import constant, functions


VariableBounds = Tuple[Optional[float], Optional[float]]


@dataclass(frozen=True)
class SingleStepResult:
    """Solver outcome and diagnostics for one Pyomo primary-drying step."""

    success: bool
    solver_status: str
    termination_condition: str
    message: str
    values: Mapping[str, Optional[float]]
    constraint_violations: Mapping[str, Optional[float]]

    def as_dict(self) -> Dict[str, Optional[float]]:
        """Return solved variable values in the legacy dictionary shape."""
        return dict(self.values)


def _require_keys(name: str, data: Mapping[str, float], keys: Tuple[str, ...]) -> None:
    missing = [key for key in keys if key not in data]
    if missing:
        joined = ", ".join(missing)
        raise KeyError(f"{name} is missing required key(s): {joined}")


def _vapor_pressure_value(t_sub: float) -> float:
    return float(functions.Vapor_pressure(t_sub))


def _initial_values(
    product: Mapping[str, float],
    pch_bounds: VariableBounds,
    tsh_bounds: VariableBounds,
    fixed_pch: Optional[float],
    fixed_tsh: Optional[float],
    initialize: Optional[Mapping[str, float]],
) -> Dict[str, float]:
    values: Dict[str, float] = {}
    if initialize is not None:
        values.update({key: float(value) for key, value in initialize.items()})

    pch_lower, pch_upper = pch_bounds
    tsh_lower, tsh_upper = tsh_bounds
    pch_default = fixed_pch
    if pch_default is None:
        lower = 0.05 if pch_lower is None else pch_lower
        upper = 0.5 if pch_upper is None else pch_upper
        pch_default = (lower + upper) / 2.0

    tsh_default = fixed_tsh
    if tsh_default is None:
        lower = -45.0 if tsh_lower is None else tsh_lower
        upper = 20.0 if tsh_upper is None else tsh_upper
        tsh_default = (lower + upper) / 2.0

    tcrit = float(product.get("T_pr_crit", -5.0))
    tbot_default = min(tcrit - 0.1, float(tsh_default) - 0.1)
    tsub_default = max(-60.0, min(tbot_default - 0.5, -1.0))
    psub_default = _vapor_pressure_value(tsub_default)

    values.setdefault("Pch", float(pch_default))
    values.setdefault("Tsh", float(tsh_default))
    values.setdefault("Tbot", float(tbot_default))
    values.setdefault("Tsub", float(tsub_default))
    values.setdefault("Psub", psub_default)
    values.setdefault("log_Psub", pyo.log(psub_default))
    values.setdefault("dmdt", 1.0e-4)
    values.setdefault("Kv", 3.0e-4)
    return values


def create_single_step_model(
    vial: Mapping[str, float],
    product: Mapping[str, float],
    ht: Mapping[str, float],
    lpr0: float,
    lck: float,
    pch_bounds: VariableBounds = (0.05, 0.5),
    tsh_bounds: VariableBounds = (-50.0, 50.0),
    eq_cap: Optional[Mapping[str, float]] = None,
    nvial: Optional[int] = None,
    fixed_pch: Optional[float] = None,
    fixed_tsh: Optional[float] = None,
    initialize: Optional[Mapping[str, float]] = None,
) -> pyo.ConcreteModel:
    """Create one primary-drying optimization step as an explicit Pyomo model.

    Units match the legacy SciPy optimizers: pressure in Torr, temperatures in
    degC, product lengths in cm, heat-transfer coefficients in cal/s/K/cm^2,
    product resistance in cm^2-hr-Torr/g, and sublimation rate in kg/hr/vial.
    """
    _require_keys("vial", vial, ("Av", "Ap"))
    _require_keys("product", product, ("R0", "A1", "A2", "T_pr_crit"))
    _require_keys("ht", ht, ("KC", "KP", "KD"))
    if eq_cap is not None:
        _require_keys("eq_cap", eq_cap, ("a", "b"))
        if nvial is None:
            raise ValueError("nvial is required when eq_cap is provided")
    if lpr0 <= 0:
        raise ValueError("lpr0 must be positive")
    if lck < 0 or lck >= lpr0:
        raise ValueError("lck must satisfy 0 <= lck < lpr0 for a drying step")

    initial = _initial_values(product, pch_bounds, tsh_bounds, fixed_pch, fixed_tsh, initialize)
    model = pyo.ConcreteModel()

    model.Lpr0 = pyo.Param(initialize=float(lpr0))
    model.Lck = pyo.Param(initialize=float(lck))
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

    model.Pch = pyo.Var(domain=pyo.NonNegativeReals, bounds=pch_bounds, initialize=initial["Pch"])
    model.Tsh = pyo.Var(domain=pyo.Reals, bounds=tsh_bounds, initialize=initial["Tsh"])
    model.Tsub = pyo.Var(domain=pyo.Reals, bounds=(-60.0, 0.0), initialize=initial["Tsub"])
    model.Tbot = pyo.Var(domain=pyo.Reals, bounds=(-60.0, 50.0), initialize=initial["Tbot"])
    model.Psub = pyo.Var(
        domain=pyo.NonNegativeReals, bounds=(1.0e-8, 10.0), initialize=initial["Psub"]
    )
    model.log_Psub = pyo.Var(domain=pyo.Reals, bounds=(-20.0, 3.0), initialize=initial["log_Psub"])
    model.dmdt = pyo.Var(
        domain=pyo.NonNegativeReals, bounds=(0.0, None), initialize=initial["dmdt"]
    )
    model.Kv = pyo.Var(domain=pyo.PositiveReals, bounds=(1.0e-8, None), initialize=initial["Kv"])

    model.Rp = pyo.Expression(expr=model.R0 + model.A1 * model.Lck / (1.0 + model.A2 * model.Lck))

    model.vapor_pressure_log = pyo.Constraint(
        expr=model.log_Psub == pyo.log(2.698e10) - 6144.96 / (273.15 + model.Tsub)
    )
    model.vapor_pressure_exp = pyo.Constraint(expr=model.Psub == pyo.exp(model.log_Psub))
    model.mass_transfer = pyo.Constraint(
        expr=model.dmdt == model.Ap / model.Rp / model.kg_To_g * (model.Psub - model.Pch)
    )
    model.frozen_layer_heat_balance = pyo.Constraint(
        expr=(model.Tsh - model.Tbot) * model.Av * model.Kv * (model.Lpr0 - model.Lck)
        == model.Ap * (model.Tbot - model.Tsub) * model.k_ice
    )
    model.energy_balance = pyo.Constraint(
        expr=model.Tsh
        == model.dmdt * model.kg_To_g / model.hr_To_s * model.dHs / model.Av / model.Kv + model.Tbot
    )
    model.vial_heat_transfer = pyo.Constraint(
        expr=model.Kv == model.KC + model.KP * model.Pch / (1.0 + model.KD * model.Pch)
    )
    model.product_temperature_limit = pyo.Constraint(expr=model.Tbot <= model.T_crit)

    if fixed_pch is not None:
        model.fixed_chamber_pressure = pyo.Constraint(expr=model.Pch == float(fixed_pch))
    if fixed_tsh is not None:
        model.fixed_shelf_temperature = pyo.Constraint(expr=model.Tsh == float(fixed_tsh))
    if eq_cap is not None and nvial is not None:
        model.eq_cap_a = pyo.Param(initialize=float(eq_cap["a"]))
        model.eq_cap_b = pyo.Param(initialize=float(eq_cap["b"]))
        model.nvial = pyo.Param(initialize=int(nvial))
        model.equipment_capability = pyo.Constraint(
            expr=model.eq_cap_a + model.eq_cap_b * model.Pch - model.nvial * model.dmdt >= 0
        )

    model.obj = pyo.Objective(expr=model.Pch - model.Psub, sense=pyo.minimize)
    return model


def _set_solver_options(solver: Any, solver_name: Optional[str], tee: bool) -> None:
    options = getattr(solver, "options", None)
    if options is None or solver_name != "ipopt":
        return
    options.setdefault("max_iter", 3000)
    options.setdefault("tol", 1.0e-7)
    options.setdefault("mu_strategy", "adaptive")
    options.setdefault("print_level", 5 if tee else 0)


def _solver_from_arg(solver: Union[str, Any], tee: bool) -> Tuple[Any, Optional[str]]:
    solver_name: Optional[str]
    if isinstance(solver, str):
        solver_name = solver.lower()
        opt = pyo.SolverFactory(solver)
    else:
        raw_solver_name = getattr(solver, "name", None)
        solver_name = raw_solver_name.lower() if isinstance(raw_solver_name, str) else None
        opt = solver
    _set_solver_options(opt, solver_name, tee)
    return opt, solver_name


def _termination_success(termination: Any) -> bool:
    successful = {pyo.TerminationCondition.optimal}
    for name in ("locallyOptimal", "globallyOptimal"):
        condition = getattr(pyo.TerminationCondition, name, None)
        if condition is not None:
            successful.add(condition)
    return termination in successful


def _extract_values(model: pyo.ConcreteModel) -> Dict[str, Optional[float]]:
    values: Dict[str, Optional[float]] = {}
    for name in ("Pch", "Tsh", "Tsub", "Tbot", "Psub", "log_Psub", "dmdt", "Kv", "Rp", "obj"):
        component = getattr(model, name)
        value = pyo.value(component, exception=False)
        values[name] = None if value is None else float(value)
    return values


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


def solve_single_step(
    model: pyo.ConcreteModel,
    solver: Union[str, Any] = "ipopt",
    tee: bool = False,
) -> SingleStepResult:
    """Solve a single-step model and return values plus clear diagnostics."""
    try:
        opt, _solver_name = _solver_from_arg(solver, tee)
        results = opt.solve(model, tee=tee)
    except Exception as exc:  # pragma: no cover - exact solver failures are environment specific
        return SingleStepResult(
            success=False,
            solver_status="not_available",
            termination_condition="not_available",
            message=f"Pyomo solve failed before returning results: {exc}",
            values=_extract_values(model),
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
            f"Pyomo solve reached {termination}; maximum constraint violation {max_violation:.3e}."
        )
    else:
        message = (
            "Pyomo solve did not reach an optimal solution "
            f"(status={status}, termination_condition={termination}); maximum "
            f"constraint violation {max_violation:.3e}."
        )

    return SingleStepResult(
        success=success,
        solver_status=str(status),
        termination_condition=str(termination),
        message=message,
        values=_extract_values(model),
        constraint_violations=violations,
    )
