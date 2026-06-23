from __future__ import annotations

from typing import Dict

import numpy as np
import pytest

from lyopronto import constant, functions

pyo = pytest.importorskip("pyomo.environ")

from lyopronto.pyomo_models.advanced import (
    create_design_space_feasibility_model,
    create_design_space_grid_models,
    create_multivial_optimization_model,
    create_parameter_estimation_model,
    create_robust_optimization_model,
    create_sensitivity_analysis_models,
)

pytestmark = pytest.mark.pyomo


@pytest.fixture
def advanced_case() -> Dict[str, object]:
    return {
        "vial": {"Av": 3.8, "Ap": 3.14, "Vfill": 2.0},
        "product": {
            "cSolid": 0.05,
            "R0": 1.4,
            "A1": 16.0,
            "A2": 0.05,
            "T_pr_crit": -15.0,
        },
        "ht": {"KC": 2.75e-4, "KP": 8.93e-4, "KD": 0.46},
        "pchamber": {
            "min": 0.05,
            "max": 0.5,
            "setpt": np.array([0.15]),
            "dt_setpt": np.array([1800.0]),
            "ramp_rate": 0.5,
        },
        "tshelf": {
            "min": -45.0,
            "max": 50.0,
            "init": -35.0,
            "setpt": np.array([20.0]),
            "dt_setpt": np.array([1800.0]),
            "ramp_rate": 1.0,
        },
        "eq_cap": {"a": -0.182, "b": 11.7},
        "nvial": 398,
    }


def _rp(product: Dict[str, float], lck: float) -> float:
    return float(functions.Rp_FUN(lck, product["R0"], product["A1"], product["A2"]))


def _kv(ht: Dict[str, float], pch: float) -> float:
    return float(functions.Kv_FUN(ht["KC"], ht["KP"], ht["KD"], pch))


def test_parameter_estimation_model_uses_synthetic_resistance_and_kv_targets(advanced_case):
    vial = advanced_case["vial"]
    product = advanced_case["product"]
    ht = advanced_case["ht"]
    observations = []

    for lck, pch, tsub in [(0.0, 0.10, -30.0), (0.15, 0.12, -28.0), (0.30, 0.14, -26.0)]:
        rp = _rp(product, lck)
        psub = float(functions.Vapor_pressure(tsub))
        observations.append(
            {
                "Lck": lck,
                "Pch": pch,
                "Tsub": tsub,
                "Rp": rp,
                "Kv": _kv(ht, pch),
                "dmdt": vial["Ap"] / rp / constant.kg_To_g * (psub - pch),
            }
        )

    model = create_parameter_estimation_model(
        vial,
        product,
        ht,
        observations,
        residual_weights={"dmdt": 1.0e6},
    )

    assert model.advanced_workflow == "parameter_estimation"
    assert model.estimated_parameters == ("R0", "A1", "A2", "KC", "KP", "KD")
    assert set(model.residual_targets) == {
        "Rp[0]",
        "Rp[1]",
        "Rp[2]",
        "Kv[0]",
        "Kv[1]",
        "Kv[2]",
        "dmdt[0]",
        "dmdt[1]",
        "dmdt[2]",
    }
    assert pyo.value(model.obj.expr) == pytest.approx(0.0, abs=1.0e-14)


def test_design_space_feasibility_model_fixes_controls_and_capacity(advanced_case):
    model = create_design_space_feasibility_model(
        advanced_case["vial"],
        advanced_case["product"],
        advanced_case["ht"],
        pch_profile=[0.12, 0.12, 0.12],
        tsh_profile=[-35.0, -30.0, -25.0],
        n_steps=2,
        dt=0.5,
        final_dried_fraction=0.10,
        eq_cap=advanced_case["eq_cap"],
        nvial=advanced_case["nvial"],
    )

    assert model.advanced_workflow == "design_space_feasibility"
    assert model.fixed_controls == ("Pch", "Tsh")
    assert not model.obj.active
    assert model.feasibility_objective.active
    assert hasattr(model, "fixed_chamber_pressure_profile")
    assert hasattr(model, "fixed_shelf_temperature_profile")
    assert hasattr(model, "product_temperature_limit")
    assert hasattr(model, "equipment_capability")
    assert pyo.value(model.fixed_Pch[0]) == pytest.approx(0.12)
    assert pyo.value(model.fixed_Tsh[2]) == pytest.approx(-25.0)


