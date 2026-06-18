from __future__ import annotations

import pytest

from tests import pyomo_solver


class _FakeSolver:
    def __init__(self, is_available: bool) -> None:
        self.is_available = is_available
        self.exception_flag = None

    def available(self, exception_flag: bool = True) -> bool:
        self.exception_flag = exception_flag
        return self.is_available


class _FakePyomo:
    def __init__(self, solver: _FakeSolver) -> None:
        self.solver = solver
        self.requested_solver = None

    def SolverFactory(self, solver_name: str) -> _FakeSolver:
        self.requested_solver = solver_name
        return self.solver


def test_pyomo_solver_missing_reason_is_none_for_available_solver() -> None:
    solver = _FakeSolver(is_available=True)
    pyomo_environ = _FakePyomo(solver)

    assert pyomo_solver._solver_missing_reason("ipopt", pyomo_environ) is None
    assert pyomo_environ.requested_solver == "ipopt"
    assert solver.exception_flag is False


def test_pyomo_solver_missing_reason_explains_missing_solver() -> None:
    solver = _FakeSolver(is_available=False)
    pyomo_environ = _FakePyomo(solver)

    reason = pyomo_solver._solver_missing_reason("ipopt", pyomo_environ)

    assert reason is not None
    assert "Pyomo solver 'ipopt' is not available" in reason
    assert pyomo_solver.IPOPT_IDAES_INSTALL in reason
    assert pyomo_solver.IPOPT_CONDA_INSTALL in reason
    assert solver.exception_flag is False


def test_pyomo_solver_missing_reason_explains_missing_pyomo(monkeypatch) -> None:
    def fake_import_module(name: str) -> object:
        assert name == "pyomo.environ"
        raise ImportError

    monkeypatch.setattr(pyomo_solver.importlib, "import_module", fake_import_module)

    reason = pyomo_solver._solver_missing_reason("ipopt")

    assert reason is not None
    assert "Pyomo is not installed" in reason
    assert pyomo_solver.PYOMO_DEV_EXTRA_INSTALL in reason
    assert pyomo_solver.PYOMO_EXTRA_INSTALL in reason


def test_require_pyomo_solver_skips_with_install_hint(monkeypatch) -> None:
    monkeypatch.setattr(
        pyomo_solver,
        "_solver_missing_reason",
        lambda solver_name: f"{solver_name} missing",
    )

    with pytest.raises(pytest.skip.Exception) as exc_info:
        pyomo_solver.require_pyomo_solver("ipopt")

    assert "ipopt missing" in str(exc_info.value)
