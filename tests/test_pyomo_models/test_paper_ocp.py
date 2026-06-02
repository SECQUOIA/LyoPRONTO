# Copyright (C) 2026, SECQUOIA

"""Tests for the paper-reference Pyomo OCP benchmark."""

import subprocess
import sys

import numpy as np
import pytest
from lyopronto.pyomo_models.paper_ocp import (
    PaperDiscretization,
    PaperPrimaryDryingConfig,
    classify_paper_policies,
    compare_paper_problem1_trajectories,
    create_paper_problem1_model,
    derive_primary_drying_parameters,
    generate_problem1_policy_initialization,
    initialize_paper_problem1_from_trajectory,
    interface_velocity,
    load_upstream_matlab_trajectory,
    product_resistance,
    saturation_pressure,
    solve_paper_problem1,
    sublimation_flux,
)

pyo = pytest.importorskip("pyomo.environ", reason="Pyomo not available")

pytestmark = pytest.mark.pyomo


def _ipopt_available():
    try:
        from idaes.core.solvers import get_solver

        return get_solver("ipopt").available()
    except Exception:
        try:
            return pyo.SolverFactory("ipopt").available(False)
        except Exception:
            return False


def test_default_parameter_translation_matches_upstream_processing():
    config = PaperPrimaryDryingConfig()
    derived = derive_primary_drying_parameters(config, n_z=20)

    assert np.isclose(derived.solution_density, 1018.86102386582)
    assert np.isclose(derived.frozen_density, 936.7900511787848)
    assert np.isclose(derived.frozen_heat_capacity, 2064.6)
    assert np.isclose(derived.frozen_conductivity, 2.1438)
    assert np.isclose(derived.frozen_diffusivity, 1.1084243905880022e-6)
    assert np.isclose(derived.cross_section_area, 4.523893421169302e-4)
    assert np.isclose(derived.product_height, 7.2124292981419705e-3)
    assert len(derived.psi) == 20
    assert np.isclose(derived.dpsi, 1.0 / 19.0)


def test_equation_helpers_match_upstream_formula_values():
    config = PaperPrimaryDryingConfig()
    derived = derive_primary_drying_parameters(config, n_z=20)

    assert np.isclose(saturation_pressure(228.0, config), 7.112217181578972)
    assert np.isclose(saturation_pressure(243.0, config), 37.491783814828466)

    resistance = product_resistance(0.005, config)
    expected_resistance = config.resistance_0 + config.resistance_1 * 0.005 / (
        1.0 + config.resistance_2 * 0.005
    )
    assert np.isclose(resistance, expected_resistance)

    flux = sublimation_flux(228.0, 0.0, config)
    expected_flux = (saturation_pressure(228.0, config) - 3.0) / config.resistance_0
    assert np.isclose(flux, expected_flux)

    velocity = interface_velocity(228.0, 0.0, config, derived)
    assert np.isclose(velocity, flux / (derived.frozen_density - 215.0))


def test_problem1_model_constructs_with_collocation():
    discretization = PaperDiscretization(n_z=5, nfe=4, ncp=2)
    model = create_paper_problem1_model(discretization=discretization)

    assert len(list(model.z)) == 5
    assert len(list(model.t)) == 4 * 2 + 1
    assert hasattr(model, "T")
    assert hasattr(model, "S")
    assert hasattr(model, "Tb")
    assert hasattr(model, "temperature_ode")
    assert len(model.product_temperature_limit) == len(list(model.t))
    assert len(model.nonnegative_sublimation_flux) == len(list(model.t))
    assert hasattr(model, "terminal_drying")
    assert hasattr(model, "objective")

    lb, ub = model.Tb[next(iter(model.t))].bounds
    assert lb == 228.0
    assert ub == 273.0


def test_problem1_model_initial_values_are_extractable():
    discretization = PaperDiscretization(n_z=5, nfe=3, ncp=2)
    model = create_paper_problem1_model(discretization=discretization)

    t_points = sorted(model.t)
    assert pyo.value(model.S[t_points[0]]) == 0.0
    assert pyo.value(model.S[t_points[-1]]) > 0.0
    assert pyo.value(model.t_final) == PaperPrimaryDryingConfig().problem1_time_guess


def test_problem1_model_constrains_sublimation_flux_nonnegative():
    config = PaperPrimaryDryingConfig()
    discretization = PaperDiscretization(n_z=5, nfe=3, ncp=2)
    model = create_paper_problem1_model(config=config, discretization=discretization)

    for t in model.t:
        constraint = model.nonnegative_sublimation_flux[t]
        assert constraint.lower == config.chamber_water_pressure
        assert constraint.upper is None

    first_time = next(iter(model.t))
    model.T[0, first_time].set_value(discretization.temperature_lower_bound)
    assert pyo.value(model.nonnegative_sublimation_flux[first_time].body) < (
        config.chamber_water_pressure
    )


