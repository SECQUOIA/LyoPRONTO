# Copyright (C) 2026, SECQUOIA

"""Paper-reference optimal-control benchmarks for lyophilization.

This module is intentionally separate from the production LyoPRONTO primary
drying models.  It translates the primary-drying benchmark from Srisuma and
Braatz, arXiv:2509.10826v1, into a Pyomo direct-transcription problem so we can
validate the Pyomo.DAE + orthogonal collocation + IPOPT stack on a published
lyophilization OCP.

The equations and defaults in this file use the paper/upstream SI convention:
temperatures in K, pressure in Pa, length in m, and time in s.  Do not mix these
helpers with the existing LyoPRONTO cm/Torr/degC/cal APIs without an explicit
adapter.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

import numpy as np


@dataclass(frozen=True)
class PaperPrimaryDryingConfig:
    """Default primary-drying parameters from the paper's upstream code.

    The defaults are translated from:
    - ``Code (Conference Version)/Input Data/get_inputdata.m``
    - ``Code (Conference Version)/Input Data/input_processing.m``

    The first milestone targets Paper Problem 1:
    minimize drying time subject to ``T(z,t) <= 243 K`` and
    ``228 K <= Tb(t) <= 273 K``.
    """

    # Material properties.
    solute_mass_fraction: float = 0.05
    solute_density: float = 1587.9
    water_density: float = 1000.0
    ice_density: float = 917.0
    dried_region_density: float = 215.0
    solute_heat_capacity: float = 1240.0
    ice_heat_capacity: float = 2108.0
    solute_conductivity: float = 0.126
    ice_conductivity: float = 2.25
    heat_of_sublimation: float = 2.84e6

    # Geometry and radiation.
    frozen_volume: float = 3.0e-6
    vial_diameter: float = 0.024
    glass_emissivity: float = 0.8
    steel_emissivity: float = 0.3
    stefan_boltzmann: float = 5.67e-8
    side_transfer_factor_multiplier: float = 0.78
    top_transfer_factor_multiplier: float = 1.0

    # Primary drying conditions.
    bottom_heat_transfer_coefficient: float = 25.0
    initial_temperature: float = 228.0
    wall_temperature: float = 240.0
    top_surface_temperature: float = 240.0
    initial_interface_position: float = 0.0
    chamber_water_pressure: float = 3.0
    resistance_0: float = 1.5e4
    resistance_1: float = 3.0e7
    resistance_2: float = 1.0e1
    vapor_pressure_a: float = -6139.9
    vapor_pressure_b: float = 28.8912
    microwave_heat_input: float = 0.0

    # Paper Problem 1 OCP settings.
    shelf_temperature_min: float = 228.0
    shelf_temperature_max: float = 273.0
    problem1_temperature_limit: float = 243.0
    problem1_time_guess: float = 7.0 * 3600.0
    time_bounds: tuple[float, float] = (0.25 * 3600.0, 15.0 * 3600.0)

    # Paper Problem 2 OCP settings.
    problem2_temperature_limit: float = 240.0
    problem2_interface_velocity_limit: float = 2.8e-7
    problem2_shelf_temperature_max: float = 260.0
    problem2_time_guess: float = 8.9 * 3600.0
    problem2_policy3_switch_time_guess: float = 2.0 * 3600.0
    problem2_policy1_switch_time_guess: float = 3.9 * 3600.0


@dataclass(frozen=True)
class PaperProblemSettings:
    """Problem-specific path limits for paper-reference OCPs."""

    key: str
    name: str
    temperature_limit: float
    shelf_temperature_min: float
    shelf_temperature_max: float
    time_guess: float
    interface_velocity_limit: float | None = None


@dataclass(frozen=True)
class PaperDiscretization:
    """Discretization controls for the paper-reference Pyomo model."""

    n_z: int = 5
    nfe: int = 12
    ncp: int = 3
    terminal_drying_fraction: float = 0.995
    temperature_lower_bound: float = 220.0
    temperature_upper_bound: float = 280.0
    scheme: str = "LAGRANGE-RADAU"


@dataclass(frozen=True)
class PaperDerivedParameters:
    """Derived parameters used by the paper-reference primary drying model."""

    solution_density: float
    frozen_density: float
    frozen_heat_capacity: float
    frozen_conductivity: float
    frozen_diffusivity: float
    initial_mass: float
    frozen_volume: float
    cross_section_area: float
    product_height: float
    side_area: float
    side_transfer_factor: float
    top_transfer_factor: float
    dpsi: float
    psi: tuple[float, ...]


def derive_primary_drying_parameters(
    config: PaperPrimaryDryingConfig,
    n_z: int,
) -> PaperDerivedParameters:
    """Return the upstream-derived primary-drying parameters.

    This mirrors the relevant pieces of upstream ``input_processing.m``.
    """
    if n_z < 3:
        raise ValueError("n_z must be at least 3 for the MOL stencil")

    xs = config.solute_mass_fraction
    solution_density = 1.0 / (
        xs / config.solute_density + (1.0 - xs) / config.water_density
    )
    frozen_density = 1.0 / (
        xs / config.solute_density + (1.0 - xs) / config.ice_density
    )
    frozen_heat_capacity = (
        xs * config.solute_heat_capacity + (1.0 - xs) * config.ice_heat_capacity
    )
    frozen_conductivity = (
        xs * config.solute_conductivity + (1.0 - xs) * config.ice_conductivity
    )
    frozen_diffusivity = frozen_conductivity / (frozen_density * frozen_heat_capacity)
    initial_mass = config.frozen_volume * solution_density
    frozen_volume = initial_mass / frozen_density
    cross_section_area = np.pi * config.vial_diameter**2 / 4.0
    product_height = frozen_volume / cross_section_area
    side_area = np.pi * config.vial_diameter * product_height
    side_transfer_factor = (
        config.side_transfer_factor_multiplier * config.glass_emissivity
    )
    top_transfer_factor = (
        config.top_transfer_factor_multiplier * config.glass_emissivity
    )
    dpsi = 1.0 / (n_z - 1)
    psi = tuple(float(i * dpsi) for i in range(n_z))

    return PaperDerivedParameters(
        solution_density=solution_density,
        frozen_density=frozen_density,
        frozen_heat_capacity=frozen_heat_capacity,
        frozen_conductivity=frozen_conductivity,
        frozen_diffusivity=frozen_diffusivity,
        initial_mass=initial_mass,
        frozen_volume=frozen_volume,
        cross_section_area=cross_section_area,
        product_height=product_height,
        side_area=side_area,
        side_transfer_factor=side_transfer_factor,
        top_transfer_factor=top_transfer_factor,
        dpsi=dpsi,
        psi=psi,
    )


def saturation_pressure(
    temperature: np.ndarray | float,
    config: PaperPrimaryDryingConfig = PaperPrimaryDryingConfig(),
) -> np.ndarray | float:
    """Return water saturation pressure [Pa] from temperature [K]."""
    return np.exp(config.vapor_pressure_a / temperature + config.vapor_pressure_b)


def product_resistance(
    interface_position: np.ndarray | float,
    config: PaperPrimaryDryingConfig = PaperPrimaryDryingConfig(),
) -> np.ndarray | float:
    """Return cake resistance [m/s] at interface position ``S`` [m]."""
    return config.resistance_0 + config.resistance_1 * interface_position / (
        1.0 + config.resistance_2 * interface_position
    )


def sublimation_flux(
    interface_temperature: np.ndarray | float,
    interface_position: np.ndarray | float,
    config: PaperPrimaryDryingConfig = PaperPrimaryDryingConfig(),
) -> np.ndarray | float:
    """Return sublimation flux [kg/(m^2 s)].

    This helper mirrors the smooth signed equation used in the
    direct-transcription model. The Pyomo model adds a separate constraint that
    keeps the sublimation driving force nonnegative.
    """
    pressure = saturation_pressure(interface_temperature, config)
    resistance = product_resistance(interface_position, config)
    return (pressure - config.chamber_water_pressure) / resistance


def interface_velocity(
    interface_temperature: np.ndarray | float,
    interface_position: np.ndarray | float,
    config: PaperPrimaryDryingConfig = PaperPrimaryDryingConfig(),
    derived: PaperDerivedParameters | None = None,
) -> np.ndarray | float:
    """Return interface velocity ``dS/dt`` [m/s]."""
    if derived is None:
        derived = derive_primary_drying_parameters(config, n_z=20)
    flux = sublimation_flux(interface_temperature, interface_position, config)
    return flux / (derived.frozen_density - config.dried_region_density)


def temperature_for_saturation_pressure(
    pressure: np.ndarray | float,
    config: PaperPrimaryDryingConfig = PaperPrimaryDryingConfig(),
) -> np.ndarray | float:
    """Return temperature [K] for the paper saturation-pressure equation."""
    return config.vapor_pressure_a / (np.log(pressure) - config.vapor_pressure_b)


def _paper_problem_settings(
    config: PaperPrimaryDryingConfig,
    problem: str,
) -> PaperProblemSettings:
    if problem == "problem1":
        return PaperProblemSettings(
            key=problem,
            name="paper_problem_1",
            temperature_limit=config.problem1_temperature_limit,
            shelf_temperature_min=config.shelf_temperature_min,
            shelf_temperature_max=config.shelf_temperature_max,
            time_guess=config.problem1_time_guess,
        )
    if problem == "problem2":
        return PaperProblemSettings(
            key=problem,
            name="paper_problem_2",
            temperature_limit=config.problem2_temperature_limit,
            shelf_temperature_min=config.shelf_temperature_min,
            shelf_temperature_max=config.problem2_shelf_temperature_max,
            time_guess=config.problem2_time_guess,
            interface_velocity_limit=config.problem2_interface_velocity_limit,
        )
    raise ValueError(f"unsupported paper OCP problem: {problem}")


def generate_problem1_policy_initialization(
    config: PaperPrimaryDryingConfig | None = None,
    discretization: PaperDiscretization | None = None,
    n_time_points: int = 240,
    rtol: float = 1.0e-7,
    atol: float = 1.0e-9,
) -> dict[str, Any]:
    """Generate an upstream-style policy trajectory for Problem 1 warm starts.

    This mirrors the paper implementation's control logic for Problem 1 without
    depending on MATLAB or GEKKO: integrate Policy 1 with maximum shelf
    temperature until the bottom product temperature reaches the limit, then use
    the Policy 2 algebraic condition to keep the bottom temperature at the limit.
    """
    from scipy.integrate import solve_ivp

    config = config or PaperPrimaryDryingConfig()
    discretization = discretization or PaperDiscretization()
    derived = derive_primary_drying_parameters(config, discretization.n_z)
    n_z = discretization.n_z
    target_s = discretization.terminal_drying_fraction * derived.product_height
    y0 = np.concatenate(
        (
            np.full(n_z, config.initial_temperature, dtype=float),
            np.array([config.initial_interface_position], dtype=float),
        )
    )

    def policy1_rhs(_time, y):
        temperature = y[:n_z]
        interface_position = float(y[-1])
        dtemperature_dt, dinterface_dt = _numeric_temperature_rhs(
            temperature,
            interface_position,
            config.shelf_temperature_max,
            config,
            derived,
        )
        return np.concatenate((dtemperature_dt, [dinterface_dt]))

    def temperature_event(_time, y):
        return y[n_z - 1] - config.problem1_temperature_limit

    temperature_event.terminal = True
    temperature_event.direction = 1

    def finish_event(_time, y):
        return y[-1] - target_s

    finish_event.terminal = True
    finish_event.direction = 1

    sol1 = solve_ivp(
        policy1_rhs,
        (0.0, config.time_bounds[1]),
        y0,
        method="BDF",
        dense_output=True,
        events=(temperature_event, finish_event),
        rtol=rtol,
        atol=atol,
        max_step=100.0,
    )
    if not sol1.success:
        raise RuntimeError(f"Policy 1 initialization failed: {sol1.message}")

    switch_time = (
        float(sol1.t_events[0][0]) if len(sol1.t_events[0]) else float(sol1.t[-1])
    )
    finished_in_policy1 = bool(len(sol1.t_events[1]))

    sol2 = None
    final_time = float(sol1.t_events[1][0]) if finished_in_policy1 else None
    if not finished_in_policy1:
        switch_state = sol1.sol(switch_time)
        y2_0 = np.concatenate(
            (
                switch_state[: n_z - 1],
                np.array([float(switch_state[-1])], dtype=float),
            )
        )

        def policy2_rhs(_time, y):
            temperature = np.empty(n_z, dtype=float)
            temperature[: n_z - 1] = y[: n_z - 1]
            temperature[n_z - 1] = config.problem1_temperature_limit
            interface_position = float(y[-1])
            shelf_temperature = _policy2_shelf_temperature(
                temperature,
                interface_position,
                config,
                derived,
            )
            shelf_temperature = float(
                np.clip(
                    shelf_temperature,
                    config.shelf_temperature_min,
                    config.shelf_temperature_max,
                )
            )
            dtemperature_dt, dinterface_dt = _numeric_temperature_rhs(
                temperature,
                interface_position,
                shelf_temperature,
                config,
                derived,
            )
            return np.concatenate((dtemperature_dt[: n_z - 1], [dinterface_dt]))

        def finish_event_policy2(_time, y):
            return y[-1] - target_s

        finish_event_policy2.terminal = True
        finish_event_policy2.direction = 1

        sol2 = solve_ivp(
            policy2_rhs,
            (switch_time, config.time_bounds[1]),
            y2_0,
            method="BDF",
            dense_output=True,
            events=finish_event_policy2,
            rtol=rtol,
            atol=atol,
            max_step=100.0,
        )
        if not sol2.success:
            raise RuntimeError(f"Policy 2 initialization failed: {sol2.message}")
        final_time = (
            float(sol2.t_events[0][0]) if len(sol2.t_events[0]) else float(sol2.t[-1])
        )

    time_s = _policy_sample_times(
        switch_time, final_time, n_time_points, sol2 is not None
    )
    temperature_values = np.zeros((len(time_s), n_z), dtype=float)
    interface_values = np.zeros(len(time_s), dtype=float)
    shelf_values = np.zeros(len(time_s), dtype=float)
    interface_velocity_values = np.zeros(len(time_s), dtype=float)
    flux_values = np.zeros(len(time_s), dtype=float)
    labels: list[str] = []

    for index, time in enumerate(time_s):
        if sol2 is None or time <= switch_time:
            state = sol1.sol(time)
            temperature = np.asarray(state[:n_z], dtype=float)
            interface_position = float(state[-1])
            shelf_temperature = config.shelf_temperature_max
            label = "policy_1_max_heat_input"
        else:
            state = sol2.sol(time)
            temperature = np.empty(n_z, dtype=float)
            temperature[: n_z - 1] = np.asarray(state[: n_z - 1], dtype=float)
            temperature[n_z - 1] = config.problem1_temperature_limit
            interface_position = float(state[-1])
            shelf_temperature = _policy2_shelf_temperature(
                temperature,
                interface_position,
                config,
                derived,
            )
            shelf_temperature = float(
                np.clip(
                    shelf_temperature,
                    config.shelf_temperature_min,
                    config.shelf_temperature_max,
                )
            )
            label = "policy_2_temperature_tracking"

        _, dinterface_dt = _numeric_temperature_rhs(
            temperature,
            interface_position,
            shelf_temperature,
            config,
            derived,
        )
        flux = float(sublimation_flux(temperature[0], interface_position, config))

        temperature_values[index, :] = temperature
        interface_values[index] = interface_position
        shelf_values[index] = shelf_temperature
        interface_velocity_values[index] = dinterface_dt
        flux_values[index] = flux
        labels.append(label)

    return {
        "states": {
            "time_s": time_s,
            "time_hr": time_s / 3600.0,
            "temperature_K": temperature_values,
            "max_temperature_K": temperature_values.max(axis=1),
            "interface_position_m": interface_values,
            "interface_velocity_m_per_s": interface_velocity_values,
            "sublimation_flux_kg_m2_s": flux_values,
        },
        "controls": {
            "shelf_temperature_K": shelf_values,
        },
        "policies": {
            "labels": labels,
            "segments": _compress_policy_labels(time_s / 3600.0, labels),
            "switch_times_hr": [switch_time / 3600.0] if sol2 is not None else [],
        },
        "metrics": {
            "drying_time_s": final_time,
            "drying_time_hr": final_time / 3600.0,
            "policy1_switch_time_s": switch_time,
            "policy1_switch_time_hr": switch_time / 3600.0,
            "terminal_drying_fraction": float(
                interface_values[-1] / derived.product_height
            ),
        },
        "metadata": {
            "source": "problem1_policy_initialization",
            "n_z": n_z,
            "rtol": rtol,
            "atol": atol,
        },
        "problem": {
            "name": "paper_problem_1_policy_initialization",
            "temperature_limit_K": config.problem1_temperature_limit,
            "shelf_temperature_min_K": config.shelf_temperature_min,
            "shelf_temperature_max_K": config.shelf_temperature_max,
            "terminal_drying_fraction_target": discretization.terminal_drying_fraction,
        },
    }


def generate_problem2_policy_initialization(
    config: PaperPrimaryDryingConfig | None = None,
    discretization: PaperDiscretization | None = None,
    n_time_points: int = 260,
    rtol: float = 1.0e-8,
    atol: float = 1.0e-10,
) -> dict[str, Any]:
    """Generate a policy-sequenced warm start for Paper Problem 2.

    The paper reports Policy 3 -> Policy 1 -> Policy 2 switching at about
    2.0 h and 3.9 h, then terminal drying near 8.9 h.  This initializer uses
    those switch-time landmarks and the model's algebraic flux equations to
    build a deterministic, feasible-scale seed for direct transcription.
    """
    from scipy.integrate import solve_ivp
    from scipy.optimize import brentq

    config = config or PaperPrimaryDryingConfig()
    discretization = discretization or PaperDiscretization()
    settings = _paper_problem_settings(config, "problem2")
    derived = derive_primary_drying_parameters(config, discretization.n_z)
    n_z = discretization.n_z
    velocity_limit = float(settings.interface_velocity_limit)
    target_s = discretization.terminal_drying_fraction * derived.product_height
    switch_31 = float(config.problem2_policy3_switch_time_guess)
    switch_12 = float(config.problem2_policy1_switch_time_guess)

    if not 0.0 < switch_31 < switch_12 < config.time_bounds[1]:
        raise ValueError("Problem 2 switch-time guesses must be ordered")

    policy3_switch_s = min(velocity_limit * switch_31, 0.9 * target_s)

    def velocity_at_temperature(interface_position: float) -> float:
        return _interface_velocity_at_temperature(
            settings.temperature_limit,
            interface_position,
            config,
            derived,
        )

    try:
        policy2_switch_s = brentq(
            lambda s: velocity_at_temperature(s) - velocity_limit,
            policy3_switch_s,
            target_s,
        )
    except ValueError:
        policy2_switch_s = min(
            policy3_switch_s + velocity_limit * 0.8 * (switch_12 - switch_31),
            0.8 * target_s,
        )

    policy1_velocity = (policy2_switch_s - policy3_switch_s) / (switch_12 - switch_31)
    policy1_velocity = max(min(policy1_velocity, 0.98 * velocity_limit), 1.0e-12)

    def policy2_rhs(_time, y):
        return [velocity_at_temperature(float(y[0]))]

    def finish_event(_time, y):
        return float(y[0]) - target_s

    finish_event.terminal = True
    finish_event.direction = 1

    sol2 = solve_ivp(
        policy2_rhs,
        (switch_12, config.time_bounds[1]),
        [policy2_switch_s],
        method="BDF",
        dense_output=True,
        events=finish_event,
        rtol=rtol,
        atol=atol,
        max_step=100.0,
    )
    if not sol2.success:
        raise RuntimeError(f"Problem 2 Policy 2 initialization failed: {sol2.message}")
    final_time = (
        float(sol2.t_events[0][0]) if len(sol2.t_events[0]) else float(sol2.t[-1])
    )

    time_s = _policy_sample_times_multiple(
        (switch_31, switch_12),
        final_time,
        n_time_points,
    )
    temperature_values = np.zeros((len(time_s), n_z), dtype=float)
    interface_values = np.zeros(len(time_s), dtype=float)
    shelf_values = np.zeros(len(time_s), dtype=float)
    interface_velocity_values = np.zeros(len(time_s), dtype=float)
    flux_values = np.zeros(len(time_s), dtype=float)
    labels: list[str] = []

    for index, time in enumerate(time_s):
        if np.isclose(time, 0.0):
            interface_position = config.initial_interface_position
            velocity = float(
                interface_velocity(
                    config.initial_temperature,
                    interface_position,
                    config,
                    derived,
                )
            )
            top_temperature = config.initial_temperature
            bottom_temperature = config.initial_temperature
            shelf_temperature = settings.shelf_temperature_min
            label = "policy_3_interface_velocity_tracking"
        elif time <= switch_31:
            fraction = float(time / switch_31)
            interface_position = velocity_limit * time
            velocity = velocity_limit
            top_temperature = _temperature_for_interface_velocity(
                velocity,
                interface_position,
                config,
                derived,
            )
            bottom_temperature = min(
                settings.temperature_limit - 2.0,
                config.initial_temperature
                + (settings.temperature_limit - 4.0 - config.initial_temperature)
                * fraction,
            )
            shelf_temperature = (
                settings.shelf_temperature_min
                + (settings.shelf_temperature_max - settings.shelf_temperature_min)
                * fraction**1.4
            )
            label = "policy_3_interface_velocity_tracking"
        elif time <= switch_12:
            fraction = float((time - switch_31) / (switch_12 - switch_31))
            interface_position = (
                policy3_switch_s + (policy2_switch_s - policy3_switch_s) * fraction
            )
            velocity = policy1_velocity
            top_temperature = _temperature_for_interface_velocity(
                velocity,
                interface_position,
                config,
                derived,
            )
            bottom_temperature = settings.temperature_limit - 2.0 * (1.0 - fraction)
            shelf_temperature = settings.shelf_temperature_max
            label = "policy_1_max_heat_input"
        else:
            fraction = float((time - switch_12) / max(final_time - switch_12, 1.0))
            interface_position = float(sol2.sol(time)[0])
            velocity = velocity_at_temperature(interface_position)
            top_temperature = settings.temperature_limit
            bottom_temperature = settings.temperature_limit
            shelf_temperature = settings.shelf_temperature_max - 8.0 * fraction
            shelf_temperature = float(
                np.clip(
                    shelf_temperature,
                    settings.shelf_temperature_min,
                    settings.shelf_temperature_max,
                )
            )
            label = "policy_2_temperature_tracking"

        top_temperature = float(
            np.clip(
                top_temperature,
                discretization.temperature_lower_bound,
                settings.temperature_limit,
            )
        )
        bottom_temperature = float(
            np.clip(
                bottom_temperature,
                top_temperature,
                settings.temperature_limit,
            )
        )
        temperature = np.linspace(top_temperature, bottom_temperature, n_z)
        flux = float(sublimation_flux(top_temperature, interface_position, config))

        temperature_values[index, :] = temperature
        interface_values[index] = interface_position
        shelf_values[index] = shelf_temperature
        interface_velocity_values[index] = velocity
        flux_values[index] = flux
        labels.append(label)

    return {
        "states": {
            "time_s": time_s,
            "time_hr": time_s / 3600.0,
            "temperature_K": temperature_values,
            "max_temperature_K": temperature_values.max(axis=1),
            "interface_position_m": interface_values,
            "interface_velocity_m_per_s": interface_velocity_values,
            "sublimation_flux_kg_m2_s": flux_values,
        },
        "controls": {
            "shelf_temperature_K": shelf_values,
        },
        "policies": {
            "labels": labels,
            "segments": _compress_policy_labels(time_s / 3600.0, labels),
            "switch_times_hr": [switch_31 / 3600.0, switch_12 / 3600.0],
        },
        "metrics": {
            "drying_time_s": final_time,
            "drying_time_hr": final_time / 3600.0,
            "policy3_switch_time_s": switch_31,
            "policy3_switch_time_hr": switch_31 / 3600.0,
            "policy1_switch_time_s": switch_12,
            "policy1_switch_time_hr": switch_12 / 3600.0,
            "terminal_drying_fraction": float(
                interface_values[-1] / derived.product_height
            ),
            "max_interface_velocity_m_per_s": float(
                interface_velocity_values[1:].max()
            ),
        },
        "metadata": {
            "source": "problem2_policy_initialization",
            "n_z": n_z,
            "rtol": rtol,
            "atol": atol,
        },
        "problem": {
            "name": "paper_problem_2_policy_initialization",
            "temperature_limit_K": settings.temperature_limit,
            "interface_velocity_limit_m_per_s": velocity_limit,
            "shelf_temperature_min_K": settings.shelf_temperature_min,
            "shelf_temperature_max_K": settings.shelf_temperature_max,
            "terminal_drying_fraction_target": discretization.terminal_drying_fraction,
        },
    }


def initialize_paper_problem_from_trajectory(
    model: Any,
    trajectory: Mapping[str, Any],
    set_final_time: bool = True,
) -> None:
    """Initialize a discretized paper-reference model from a trajectory dict."""
    states = trajectory.get("states", trajectory)
    controls = trajectory.get("controls", {})
    time_s = np.asarray(states["time_s"], dtype=float)
    temperature = np.asarray(states["temperature_K"], dtype=float)
    interface_position = np.asarray(states["interface_position_m"], dtype=float)
    if "shelf_temperature_K" in controls:
        shelf_temperature = np.asarray(controls["shelf_temperature_K"], dtype=float)
    else:
        shelf_temperature = np.asarray(states["shelf_temperature_K"], dtype=float)

    if temperature.ndim != 2:
        raise ValueError("temperature_K must be a 2-D array with shape (time, z)")
    if len(time_s) != len(temperature):
        raise ValueError("time_s and temperature_K have inconsistent lengths")
    if not np.all(np.diff(time_s) > 0.0):
        raise ValueError("time_s must be strictly increasing")

    final_time = float(time_s[-1])
    if set_final_time:
        _set_var_value_within_bounds(model.t_final, final_time)

    source_psi = np.linspace(0.0, 1.0, temperature.shape[1])
    target_psi = np.linspace(0.0, 1.0, len(list(model.z)))
    dtemperature_dt = np.gradient(temperature, time_s, axis=0, edge_order=1)
    dinterface_dt = (
        np.asarray(states["interface_velocity_m_per_s"], dtype=float)
        if "interface_velocity_m_per_s" in states
        else np.gradient(interface_position, time_s, edge_order=1)
    )

    for tau in sorted(model.t):
        absolute_time = float(tau) * final_time
        interface_value = float(np.interp(absolute_time, time_s, interface_position))
        shelf_value = float(np.interp(absolute_time, time_s, shelf_temperature))
        source_temperature_at_time = np.array(
            [
                np.interp(absolute_time, time_s, temperature[:, j])
                for j in range(temperature.shape[1])
            ]
        )
        source_dtemperature_at_time = np.array(
            [
                np.interp(absolute_time, time_s, dtemperature_dt[:, j])
                for j in range(temperature.shape[1])
            ]
        )
        target_temperature = np.interp(
            target_psi, source_psi, source_temperature_at_time
        )
        target_dtemperature_dt = np.interp(
            target_psi,
            source_psi,
            source_dtemperature_at_time,
        )

        _set_var_value_within_bounds(model.S[tau], interface_value)
        _set_var_value_within_bounds(model.Tb[tau], shelf_value)
        for i, value in zip(model.z, target_temperature):
            _set_var_value_within_bounds(model.T[i, tau], float(value))
            if hasattr(model, "dT_dtau"):
                model.dT_dtau[i, tau].set_value(
                    float(final_time * target_dtemperature_dt[i])
                )

        velocity = float(np.interp(absolute_time, time_s, dinterface_dt))
        velocity = max(velocity, 1.0e-12)

        if hasattr(model, "dS_dtau"):
            model.dS_dtau[tau].set_value(final_time * velocity)


def initialize_paper_problem1_from_trajectory(
    model: Any,
    trajectory: Mapping[str, Any],
    set_final_time: bool = True,
) -> None:
    """Backward-compatible alias for ``initialize_paper_problem_from_trajectory``."""
    initialize_paper_problem_from_trajectory(
        model,
        trajectory,
        set_final_time=set_final_time,
    )


def load_upstream_matlab_trajectory(mat_path: str | Path) -> dict[str, Any]:
    """Load an upstream MATLAB trajectory saved from ``Sim_1stDrying_OCP``.

    The loader accepts either arrays named like the upstream output fields
    (``t``, ``T``, ``S``, ``Tb``, optionally ``dSdt``, ``policy``, and
    ``tsw``) or the first-segment arrays produced by the local verification
    script (``t``, ``y``, ``Tb``), where ``y`` contains temperature columns
    followed by interface position.
    """
    from scipy.io import loadmat

    data = loadmat(mat_path, squeeze_me=True)
    if "t" not in data:
        raise ValueError("MATLAB trajectory must contain a 't' time array")

    time_s = np.atleast_1d(np.asarray(data["t"], dtype=float)).reshape(-1)
    if "T" in data:
        temperature = np.asarray(data["T"], dtype=float)
    elif "y" in data:
        y = np.asarray(data["y"], dtype=float)
        if y.ndim != 2 or y.shape[1] < 2:
            raise ValueError("'y' must have temperature columns followed by S")
        temperature = y[:, :-1]
    else:
        raise ValueError("MATLAB trajectory must contain either 'T' or 'y'")

    if temperature.ndim == 1:
        temperature = temperature.reshape(-1, 1)
    if "S" in data:
        interface_position = np.atleast_1d(np.asarray(data["S"], dtype=float)).reshape(
            -1
        )
    elif "y" in data:
        interface_position = np.asarray(data["y"], dtype=float)[:, -1]
    else:
        raise ValueError("MATLAB trajectory must contain 'S' when 'y' is absent")

    if "Tb" not in data:
        raise ValueError(
            "MATLAB trajectory must contain a 'Tb' shelf-temperature array"
        )
    shelf_temperature = np.atleast_1d(np.asarray(data["Tb"], dtype=float)).reshape(-1)

    if len(time_s) != len(temperature) or len(time_s) != len(interface_position):
        raise ValueError("MATLAB trajectory arrays must share the same time dimension")
    if len(shelf_temperature) == 1:
        shelf_temperature = np.full_like(time_s, float(shelf_temperature[0]))
    if len(shelf_temperature) != len(time_s):
        raise ValueError("Tb must be scalar or share the same length as t")

    if "dSdt" in data:
        interface_velocity_values = np.atleast_1d(
            np.asarray(data["dSdt"], dtype=float)
        ).reshape(-1)
        if len(interface_velocity_values) != len(time_s):
            raise ValueError("dSdt must share the same length as t")
        (
            time_s,
            temperature,
            interface_position,
            shelf_temperature,
            interface_velocity_values,
        ) = _collapse_duplicate_time_points(
            time_s,
            temperature,
            interface_position,
            shelf_temperature,
            interface_velocity_values,
        )
    else:
        (
            time_s,
            temperature,
            interface_position,
            shelf_temperature,
        ) = _collapse_duplicate_time_points(
            time_s,
            temperature,
            interface_position,
            shelf_temperature,
        )
        interface_velocity_values = np.gradient(
            interface_position, time_s, edge_order=1
        )

    config = PaperPrimaryDryingConfig()
    policies: dict[str, Any] = {}
    if "policy" in data:
        policies["raw_policy"] = np.atleast_1d(np.asarray(data["policy"])).reshape(-1)
    if "tsw" in data:
        switch_times_s = np.atleast_1d(np.asarray(data["tsw"], dtype=float)).reshape(-1)
        policies["switch_times_s"] = switch_times_s
        policies["switch_times_hr"] = switch_times_s / 3600.0

    trajectory = {
        "states": {
            "time_s": time_s,
            "time_hr": time_s / 3600.0,
            "temperature_K": temperature,
            "max_temperature_K": temperature.max(axis=1),
            "interface_position_m": interface_position,
            "interface_velocity_m_per_s": interface_velocity_values,
        },
        "controls": {
            "shelf_temperature_K": shelf_temperature,
        },
        "metrics": {
            "drying_time_s": float(time_s[-1]),
            "drying_time_hr": float(time_s[-1] / 3600.0),
            "terminal_interface_position_m": float(interface_position[-1]),
            "max_product_temperature_K": float(temperature.max()),
        },
        "problem": {
            "name": "paper_problem_1_upstream_reference",
            "temperature_limit_K": config.problem1_temperature_limit,
            "shelf_temperature_min_K": config.shelf_temperature_min,
            "shelf_temperature_max_K": config.shelf_temperature_max,
        },
        "metadata": {
            "source": "upstream_matlab",
            "path": str(mat_path),
        },
    }
    if policies:
        trajectory["policies"] = policies
    return trajectory


def _collapse_duplicate_time_points(
    time_s: np.ndarray,
    *series: np.ndarray,
) -> tuple[np.ndarray, ...]:
    """Collapse repeated upstream segment-boundary samples, keeping later values."""
    time_s = np.asarray(time_s, dtype=float).reshape(-1)
    if len(time_s) < 2:
        return (time_s, *series)

    deltas = np.diff(time_s)
    if np.any(deltas < 0.0):
        raise ValueError("t must be nondecreasing")
    if not np.any(deltas == 0.0):
        return (time_s, *series)

    keep = np.ones(len(time_s), dtype=bool)
    keep[:-1] = time_s[:-1] != time_s[1:]
    collapsed_series = tuple(np.asarray(values)[keep] for values in series)
    return (time_s[keep], *collapsed_series)


def compare_paper_problem1_trajectories(
    pyomo_result: Mapping[str, Any],
    upstream_trajectory: Mapping[str, Any],
) -> dict[str, Any]:
    """Compare a Pyomo Paper Problem 1 result against an upstream trajectory."""
    pyomo_drying_time_hr = _drying_time_hr(pyomo_result)
    upstream_drying_time_hr = _drying_time_hr(upstream_trajectory)
    pyomo_switch_time_hr = _first_switch_time_hr(pyomo_result)
    upstream_switch_time_hr = _first_switch_time_hr(upstream_trajectory)
    pyomo_terminal_s = _terminal_interface_position(pyomo_result)
    upstream_terminal_s = _terminal_interface_position(upstream_trajectory)
    pyomo_peak_temperature = _peak_temperature(pyomo_result)
    upstream_peak_temperature = _peak_temperature(upstream_trajectory)

    return {
        "pyomo_drying_time_hr": pyomo_drying_time_hr,
        "upstream_drying_time_hr": upstream_drying_time_hr,
        "drying_time_deviation_hr": pyomo_drying_time_hr - upstream_drying_time_hr,
        "pyomo_first_switch_time_hr": pyomo_switch_time_hr,
        "upstream_first_switch_time_hr": upstream_switch_time_hr,
        "first_switch_time_deviation_hr": _nullable_difference(
            pyomo_switch_time_hr,
            upstream_switch_time_hr,
        ),
        "pyomo_terminal_interface_position_m": pyomo_terminal_s,
        "upstream_terminal_interface_position_m": upstream_terminal_s,
        "terminal_interface_position_deviation_m": pyomo_terminal_s
        - upstream_terminal_s,
        "pyomo_peak_temperature_K": pyomo_peak_temperature,
        "upstream_peak_temperature_K": upstream_peak_temperature,
        "peak_temperature_deviation_K": pyomo_peak_temperature
        - upstream_peak_temperature,
        "max_temperature_profile_max_abs_deviation_K": (
            _max_temperature_profile_deviation(pyomo_result, upstream_trajectory)
        ),
    }


def _drying_time_hr(result: Mapping[str, Any]) -> float:
    metrics = result.get("metrics", {})
    if "drying_time_hr" in metrics:
        return float(metrics["drying_time_hr"])
    return float(np.asarray(result["states"]["time_s"], dtype=float)[-1] / 3600.0)


def _first_switch_time_hr(result: Mapping[str, Any]) -> float | None:
    policies = result.get("policies", {})
    switch_times = policies.get("switch_times_hr")
    if switch_times is not None:
        switch_array = np.atleast_1d(np.asarray(switch_times, dtype=float)).reshape(-1)
        if len(switch_array) > 0:
            return float(switch_array[0])

    segments = policies.get("segments", [])
    if len(segments) > 1:
        return float(segments[1]["start_time_hr"])
    return None


def _terminal_interface_position(result: Mapping[str, Any]) -> float:
    metrics = result.get("metrics", {})
    if "terminal_interface_position_m" in metrics:
        return float(metrics["terminal_interface_position_m"])
    interface_position = np.asarray(
        result["states"]["interface_position_m"],
        dtype=float,
    )
    return float(interface_position[-1])


def _peak_temperature(result: Mapping[str, Any]) -> float:
    metrics = result.get("metrics", {})
    if "max_product_temperature_K" in metrics:
        return float(metrics["max_product_temperature_K"])
    max_temperature = np.asarray(result["states"]["max_temperature_K"], dtype=float)
    return float(max_temperature.max())


def _nullable_difference(left: float | None, right: float | None) -> float | None:
    if left is None or right is None:
        return None
    return float(left - right)


def _max_temperature_profile_deviation(
    pyomo_result: Mapping[str, Any],
    upstream_trajectory: Mapping[str, Any],
) -> float:
    pyomo_time, pyomo_max_temperature = _unique_time_series(
        pyomo_result["states"]["time_s"],
        pyomo_result["states"]["max_temperature_K"],
    )
    upstream_time, upstream_max_temperature = _unique_time_series(
        upstream_trajectory["states"]["time_s"],
        upstream_trajectory["states"]["max_temperature_K"],
    )
    start = max(float(pyomo_time[0]), float(upstream_time[0]))
    stop = min(float(pyomo_time[-1]), float(upstream_time[-1]))
    if stop <= start:
        return float("nan")

    sample_time = upstream_time[(upstream_time >= start) & (upstream_time <= stop)]
    sample_time = np.unique(np.concatenate(([start], sample_time, [stop])))
    if len(sample_time) < 2:
        sample_time = np.linspace(start, stop, 2)

    pyomo_interp = np.interp(sample_time, pyomo_time, pyomo_max_temperature)
    upstream_interp = np.interp(
        sample_time,
        upstream_time,
        upstream_max_temperature,
    )
    return float(np.max(np.abs(pyomo_interp - upstream_interp)))


def _unique_time_series(
    time_values: Iterable[float],
    values: Iterable[float],
) -> tuple[np.ndarray, np.ndarray]:
    time = np.asarray(time_values, dtype=float).reshape(-1)
    series = np.asarray(values, dtype=float).reshape(-1)
    order = np.argsort(time)
    time = time[order]
    series = series[order]
    unique_time, unique_indices = np.unique(time, return_index=True)
    return unique_time, series[unique_indices]


def create_paper_problem1_model(
    config: PaperPrimaryDryingConfig | None = None,
    discretization: PaperDiscretization | None = None,
    apply_scaling: bool = False,
):
    """Create the Pyomo direct-transcription model for Paper Problem 1."""
    return _create_paper_problem_model(
        "problem1",
        config=config,
        discretization=discretization,
        apply_scaling=apply_scaling,
    )


def create_paper_problem2_model(
    config: PaperPrimaryDryingConfig | None = None,
    discretization: PaperDiscretization | None = None,
    apply_scaling: bool = False,
):
    """Create the Pyomo direct-transcription model for Paper Problem 2."""
    return _create_paper_problem_model(
        "problem2",
        config=config,
        discretization=discretization,
        apply_scaling=apply_scaling,
    )


def _create_paper_problem_model(
    problem: str,
    config: PaperPrimaryDryingConfig | None = None,
    discretization: PaperDiscretization | None = None,
    apply_scaling: bool = False,
):
    """Create a Pyomo direct-transcription model for a paper OCP.

    The model is discretized immediately with orthogonal collocation so callers
    receive an NLP ready for initialization and solve. Scaling suffixes are
    optional because the validated coarse benchmark solves cleanly without them.
    """
    import pyomo.dae as dae
    import pyomo.environ as pyo

    config = config or PaperPrimaryDryingConfig()
    discretization = discretization or PaperDiscretization()
    settings = _paper_problem_settings(config, problem)
    derived = derive_primary_drying_parameters(config, discretization.n_z)
    if not 0.0 < discretization.terminal_drying_fraction < 1.0:
        raise ValueError("terminal_drying_fraction must be in (0, 1)")

    model = pyo.ConcreteModel()
    model._paper_config = config
    model._paper_discretization = discretization
    model._paper_derived = derived
    model._paper_problem_settings = settings

    model.z = pyo.RangeSet(0, discretization.n_z - 1)
    model.t = dae.ContinuousSet(bounds=(0.0, 1.0))
    model.psi = pyo.Param(
        model.z,
        initialize={i: derived.psi[i] for i in range(discretization.n_z)},
    )

    terminal_s = discretization.terminal_drying_fraction * derived.product_height
    model.t_final = pyo.Var(
        bounds=config.time_bounds,
        initialize=settings.time_guess,
    )
    model.T = pyo.Var(
        model.z,
        model.t,
        bounds=(
            discretization.temperature_lower_bound,
            discretization.temperature_upper_bound,
        ),
        initialize=config.initial_temperature,
    )
    model.S = pyo.Var(
        model.t,
        bounds=(0.0, terminal_s),
        initialize=0.5 * terminal_s,
    )
    model.Tb = pyo.Var(
        model.t,
        bounds=(settings.shelf_temperature_min, settings.shelf_temperature_max),
        initialize=settings.shelf_temperature_max,
    )

    model.dT_dtau = dae.DerivativeVar(model.T, wrt=model.t)
    model.dS_dtau = dae.DerivativeVar(model.S, wrt=model.t)

    def vapor_pressure_rule(m, t):
        return pyo.exp(config.vapor_pressure_a / m.T[0, t] + config.vapor_pressure_b)

    model.Pw = pyo.Expression(model.t, rule=vapor_pressure_rule)

    def resistance_rule(m, t):
        return config.resistance_0 + config.resistance_1 * m.S[t] / (
            1.0 + config.resistance_2 * m.S[t]
        )

    model.Rp = pyo.Expression(model.t, rule=resistance_rule)

    def sublimation_flux_rule(m, t):
        return (m.Pw[t] - config.chamber_water_pressure) / m.Rp[t]

    model.Nw = pyo.Expression(model.t, rule=sublimation_flux_rule)

    def nonnegative_sublimation_flux_rule(m, t):
        return m.Pw[t] >= config.chamber_water_pressure

    model.nonnegative_sublimation_flux = pyo.Constraint(
        model.t,
        rule=nonnegative_sublimation_flux_rule,
    )

    def interface_velocity_rule(m, t):
        return m.Nw[t] / (derived.frozen_density - config.dried_region_density)

    model.dSdt = pyo.Expression(model.t, rule=interface_velocity_rule)

    def interface_ode_rule(m, t):
        if t == m.t.first():
            return pyo.Constraint.Skip
        return m.dS_dtau[t] == m.t_final * m.dSdt[t]

    model.interface_ode = pyo.Constraint(model.t, rule=interface_ode_rule)

    def temperature_rhs(m, i, t):
        thickness = derived.product_height - m.S[t]
        volume = derived.cross_section_area * thickness
        side_loss = (
            derived.side_transfer_factor
            * config.stefan_boltzmann
            * derived.side_area
            * (m.T[i, t] ** 4 - config.wall_temperature**4)
            / (volume * derived.frozen_density * derived.frozen_heat_capacity)
        )
        source = config.microwave_heat_input / (
            volume * derived.frozen_density * derived.frozen_heat_capacity
        )

        if i == 0:
            top_radiation = (
                derived.top_transfer_factor
                * config.stefan_boltzmann
                * (m.T[i, t] ** 4 - config.top_surface_temperature**4)
            )
            diffusion = (
                derived.frozen_diffusivity
                / thickness**2
                / derived.dpsi**2
                * (
                    2.0 * m.T[1, t]
                    - 2.0 * m.T[0, t]
                    - 2.0
                    * m.Nw[t]
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
                * m.Nw[t]
                * config.heat_of_sublimation
                / derived.frozen_conductivity
                + top_radiation * thickness / derived.frozen_conductivity
            )
            convection = (
                -((m.psi[i] - 1.0) * m.dSdt[t] / thickness) * convection_gradient
            )
            return diffusion + convection - side_loss + source

        if i == discretization.n_z - 1:
            diffusion = (
                derived.frozen_diffusivity
                / thickness**2
                / derived.dpsi**2
                * (
                    2.0 * m.T[i - 1, t]
                    - 2.0 * m.T[i, t]
                    + 2.0
                    * (m.S[t] - derived.product_height)
                    * config.bottom_heat_transfer_coefficient
                    * derived.dpsi
                    * (m.T[i, t] - m.Tb[t])
                    / derived.frozen_conductivity
                )
            )
            convection_gradient = (
                (m.S[t] - derived.product_height)
                * config.bottom_heat_transfer_coefficient
                * (m.T[i, t] - m.Tb[t])
                / derived.frozen_conductivity
            )
            convection = (
                -((m.psi[i] - 1.0) * m.dSdt[t] / thickness) * convection_gradient
            )
            return diffusion + convection - side_loss + source

        diffusion = (
            derived.frozen_diffusivity
            / thickness**2
            / derived.dpsi**2
            * (m.T[i - 1, t] - 2.0 * m.T[i, t] + m.T[i + 1, t])
        )
        convection = (
            -((m.psi[i] - 1.0) * m.dSdt[t] / thickness)
            * (m.T[i + 1, t] - m.T[i - 1, t])
            / (2.0 * derived.dpsi)
        )
        return diffusion + convection - side_loss + source

    def temperature_ode_rule(m, i, t):
        if t == m.t.first():
            return pyo.Constraint.Skip
        return m.dT_dtau[i, t] == m.t_final * temperature_rhs(m, i, t)

    model.temperature_ode = pyo.Constraint(
        model.z,
        model.t,
        rule=temperature_ode_rule,
    )

    model.initial_interface = pyo.Constraint(
        expr=model.S[0.0] == config.initial_interface_position
    )

    def initial_temperature_rule(m, i):
        return m.T[i, 0.0] == config.initial_temperature

    model.initial_temperature = pyo.Constraint(
        model.z,
        rule=initial_temperature_rule,
    )

    bottom_node = discretization.n_z - 1

    def product_temperature_limit_rule(m, t):
        return m.T[bottom_node, t] <= settings.temperature_limit

    model.product_temperature_limit = pyo.Constraint(
        model.t,
        rule=product_temperature_limit_rule,
    )

    if settings.interface_velocity_limit is not None:

        def interface_velocity_limit_rule(m, t):
            if t == m.t.first():
                # The paper reports an initial velocity excursion. Only that
                # initial point is skipped; all post-initial collocation points
                # remain constrained and included in violation metrics.
                return pyo.Constraint.Skip
            return 1.0e7 * m.dSdt[t] <= 1.0e7 * settings.interface_velocity_limit

        model.interface_velocity_limit = pyo.Constraint(
            model.t,
            rule=interface_velocity_limit_rule,
        )

    model.terminal_drying = pyo.Constraint(expr=model.S[1.0] >= terminal_s)
    model.objective = pyo.Objective(expr=model.t_final, sense=pyo.minimize)

    discretizer = pyo.TransformationFactory("dae.collocation")
    discretizer.apply_to(
        model,
        nfe=discretization.nfe,
        ncp=discretization.ncp,
        scheme=discretization.scheme,
    )

    _initialize_problem1_model(model)
    if apply_scaling:
        _add_problem1_scaling(model)

    return model


def _initialize_problem1_model(model: Any) -> None:
    """Populate deterministic initial guesses after collocation."""
    config = model._paper_config
    discretization = model._paper_discretization
    derived = model._paper_derived
    settings = model._paper_problem_settings
    terminal_s = discretization.terminal_drying_fraction * derived.product_height
    time_guess = settings.time_guess
    model.t_final.set_value(time_guess)

    for t in sorted(model.t):
        tau = float(t)
        s_guess = terminal_s * tau
        model.S[t].set_value(s_guess)

        if tau <= 0.35:
            tb_guess = settings.shelf_temperature_max
        else:
            decline = (tau - 0.35) / 0.65
            tb_guess = settings.shelf_temperature_max - 20.0 * min(
                max(decline, 0.0),
                1.0,
            )
        model.Tb[t].set_value(max(settings.shelf_temperature_min, tb_guess))

        top_guess = min(
            settings.temperature_limit - 1.0,
            config.initial_temperature + 13.0 * tau,
        )
        bottom_guess = min(
            settings.temperature_limit - 0.25,
            config.initial_temperature + 15.0 * tau,
        )
        for i in model.z:
            frac = i / (discretization.n_z - 1)
            model.T[i, t].set_value(top_guess + frac * (bottom_guess - top_guess))

        top_temperature = model.T[0, t].value
        pressure = float(saturation_pressure(top_temperature, config))
        resistance = float(product_resistance(s_guess, config))
        flux = max((pressure - config.chamber_water_pressure) / resistance, 1.0e-8)
        velocity = flux / (derived.frozen_density - config.dried_region_density)
        if hasattr(model, "dS_dtau"):
            model.dS_dtau[t].set_value(time_guess * velocity)


def _add_problem1_scaling(model: Any) -> None:
    """Add IPOPT scaling suffixes for the SI-unit benchmark model."""
    import pyomo.environ as pyo

    model.scaling_factor = pyo.Suffix(direction=pyo.Suffix.EXPORT)
    model.scaling_factor[model.t_final] = 1.0e-4
    for t in model.t:
        model.scaling_factor[model.S[t]] = 1.0e2
        model.scaling_factor[model.Tb[t]] = 1.0e-2
        for i in model.z:
            model.scaling_factor[model.T[i, t]] = 1.0e-2

    _set_component_scaling(model, "interface_ode", 1.0e2)
    _set_component_scaling(model, "temperature_ode", 1.0e-2)
    _set_component_scaling(model, "initial_interface", 1.0e2)
    _set_component_scaling(model, "initial_temperature", 1.0e-2)
    _set_component_scaling(model, "product_temperature_limit", 1.0e-2)
    _set_component_scaling(model, "nonnegative_sublimation_flux", 1.0e-1)
    _set_component_scaling(model, "interface_velocity_limit", 1.0e7)
    _set_component_scaling(model, "terminal_drying", 1.0e2)
    _set_component_scaling(model, "dS_dtau_disc_eq", 1.0e2)
    _set_component_scaling(model, "dT_dtau_disc_eq", 1.0e-2)


def _set_component_scaling(model: Any, component_name: str, factor: float) -> None:
    if not hasattr(model, component_name):
        return
    component = getattr(model, component_name)
    if component.is_indexed():
        for index in component:
            model.scaling_factor[component[index]] = factor
    else:
        model.scaling_factor[component] = factor


def _numeric_temperature_rhs(
    temperature: np.ndarray,
    interface_position: float,
    shelf_temperature: float,
    config: PaperPrimaryDryingConfig,
    derived: PaperDerivedParameters,
) -> tuple[np.ndarray, float]:
    """Return dimensional RHS values for the paper primary-drying model."""
    n_z = len(temperature)
    thickness = max(derived.product_height - interface_position, 1.0e-9)
    volume = derived.cross_section_area * thickness
    pressure = float(saturation_pressure(temperature[0], config))
    resistance = float(product_resistance(interface_position, config))
    flux = max((pressure - config.chamber_water_pressure) / resistance, 0.0)
    dinterface_dt = flux / (derived.frozen_density - config.dried_region_density)
    dtemperature_dt = np.zeros(n_z, dtype=float)

    for i in range(n_z):
        side_loss = (
            derived.side_transfer_factor
            * config.stefan_boltzmann
            * derived.side_area
            * (temperature[i] ** 4 - config.wall_temperature**4)
            / (volume * derived.frozen_density * derived.frozen_heat_capacity)
        )
        source = config.microwave_heat_input / (
            volume * derived.frozen_density * derived.frozen_heat_capacity
        )

        if i == 0:
            top_radiation = (
                derived.top_transfer_factor
                * config.stefan_boltzmann
                * (temperature[i] ** 4 - config.top_surface_temperature**4)
            )
            diffusion = (
                derived.frozen_diffusivity
                / thickness**2
                / derived.dpsi**2
                * (
                    2.0 * temperature[1]
                    - 2.0 * temperature[0]
                    - 2.0
                    * flux
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
                * flux
                * config.heat_of_sublimation
                / derived.frozen_conductivity
                + top_radiation * thickness / derived.frozen_conductivity
            )
            convection = (
                -((derived.psi[i] - 1.0) * dinterface_dt / thickness)
                * convection_gradient
            )
            dtemperature_dt[i] = diffusion + convection - side_loss + source
        elif i == n_z - 1:
            diffusion = (
                derived.frozen_diffusivity
                / thickness**2
                / derived.dpsi**2
                * (
                    2.0 * temperature[i - 1]
                    - 2.0 * temperature[i]
                    + 2.0
                    * (interface_position - derived.product_height)
                    * config.bottom_heat_transfer_coefficient
                    * derived.dpsi
                    * (temperature[i] - shelf_temperature)
                    / derived.frozen_conductivity
                )
            )
            convection_gradient = (
                (interface_position - derived.product_height)
                * config.bottom_heat_transfer_coefficient
                * (temperature[i] - shelf_temperature)
                / derived.frozen_conductivity
            )
            convection = (
                -((derived.psi[i] - 1.0) * dinterface_dt / thickness)
                * convection_gradient
            )
            dtemperature_dt[i] = diffusion + convection - side_loss + source
        else:
            diffusion = (
                derived.frozen_diffusivity
                / thickness**2
                / derived.dpsi**2
                * (temperature[i - 1] - 2.0 * temperature[i] + temperature[i + 1])
            )
            convection = (
                -((derived.psi[i] - 1.0) * dinterface_dt / thickness)
                * (temperature[i + 1] - temperature[i - 1])
                / (2.0 * derived.dpsi)
            )
            dtemperature_dt[i] = diffusion + convection - side_loss + source

    return dtemperature_dt, dinterface_dt


def _policy2_shelf_temperature(
    temperature: np.ndarray,
    interface_position: float,
    config: PaperPrimaryDryingConfig,
    derived: PaperDerivedParameters,
) -> float:
    """Return shelf temperature that makes the bottom-node derivative zero."""
    bottom_index = len(temperature) - 1
    thickness = max(derived.product_height - interface_position, 1.0e-9)
    volume = derived.cross_section_area * thickness
    bottom_temperature = temperature[bottom_index]
    side_loss = (
        derived.side_transfer_factor
        * config.stefan_boltzmann
        * derived.side_area
        * (bottom_temperature**4 - config.wall_temperature**4)
        / (volume * derived.frozen_density * derived.frozen_heat_capacity)
    )
    source = config.microwave_heat_input / (
        volume * derived.frozen_density * derived.frozen_heat_capacity
    )
    diffusion_scale = derived.frozen_diffusivity / thickness**2 / derived.dpsi**2
    target_stencil = (side_loss - source) / diffusion_scale
    bottom_delta = (
        target_stencil - 2.0 * temperature[bottom_index - 1] + 2.0 * bottom_temperature
    )
    denominator = (
        2.0
        * (interface_position - derived.product_height)
        * config.bottom_heat_transfer_coefficient
        * derived.dpsi
    )
    bottom_minus_shelf = bottom_delta * derived.frozen_conductivity / denominator
    return bottom_temperature - bottom_minus_shelf


def _policy_sample_times(
    switch_time: float,
    final_time: float,
    n_time_points: int,
    has_policy2: bool,
) -> np.ndarray:
    """Return monotonically increasing sample times preserving the switch point."""
    if n_time_points < 4:
        raise ValueError("n_time_points must be at least 4")
    if not has_policy2:
        return np.linspace(0.0, final_time, n_time_points)

    policy1_fraction = max(0.1, min(0.9, switch_time / final_time))
    n_policy1 = max(3, int(round(n_time_points * policy1_fraction)))
    n_policy2 = max(3, n_time_points - n_policy1 + 1)
    return np.unique(
        np.concatenate(
            (
                np.linspace(0.0, switch_time, n_policy1),
                np.linspace(switch_time, final_time, n_policy2),
            )
        )
    )


def _policy_sample_times_multiple(
    switch_times: tuple[float, ...],
    final_time: float,
    n_time_points: int,
) -> np.ndarray:
    """Return sample times preserving multiple switch points."""
    if n_time_points < 3 * (len(switch_times) + 1):
        raise ValueError("n_time_points is too small for the policy sequence")

    boundaries = (0.0, *switch_times, final_time)
    durations = np.diff(boundaries)
    if np.any(durations <= 0.0):
        raise ValueError("switch times must be strictly increasing")

    raw_counts = n_time_points * durations / final_time
    counts = [max(3, int(round(count))) for count in raw_counts]
    while sum(counts) - len(counts) + 1 > n_time_points:
        index = int(np.argmax(counts))
        if counts[index] <= 3:
            break
        counts[index] -= 1
    while sum(counts) - len(counts) + 1 < n_time_points:
        index = int(np.argmax(durations))
        counts[index] += 1

    pieces = [
        np.linspace(start, stop, count)
        for start, stop, count in zip(boundaries[:-1], boundaries[1:], counts)
    ]
    return np.unique(np.concatenate(pieces))


def _interface_velocity_at_temperature(
    interface_temperature: float,
    interface_position: float,
    config: PaperPrimaryDryingConfig,
    derived: PaperDerivedParameters,
) -> float:
    flux = float(sublimation_flux(interface_temperature, interface_position, config))
    return flux / (derived.frozen_density - config.dried_region_density)


def _temperature_for_interface_velocity(
    interface_velocity_value: float,
    interface_position: float,
    config: PaperPrimaryDryingConfig,
    derived: PaperDerivedParameters,
) -> float:
    flux = interface_velocity_value * (
        derived.frozen_density - config.dried_region_density
    )
    pressure = config.chamber_water_pressure + flux * float(
        product_resistance(interface_position, config)
    )
    pressure = max(pressure, 1.0e-12)
    return float(temperature_for_saturation_pressure(pressure, config))


def _set_var_value_within_bounds(var: Any, value: float) -> None:
    """Set a Pyomo VarData value after clipping to its finite bounds."""
    lower, upper = var.bounds
    if lower is not None:
        value = max(float(lower), value)
    if upper is not None:
        value = min(float(upper), value)
    var.set_value(value)


def solve_paper_problem1(
    config: PaperPrimaryDryingConfig | None = None,
    discretization: PaperDiscretization | None = None,
    solver: str = "ipopt",
    solver_options: Mapping[str, Any] | None = None,
    initialization: str | Mapping[str, Any] | None = "policy",
    tee: bool = False,
    require_success: bool = True,
    return_model: bool = False,
) -> dict[str, Any]:
    """Build and solve Paper Problem 1 with Pyomo/IPOPT."""
    return _solve_paper_problem(
        "problem1",
        config=config,
        discretization=discretization,
        solver=solver,
        solver_options=solver_options,
        initialization=initialization,
        tee=tee,
        require_success=require_success,
        return_model=return_model,
    )


def solve_paper_problem2(
    config: PaperPrimaryDryingConfig | None = None,
    discretization: PaperDiscretization | None = None,
    solver: str = "ipopt",
    solver_options: Mapping[str, Any] | None = None,
    initialization: str | Mapping[str, Any] | None = "policy",
    tee: bool = False,
    require_success: bool = True,
    return_model: bool = False,
) -> dict[str, Any]:
    """Build and solve Paper Problem 2 with Pyomo/IPOPT."""
    return _solve_paper_problem(
        "problem2",
        config=config,
        discretization=discretization,
        solver=solver,
        solver_options=solver_options,
        initialization=initialization,
        tee=tee,
        require_success=require_success,
        return_model=return_model,
    )


def _solve_paper_problem(
    problem: str,
    config: PaperPrimaryDryingConfig | None = None,
    discretization: PaperDiscretization | None = None,
    solver: str = "ipopt",
    solver_options: Mapping[str, Any] | None = None,
    initialization: str | Mapping[str, Any] | None = "policy",
    tee: bool = False,
    require_success: bool = True,
    return_model: bool = False,
) -> dict[str, Any]:
    """Build and solve a paper-reference problem with Pyomo/IPOPT."""
    import pyomo.environ as pyo

    if problem == "problem1":
        model = create_paper_problem1_model(config, discretization)
    elif problem == "problem2":
        model = create_paper_problem2_model(config, discretization)
    else:
        raise ValueError(f"unsupported paper OCP problem: {problem}")
    config = config or model._paper_config
    discretization = discretization or model._paper_discretization
    if initialization == "policy":
        if problem == "problem1":
            trajectory = generate_problem1_policy_initialization(config, discretization)
        else:
            trajectory = generate_problem2_policy_initialization(config, discretization)
        initialize_paper_problem_from_trajectory(model, trajectory)
    elif isinstance(initialization, Mapping):
        initialize_paper_problem_from_trajectory(model, initialization)
    elif initialization is not None:
        raise ValueError(
            "initialization must be 'policy', a trajectory mapping, or None"
        )

    try:
        from idaes.core.solvers import get_solver

        opt = get_solver(solver)
    except Exception:
        opt = pyo.SolverFactory(solver)

    if solver == "ipopt" and hasattr(opt, "options"):
        opt.options.setdefault("max_iter", 5000)
        opt.options.setdefault("tol", 1.0e-6)
        opt.options.setdefault("acceptable_tol", 1.0e-3)
        opt.options.setdefault("acceptable_iter", 5)
        opt.options.setdefault("constr_viol_tol", 1.0e-6)
        opt.options.setdefault("mu_strategy", "adaptive")
        opt.options.setdefault("bound_relax_factor", 1.0e-8)
        opt.options.setdefault("nlp_scaling_method", "user-scaling")
        opt.options.setdefault("print_level", 5 if tee else 0)

    if solver_options:
        for key, value in solver_options.items():
            opt.options[key] = value

    results = opt.solve(model, tee=tee)
    solution = extract_paper_solution(model, results)
    solution["policies"] = classify_paper_policies(solution)
    if return_model:
        solution["model"] = model

    if require_success and not _is_successful_termination(results):
        settings = model._paper_problem_settings
        metadata = solution["metadata"]
        raise RuntimeError(
            f"{settings.name.replace('_', ' ').title()} solve did not converge "
            f"(status={metadata['status']}, "
            f"termination_condition={metadata['termination_condition']})"
        )

    return solution


def extract_paper_solution(model: Any, results: Any | None = None) -> dict[str, Any]:
    """Extract a solved or initialized paper OCP model into a rich result dict."""
    import pyomo.environ as pyo

    config = model._paper_config
    discretization = model._paper_discretization
    derived = model._paper_derived
    settings = model._paper_problem_settings
    t_points = sorted(model.t)
    z_points = list(model.z)
    t_final = float(pyo.value(model.t_final))
    tau = np.array([float(t) for t in t_points])
    time_s = tau * t_final

    temperature = np.array(
        [[float(pyo.value(model.T[i, t])) for i in z_points] for t in t_points]
    )
    interface_position = np.array([float(pyo.value(model.S[t])) for t in t_points])
    shelf_temperature = np.array([float(pyo.value(model.Tb[t])) for t in t_points])
    interface_velocity_values = np.array(
        [float(pyo.value(model.dSdt[t])) for t in t_points]
    )
    flux = np.array([float(pyo.value(model.Nw[t])) for t in t_points])
    resistance = np.array([float(pyo.value(model.Rp[t])) for t in t_points])
    vapor_pressure = np.array([float(pyo.value(model.Pw[t])) for t in t_points])
    max_temperature = temperature.max(axis=1)
    constrained_velocity = (
        interface_velocity_values[1:]
        if len(interface_velocity_values) > 1
        else interface_velocity_values
    )

    target_s = discretization.terminal_drying_fraction * derived.product_height
    metrics = {
        "drying_time_s": t_final,
        "drying_time_hr": t_final / 3600.0,
        "terminal_interface_position_m": float(interface_position[-1]),
        "terminal_drying_fraction": float(
            interface_position[-1] / derived.product_height
        ),
        "target_interface_position_m": target_s,
        "terminal_gap_m": max(0.0, target_s - float(interface_position[-1])),
        "max_product_temperature_K": float(max_temperature.max()),
        "max_temperature_violation_K": max(
            0.0,
            float(max_temperature.max() - settings.temperature_limit),
        ),
        "shelf_lower_violation_K": max(
            0.0,
            float(settings.shelf_temperature_min - shelf_temperature.min()),
        ),
        "shelf_upper_violation_K": max(
            0.0,
            float(shelf_temperature.max() - settings.shelf_temperature_max),
        ),
        "max_interface_velocity_m_per_s": float(constrained_velocity.max()),
    }
    if settings.interface_velocity_limit is not None:
        metrics["initial_interface_velocity_m_per_s"] = float(
            interface_velocity_values[0]
        )
        metrics["max_interface_velocity_violation_m_per_s"] = max(
            0.0,
            float(constrained_velocity.max() - settings.interface_velocity_limit),
        )

    status = None
    termination_condition = None
    if results is not None:
        solver_info = getattr(results, "solver", None)
        status = str(getattr(solver_info, "status", None))
        termination_condition = str(getattr(solver_info, "termination_condition", None))

    return {
        "states": {
            "tau": tau,
            "time_s": time_s,
            "time_hr": time_s / 3600.0,
            "temperature_K": temperature,
            "max_temperature_K": max_temperature,
            "interface_position_m": interface_position,
            "interface_velocity_m_per_s": interface_velocity_values,
            "sublimation_flux_kg_m2_s": flux,
            "resistance_m_per_s": resistance,
            "vapor_pressure_Pa": vapor_pressure,
        },
        "controls": {
            "shelf_temperature_K": shelf_temperature,
        },
        "metrics": metrics,
        "metadata": {
            "status": status,
            "termination_condition": termination_condition,
            "n_z": discretization.n_z,
            "nfe": discretization.nfe,
            "ncp": discretization.ncp,
            "scheme": discretization.scheme,
        },
        "problem": {
            "name": settings.name,
            "temperature_limit_K": settings.temperature_limit,
            "interface_velocity_limit_m_per_s": settings.interface_velocity_limit,
            "shelf_temperature_min_K": settings.shelf_temperature_min,
            "shelf_temperature_max_K": settings.shelf_temperature_max,
            "terminal_drying_fraction_target": discretization.terminal_drying_fraction,
        },
        "config": asdict(config),
        "derived": asdict(derived),
    }


def classify_paper_policies(
    result: Mapping[str, Any],
    tolerances: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    """Infer active paper policies from a result trajectory.

    Policy 1 is maximum heat input (``Tb = Tb_max``).  Policy 2 is product
    temperature tracking (``max(T) = T_limit``).  Policy 3 is interface-velocity
    tracking (``dS/dt = dSdt_limit``).  If multiple path constraints are active
    at a point, Policy 2 takes precedence over Policy 3 because the product
    temperature limit becomes the controlling active constraint in the paper's
    Problem 2 sequence.
    """
    tolerances = dict(tolerances or {})
    temperature_tolerance = tolerances.get("temperature_K", 0.35)
    shelf_tolerance = tolerances.get("shelf_temperature_K", 0.35)
    velocity_tolerance = tolerances.get("interface_velocity_m_per_s", 2.0e-9)

    states = result["states"]
    controls = result["controls"]
    problem = result["problem"]
    time_hr = np.asarray(states["time_hr"])
    max_temperature = np.asarray(states["max_temperature_K"])
    shelf_temperature = np.asarray(controls["shelf_temperature_K"])
    interface_velocity_values = np.asarray(
        states.get(
            "interface_velocity_m_per_s",
            np.full(max_temperature.shape, np.nan, dtype=float),
        )
    )
    temperature_limit = float(problem["temperature_limit_K"])
    velocity_limit = problem.get("interface_velocity_limit_m_per_s")
    velocity_limit = None if velocity_limit is None else float(velocity_limit)
    shelf_max = float(problem["shelf_temperature_max_K"])

    labels: list[str] = []
    for temp, shelf, velocity in zip(
        max_temperature,
        shelf_temperature,
        interface_velocity_values,
    ):
        temp_active = temp >= temperature_limit - temperature_tolerance
        velocity_active = (
            velocity_limit is not None
            and velocity >= velocity_limit - velocity_tolerance
        )
        shelf_active = abs(shelf - shelf_max) <= shelf_tolerance
        if temp_active:
            labels.append("policy_2_temperature_tracking")
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


def _compress_policy_labels(
    time_hr: Iterable[float],
    labels: Iterable[str],
) -> list[dict[str, Any]]:
    """Return contiguous policy-label segments."""
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


def _is_successful_termination(results: Any) -> bool:
    """Return whether a Pyomo solve status is acceptable for extraction."""
    import pyomo.environ as pyo

    solver = getattr(results, "solver", None)
    termination_condition = getattr(solver, "termination_condition", None)
    acceptable = {str(pyo.TerminationCondition.optimal).lower()}
    locally_optimal = getattr(pyo.TerminationCondition, "locallyOptimal", None)
    if locally_optimal is not None:
        acceptable.add(str(locally_optimal).lower())
    return str(termination_condition).lower() in acceptable
