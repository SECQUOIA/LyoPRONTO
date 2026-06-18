"""Helpers for optional Pyomo/IPOPT tests."""

from __future__ import annotations

import importlib
from typing import Optional

import pytest


PYOMO_DEV_EXTRA_INSTALL = 'python -m pip install -e ".[dev,pyomo]"'
PYOMO_EXTRA_INSTALL = 'python -m pip install -e ".[pyomo]"'
IPOPT_IDAES_INSTALL = "idaes get-extensions --extra petsc"
IPOPT_CONDA_INSTALL = "conda install -c conda-forge ipopt"


def _solver_missing_reason(
    solver_name: str,
    pyomo_environ: Optional[object] = None,
) -> Optional[str]:
    if pyomo_environ is None:
        try:
            pyomo_environ = importlib.import_module("pyomo.environ")
        except ImportError:
            return (
                "Pyomo is not installed. Install the optional Pyomo stack with "
                f"`{PYOMO_DEV_EXTRA_INSTALL}` for tests or `{PYOMO_EXTRA_INSTALL}` "
                "for runtime-only experiments."
            )

    solver_factory = getattr(pyomo_environ, "SolverFactory")
    solver = solver_factory(solver_name)
    if solver.available(exception_flag=False):
        return None

    return (
        f"Pyomo solver '{solver_name}' is not available. Install IPOPT with "
        f"`{IPOPT_IDAES_INSTALL}` after installing the Pyomo extra, or use "
        f"`{IPOPT_CONDA_INSTALL}` in a conda environment with IPOPT on PATH."
    )


def require_pyomo_solver(solver_name: str = "ipopt") -> object:
    """Return a Pyomo solver or skip with the documented installation hint."""
    reason = _solver_missing_reason(solver_name)
    if reason is not None:
        pytest.skip(reason)

    pyomo_environ = importlib.import_module("pyomo.environ")
    return pyomo_environ.SolverFactory(solver_name)
