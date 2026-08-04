"""Validation-only GDP switching model for the paper optimal-control cases.

The model in this module uses the SI-unit physical equations from
``paper_ocp`` (K, Pa, m, and s), but represents the active control policy with
Pyomo.GDP disjuncts.  It is intentionally a small verification model rather
than a production cycle-design API.

Each phase has normalized local time and a free duration [s].  The physical
DAE and path inequalities are common to all modes; a phase disjunct adds only
one of the three policy equalities:

* Policy 1: maximum shelf heat input, ``Tb = Tb_max``.
* Policy 2: product-temperature tracking, ``T_bottom = T_limit``.
* Policy 3: interface-velocity tracking, ``dS/dt = v_limit``.

Both adjacent policy equalities hold at a phase boundary; policy identity at
that exact transition remains immaterial.  Policy equalities start immediately
after the fixed initial point so an initially incompatible candidate does not
preselect the first disjunct.  This also preserves Paper Problem 2's documented
initial velocity excursion before Policy 3 becomes active.  The shared path
constraints still apply at every later phase boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import numpy as np

from .paper_ocp import (
    PaperPrimaryDryingConfig,
    _paper_problem_settings,
    classify_paper_policies,
    derive_primary_drying_parameters,
)

POLICY_MAX_HEAT = "policy_1_max_heat_input"
POLICY_TEMPERATURE = "policy_2_temperature_tracking"
POLICY_VELOCITY = "policy_3_interface_velocity_tracking"


@dataclass(frozen=True)
class PaperGDPDiscretization:
    """Discretization controls for the multiphase GDP benchmark.

    ``nfe_per_phase`` is the number of finite elements on each phase's local
    normalized time domain.  Phase durations are positive so every selected
    policy represents a real interval rather than a zero-duration artifact.
    """

    n_z: int = 5
    nfe_per_phase: int = 4
    ncp: int = 2
    terminal_drying_fraction: float = 0.995
    minimum_phase_duration_s: float = 1.0
    temperature_lower_bound_K: float = 220.0
    temperature_upper_bound_K: float = 280.0
    scheme: str = "LAGRANGE-RADAU"


def _problem_structure(problem: str) -> tuple[int, tuple[str, ...]]:
    if problem == "problem1":
        return 2, (POLICY_MAX_HEAT, POLICY_TEMPERATURE)
    if problem == "problem2":
        return 3, (POLICY_MAX_HEAT, POLICY_TEMPERATURE, POLICY_VELOCITY)
    raise ValueError(f"unsupported paper GDP problem: {problem}")


def _normalized_duration_weights(
    n_phases: int,
    phase_duration_weights: Sequence[float] | None,
) -> tuple[float, ...]:
    if phase_duration_weights is None:
        return tuple(1.0 / n_phases for _ in range(n_phases))
    if len(phase_duration_weights) != n_phases:
        raise ValueError(f"phase_duration_weights must contain {n_phases} values")
    weights = np.asarray(phase_duration_weights, dtype=float)
    if not np.all(np.isfinite(weights)) or np.any(weights <= 0.0):
        raise ValueError("phase_duration_weights must be finite and positive")
    weights /= np.sum(weights)
    return tuple(float(weight) for weight in weights)


def create_paper_problem1_gdp_model(
    config: PaperPrimaryDryingConfig | None = None,
    discretization: PaperGDPDiscretization | None = None,
    *,
    phase_duration_weights: Sequence[float] | None = None,
):
    """Create the two-phase GDP model for Paper Problem 1."""
    return _create_paper_gdp_model(
        "problem1",
        config=config,
        discretization=discretization,
        phase_duration_weights=phase_duration_weights,
    )


def create_paper_problem2_gdp_model(
    config: PaperPrimaryDryingConfig | None = None,
    discretization: PaperGDPDiscretization | None = None,
    *,
    phase_duration_weights: Sequence[float] | None = None,
):
    """Create the three-phase GDP model for Paper Problem 2."""
    return _create_paper_gdp_model(
        "problem2",
        config=config,
        discretization=discretization,
        phase_duration_weights=phase_duration_weights,
    )


def _create_paper_gdp_model(
    problem: str,
    config: PaperPrimaryDryingConfig | None = None,
    discretization: PaperGDPDiscretization | None = None,
    *,
    phase_duration_weights: Sequence[float] | None = None,
):
    """Create a discretized multiphase GDP model for a paper OCP."""
    import pyomo.dae as dae  # type: ignore[import-untyped]
    import pyomo.environ as pyo  # type: ignore[import-untyped]
    from pyomo.gdp import Disjunct, Disjunction  # type: ignore[import-untyped]

    config = config or PaperPrimaryDryingConfig()
    discretization = discretization or PaperGDPDiscretization()
    settings = _paper_problem_settings(config, problem)
    n_phases, policy_names = _problem_structure(problem)
    weights = _normalized_duration_weights(n_phases, phase_duration_weights)
    if discretization.n_z < 3:
        raise ValueError("n_z must be at least 3 for the MOL stencil")
    if discretization.nfe_per_phase < 1:
        raise ValueError("nfe_per_phase must be positive")
    if discretization.ncp < 1:
        raise ValueError("ncp must be positive")
    if not 0.0 < discretization.terminal_drying_fraction < 1.0:
        raise ValueError("terminal_drying_fraction must be in (0, 1)")
    if discretization.minimum_phase_duration_s <= 0.0:
        raise ValueError("minimum_phase_duration_s must be positive")

    derived = derive_primary_drying_parameters(config, discretization.n_z)
    terminal_s = discretization.terminal_drying_fraction * derived.product_height

    model = pyo.ConcreteModel(name=f"{settings.name}_gdp")
    model._paper_config = config
    model._paper_gdp_discretization = discretization
    model._paper_derived = derived
    model._paper_problem_settings = settings
    model._paper_problem = problem
    model._paper_policy_names = policy_names
    model._paper_duration_weights = weights

    model.z = pyo.RangeSet(0, discretization.n_z - 1)
    model.phases = pyo.RangeSet(1, n_phases)
    model.policy_names = pyo.Set(initialize=policy_names, ordered=True)
    model.phase = pyo.Block(model.phases)

    cumulative_weights = np.concatenate(([0.0], np.cumsum(weights)))
    shelf_initial_K = 0.5 * (
        settings.shelf_temperature_min + settings.shelf_temperature_max
    )

    for phase_index in model.phases:
        phase = model.phase[phase_index]
        phase.t = dae.ContinuousSet(bounds=(0.0, 1.0))
        phase.duration_s = pyo.Var(
            bounds=(discretization.minimum_phase_duration_s, config.time_bounds[1]),
            initialize=settings.time_guess * weights[phase_index - 1],
        )

        def progress_initializer(_block: Any, tau: float, *, p: int = phase_index):
            return float(cumulative_weights[p - 1] + weights[p - 1] * float(tau))

        def temperature_initializer(
            block: Any,
            _z: int,
            tau: float,
            *,
            progress=progress_initializer,
        ) -> float:
            fraction = progress(block, tau)
            return config.initial_temperature + fraction * (
                settings.temperature_limit - config.initial_temperature
            )

        phase.T = pyo.Var(
            model.z,
            phase.t,
            bounds=(
                discretization.temperature_lower_bound_K,
                discretization.temperature_upper_bound_K,
            ),
            initialize=temperature_initializer,
        )
        phase.S = pyo.Var(
            phase.t,
            bounds=(0.0, terminal_s),
            initialize=lambda b, tau, progress=progress_initializer: (
                terminal_s * progress(b, tau)
            ),
        )
        phase.Tb = pyo.Var(
            phase.t,
            bounds=(settings.shelf_temperature_min, settings.shelf_temperature_max),
            initialize=shelf_initial_K,
        )
        phase.dT_dtau = dae.DerivativeVar(phase.T, wrt=phase.t)
        phase.dS_dtau = dae.DerivativeVar(phase.S, wrt=phase.t)

        phase.Pw = pyo.Expression(
            phase.t,
            rule=lambda b, tau: pyo.exp(
                config.vapor_pressure_a / b.T[0, tau] + config.vapor_pressure_b
            ),
        )
        phase.Rp = pyo.Expression(
            phase.t,
            rule=lambda b, tau: config.resistance_0
            + config.resistance_1 * b.S[tau] / (1.0 + config.resistance_2 * b.S[tau]),
        )
        phase.Nw = pyo.Expression(
            phase.t,
            rule=lambda b, tau: (b.Pw[tau] - config.chamber_water_pressure) / b.Rp[tau],
        )
        phase.dSdt = pyo.Expression(
            phase.t,
            rule=lambda b, tau: b.Nw[tau]
            / (derived.frozen_density - config.dried_region_density),
        )
        phase.nonnegative_sublimation_flux = pyo.Constraint(
            phase.t,
            rule=lambda b, tau: b.Pw[tau] >= config.chamber_water_pressure,
        )

        def interface_ode_rule(block: Any, tau: float):
            if tau == block.t.first():
                return pyo.Constraint.Skip
            return block.dS_dtau[tau] == block.duration_s * block.dSdt[tau]

        phase.interface_ode = pyo.Constraint(phase.t, rule=interface_ode_rule)

        def temperature_rhs(block: Any, z_index: int, tau: float):
            thickness = derived.product_height - block.S[tau]
            volume = derived.cross_section_area * thickness
            side_loss = (
                derived.side_transfer_factor
                * config.stefan_boltzmann
                * derived.side_area
                * (block.T[z_index, tau] ** 4 - config.wall_temperature**4)
                / (volume * derived.frozen_density * derived.frozen_heat_capacity)
            )
            source = config.microwave_heat_input / (
                volume * derived.frozen_density * derived.frozen_heat_capacity
            )

            if z_index == 0:
                top_radiation = (
                    derived.top_transfer_factor
                    * config.stefan_boltzmann
                    * (block.T[z_index, tau] ** 4 - config.top_surface_temperature**4)
                )
                diffusion = (
                    derived.frozen_diffusivity
                    / thickness**2
                    / derived.dpsi**2
                    * (
                        2.0 * block.T[1, tau]
                        - 2.0 * block.T[0, tau]
                        - 2.0
                        * block.Nw[tau]
                        * derived.dpsi
                        * config.heat_of_sublimation
                        * thickness
                        / derived.frozen_conductivity
                        - top_radiation
                        * 2.0
                        * derived.dpsi
                        * thickness
                        / derived.frozen_conductivity
                    )
                )
                convection_gradient = (
                    thickness
                    * block.Nw[tau]
                    * config.heat_of_sublimation
                    / derived.frozen_conductivity
                    + top_radiation * thickness / derived.frozen_conductivity
                )
                convection = (
                    -((derived.psi[z_index] - 1.0) * block.dSdt[tau] / thickness)
                    * convection_gradient
                )
                return diffusion + convection - side_loss + source

            if z_index == discretization.n_z - 1:
                diffusion = (
                    derived.frozen_diffusivity
                    / thickness**2
                    / derived.dpsi**2
                    * (
                        2.0 * block.T[z_index - 1, tau]
                        - 2.0 * block.T[z_index, tau]
                        + 2.0
                        * (block.S[tau] - derived.product_height)
                        * config.bottom_heat_transfer_coefficient
                        * derived.dpsi
                        * (block.T[z_index, tau] - block.Tb[tau])
                        / derived.frozen_conductivity
                    )
                )
                convection_gradient = (
                    (block.S[tau] - derived.product_height)
                    * config.bottom_heat_transfer_coefficient
                    * (block.T[z_index, tau] - block.Tb[tau])
                    / derived.frozen_conductivity
                )
                convection = (
                    -((derived.psi[z_index] - 1.0) * block.dSdt[tau] / thickness)
                    * convection_gradient
                )
                return diffusion + convection - side_loss + source

            diffusion = (
                derived.frozen_diffusivity
                / thickness**2
                / derived.dpsi**2
                * (
                    block.T[z_index - 1, tau]
                    - 2.0 * block.T[z_index, tau]
                    + block.T[z_index + 1, tau]
                )
            )
            convection = (
                -((derived.psi[z_index] - 1.0) * block.dSdt[tau] / thickness)
                * (block.T[z_index + 1, tau] - block.T[z_index - 1, tau])
                / (2.0 * derived.dpsi)
            )
            return diffusion + convection - side_loss + source

        def temperature_ode_rule(block: Any, z_index: int, tau: float):
            if tau == block.t.first():
                return pyo.Constraint.Skip
            return block.dT_dtau[z_index, tau] == (
                block.duration_s * temperature_rhs(block, z_index, tau)
            )

        phase.temperature_ode = pyo.Constraint(
            model.z,
            phase.t,
            rule=temperature_ode_rule,
        )
        bottom_node = discretization.n_z - 1
        phase.product_temperature_limit = pyo.Constraint(
            phase.t,
            rule=lambda b, tau: b.T[bottom_node, tau] <= settings.temperature_limit,
        )
        if settings.interface_velocity_limit is not None:

            def velocity_limit_rule(
                block: Any,
                tau: float,
                *,
                p: int = phase_index,
            ):
                if p == 1 and tau == block.t.first():
                    return pyo.Constraint.Skip
                return 1.0e7 * block.dSdt[tau] <= (
                    1.0e7 * settings.interface_velocity_limit
                )

            phase.interface_velocity_limit = pyo.Constraint(
                phase.t,
                rule=velocity_limit_rule,
            )

        pyo.TransformationFactory("dae.collocation").apply_to(
            phase,
            wrt=phase.t,
            nfe=discretization.nfe_per_phase,
            ncp=discretization.ncp,
            scheme=discretization.scheme,
        )

    first_phase = model.phase[1]
    last_phase = model.phase[n_phases]
    model.initial_interface = pyo.Constraint(
        expr=first_phase.S[first_phase.t.first()] == config.initial_interface_position
    )
    model.initial_temperature = pyo.Constraint(
        model.z,
        rule=lambda m, z_index: first_phase.T[z_index, first_phase.t.first()]
        == config.initial_temperature,
    )
    model.transitions = pyo.RangeSet(1, n_phases - 1)
    model.interface_continuity = pyo.Constraint(
        model.transitions,
        rule=lambda m, p: m.phase[p].S[m.phase[p].t.last()]
        == m.phase[p + 1].S[m.phase[p + 1].t.first()],
    )
    model.temperature_continuity = pyo.Constraint(
        model.transitions,
        model.z,
        rule=lambda m, p, z_index: m.phase[p].T[z_index, m.phase[p].t.last()]
        == m.phase[p + 1].T[z_index, m.phase[p + 1].t.first()],
    )
    model.terminal_drying = pyo.Constraint(
        expr=last_phase.S[last_phase.t.last()] >= terminal_s
    )
    model.total_time_lower_bound = pyo.Constraint(
        expr=sum(model.phase[p].duration_s for p in model.phases)
        >= config.time_bounds[0]
    )
    model.total_time_upper_bound = pyo.Constraint(
        expr=sum(model.phase[p].duration_s for p in model.phases)
        <= config.time_bounds[1]
    )

    model.policy = Disjunct(model.phases, model.policy_names)
    for phase_index in model.phases:
        phase = model.phase[phase_index]
        phase_start = phase.t.first()
        skip_initial_policy_point = phase_index == 1
        for policy_name in model.policy_names:
            disjunct = model.policy[phase_index, policy_name]
            if policy_name == POLICY_MAX_HEAT:
                disjunct.policy_equality = pyo.Constraint(
                    phase.t,
                    rule=lambda _d, tau, b=phase: (
                        pyo.Constraint.Skip
                        if skip_initial_policy_point and tau == phase_start
                        else b.Tb[tau] == settings.shelf_temperature_max
                    ),
                )
            elif policy_name == POLICY_TEMPERATURE:
                disjunct.policy_equality = pyo.Constraint(
                    phase.t,
                    rule=lambda _d, tau, b=phase: (
                        pyo.Constraint.Skip
                        if skip_initial_policy_point and tau == phase_start
                        else b.T[discretization.n_z - 1, tau]
                        == settings.temperature_limit
                    ),
                )
            elif policy_name == POLICY_VELOCITY:
                assert settings.interface_velocity_limit is not None
                disjunct.policy_equality = pyo.Constraint(
                    phase.t,
                    rule=lambda _d, tau, b=phase: (
                        pyo.Constraint.Skip
                        if skip_initial_policy_point and tau == phase_start
                        else 1.0e7 * b.dSdt[tau]
                        == 1.0e7 * settings.interface_velocity_limit
                    ),
                )

    model.policy_choice = Disjunction(
        model.phases,
        rule=lambda m, p: [m.policy[p, name] for name in m.policy_names],
    )
    model.no_immediate_repeat = pyo.Constraint(
        model.transitions,
        model.policy_names,
        rule=lambda m, p, name: m.policy[p, name].binary_indicator_var
        + m.policy[p + 1, name].binary_indicator_var
        <= 1,
    )
    model.objective = pyo.Objective(
        expr=sum(model.phase[p].duration_s for p in model.phases),
        sense=pyo.minimize,
    )
    return model


def indicator_policy_sequence(model: Any) -> tuple[str, ...]:
    """Return the selected policy sequence directly from GDP indicators."""
    import pyomo.environ as pyo  # type: ignore[import-untyped]

    sequence: list[str] = []
    for phase_index in model.phases:
        selected = [
            str(policy_name)
            for policy_name in model.policy_names
            if pyo.value(model.policy[phase_index, policy_name].indicator_var)
        ]
        if len(selected) != 1:
            raise ValueError(
                f"phase {phase_index} has {len(selected)} selected policies"
            )
        sequence.append(selected[0])
    return tuple(sequence)


def _solver_missing_message(solver_name: str) -> str:
    if solver_name == "ipopt":
        return (
            "IPOPT is required for GDP nonlinear subproblems. Install it with "
            "`idaes get-extensions --extra petsc` or "
            "`conda install -c conda-forge ipopt`."
        )
    return (
        f"The GDP discrete solver {solver_name!r} is not available. Install "
        "GLPK with `sudo apt-get install glpk-utils` or "
        "`conda install -c conda-forge glpk`."
    )


def solve_paper_gdp_model(
    model: Any,
    *,
    gdp_solver: str = "gdpopt.ric",
    mip_solver: str = "glpk",
    nlp_solver: str = "ipopt",
    init_algorithm: str = "set_covering",
    discrete_problem_transformation: str = "gdp.bigm",
    nlp_solver_options: Mapping[str, Any] | None = None,
    time_limit_s: float | None = 600.0,
    tee: bool = False,
) -> dict[str, Any]:
    """Solve a paper GDP model and return an indicator-derived trajectory.

    GDPopt RIC uses local IPOPT subproblem solves by default.  Therefore an
    ``optimal`` termination is a locally solved nonconvex GDP result, not a
    global certificate.
    """
    import pyomo.environ as pyo  # type: ignore[import-untyped]

    for solver_name in (mip_solver, nlp_solver):
        if not pyo.SolverFactory(solver_name).available(exception_flag=False):
            raise RuntimeError(_solver_missing_message(solver_name))
    solver = pyo.SolverFactory(gdp_solver)
    if not solver.available(exception_flag=False):
        raise RuntimeError(f"Pyomo GDP solver {gdp_solver!r} is not available")
    options = {
        "max_iter": 3000,
        "tol": 1.0e-5,
        "acceptable_tol": 1.0e-3,
        "print_level": 0,
    }
    if nlp_solver_options:
        options.update(nlp_solver_options)
    results = solver.solve(
        model,
        mip_solver=mip_solver,
        nlp_solver=nlp_solver,
        init_algorithm=init_algorithm,
        discrete_problem_transformation=discrete_problem_transformation,
        nlp_solver_args={"options": options},
        time_limit=time_limit_s,
        tee=tee,
    )
    return extract_paper_gdp_solution(
        model,
        results,
        solver_configuration={
            "gdp_solver": gdp_solver,
            "mip_solver": mip_solver,
            "nlp_solver": nlp_solver,
            "init_algorithm": init_algorithm,
            "discrete_problem_transformation": discrete_problem_transformation,
            "indicator_initialization": "unset",
            "phase_duration_weights": model._paper_duration_weights,
            "continuous_initialization": "neutral_linear_profile",
            "nlp_solver_options": options,
        },
    )


def solve_paper_problem1_gdp(**kwargs: Any) -> dict[str, Any]:
    """Build and solve the GDP validation model for Paper Problem 1."""
    builder_keys = {"config", "discretization", "phase_duration_weights"}
    builder_args = {
        key: kwargs.pop(key) for key in tuple(kwargs) if key in builder_keys
    }
    model = create_paper_problem1_gdp_model(**builder_args)
    return solve_paper_gdp_model(model, **kwargs)


def solve_paper_problem2_gdp(**kwargs: Any) -> dict[str, Any]:
    """Build and solve the GDP validation model for Paper Problem 2."""
    builder_keys = {"config", "discretization", "phase_duration_weights"}
    builder_args = {
        key: kwargs.pop(key) for key in tuple(kwargs) if key in builder_keys
    }
    model = create_paper_problem2_gdp_model(**builder_args)
    return solve_paper_gdp_model(model, **kwargs)


def extract_paper_gdp_solution(
    model: Any,
    results: Any | None = None,
    *,
    solver_configuration: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Extract one global trajectory and indicator-derived policy schedule."""
    import pyomo.environ as pyo  # type: ignore[import-untyped]

    config = model._paper_config
    derived = model._paper_derived
    settings = model._paper_problem_settings
    discretization = model._paper_gdp_discretization
    sequence = indicator_policy_sequence(model)

    global_time_s: list[float] = []
    interface_position_m: list[float] = []
    shelf_temperature_K: list[float] = []
    interface_velocity_m_per_s: list[float] = []
    temperature_rows: list[list[float]] = []
    phase_rows: list[dict[str, Any]] = []
    switch_intervals_hr: list[tuple[float, float]] = []
    elapsed_s = 0.0

    for phase_index in model.phases:
        phase = model.phase[phase_index]
        duration_s = float(pyo.value(phase.duration_s))
        local_points = sorted(float(tau) for tau in phase.t)
        phase_start_s = elapsed_s
        phase_end_s = phase_start_s + duration_s
        phase_rows.append(
            {
                "phase": int(phase_index),
                "policy": sequence[phase_index - 1],
                "duration_s": duration_s,
                "start_time_hr": phase_start_s / 3600.0,
                "end_time_hr": phase_end_s / 3600.0,
            }
        )
        if phase_index > 1:
            previous = model.phase[phase_index - 1]
            previous_interior = sorted(float(tau) for tau in previous.t)[-2]
            next_interior = local_points[1]
            switch_intervals_hr.append(
                (
                    (
                        phase_start_s
                        - float(pyo.value(previous.duration_s))
                        * (1.0 - previous_interior)
                    )
                    / 3600.0,
                    (phase_start_s + duration_s * next_interior) / 3600.0,
                )
            )
        for point_index, tau in enumerate(local_points):
            if phase_index > 1 and point_index == 0:
                continue
            global_time_s.append(phase_start_s + duration_s * tau)
            interface_position_m.append(float(pyo.value(phase.S[tau])))
            shelf_temperature_K.append(float(pyo.value(phase.Tb[tau])))
            interface_velocity_m_per_s.append(float(pyo.value(phase.dSdt[tau])))
            temperature_rows.append(
                [float(pyo.value(phase.T[z_index, tau])) for z_index in model.z]
            )
        elapsed_s = phase_end_s

    temperature_K = np.asarray(temperature_rows, dtype=float)
    velocity = np.asarray(interface_velocity_m_per_s, dtype=float)
    terminal_gap_m = (
        discretization.terminal_drying_fraction * derived.product_height
        - interface_position_m[-1]
    )
    residual_s = (derived.product_height - interface_position_m[-1]) / velocity[-1]
    termination = None
    status = None
    if results is not None:
        termination = str(results.solver.termination_condition)
        status = str(results.solver.status)

    solution = {
        "metadata": {
            "status": status,
            "termination_condition": termination,
            "formulation": "multiphase_pyomo_gdp",
            "global_optimality_certified": False,
            "solver_configuration": dict(solver_configuration or {}),
        },
        "problem": {
            "key": model._paper_problem,
            "temperature_limit_K": settings.temperature_limit,
            "interface_velocity_limit_m_per_s": settings.interface_velocity_limit,
            "shelf_temperature_min_K": settings.shelf_temperature_min,
            "shelf_temperature_max_K": settings.shelf_temperature_max,
            "terminal_drying_fraction": discretization.terminal_drying_fraction,
            "time_bounds_s": config.time_bounds,
            "minimum_phase_duration_s": discretization.minimum_phase_duration_s,
        },
        "states": {
            "time_s": np.asarray(global_time_s, dtype=float),
            "time_hr": np.asarray(global_time_s, dtype=float) / 3600.0,
            "temperature_K": temperature_K,
            "max_temperature_K": np.max(temperature_K, axis=1),
            "interface_position_m": np.asarray(interface_position_m, dtype=float),
            "interface_velocity_m_per_s": velocity,
        },
        "controls": {
            "shelf_temperature_K": np.asarray(shelf_temperature_K, dtype=float),
        },
        "policies": {
            "indicator_sequence": sequence,
            "phases": phase_rows,
            "switch_times_hr": [row["end_time_hr"] for row in phase_rows[:-1]],
            "switch_intervals_hr": switch_intervals_hr,
        },
        "metrics": {
            "solver_endpoint_time_hr": elapsed_s / 3600.0,
            "complete_drying_time_hr": (elapsed_s + residual_s) / 3600.0,
            "terminal_gap_m": terminal_gap_m,
            "max_temperature_violation_K": max(
                0.0, float(np.max(temperature_K) - settings.temperature_limit)
            ),
            "max_interface_velocity_violation_m_per_s": (
                0.0
                if settings.interface_velocity_limit is None
                else max(
                    0.0, float(np.max(velocity[1:]) - settings.interface_velocity_limit)
                )
            ),
        },
    }
    solution["policies"]["continuous_classifier"] = classify_paper_policies(solution)
    return solution