def test_design_space_grid_models_tag_each_candidate_point(advanced_case):
    models = create_design_space_grid_models(
        advanced_case["vial"],
        advanced_case["product"],
        advanced_case["ht"],
        pressure_values=[0.10, 0.20],
        shelf_temperature_values=[-35.0, -25.0],
        n_steps=1,
        dt=0.5,
        final_dried_fraction=0.05,
    )

    assert set(models) == {
        (0.10, -35.0),
        (0.10, -25.0),
        (0.20, -35.0),
        (0.20, -25.0),
    }
    for point, model in models.items():
        assert model.advanced_workflow == "design_space_feasibility"
        assert model.design_space_point == point
        assert pyo.value(model.fixed_Pch[0]) == pytest.approx(point[0])
        assert pyo.value(model.fixed_Tsh[0]) == pytest.approx(point[1])


def test_sensitivity_analysis_models_tag_baseline_and_parameter_perturbations(advanced_case):
    models = create_sensitivity_analysis_models(
        advanced_case["vial"],
        advanced_case["product"],
        advanced_case["ht"],
        pch_profile=[0.12, 0.12, 0.12],
        tsh_profile=[-35.0, -30.0, -25.0],
        parameter_perturbations={"R0": [-0.10, 0.10], "KC": [0.20]},
        n_steps=2,
        dt=0.5,
        final_dried_fraction=0.10,
        eq_cap=advanced_case["eq_cap"],
        nvial=advanced_case["nvial"],
    )

    assert set(models) == {
        ("baseline", 0.0),
        ("R0", -0.10),
        ("R0", 0.10),
        ("KC", 0.20),
    }

    baseline = models[("baseline", 0.0)]
    assert baseline.advanced_workflow == "sensitivity_analysis"
    assert baseline.sensitivity_parameter == "baseline"
    assert baseline.sensitivity_difference_denominator is None
    assert hasattr(baseline, "fixed_chamber_pressure_profile")

    low_r0 = models[("R0", -0.10)]
    assert low_r0.sensitivity_parameter == "R0"
    assert low_r0.sensitivity_perturbation_fraction == pytest.approx(-0.10)
    assert low_r0.sensitivity_base_value == pytest.approx(advanced_case["product"]["R0"])
    assert low_r0.sensitivity_perturbed_value == pytest.approx(
        advanced_case["product"]["R0"] * 0.90
    )
    assert low_r0.sensitivity_difference_denominator == pytest.approx(
        -0.10 * advanced_case["product"]["R0"]
    )
    assert pyo.value(low_r0.R0) == pytest.approx(advanced_case["product"]["R0"] * 0.90)

    high_kc = models[("KC", 0.20)]
    assert pyo.value(high_kc.KC) == pytest.approx(advanced_case["ht"]["KC"] * 1.20)


def test_sensitivity_analysis_rejects_unknown_parameter(advanced_case):
    with pytest.raises(KeyError, match="unknown parameter"):
        create_sensitivity_analysis_models(
            advanced_case["vial"],
            advanced_case["product"],
            advanced_case["ht"],
            pch_profile=[0.12, 0.12],
            tsh_profile=[-35.0, -30.0],
            parameter_perturbations={"missing": [0.10]},
            n_steps=1,
            dt=0.5,
            final_dried_fraction=0.05,
        )


