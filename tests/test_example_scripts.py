"""Smoke tests for documentation notebooks and example scripts."""

import subprocess
import sys

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
        assert "Example complete!" in result.stdout