def test_policy_classifier_detects_problem1_sequence():
    result = {
        "states": {
            "time_hr": np.array([0.0, 1.0, 2.0, 3.0, 4.0]),
            "max_temperature_K": np.array([228.0, 235.0, 241.0, 242.8, 243.0]),
        },
        "controls": {
            "shelf_temperature_K": np.array([273.0, 273.0, 273.0, 265.0, 258.0]),
        },
        "problem": {
            "temperature_limit_K": 243.0,
            "shelf_temperature_max_K": 273.0,
        },
    }

    policies = classify_paper_policies(result, tolerances={"temperature_K": 0.3})

    assert policies["segments"][0]["label"] == "policy_1_max_heat_input"
    assert policies["segments"][1]["label"] == "policy_2_temperature_tracking"
    assert policies["switch_times_hr"] == [3.0]


def test_policy_initialization_matches_upstream_policy1_event():
    trajectory = generate_problem1_policy_initialization(
        discretization=PaperDiscretization(n_z=20),
        n_time_points=80,
    )

    assert np.isclose(
        trajectory["metrics"]["policy1_switch_time_hr"],
        2.363310733077,
        atol=0.03,
    )
    assert trajectory["policies"]["segments"][0]["label"] == "policy_1_max_heat_input"
    assert trajectory["policies"]["segments"][1]["label"] == (
        "policy_2_temperature_tracking"
    )
    assert trajectory["metrics"]["terminal_drying_fraction"] >= 0.994


def test_initialize_model_from_policy_trajectory_sets_consistent_values():
    discretization = PaperDiscretization(n_z=5, nfe=4, ncp=2)
    trajectory = generate_problem1_policy_initialization(
        discretization=discretization,
        n_time_points=80,
    )
    model = create_paper_problem1_model(discretization=discretization)

    initialize_paper_problem1_from_trajectory(model, trajectory)

    t_points = sorted(model.t)
    assert np.isclose(
        pyo.value(model.t_final),
        trajectory["metrics"]["drying_time_s"],
    )
    assert np.isclose(
        pyo.value(model.S[t_points[-1]]),
        trajectory["states"]["interface_position_m"][-1],
        atol=1e-7,
    )
    assert pyo.value(model.Tb[t_points[0]]) == PaperPrimaryDryingConfig().shelf_temperature_max
    assert pyo.value(model.Tb[t_points[-1]]) < PaperPrimaryDryingConfig().shelf_temperature_max


def test_load_upstream_matlab_trajectory_from_segment_file(tmp_path):
    from scipy.io import savemat

    mat_path = tmp_path / "upstream_segment.mat"
    t = np.array([0.0, 50.0, 100.0])
    y = np.array(
        [
            [228.0, 228.1, 0.0],
            [229.0, 230.0, 1.0e-4],
            [230.0, 232.0, 2.0e-4],
        ]
    )
    savemat(
        mat_path,
        {
            "t": t,
            "y": y,
            "Tb": np.full_like(t, 273.0),
            "dSdt": np.array([1.0e-7, 1.1e-7, 1.2e-7]),
        },
    )

    trajectory = load_upstream_matlab_trajectory(mat_path)

    assert trajectory["metadata"]["source"] == "upstream_matlab"
    assert trajectory["states"]["temperature_K"].shape == (3, 2)
    assert np.allclose(trajectory["states"]["interface_position_m"], y[:, -1])
    assert np.allclose(trajectory["controls"]["shelf_temperature_K"], 273.0)


def test_load_upstream_matlab_trajectory_preserves_full_reference_fields(tmp_path):
    from scipy.io import savemat

    mat_path = tmp_path / "upstream_full.mat"
    t = np.array([0.0, 3600.0, 7200.0])
    temperature = np.array(
        [
            [228.0, 228.5, 229.0],
            [239.0, 240.0, 241.0],
            [241.0, 242.0, 243.0],
        ]
    )
    interface_position = np.array([0.0, 1.0e-3, 2.0e-3])
    savemat(
        mat_path,
        {
            "t": t,
            "T": temperature,
            "S": interface_position,
            "Tb": np.array([273.0, 270.0, 266.0]),
            "dSdt": np.array([2.0e-7, 3.0e-7, 4.0e-7]),
            "policy": np.array([1, 2]),
            "tsw": np.array([3600.0]),
        },
    )

    trajectory = load_upstream_matlab_trajectory(mat_path)

    assert trajectory["states"]["temperature_K"].shape == (3, 3)
    assert np.allclose(trajectory["states"]["interface_velocity_m_per_s"], [2.0e-7, 3.0e-7, 4.0e-7])
    assert np.allclose(trajectory["policies"]["raw_policy"], [1, 2])
    assert np.allclose(trajectory["policies"]["switch_times_hr"], [1.0])
    assert trajectory["metrics"]["drying_time_hr"] == 2.0
    assert trajectory["metrics"]["terminal_interface_position_m"] == 2.0e-3
    assert trajectory["problem"]["temperature_limit_K"] == 243.0