def test_multivial_optimization_model_exposes_batch_capacity_margin(advanced_case):
    model = create_multivial_optimization_model(
        advanced_case["vial"],
        advanced_case["product"],
        advanced_case["ht"],
        advanced_case["pchamber"],
        advanced_case["tshelf"],
        n_steps=2,
        dt=0.5,
        mode="joint",
        final_dried_fraction=0.10,
        eq_cap=advanced_case["eq_cap"],
        nvial=advanced_case["nvial"],
    )

    assert model.advanced_workflow == "multi_vial_optimization"
    assert model.batch_capacity_basis == "nvial*dmdt <= eq_cap.a + eq_cap.b*Pch"
    assert hasattr(model, "equipment_capability")

    expected_total_rate = pyo.value(model.nvial * model.dmdt[0])
    expected_capacity = pyo.value(model.eq_cap_a + model.eq_cap_b * model.Pch[0])
    assert pyo.value(model.total_sublimation_rate[0]) == pytest.approx(expected_total_rate)
    assert pyo.value(model.equipment_capacity_limit[0]) == pytest.approx(expected_capacity)
    assert pyo.value(model.capacity_margin[0]) == pytest.approx(
        expected_capacity - expected_total_rate
    )


def test_multivial_optimization_requires_positive_vial_count(advanced_case):
    with pytest.raises(ValueError, match="nvial must be positive"):
        create_multivial_optimization_model(
            advanced_case["vial"],
            advanced_case["product"],
            advanced_case["ht"],
            advanced_case["pchamber"],
            advanced_case["tshelf"],
            n_steps=2,
            dt=0.5,
            mode="joint",
            eq_cap=advanced_case["eq_cap"],
            nvial=0,
        )


def test_robust_optimization_model_shares_controls_and_tracks_scenario_margins(advanced_case):
    scenarios = {
        "nominal": {},
        "high_resistance": {"product": {"R0": advanced_case["product"]["R0"] * 1.10}},
        "low_capacity": {"eq_cap": {"a": -0.20}},
    }

    model = create_robust_optimization_model(
        advanced_case["vial"],
        advanced_case["product"],
        advanced_case["ht"],
        advanced_case["pchamber"],
        advanced_case["tshelf"],
        scenarios,
        n_steps=2,
        dt=0.5,
        mode="joint",
        final_dried_fraction=0.10,
        eq_cap=advanced_case["eq_cap"],
        nvial=advanced_case["nvial"],
    )

    assert model.advanced_workflow == "robust_optimization"
    assert model.robust_objective == "minimize_worst_case_sum_Pch_minus_Psub"
    assert model.reference_scenario == "nominal"
    assert set(model.SCENARIOS) == {"nominal", "high_resistance", "low_capacity"}
    assert model.optimized_controls == ("Pch", "Tsh")
    assert model.obj.active
    assert len(model.shared_chamber_pressure) == 6
    assert len(model.shared_shelf_temperature) == 6
    assert len(model.worst_case_objective_bound) == 3

    nominal = model.scenario_blocks["nominal"]
    high_resistance = model.scenario_blocks["high_resistance"]
    low_capacity = model.scenario_blocks["low_capacity"]

    assert not nominal.obj.active
    assert pyo.value(high_resistance.R0) == pytest.approx(
        advanced_case["product"]["R0"] * 1.10
    )
    assert pyo.value(low_capacity.eq_cap_a) == pytest.approx(-0.20)
    assert low_capacity.batch_capacity_basis == "nvial*dmdt <= eq_cap.a + eq_cap.b*Pch"

    expected_total_rate = pyo.value(low_capacity.nvial * low_capacity.dmdt[0])
    expected_capacity = pyo.value(low_capacity.eq_cap_a + low_capacity.eq_cap_b * low_capacity.Pch[0])
    assert pyo.value(low_capacity.total_sublimation_rate[0]) == pytest.approx(
        expected_total_rate
    )
    assert pyo.value(low_capacity.equipment_capacity_limit[0]) == pytest.approx(
        expected_capacity
    )
    assert pyo.value(low_capacity.capacity_margin[0]) == pytest.approx(
        expected_capacity - expected_total_rate
    )


def test_robust_optimization_requires_scenarios(advanced_case):
    with pytest.raises(ValueError, match="scenarios must contain at least one scenario"):
        create_robust_optimization_model(
            advanced_case["vial"],
            advanced_case["product"],
            advanced_case["ht"],
            advanced_case["pchamber"],
            advanced_case["tshelf"],
            {},
            n_steps=2,
            dt=0.5,
            mode="joint",
        )
