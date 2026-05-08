"""Smoke tests for documentation notebooks and example scripts."""

import importlib.util
import subprocess
import sys
from types import SimpleNamespace

import papermill as pm
import pytest


def _ipopt_available():
    """Return whether a Pyomo-compatible IPOPT solver is available."""
    try:
        import pyomo.environ as pyo
    except ImportError:
        return False

    try:
        from idaes.core.solvers import get_solver

        return bool(get_solver("ipopt").available())
    except Exception:
        try:
            return bool(pyo.SolverFactory("ipopt").available(exception_flag=False))
        except Exception:
            return False


def _load_pyomo_example(repo_root):
    """Load the Pyomo example script as a testable module."""
    example_path = repo_root / "examples" / "example_pyomo_optimizer.py"
    spec = importlib.util.spec_from_file_location(
        "example_pyomo_optimizer_for_test", example_path
    )
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestDocsNotebooks:
    """Smoke tests: run example scripts used for documentation."""

    @pytest.mark.notebook
    def test_knownRp_notebook_execution(self, repo_root):
        """Test that the known-resistance documentation notebook runs."""
        pm.execute_notebook(
            repo_root / "docs/examples/knownRp_PD.ipynb",
            repo_root / "docs/examples/knownRp_PD_output.ipynb",
        )
        # Will error if execution fails

    @pytest.mark.notebook
    def test_unknownRp_notebook_execution(self, repo_root):
        """Test that the unknown-resistance documentation notebook runs."""
        pm.execute_notebook(
            repo_root / "docs/examples/unknownRp_PD.ipynb",
            repo_root / "docs/examples/unknownRp_PD_output.ipynb",
            parameters={"data_path": str(repo_root / "docs" / "examples") + "/"},
        )
        # Will error if execution fails


class TestPyomoExamples:
    """Smoke tests for optional Pyomo example scripts."""

    def test_pyomo_optimizer_example_reports_missing_pyomo(
        self, repo_root, monkeypatch, capsys
    ):
        """Test that the example fails clearly when Pyomo is unavailable."""
        example = _load_pyomo_example(repo_root)

        monkeypatch.setattr(example, "_pyomo_available", lambda: False)

        return_code = example.main()
        captured = capsys.readouterr()

        assert return_code == 1
        assert "ERROR: Pyomo is not installed." in captured.out
        assert "pip install lyopronto[optimization]" in captured.out

    def test_pyomo_optimizer_example_reports_missing_ipopt(
        self, repo_root, monkeypatch, capsys
    ):
        """Test that the example fails clearly when IPOPT is unavailable."""
        example = _load_pyomo_example(repo_root)

        monkeypatch.setattr(example, "_pyomo_available", lambda: True)
        monkeypatch.setattr(example, "_ipopt_available", lambda: False)

        return_code = example.main()
        captured = capsys.readouterr()

        assert return_code == 1
        assert "ERROR: IPOPT solver is not available." in captured.out
        assert "conda install -c conda-forge ipopt" in captured.out

    def test_pyomo_optimizer_example_requires_solved_stage(
        self, repo_root, monkeypatch, capsys
    ):
        """Test that the example fails if every optimization stage fails."""
        example = _load_pyomo_example(repo_root)

        def fake_optimize_single_step(**kwargs):
            raise RuntimeError("synthetic solve failure")

        fake_single_step = SimpleNamespace(
            optimize_single_step=fake_optimize_single_step
        )
        fake_utils = SimpleNamespace(
            check_solution_validity=lambda solution: (True, [])
        )

        monkeypatch.setattr(example, "_pyomo_available", lambda: True)
        monkeypatch.setattr(example, "_ipopt_available", lambda: True)
        monkeypatch.setattr(
            example, "_load_pyomo_modules", lambda: (fake_single_step, fake_utils)
        )

        return_code = example.main()
        captured = capsys.readouterr()

        assert return_code == 1
        assert "Optimization failed: synthetic solve failure" in captured.out
        assert "ERROR: No optimization stages solved successfully." in captured.out

    def test_pyomo_optimizer_example_reports_solved_stages(
        self, repo_root, monkeypatch, capsys
    ):
        """Test that a successful example run reports solved optimization stages."""
        example = _load_pyomo_example(repo_root)
        solved_stages = []

        def fake_optimize_single_step(**kwargs):
            solved_stages.append(kwargs["Lck"])
            return {
                "status": "optimal",
                "Pch": 0.1,
                "Tsh": -25.0,
                "Tsub": -28.0,
                "Tbot": -27.5,
                "Psub": 0.2,
                "dmdt": 0.05,
                "Rp": 10.0,
                "Kv": 0.0003,
            }

        fake_single_step = SimpleNamespace(
            optimize_single_step=fake_optimize_single_step
        )
        fake_utils = SimpleNamespace(
            check_solution_validity=lambda solution: (True, [])
        )

        monkeypatch.setattr(example, "_pyomo_available", lambda: True)
        monkeypatch.setattr(example, "_ipopt_available", lambda: True)
        monkeypatch.setattr(
            example, "_load_pyomo_modules", lambda: (fake_single_step, fake_utils)
        )

        return_code = example.main()
        captured = capsys.readouterr()

        assert return_code == 0
        assert len(solved_stages) == 3
        assert "Solved optimization stages: 3 of 3" in captured.out
        assert "Example complete!" in captured.out

    @pytest.mark.pyomo
    @pytest.mark.slow
    @pytest.mark.skipif(
        not _ipopt_available(), reason="Pyomo or IPOPT solver not available"
    )
    def test_pyomo_optimizer_example_runs(self, repo_root):
        """Test that the Pyomo optimizer example runs without error."""
        result = subprocess.run(
            [
                sys.executable,
                str(repo_root / "examples" / "example_pyomo_optimizer.py"),
            ],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )

        assert result.returncode == 0, result.stdout + result.stderr
        assert "Solved optimization stages:" in result.stdout
        assert "Example complete!" in result.stdout
