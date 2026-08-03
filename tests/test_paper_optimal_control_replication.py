"""Tests for the Srisuma and Braatz (2025) optimal-control replication."""

from __future__ import annotations

import numpy as np
import pytest

from examples.paper_optimal_control_replication import (
    DEFAULT_CAPABILITY_SCALE,
    PAPER_REFERENCE,
    classify_vial_policies,
    paper_comparison_rows,
    paper_reference_deviation_percent,
    policy_label,
    run_paper_case,
    run_vial_policy_case,
    shelf_bound_contact_is_contiguous,
    shelf_bound_switch_brackets_hr,
    switch_brackets_contain_published,
    vial_policy_inputs,
)
from tests.pyomo_solver import require_pyomo_solver


def test_paper_reference_records_both_published_case_studies() -> None:
    """The reference block carries the limits and switch times from Section V."""
    problem1 = PAPER_REFERENCE["problem1"]
    problem2 = PAPER_REFERENCE["problem2"]

    assert problem1["temperature_limit_K"] == pytest.approx(243.0)
    assert problem1["shelf_temperature_bounds_K"] == (228.0, 273.0)
    assert problem1["switch_times_hr"] == (2.4,)

    assert problem2["temperature_limit_K"] == pytest.approx(240.0)
    assert problem2["interface_velocity_limit_m_per_s"] == pytest.approx(2.8e-7)
    assert problem2["shelf_temperature_bounds_K"] == (228.0, 260.0)
    assert problem2["switch_times_hr"] == (2.0, 3.9)
    assert problem2["drying_time_hr"] == pytest.approx(8.9)

    # The upstream Comparison.pdf is the only published timing for the
    # optimization-based route, and the notebook quotes it verbatim.
    benchmark = PAPER_REFERENCE["problem1_runtime_benchmark_s"]
    assert benchmark["opt_Ipopt1"] == pytest.approx(1015.84)
    assert benchmark["opt_Ipopt2"] == pytest.approx(64.60)
    assert benchmark["sim_DAE"] == pytest.approx(0.58)


def test_run_paper_case_rejects_unknown_problem() -> None:
    with pytest.raises(ValueError, match="unsupported paper problem"):
        run_paper_case("problem3")


def test_run_paper_case_rejects_nonpositive_timing_repeats() -> None:
    with pytest.raises(ValueError, match="timing_repeats"):
        run_paper_case("problem1", timing_repeats=0)


def test_vial_policy_inputs_scale_only_the_capability_line() -> None:
    """Scaling the condenser leaves the mannitol product case untouched."""
    baseline = vial_policy_inputs(capability_scale=1.0)
    scaled = vial_policy_inputs(capability_scale=0.16)

    assert baseline["eq_cap"] == {"a": -0.182, "b": 11.7}
    assert scaled["eq_cap"]["a"] == pytest.approx(-0.182 * 0.16)
    assert scaled["eq_cap"]["b"] == pytest.approx(11.7 * 0.16)
    assert scaled["product"] == baseline["product"]
    assert scaled["vial"] == baseline["vial"]
    assert scaled["nvial"] == 398


def test_classify_vial_policies_rejects_non_legacy_shapes() -> None:
    with pytest.raises(ValueError, match="seven-column"):
        classify_vial_policies(np.zeros((3, 5)), vial_policy_inputs())


def test_classify_vial_policies_identifies_each_active_constraint() -> None:
    """Each of the paper's three policies maps to one active vial-scale limit."""
    data = vial_policy_inputs(capability_scale=1.0, shelf_temperature_max_c=70.0)
    capability_kg_hr = data["eq_cap"]["a"] + data["eq_cap"]["b"] * 0.15
    product_area_m2 = data["vial"]["Ap"] * 1.0e-4
    capacity_flux = capability_kg_hr / (data["nvial"] * product_area_m2)

    # Columns: t, Tsub, Tbot, Tsh, Pch [mTorr], flux [kg/hr/m^2], % dried.
    table = np.array(
        [
            # Shelf pinned at its ceiling, nothing else active -> Policy 1.
            [0.0, -30.0, -25.0, 70.0, 150.0, 0.1 * capacity_flux, 0.0],
            # Sublimation load exactly at the equipment capability -> Policy 3.
            [1.0, -30.0, -25.0, 40.0, 150.0, capacity_flux, 20.0],
            # Product at its critical temperature -> Policy 2.
            [2.0, -20.0, -5.0, 40.0, 150.0, 0.1 * capacity_flux, 50.0],
            # Product limit wins when both it and the capability bind.
            [3.0, -20.0, -5.0, 40.0, 150.0, capacity_flux, 80.0],
            # Nothing active.
            [4.0, -30.0, -25.0, 40.0, 150.0, 0.1 * capacity_flux, 100.0],
        ]
    )

    result = classify_vial_policies(table, data)

    assert result["labels"] == [
        "policy_1_max_heat_input",
        "policy_3_interface_velocity_tracking",
        "policy_2_temperature_tracking",
        "policy_2_temperature_tracking",
        "unclassified",
    ]
    # Adjacent identical labels collapse into one segment.
    assert [segment["label"] for segment in result["segments"]] == [
        "policy_1_max_heat_input",
        "policy_3_interface_velocity_tracking",
        "policy_2_temperature_tracking",
        "unclassified",
    ]
    assert result["switch_times_hr"] == [1.0, 2.0, 4.0]
    assert result["capability_kg_hr"][0] == pytest.approx(capability_kg_hr)