def paper_gdp_comparison_rows(
    gdp_result: Mapping[str, Any],
    continuous_result: Mapping[str, Any],
    published_reference: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Return a compact paper/continuous-NLP/GDP comparison table."""
    terminal_fraction = float(gdp_result["problem"]["terminal_drying_fraction"])
    continuous_height_m = float(continuous_result["derived"]["product_height"])
    continuous_terminal_m = float(
        continuous_result["metrics"]["terminal_interface_position_m"]
    )
    continuous_velocity_m_per_s = float(
        np.asarray(continuous_result["states"]["interface_velocity_m_per_s"])[-1]
    )
    continuous_complete_hr = float(continuous_result["metrics"]["drying_time_hr"])
    continuous_complete_hr += (
        (continuous_height_m - continuous_terminal_m)
        / continuous_velocity_m_per_s
        / 3600.0
    )
    return [
        {
            "quantity": f"drying time to S={terminal_fraction:g}H [hr]",
            "paper": float("nan"),
            "continuous_nlp": float(continuous_result["metrics"]["drying_time_hr"]),
            "gdp": float(gdp_result["metrics"]["solver_endpoint_time_hr"]),
        },
        {
            "quantity": "drying time to S=H [hr]",
            "paper": float(published_reference["drying_time_hr"]),
            "continuous_nlp": continuous_complete_hr,
            "gdp": float(gdp_result["metrics"]["complete_drying_time_hr"]),
        },
        {
            "quantity": "policy sequence",
            "paper": tuple(published_reference["policy_sequence"]),
            "continuous_nlp": tuple(
                segment["label"]
                for segment in continuous_result["policies"]["segments"]
            ),
            "gdp": tuple(gdp_result["policies"]["indicator_sequence"]),
        },
        {
            "quantity": "switch times [hr]",
            "paper": tuple(published_reference["switch_times_hr"]),
            "continuous_nlp": tuple(continuous_result["policies"]["switch_times_hr"]),
            "gdp": tuple(gdp_result["policies"]["switch_times_hr"]),
        },
    ]