def test_load_upstream_matlab_trajectory_collapses_duplicate_switch_times(tmp_path):
    from scipy.io import savemat

    mat_path = tmp_path / "upstream_duplicate_switch.mat"
    savemat(
        mat_path,
        {
            "t": np.array([0.0, 3600.0, 3600.0, 7200.0]),
            "T": np.array(
                [
                    [228.0, 228.5, 229.0],
                    [239.0, 240.0, 241.0],
                    [239.1, 240.1, 241.1],
                    [241.0, 242.0, 243.0],
                ]
            ),
            "S": np.array([0.0, 1.0e-3, 1.1e-3, 2.0e-3]),
            "Tb": np.array([273.0, 270.0, 269.0, 266.0]),
            "dSdt": np.array([2.0e-7, 3.0e-7, 3.1e-7, 4.0e-7]),
            "policy": np.array([1, 2]),
            "tsw": np.array([3600.0]),
        },
    )

    trajectory = load_upstream_matlab_trajectory(mat_path)

    assert np.all(np.diff(trajectory["states"]["time_s"]) > 0.0)
    assert np.allclose(trajectory["states"]["time_s"], [0.0, 3600.0, 7200.0])
    assert np.allclose(
        trajectory["states"]["temperature_K"][1],
        [239.1, 240.1, 241.1],
    )
    assert np.isclose(trajectory["states"]["interface_position_m"][1], 1.1e-3)
    assert np.isclose(trajectory["controls"]["shelf_temperature_K"][1], 269.0)
    assert np.isclose(trajectory["states"]["interface_velocity_m_per_s"][1], 3.1e-7)


def test_compare_paper_problem1_trajectories_reports_required_metrics():
    upstream = {
        "states": {
            "time_s": np.array([0.0, 3600.0, 7200.0]),
            "max_temperature_K": np.array([228.0, 241.0, 243.0]),
            "interface_position_m": np.array([0.0, 1.0e-3, 2.0e-3]),
        },
        "metrics": {
            "drying_time_hr": 2.0,
            "terminal_interface_position_m": 2.0e-3,
            "max_product_temperature_K": 243.0,
        },
        "policies": {"switch_times_hr": np.array([1.0])},
    }
    pyomo_result = {
        "states": {
            "time_s": np.array([0.0, 3600.0, 7560.0]),
            "max_temperature_K": np.array([228.0, 241.5, 243.2]),
            "interface_position_m": np.array([0.0, 1.1e-3, 2.1e-3]),
        },
        "metrics": {
            "drying_time_hr": 2.1,
            "terminal_interface_position_m": 2.1e-3,
            "max_product_temperature_K": 243.2,
        },
        "policies": {"switch_times_hr": [1.1]},
    }

    comparison = compare_paper_problem1_trajectories(pyomo_result, upstream)

    assert np.isclose(comparison["drying_time_deviation_hr"], 0.1)
    assert np.isclose(comparison["first_switch_time_deviation_hr"], 0.1)
    assert np.isclose(comparison["terminal_interface_position_deviation_m"], 1.0e-4)
    assert np.isclose(comparison["peak_temperature_deviation_K"], 0.2)
    assert comparison["max_temperature_profile_max_abs_deviation_K"] > 0.0


