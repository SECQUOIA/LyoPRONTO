"""Tests for benchmark tooling."""

import json
import os
import subprocess
import sys
from types import SimpleNamespace

import numpy as np
import pytest
from benchmarks import adapters, run_single_case
from benchmarks.grid_cli import (
    build_parser,
    metrics_failed,
    pyomo_metric_kwargs,
    scipy_metric_kwargs,
)
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


def test_single_case_script_entrypoint_help(repo_root, tmp_path):
    env = os.environ.copy()
    env["MPLCONFIGDIR"] = str(tmp_path / "mpl")

    result = subprocess.run(
        [sys.executable, "benchmarks/run_single_case.py", "--help"],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Run one SciPy/Pyomo benchmark case" in result.stdout
    assert "--set" in result.stdout
    assert "--tee" in result.stdout


def test_single_case_parser_accepts_debug_options():
    parser = run_single_case.build_parser()

    args = parser.parse_args(
        [
            "--task",
            "both",
            "--scenario",
            "baseline",
            "--set",
            "product.A1=20",
            "--set",
            "ht.KC=4e-4",
            "--method",
            "colloc",
            "--n-elements",
            "8",
            "--n-collocation",
            "2",
            "--raw-colloc",
            "--warmstart",
            "--tsh-ramp",
            "40",
            "--pch-ramp",
            "0.05",
            "--no-secant-constraints",
            "--solver-timeout",
            "12.5",
            "--solver-wall-time",
            "30",
            "--tee",
        ]
    )

    assert args.task == "both"
    assert args.overrides == ["product.A1=20", "ht.KC=4e-4"]
    assert args.method == "colloc"
    assert args.raw_colloc is True
    assert args.warmstart is True
    assert args.tsh_ramp == 40.0
    assert args.pch_ramp == 0.05
    assert args.no_secant_constraints is True
    assert args.solver_timeout == 12.5
    assert args.solver_wall_time == 30.0
    assert args.tee is True


def test_single_case_runner_uses_current_adapters(monkeypatch, capsys):
    fake_traj = np.array(
        [
            [0.0, -30.0, -25.0, -20.0, 100.0, 0.2, 0.0],
            [1.0, -29.0, -25.0, -15.0, 150.0, 0.1, 99.0],
        ]
    )
    seen = {}

    def fake_scipy_adapter(task, vial, product, ht, eq_cap, nVial, scenario, dt):
        seen["scipy"] = {
            "task": task,
            "product_A1": product["A1"],
            "ht_KC": ht["KC"],
            "nVial": nVial,
            "dt": dt,
        }
        return {
            "trajectory": fake_traj,
            "success": True,
            "message": "scipy ok",
            "wall_time_s": 0.01,
            "objective_time_hr": 1.0,
            "solver": {"status": "n/a", "termination_condition": "n/a"},
        }

    def fake_pyomo_adapter(
        task,
        vial,
        product,
        ht,
        eq_cap,
        nVial,
        scenario,
        **kwargs,
    ):
        seen["pyomo"] = {
            "task": task,
            "product_A1": product["A1"],
            "ht_KC": ht["KC"],
            "nVial": nVial,
            **kwargs,
        }
        return {
            "trajectory": fake_traj,
            "success": True,
            "message": "pyomo ok",
            "wall_time_s": 0.02,
            "objective_time_hr": 1.0,
            "solver": {"status": "ok", "termination_condition": "optimal"},
            "warmstart_used": kwargs["warmstart"],
            "discretization": {"method": kwargs["method"]},
        }

    monkeypatch.setattr(run_single_case, "scipy_adapter", fake_scipy_adapter)
    monkeypatch.setattr(run_single_case, "pyomo_adapter", fake_pyomo_adapter)

    exit_code = run_single_case.main(
        [
            "--task",
            "both",
            "--scenario",
            "baseline",
            "--set",
            "product.A1=20",
            "--set",
            "ht.KC=4e-4",
            "--method",
            "colloc",
            "--n-elements",
            "8",
            "--n-collocation",
            "2",
            "--raw-colloc",
            "--warmstart",
            "--tsh-ramp",
            "40",
            "--pch-ramp",
            "0.05",
            "--no-secant-constraints",
            "--solver-timeout",
            "12.5",
            "--solver-wall-time",
            "30",
            "--tee",
        ]
    )

    output = capsys.readouterr().out

    assert exit_code == 0
    assert seen["scipy"] == {
        "task": "both",
        "product_A1": 20,
        "ht_KC": 4e-4,
        "nVial": 400,
        "dt": 0.01,
    }
    assert seen["pyomo"]["method"] == "colloc"
    assert seen["pyomo"]["n_elements"] == 8
    assert seen["pyomo"]["n_collocation"] == 2
    assert seen["pyomo"]["effective_nfe"] is False
    assert seen["pyomo"]["warmstart"] is True
    assert seen["pyomo"]["tsh_ramp_rate"] == 40.0
    assert seen["pyomo"]["pch_ramp_rate"] == 0.05
    assert seen["pyomo"]["use_secant_ramp_constraints"] is False
    assert seen["pyomo"]["solver_cpu_time"] == 12.5
    assert seen["pyomo"]["solver_wall_time"] == 30.0
    assert seen["pyomo"]["tee"] is True
    assert "SciPy summary" in output
    assert "Pyomo summary" in output
    assert "objective_time_hr: 1" in output
    assert "termination_condition: optimal" in output
    assert "trajectory_size: 2 points x 7 columns" in output


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


def test_paper_ocp_notes_cover_issue30_comparison(repo_root):
    notes = (repo_root / "docs" / "PAPER_OCP_VALIDATION.md").read_text(encoding="utf-8")
    tsh_stats = _objective_time_stats(
        repo_root / "benchmarks" / "results" / "baseline_Tsh_3x3_summary.jsonl"
    )
    pch_stats = _objective_time_stats(
        repo_root / "benchmarks" / "results" / "baseline_Pch_3x3_summary.jsonl"
    )

    assert "## Paper-vs-LyoPRONTO Baseline Comparison" in notes
    assert (
        "| Model/case | Comparable scope | Drying time | Active constraints/control behavior | Temperature behavior | Interpretation |"
        in notes
    )
    assert "benchmarks/results/baseline_Tsh_3x3_summary.jsonl" in notes
    assert (
        _table_cell(
            notes,
            "LyoPRONTO `Tsh` SciPy baseline",
            column=3,
        )
        == f"{_range_text(tsh_stats['scipy'])} h across the 3x3 grid; mean {tsh_stats['scipy']['mean']:.2f} h"
    )
    assert (
        _table_cell(
            notes,
            "LyoPRONTO `Tsh` Pyomo FD",
            column=3,
        )
        == f"{_range_text(tsh_stats['fd'])} h; mean {tsh_stats['fd']['mean']:.2f} h"
    )
    assert (
        _table_cell(
            notes,
            "LyoPRONTO `Tsh` Pyomo collocation",
            column=3,
        )
        == f"{_range_text(tsh_stats['colloc'])} h; mean {tsh_stats['colloc']['mean']:.2f} h"
    )
    normalized_notes = " ".join(notes.split())
    assert (
        "Their drying-time ranges were "
        f"{_range_text(pch_stats['scipy'])} h for SciPy, "
        f"{_range_text(pch_stats['fd'])} h for Pyomo FD, and "
        f"{_range_text(pch_stats['colloc'])} h for Pyomo collocation."
    ) in normalized_notes
    assert "Recommendation: keep the paper-reference model validation-only" in notes
    assert "#31" in notes
    assert "optional flux/interface-velocity cap" in notes


def _objective_time_stats(summary_path):
    values = {"scipy": [], "fd": [], "colloc": []}
    for line in summary_path.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        scipy_result = record.get("scipy")
        if scipy_result and scipy_result.get("success"):
            values["scipy"].append(float(scipy_result["objective_time_hr"]))
        pyomo_result = record.get("pyomo")
        if pyomo_result and pyomo_result.get("success"):
            method = pyomo_result["discretization"]["method"]
            values[method].append(float(pyomo_result["objective_time_hr"]))

    return {
        method: {
            "min": min(method_values),
            "max": max(method_values),
            "mean": sum(method_values) / len(method_values),
        }
        for method, method_values in values.items()
    }


def _range_text(stats):
    return f"{stats['min']:.2f}-{stats['max']:.2f}"


def _table_cell(markdown, row_label, column):
    for line in markdown.splitlines():
        if line.startswith(f"| {row_label} |"):
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            return cells[column - 1]
    raise AssertionError(f"missing markdown table row: {row_label}")


def test_tracked_reference_summaries_use_current_metric_schema(repo_root):
    required_metrics = {
        "dryness_target_percent",
        "dryness_tolerance_percent",
        "final_dryness_shortfall_percent",
        "max_product_temp_violation_C",
        "tsh_ramp_limit_C_per_hr",
        "max_tsh_ramp_C_per_hr",
        "max_tsh_ramp_violation_C_per_hr",
        "tsh_ramp_ok",
        "pch_ramp_limit_Torr_per_hr",
        "max_pch_ramp_Torr_per_hr",
        "max_pch_ramp_violation_Torr_per_hr",
        "pch_ramp_ok",
    }

    for rel_path in (
        "benchmarks/results/baseline_Tsh_3x3_summary.jsonl",
        "benchmarks/results/baseline_Pch_3x3_summary.jsonl",
    ):
        records = [
            json.loads(line)
            for line in (repo_root / rel_path).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

        assert records, rel_path
        assert len(records) == 27, rel_path
        for record in records:
            for method_key in ("scipy", "pyomo"):
                method_record = record.get(method_key)
                if method_record is None:
                    continue
                assert required_metrics <= set(method_record["metrics"]), (
                    rel_path,
                    method_key,
                    record["params"],
                )


def test_success_summary_uses_record_failure_flags():
    from benchmarks.analysis import failure_lines, success_summary

    records = [
        {
            "failed": False,
            "params": {"product.A1": 16.0, "ht.KC": 2.75e-4},
            "scipy": {"success": True},
            "pyomo": None,
        },
        {
            "failed": True,
            "params": {"product.A1": 18.0, "ht.KC": 3.3e-4},
            "scipy": {"success": True},
            "pyomo": {
                "success": True,
                "discretization": {"method": "fd"},
            },
        },
        {
            "failed": False,
            "params": {"product.A1": 20.0, "ht.KC": 4.0e-4},
            "scipy": {"success": True},
            "pyomo": {
                "success": False,
                "discretization": {"method": "colloc"},
            },
        },
    ]

    summary = success_summary(records)

    assert summary == {
        "total": 3,
        "succeeded": 1,
        "failed": 2,
        "success_rate": pytest.approx(100 / 3),
    }
    assert failure_lines(records) == [
        "fd: product.A1=18.0, ht.KC=0.00033",
        "colloc: product.A1=20.0, ht.KC=0.0004",
    ]


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
    assert metrics["max_product_temp_violation_C"] == 0.5


def test_compute_residuals_reports_post_solve_constraint_violations():
    traj = np.array(
        [
            [0.0, -30.0, -26.0, -20.0, 100.0, 0.2, 0.0],
            [1.0, -29.0, -24.5, -15.0, 150.0, 0.1, 70.0],
            [2.0, -28.0, -25.5, 0.0, 300.0, 0.1, 98.0],
        ]
    )

    metrics = compute_residuals(
        traj,
        product_critical_temp=-25.0,
        tsh_ramp_rate=10.0,
        pch_ramp_rate=0.1,
    )

    assert metrics["dryness_target_met"] is False
    assert metrics["final_dryness_shortfall_percent"] == pytest.approx(0.9)
    assert metrics["product_temp_ok"] is False
    assert metrics["max_product_temp_violation_C"] == pytest.approx(0.5)
    assert metrics["tsh_ramp_ok"] is False
    assert metrics["max_tsh_ramp_C_per_hr"] == pytest.approx(15.0)
    assert metrics["max_tsh_ramp_violation_C_per_hr"] == pytest.approx(5.0)
    assert metrics["pch_ramp_ok"] is False
    assert metrics["max_pch_ramp_Torr_per_hr"] == pytest.approx(0.15)
    assert metrics["max_pch_ramp_violation_Torr_per_hr"] == pytest.approx(0.05)


def test_compute_residuals_accepts_ramp_noise_within_solver_tolerance():
    traj = np.array(
        [
            [0.0, -30.0, -26.0, -20.0, 100.0, 0.2, 0.0],
            [1.0, -29.0, -25.5, -9.9999995, 200.0005, 0.1, 99.0],
        ]
    )

    metrics = compute_residuals(
        traj,
        tsh_ramp_rate=10.0,
        pch_ramp_rate=0.1,
    )

    assert metrics["tsh_ramp_ok"] is True
    assert metrics["max_tsh_ramp_violation_C_per_hr"] == pytest.approx(5e-7)
    assert metrics["pch_ramp_ok"] is True
    assert metrics["max_pch_ramp_violation_Torr_per_hr"] == pytest.approx(5e-7)


def test_metrics_failed_includes_ramp_validation_flags():
    assert metrics_failed({"dryness_target_met": True, "tsh_ramp_ok": True}) is False
    assert metrics_failed({"dryness_target_met": True, "tsh_ramp_ok": False}) is True


def test_grid_cli_scipy_metrics_ignore_pyomo_only_ramp_limits():
    args = SimpleNamespace(tsh_ramp=1.0, pch_ramp=0.01)
    product = {"T_pr_crit": -25.0}
    traj = np.array(
        [
            [0.0, -30.0, -26.0, -20.0, 100.0, 0.2, 0.0],
            [1.0, -29.0, -26.0, 20.0, 500.0, 0.1, 99.0],
        ]
    )

    scipy_metrics = compute_residuals(
        traj,
        **scipy_metric_kwargs(args, product),
    )
    pyomo_metrics = compute_residuals(
        traj,
        **pyomo_metric_kwargs(args, product),
    )

    assert scipy_metrics["tsh_ramp_ok"] is None
    assert scipy_metrics["pch_ramp_ok"] is None
    assert metrics_failed(scipy_metrics) is False
    assert pyomo_metrics["tsh_ramp_ok"] is False
    assert pyomo_metrics["pch_ramp_ok"] is False
    assert metrics_failed(pyomo_metrics) is True


def test_grid_cli_parses_solver_time_guards():
    parser = build_parser()

    args = parser.parse_args(
        [
            "generate",
            "--task",
            "Tsh",
            "--scenario",
            "baseline",
            "--vary",
            "product.A1=16",
            "--out",
            "benchmarks/results/local.jsonl",
            "--solver-timeout",
            "12.5",
            "--solver-wall-time",
            "30",
        ]
    )

    assert args.solver_timeout == 12.5
    assert args.solver_wall_time == 30.0


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


def test_pyomo_adapter_propagates_solver_time_guards(monkeypatch):
    baseline = SCENARIOS["baseline"]
    fake_output = np.array(
        [
            [0.0, -26.0, -25.0, -20.0, 100.0, 0.2, 0.0],
            [1.0, -25.0, -25.0, -18.0, 100.0, 0.1, 99.0],
        ]
    )
    seen = {}

    def fake_optimizer(*args, **kwargs):
        seen.update(kwargs)
        return {
            "output": fake_output,
            "metadata": {
                "status": "ok",
                "termination_condition": "optimal",
                "objective_time_hr": 1.0,
                "solver_max_cpu_time_s": kwargs["solver_cpu_time"],
                "solver_max_wall_time_s": kwargs["solver_wall_time"],
                "solver_timeout_options": {
                    "max_cpu_time": kwargs["solver_cpu_time"],
                    "max_wall_time": kwargs["solver_wall_time"],
                },
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
        solver_cpu_time=12.5,
        solver_wall_time=30.0,
        tee=True,
    )

    assert seen["solver_cpu_time"] == 12.5
    assert seen["solver_wall_time"] == 30.0
    assert seen["tee"] is True
    assert result["solver"]["max_cpu_time_s"] == 12.5
    assert result["solver"]["max_wall_time_s"] == 30.0
    assert result["solver"]["timeout_options"] == {
        "max_cpu_time": 12.5,
        "max_wall_time": 30.0,
    }


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
