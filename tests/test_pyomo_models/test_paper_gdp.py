"""Tests for the validation-only paper GDP switching formulation."""

from __future__ import annotations

import numpy as np
import pytest
from lyopronto.pyomo_models.paper_gdp import (
    POLICY_MAX_HEAT,
    POLICY_TEMPERATURE,
    POLICY_VELOCITY,
    PaperGDPDiscretization,
    create_paper_problem1_gdp_model,
    create_paper_problem2_gdp_model,
    solve_paper_problem1_gdp,
    solve_paper_problem2_gdp,
)
from lyopronto.pyomo_models.paper_ocp import (
    PaperDiscretization,
    PaperPrimaryDryingConfig,
    product_resistance,
    solve_paper_problem2,
    temperature_for_saturation_pressure,
)

pyo = pytest.importorskip("pyomo.environ", reason="Pyomo not available")

pytestmark = pytest.mark.pyomo


def _coarse_discretization() -> PaperGDPDiscretization:
    """Return the small deterministic grid used by solver smoke tests."""
    return PaperGDPDiscretization(n_z=3, nfe_per_phase=2, ncp=2)


def _gdp_solvers_available() -> bool:
    return all(
        pyo.SolverFactory(name).available(exception_flag=False)
        for name in ("glpk", "ipopt")
    )


def _require_gdp_solvers() -> None:
    if not _gdp_solvers_available():
        pytest.skip(
            "Paper GDP solves require IPOPT "
            "(`idaes get-extensions --extra petsc`) and GLPK "
            "(`sudo apt-get install glpk-utils` or "
            "`conda install -c conda-forge glpk`)."
        )


def test_problem1_builds_two_free_unseeded_policy_disjunctions() -> None:
    """Problem 1 chooses between Policies 1 and 2 in both phases."""
    model = create_paper_problem1_gdp_model(discretization=_coarse_discretization())

    assert list(model.phases) == [1, 2]
    assert list(model.policy_names) == [POLICY_MAX_HEAT, POLICY_TEMPERATURE]
    assert len(model.policy_choice) == 2
    assert len(model.no_immediate_repeat) == 2
    for phase_index in model.phases:
        for policy_name in model.policy_names:
            indicator = model.policy[phase_index, policy_name].indicator_var
            assert not indicator.fixed
            assert indicator.value is None


def test_problem2_builds_three_free_unseeded_policy_disjunctions() -> None:
    """Problem 2 exposes all three policies without prescribing their order."""
    model = create_paper_problem2_gdp_model(discretization=_coarse_discretization())

    assert list(model.phases) == [1, 2, 3]
    assert list(model.policy_names) == [
        POLICY_MAX_HEAT,
        POLICY_TEMPERATURE,
        POLICY_VELOCITY,
    ]
    assert len(model.policy_choice) == 3
    assert len(model.no_immediate_repeat) == 6
    for disjunct in model.policy.values():
        assert not disjunct.indicator_var.fixed
        assert disjunct.indicator_var.value is None


def test_problem2_contains_no_constraint_that_forces_a_policy_sequence() -> None:
    """Only the no-repeat rule may constrain policy indicator binaries."""
    from pyomo.core.expr.visitor import identify_variables

    model = create_paper_problem2_gdp_model(discretization=_coarse_discretization())
    indicators = {
        id(disjunct.binary_indicator_var) for disjunct in model.policy.values()
    }

    for constraint in model.component_data_objects(
        pyo.Constraint,
        active=True,
        descend_into=True,
    ):
        binary_ids = {
            id(variable)
            for variable in identify_variables(constraint.body)
            if variable.is_binary()
        }
        if constraint.parent_component() is model.no_immediate_repeat:
            assert binary_ids
        else:
            assert indicators.isdisjoint(binary_ids)


def test_phase_continuity_covers_interface_and_every_temperature_state() -> None:
    """Every phase handoff preserves ``S`` [m] and ``T`` [K]."""
    model = create_paper_problem2_gdp_model(discretization=_coarse_discretization())

    assert len(model.interface_continuity) == 2
    assert len(model.temperature_continuity) == 2 * len(model.z)
    transition = model.interface_continuity[1]
    phase_1 = model.phase[1]
    phase_2 = model.phase[2]
    phase_1.S[phase_1.t.last()].set_value(1.0e-3)
    phase_2.S[phase_2.t.first()].set_value(2.0e-3)
    assert np.isclose(pyo.value(transition.body), -1.0e-3)
    phase_2.S[phase_2.t.first()].set_value(1.0e-3)
    assert np.isclose(pyo.value(transition.body), 0.0)