def test_policy_label_falls_back_to_the_raw_name() -> None:
    assert policy_label("policy_1_max_heat_input").startswith("Policy 1")
    assert policy_label("something_else") == "something_else"


@pytest.mark.slow
def test_vial_case_reproduces_the_paper_problem_2_policy_sequence() -> None:
    """LyoPRONTO's sequential optimizer switches Policy 3 -> 1 -> 2."""
    run = run_vial_policy_case(dt=0.05, capability_scale=DEFAULT_CAPABILITY_SCALE)

    assert run.policy_sequence == PAPER_REFERENCE["problem2"]["policy_sequence"]
    assert len(run.switch_times_hr) == 2
    assert run.switch_times_hr[0] < run.switch_times_hr[1] < run.drying_time_hr
    assert run.trajectory[-1, 6] >= 100.0 - 1.0e-6
    # The scaled-down condenser is what makes Policy 3 reachable at all.
    load = run.policies["load_kg_hr"]
    capability = run.policies["capability_kg_hr"]
    assert np.max(load - capability) < 1.0e-6


@pytest.mark.pyomo
@pytest.mark.parametrize(
    ("problem", "expected_switches"),
    [("problem1", 1), ("problem2", 2)],
)
def test_paper_case_solves_and_recovers_the_published_policy_sequence(
    problem: str,
    expected_switches: int,
) -> None:
    require_pyomo_solver("ipopt")

    run = run_paper_case(problem, n_z=5, nfe=12)
    reference = PAPER_REFERENCE[problem]

    assert run.terminated_optimally
    assert run.policy_sequence == reference["policy_sequence"]
    assert abs(paper_reference_deviation_percent(run)) < 5.0
    assert len(shelf_bound_switch_brackets_hr(run)) == expected_switches

    metrics = run.solution["metrics"]
    assert metrics["max_temperature_violation_K"] < 1.0e-4
    if problem == "problem2":
        limit = reference["interface_velocity_limit_m_per_s"]
        assert metrics["max_post_initial_interface_velocity_m_per_s"] <= limit * (1.0 + 1.0e-6)


@pytest.mark.pyomo
def test_paper_comparison_rows_report_switches_as_brackets() -> None:
    """Switch rows carry an interval because collocation resolves no instant."""
    require_pyomo_solver("ipopt")

    run = run_paper_case("problem1", n_z=5, nfe=12)
    rows = paper_comparison_rows(run)

    assert rows[0]["quantity"] == "drying time [hr]"
    assert rows[0]["lyopronto_low"] == rows[0]["lyopronto_high"] == run.drying_time_hr
    assert rows[1]["quantity"] == "policy switch 1 [hr]"
    assert rows[1]["lyopronto_low"] < rows[1]["lyopronto_high"]
    assert rows[1]["paper"] == pytest.approx(2.4)


@pytest.mark.pyomo
def test_refining_the_time_mesh_brackets_the_published_switch_time() -> None:
    """The switch interval narrows onto the published 2.4 h as nfe grows."""
    require_pyomo_solver("ipopt")

    coarse = run_paper_case("problem1", n_z=20, nfe=24)
    fine = run_paper_case("problem1", n_z=20, nfe=36)

    (coarse_low, coarse_high), = shelf_bound_switch_brackets_hr(coarse)
    (fine_low, fine_high), = shelf_bound_switch_brackets_hr(fine)

    # The drying time is already converged; only the switch interval moves.
    assert fine.drying_time_hr == pytest.approx(coarse.drying_time_hr, abs=1.0e-3)
    assert coarse_low < coarse_high
    assert fine_low < fine_high
    assert switch_brackets_contain_published(fine) == [True]
    # The control sits on its bound as one unbroken run at these meshes.
    assert shelf_bound_contact_is_contiguous(fine)


@pytest.mark.pyomo
def test_cold_start_reaches_the_same_optimum_as_the_policy_warm_start() -> None:
    """The fast solve is not an artifact of the policy-sequenced initialization."""
    require_pyomo_solver("ipopt")

    warm = run_paper_case("problem1", n_z=5, nfe=12, initialization="policy")
    cold = run_paper_case("problem1", n_z=5, nfe=12, initialization=None)

    assert cold.terminated_optimally
    assert cold.initialization == "cold"
    assert cold.drying_time_hr == pytest.approx(warm.drying_time_hr, abs=1.0e-3)


@pytest.mark.serial
@pytest.mark.notebook
@pytest.mark.pyomo
def test_paper_optimal_control_replication_notebook_execution(repo_root) -> None:
    require_pyomo_solver("ipopt")
    papermill = pytest.importorskip("papermill")

    papermill.execute_notebook(
        repo_root / "docs/examples/paper_optimal_control_replication.ipynb",
        repo_root / "docs/examples/paper_optimal_control_replication_output.ipynb",
        parameters={
            # A coarse spatial mesh and a short sweep keep the smoke run quick
            # while still exercising every cell.
            "n_z": 5,
            "nfe": 12,
            "timing_repeats": 1,
            "mesh_sweep": [[5, 12], [10, 24]],
            "vial_dt": 0.05,
        },
    )
