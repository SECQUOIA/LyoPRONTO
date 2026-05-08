"""Tests for benchmark tooling."""

import json
import os
import subprocess
import sys
from types import SimpleNamespace

import numpy as np
import pytest
from benchmarks import adapters
from benchmarks.scenarios import SCENARIOS
from benchmarks.schema import serialize
from benchmarks.validate import compute_residuals

ALLOWED_TRACKED_BENCHMARK_RESULTS = {
    "benchmarks/results/.gitignore",
    "benchmarks/results/README.md",
    "benchmarks/results/baseline_Pch_3x3_summary.jsonl",
    "benchmarks/results/baseline_Tsh_3x3_summary.jsonl",
}


def test_grid_cli_script_entrypoint_help(repo_root, tmp_path):
    env = os.environ.copy()
    env["MPLCONFIGDIR"] = str(tmp_path / "mpl")

    result = subprocess.run(
        [sys.executable, "benchmarks/grid_cli.py", "--help"],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Benchmark generation CLI" in result.stdout


def test_benchmark_results_tracks_only_policy_files(repo_root):
    result = subprocess.run(
        ["git", "ls-files", "benchmarks/results"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.skip(f"git ls-files unavailable: {result.stderr.strip()}")

    tracked_results = set(result.stdout.splitlines())

    assert tracked_results == ALLOWED_TRACKED_BENCHMARK_RESULTS


def test_benchmark_results_gitignore_blocks_generated_outputs(repo_root):
    generated_outputs = [
        "benchmarks/results/local_grid.jsonl",
        "benchmarks/results/archive/grid_ratio.png",
        "benchmarks/results/test/processed/summary.json",
    ]

    result = subprocess.run(
        ["git", "check-ignore", "--no-index", *generated_outputs],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode not in {0, 1}:
        pytest.skip(f"git check-ignore unavailable: {result.stderr.strip()}")

    assert result.returncode == 0, result.stderr
    assert set(result.stdout.splitlines()) == set(generated_outputs)

    allowed_result = subprocess.run(
        [
            "git",
            "check-ignore",
            "--no-index",
            "benchmarks/results/baseline_Tsh_3x3_summary.jsonl",
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert allowed_result.returncode == 1, allowed_result.stdout


def test_compute_residuals_uses_native_bools_and_checks_product_temperature():
    traj = np.array(
        [
            [0.0, -26.0, -25.0, -20.0, 100.0, 0.2, 0.0],
            [1.0, -25.0, -24.5, -18.0, 100.0, 0.1, 99.0],
        ]
    )

    metrics = compute_residuals(traj, product_critical_temp=-25.0)

    assert metrics["dryness_target_met"] is True
    assert metrics["product_temp_ok"] is False
    assert metrics["max_Tbot"] == -24.5


def test_serialize_emits_numpy_scalars_as_json_scalars_and_hashes_inputs():
    record = {
        "params": {"product.A1": 16.0, "ht.KC": 2.75e-4},
        "metrics": {"dryness_target_met": np.bool_(True)},
    }

    payload = json.loads(serialize(record))

    assert payload["metrics"]["dryness_target_met"] is True
    assert isinstance(payload["hash.inputs"], str)
    assert isinstance(payload["hash.record"], str)


def test_pyomo_adapter_rejects_non_optimal_metadata(monkeypatch):
    baseline = SCENARIOS["baseline"]
    fake_output = np.array(
        [
            [0.0, -26.0, -25.0, -20.0, 100.0, 0.2, 0.0],
            [1.0, -25.0, -25.0, -18.0, 100.0, 0.1, 99.0],
        ]
    )

    def fake_optimizer(*args, **kwargs):
        return {
            "output": fake_output,
            "metadata": {
                "status": "warning",
                "termination_condition": "infeasible",
                "objective_time_hr": 1.0,
            },
        }

    fake_pyomo = SimpleNamespace(optimize_Tsh_pyomo=fake_optimizer)
    monkeypatch.setattr(adapters, "_load_pyomo_optimizers", lambda: fake_pyomo)

    result = adapters.pyomo_adapter(
        "Tsh",
        baseline["vial"],
        baseline["product"],
        baseline["ht"],
        baseline["eq_cap"],
        baseline["nVial"],
        baseline,
    )

    assert result["success"] is False
    assert result["objective_time_hr"] is None
    assert "infeasible" in result["message"]


def test_pyomo_pch_adapter_uses_constant_fixed_shelf_profile(monkeypatch):
    baseline = SCENARIOS["baseline"]
    fake_output = np.array(
        [
            [0.0, -26.0, -25.0, -18.0, 100.0, 0.2, 0.0],
            [1.0, -25.0, -25.0, -18.0, 100.0, 0.1, 99.0],
        ]
    )
    seen = {}

    def fake_optimizer(*args, **kwargs):
        seen["Pchamber"] = args[3]
        seen["Tshelf"] = args[4]
        return {
            "output": fake_output,
            "metadata": {
                "status": "ok",
                "termination_condition": "optimal",
                "objective_time_hr": 1.0,
            },
        }

    fake_pyomo = SimpleNamespace(optimize_Pch_pyomo=fake_optimizer)
    monkeypatch.setattr(adapters, "_load_pyomo_optimizers", lambda: fake_pyomo)

    result = adapters.pyomo_adapter(
        "Pch",
        baseline["vial"],
        baseline["product"],
        baseline["ht"],
        baseline["eq_cap"],
        baseline["nVial"],
        baseline,
    )

    assert result["success"] is True
    assert seen["Pchamber"]["min"] == 0.05
    assert seen["Pchamber"]["max"] == 0.5
    assert seen["Tshelf"]["init"] == -18.0
    assert seen["Tshelf"]["init"] == seen["Tshelf"]["setpt"][0]
    assert len(seen["Tshelf"]["setpt"]) == 1


def test_ipopt_replay_adapter_reports_validation_metadata(monkeypatch):
    baseline = SCENARIOS["baseline"]
    scipy_trajectory = np.array(
        [
            [0.0, -26.0, -25.0, -20.0, 100.0, 0.2, 0.0],
            [1.0, -25.0, -25.0, -18.0, 100.0, 0.1, 99.0],
        ]
    )

    def fake_replay(scipy_output, *args, **kwargs):
        return {
            "output": scipy_output.copy(),
            "metadata": {
                "status": "ok",
                "termination_condition": "optimal",
                "objective_time_hr": 1.0,
                "n_points": 2,
                "max_constraint_residual": 1e-8,
                "residuals": {"energy_balance": {"max": 1e-8, "mean": 1e-9}},
                "max_scipy_trajectory_residual": 1e-8,
                "scipy_trajectory_residuals": {
                    "energy_balance": {"max": 1e-8, "mean": 1e-9}
                },
                "max_scipy_mesh_residual": 2e-8,
                "scipy_mesh_residuals": {"energy_balance": {"max": 2e-8, "mean": 2e-9}},
                "max_replay_solution_residual": 1e-10,
                "replay_solution_residuals": {
                    "energy_balance": {"max": 1e-10, "mean": 1e-11}
                },
            },
        }

    fake_pyomo = SimpleNamespace(replay_scipy_controls_with_ipopt=fake_replay)
    monkeypatch.setattr(adapters, "_load_pyomo_optimizers", lambda: fake_pyomo)

    result = adapters.ipopt_replay_adapter(
        "Tsh",
        baseline["vial"],
        baseline["product"],
        baseline["ht"],
        baseline["eq_cap"],
        baseline["nVial"],
        baseline,
        scipy_result={"trajectory": scipy_trajectory},
    )

    assert result["success"] is True
    assert result["discretization"]["method"] == "replay-fd"
    assert result["validation"]["kind"] == "scipy_control_replay"
    assert result["validation"]["max_constraint_residual"] == 1e-8
    assert result["validation"]["max_scipy_trajectory_residual"] == 1e-8
    assert result["validation"]["max_scipy_mesh_residual"] == 2e-8
    assert result["validation"]["max_replay_solution_residual"] == 1e-10
    assert result["validation"]["trajectory_comparison"]["matched"] is True