def test_no_repeat_constraint_detects_a_forced_repeated_mode() -> None:
    """A forced adjacent repeat violates the explicit sequence constraint."""
    model = create_paper_problem2_gdp_model(discretization=_coarse_discretization())
    model.policy[1, POLICY_MAX_HEAT].binary_indicator_var.set_value(1)
    model.policy[2, POLICY_MAX_HEAT].binary_indicator_var.set_value(1)

    constraint = model.no_immediate_repeat[1, POLICY_MAX_HEAT]
    assert pyo.value(constraint.body) == 2
    assert pyo.value(constraint.upper) == 1


def test_policy_disjuncts_encode_the_three_physical_equalities() -> None:
    """Each active mode constrains its intended physical quantity and units."""
    model = create_paper_problem2_gdp_model(discretization=_coarse_discretization())
    config = PaperPrimaryDryingConfig()
    settings = model._paper_problem_settings
    derived = model._paper_derived
    phase = model.phase[2]
    tau = phase.t.last()

    max_heat = model.policy[2, POLICY_MAX_HEAT].policy_equality[tau]
    phase.Tb[tau].set_value(settings.shelf_temperature_max - 3.0)
    assert np.isclose(
        pyo.value(max_heat.body) - pyo.value(max_heat.lower),
        -3.0,
    )

    temperature = model.policy[2, POLICY_TEMPERATURE].policy_equality[tau]
    phase.T[len(model.z) - 1, tau].set_value(settings.temperature_limit - 2.0)
    assert np.isclose(
        pyo.value(temperature.body) - pyo.value(temperature.lower),
        -2.0,
    )

    phase.S[tau].set_value(2.0e-3)
    resistance_m_per_s = product_resistance(2.0e-3, config)
    target_pressure_Pa = config.chamber_water_pressure + (
        settings.interface_velocity_limit
        * (derived.frozen_density - config.dried_region_density)
        * resistance_m_per_s
    )
    phase.T[0, tau].set_value(
        temperature_for_saturation_pressure(target_pressure_Pa, config)
    )
    velocity = model.policy[2, POLICY_VELOCITY].policy_equality[tau]
    assert abs(pyo.value(velocity.body) - pyo.value(velocity.lower)) <= 1.0e-10


def test_duration_initialization_can_change_without_seeding_policy_identity() -> None:
    """Alternative continuous starts leave every discrete choice unset."""
    model = create_paper_problem2_gdp_model(
        discretization=_coarse_discretization(),
        phase_duration_weights=(3.0, 2.0, 1.0),
    )
    durations_s = np.asarray(
        [pyo.value(model.phase[p].duration_s) for p in model.phases]
    )

    assert np.allclose(durations_s / np.sum(durations_s), [0.5, 1.0 / 3.0, 1.0 / 6.0])
    assert all(
        disjunct.indicator_var.value is None for disjunct in model.policy.values()
    )


@pytest.mark.parametrize(
    "weights, message",
    [
        ((1.0, 2.0), "must contain 3 values"),
        ((1.0, 0.0, 2.0), "finite and positive"),
        ((1.0, np.nan, 2.0), "finite and positive"),
    ],
)
def test_duration_initialization_rejects_invalid_weights(weights, message) -> None:
    with pytest.raises(ValueError, match=message):
        create_paper_problem2_gdp_model(
            discretization=_coarse_discretization(),
            phase_duration_weights=weights,
        )


@pytest.mark.slow
def test_problem1_gdp_selects_policy_1_then_2_without_indicator_seed() -> None:
    """GDPopt recovers Problem 1's published sequence from free indicators."""
    _require_gdp_solvers()
    result = solve_paper_problem1_gdp(
        discretization=_coarse_discretization(),
        time_limit_s=180.0,
    )

    assert result["metadata"]["termination_condition"] == "optimal"
    assert result["metadata"]["global_optimality_certified"] is False
    assert result["policies"]["indicator_sequence"] == (
        POLICY_MAX_HEAT,
        POLICY_TEMPERATURE,
    )
    assert np.isclose(result["metrics"]["complete_drying_time_hr"], 6.2, atol=0.15)
    assert np.isclose(result["policies"]["switch_times_hr"][0], 2.4, atol=0.15)


