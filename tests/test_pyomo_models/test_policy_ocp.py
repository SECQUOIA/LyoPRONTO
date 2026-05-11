# Copyright (C) 2026, SECQUOIA

"""Tests for the experimental LyoPRONTO policy OCP adapter."""

import numpy as np
import pytest
from lyopronto.pyomo_models.optimizers import create_optimizer_model
from lyopronto.pyomo_models.policy_ocp import (
    classify_lyopronto_policies,
    create_lyopronto_policy_ocp_model,
    extract_lyopronto_policy_solution,
)

pyo = pytest.importorskip("pyomo.environ", reason="Pyomo not available")

pytestmark = pytest.mark.pyomo


def _policy_inputs(standard_vial, standard_product, standard_ht):
    return {
        "vial": standard_vial,
        "product": standard_product,
        "ht": standard_ht,
        "Pchamber": {"setpt": [0.1], "dt_setpt": [180.0], "ramp_rate": 0.5},
        "Tshelf": {"min": -45.0, "max": 120.0},
        "eq_cap": {"a": -0.182, "b": 11.7},
        "nVial": 398,
    }


def test_policy_ocp_without_caps_matches_base_constraint_surface(
    standard_vial,
    standard_product,
    standard_ht,
):
    inputs = _policy_inputs(standard_vial, standard_product, standard_ht)

    base_model = create_optimizer_model(
        inputs["vial"],
        inputs["product"],
        inputs["ht"],
        inputs["vial"]["Vfill"],
        inputs["eq_cap"],
        inputs["nVial"],
        Pchamber=inputs["Pchamber"],
        Tshelf=inputs["Tshelf"],
        n_elements=3,
        control_mode="Tsh",
    )
    policy_model = create_lyopronto_policy_ocp_model(
        **inputs,
        n_elements=3,
    )

    base_constraints = {
        component.local_name
        for component in base_model.component_objects(pyo.Constraint, active=True)
    }
    policy_constraints = {
        component.local_name
        for component in policy_model.component_objects(pyo.Constraint, active=True)
    }

    assert policy_constraints == base_constraints
    assert not hasattr(policy_model, "sublimation_flux_cap")
    assert not hasattr(policy_model, "interface_velocity_cap")
    assert (
        policy_model._lyopronto_policy_problem["sublimation_flux_cap_kg_hr_m2"] is None
    )


def test_policy_ocp_adds_flux_cap_in_lyopronto_units(
    standard_vial,
    standard_product,
    standard_ht,
):
    inputs = _policy_inputs(standard_vial, standard_product, standard_ht)

    model = create_lyopronto_policy_ocp_model(
        **inputs,
        n_elements=3,
        sublimation_flux_cap_kg_hr_m2=350.0,
    )

    assert hasattr(model, "sublimation_flux_cap")
    assert len(model.sublimation_flux_cap) == len(list(model.t))
    first_time = sorted(model.t)[0]
    assert np.isclose(pyo.value(model.sublimation_flux_cap[first_time].upper), 350.0)
    assert model._lyopronto_policy_area_m2 == pytest.approx(
        standard_vial["Ap"] * 0.01**2
    )

    result = extract_lyopronto_policy_solution(model)
    assert result["problem"]["sublimation_flux_cap_kg_hr_m2"] == 350.0
    assert result["trajectory"].shape[1] == 7
    assert set(result) >= {
        "states",
        "controls",
        "metrics",
        "metadata",
        "problem",
        "config",
        "trajectory",
    }


def test_policy_classifier_detects_flux_cap_policy3():
    result = {
        "states": {
            "time_hr": np.array([0.0, 1.0, 2.0, 3.0, 4.0]),
            "product_temperature_C": np.array([-35.0, -31.0, -28.0, -25.02, -25.0]),
            "sublimation_flux_kg_hr_m2": np.array([5.0, 4.99, 4.0, 3.6, 3.1]),
            "interface_velocity_cm_per_hr": np.array([0.3, 0.3, 0.2, 0.2, 0.1]),
        },
        "controls": {
            "shelf_temperature_C": np.array([40.0, 80.0, 120.0, 120.0, 110.0]),
        },
        "problem": {
            "temperature_limit_C": -25.0,
            "shelf_temperature_max_C": 120.0,
            "sublimation_flux_cap_kg_hr_m2": 5.0,
            "interface_velocity_cap_cm_hr": None,
        },
    }

    policies = classify_lyopronto_policies(
        result,
        tolerances={
            "temperature_C": 0.05,
            "shelf_temperature_C": 0.05,
            "sublimation_flux_kg_hr_m2": 0.02,
        },
    )

    assert policies["segments"][0]["label"] == "policy_3_sublimation_flux_tracking"
    assert policies["segments"][1]["label"] == "policy_1_max_heat_input"
    assert policies["segments"][2]["label"] == "policy_2_product_temperature_tracking"
    assert policies["switch_times_hr"] == [2.0, 3.0]