def test_paper_problem1_reference_runner_writes_batch_safe_wrappers(tmp_path):
    import importlib.util
    from pathlib import Path

    script_path = (
        Path(__file__).resolve().parents[2]
        / "benchmarks"
        / "paper_problem1_reference.py"
    )
    spec = importlib.util.spec_from_file_location(
        "paper_problem1_reference",
        script_path,
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    upstream_root = tmp_path / "upstream"
    work_dir = tmp_path / "work"

    files = module.write_matlab_batch_files(work_dir, upstream_root)
    command = module.build_matlab_batch_command(
        "matlab",
        work_dir,
        upstream_root,
        tmp_path / "reference.mat",
    )

    wrapper_source = files["max_t"].read_text(encoding="utf-8")
    runner_source = files["runner"].read_text(encoding="utf-8")
    assert "matlab.desktop.editor.getActiveFilename" not in wrapper_source
    assert "pyfun_MaxT.py" in wrapper_source
    assert "pyrunfile" in wrapper_source
    assert "Sim_1stDrying_OCP" in runner_source
    assert "policy" in runner_source
    assert "tsw" in runner_source
    last_upstream_path = runner_source.index("addpath(fullfile(code_root, 'Sim_DAE'));")
    assert runner_source.rindex("addpath(runner_root, '-begin');") > last_upstream_path
    assert command[0] == "matlab"
    assert command[1] == "-batch"
    assert "run_paper_problem1_upstream_reference" in command[2]


def test_paper_problem1_reference_script_runs_from_source_checkout():
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "benchmarks" / "paper_problem1_reference.py"

    result = subprocess.run(
        [sys.executable, str(script_path), "--help"],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "Generate and compare Paper Problem 1" in result.stdout


@pytest.mark.slow
@pytest.mark.skipif(not _ipopt_available(), reason="IPOPT solver not available")
def test_problem1_coarse_solve_reaches_terminal_target_and_classifies_policy():
    discretization = PaperDiscretization(
        n_z=5,
        nfe=12,
        ncp=3,
        terminal_drying_fraction=0.995,
    )
    result = solve_paper_problem1(
        discretization=discretization,
        solver_options={
            "max_iter": 2000,
            "tol": 1.0e-5,
            "acceptable_tol": 1.0e-4,
            "print_level": 0,
        },
        require_success=True,
    )

    metrics = result["metrics"]
    policies = result["policies"]
    labels = policies["labels"]

    assert metrics["terminal_gap_m"] <= 1.0e-7
    assert metrics["max_temperature_violation_K"] <= 1.0e-3
    assert metrics["shelf_lower_violation_K"] <= 1.0e-6
    assert metrics["shelf_upper_violation_K"] <= 1.0e-6
    assert np.isclose(metrics["drying_time_hr"], 6.19, atol=0.35)
    assert "policy_1_max_heat_input" in labels
    assert "policy_2_temperature_tracking" in labels
    assert policies["segments"][0]["label"] == "policy_1_max_heat_input"
    assert policies["segments"][1]["label"] == "policy_2_temperature_tracking"
    assert np.isclose(policies["switch_times_hr"][0], 2.4, atol=0.35)


@pytest.mark.slow
@pytest.mark.skipif(not _ipopt_available(), reason="IPOPT solver not available")
def test_problem1_nz10_solve_matches_reference_policy_sequence():
    discretization = PaperDiscretization(
        n_z=10,
        nfe=12,
        ncp=3,
        terminal_drying_fraction=0.995,
    )
    result = solve_paper_problem1(
        discretization=discretization,
        solver_options={
            "max_iter": 3000,
            "tol": 1.0e-5,
            "acceptable_tol": 1.0e-4,
            "print_level": 0,
        },
        require_success=True,
    )

    metrics = result["metrics"]
    policies = result["policies"]

    assert result["metadata"]["status"] == "ok"
    assert metrics["terminal_gap_m"] <= 1.0e-7
    assert metrics["max_temperature_violation_K"] <= 2.0e-6
    assert np.isclose(metrics["drying_time_hr"], 6.19, atol=0.08)
    assert policies["segments"][0]["label"] == "policy_1_max_heat_input"
    assert policies["segments"][1]["label"] == "policy_2_temperature_tracking"
    assert np.isclose(policies["switch_times_hr"][0], 2.4, atol=0.12)


@pytest.mark.slow
@pytest.mark.skipif(not _ipopt_available(), reason="IPOPT solver not available")
def test_problem1_nz20_solve_matches_reference_policy_sequence():
    discretization = PaperDiscretization(
        n_z=20,
        nfe=12,
        ncp=3,
        terminal_drying_fraction=0.995,
    )
    result = solve_paper_problem1(
        discretization=discretization,
        solver_options={
            "max_iter": 5000,
            "max_cpu_time": 120,
            "tol": 1.0e-5,
            "acceptable_tol": 1.0e-3,
            "acceptable_iter": 5,
            "print_level": 0,
        },
        require_success=True,
    )

    metrics = result["metrics"]
    policies = result["policies"]

    assert result["metadata"]["status"] == "ok"
    assert metrics["terminal_gap_m"] <= 1.0e-7
    assert metrics["max_temperature_violation_K"] <= 2.0e-6
    assert metrics["shelf_lower_violation_K"] <= 1.0e-6
    assert metrics["shelf_upper_violation_K"] <= 1.0e-6
    assert np.isclose(metrics["drying_time_hr"], 6.19, atol=0.08)
    assert policies["segments"][0]["label"] == "policy_1_max_heat_input"
    assert policies["segments"][1]["label"] == "policy_2_temperature_tracking"
    assert np.isclose(policies["switch_times_hr"][0], 2.4, atol=0.12)