@pytest.mark.slow
def test_problem2_gdp_selects_policy_3_1_2_from_two_neutral_initializations() -> None:
    """Discrete and continuous initialization changes preserve the GDP result."""
    _require_gdp_solvers()
    discretization = _coarse_discretization()
    default = solve_paper_problem2_gdp(
        discretization=discretization,
        time_limit_s=180.0,
    )
    alternative = solve_paper_problem2_gdp(
        discretization=discretization,
        phase_duration_weights=(3.0, 2.0, 1.0),
        init_algorithm="no_init",
        time_limit_s=180.0,
    )
    expected = (POLICY_VELOCITY, POLICY_MAX_HEAT, POLICY_TEMPERATURE)

    for result in (default, alternative):
        assert result["metadata"]["termination_condition"] == "optimal"
        assert result["policies"]["indicator_sequence"] == expected
        assert np.isclose(result["metrics"]["complete_drying_time_hr"], 8.9, atol=0.15)
        classifier_labels = tuple(
            segment["label"]
            for segment in result["policies"]["continuous_classifier"]["segments"]
            if segment["label"] != "unclassified"
        )
        assert classifier_labels == expected

    continuous = solve_paper_problem2(
        discretization=PaperDiscretization(n_z=3, nfe=6, ncp=2),
        initialization=None,
        require_success=True,
    )
    continuous_labels = tuple(
        segment["label"] for segment in continuous["policies"]["segments"]
    )
    assert continuous_labels == expected
    assert np.isclose(
        default["metrics"]["solver_endpoint_time_hr"],
        continuous["metrics"]["drying_time_hr"],
        atol=0.01,
    )
    gdp_time_hr = default["states"]["time_hr"]
    continuous_time_hr = continuous["states"]["time_hr"]
    assert (
        np.max(
            np.abs(
                default["states"]["interface_position_m"]
                - np.interp(
                    gdp_time_hr,
                    continuous_time_hr,
                    continuous["states"]["interface_position_m"],
                )
            )
        )
        <= 1.0e-5
    )
    assert (
        np.max(
            np.abs(
                default["states"]["max_temperature_K"]
                - np.interp(
                    gdp_time_hr,
                    continuous_time_hr,
                    continuous["states"]["max_temperature_K"],
                )
            )
        )
        <= 0.5
    )
    post_start = gdp_time_hr >= 0.5
    assert (
        np.max(
            np.abs(
                default["controls"]["shelf_temperature_K"][post_start]
                - np.interp(
                    gdp_time_hr[post_start],
                    continuous_time_hr,
                    continuous["controls"]["shelf_temperature_K"],
                )
            )
        )
        <= 1.0
    )

    assert np.allclose(
        default["policies"]["switch_times_hr"],
        alternative["policies"]["switch_times_hr"],
        atol=1.0e-8,
    )
    for interval, published_time_hr in zip(
        default["policies"]["switch_intervals_hr"],
        (2.0, 3.9),
    ):
        assert interval[0] <= published_time_hr + 0.1
        assert interval[1] >= published_time_hr - 0.1


@pytest.mark.slow
def test_problem2_gdp_mesh_refinement_preserves_solution_and_tightens_switches() -> (
    None
):
    """A finer phase grid keeps the mode order and narrows switch intervals."""
    _require_gdp_solvers()
    coarse = solve_paper_problem2_gdp(
        discretization=_coarse_discretization(),
        time_limit_s=180.0,
    )
    refined = solve_paper_problem2_gdp(
        discretization=PaperGDPDiscretization(n_z=3, nfe_per_phase=4, ncp=2),
        time_limit_s=240.0,
    )
    expected = (POLICY_VELOCITY, POLICY_MAX_HEAT, POLICY_TEMPERATURE)

    assert coarse["policies"]["indicator_sequence"] == expected
    assert refined["policies"]["indicator_sequence"] == expected
    assert np.isclose(
        coarse["metrics"]["complete_drying_time_hr"],
        refined["metrics"]["complete_drying_time_hr"],
        atol=0.02,
    )
    coarse_widths = [
        upper - lower for lower, upper in coarse["policies"]["switch_intervals_hr"]
    ]
    refined_widths = [
        upper - lower for lower, upper in refined["policies"]["switch_intervals_hr"]
    ]
    assert np.all(np.asarray(refined_widths) < np.asarray(coarse_widths))
    assert np.allclose(
        refined["policies"]["switch_times_hr"],
        (2.0, 3.9),
        atol=0.25,
    )
