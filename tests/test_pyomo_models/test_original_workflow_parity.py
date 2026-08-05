"""Optional Pyomo parity checks for the two original LyoPRONTO workflows.

Inputs use time [hr], temperature [degC], pressure [Torr], cake length [cm],
and product resistance [cm^2 hr Torr/g].  Trajectory tables expose pressure in
mTorr, flux in kg/hr/m^2, and percent dried on the 0-100 scale.
"""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from examples.original_workflow_parity import (
    KNOWN_RP_ENDPOINT_TOLERANCE_PP,
    build_known_rp_pyomo_model,
    build_unknown_rp_pyomo_model,
    fit_unknown_rp_pyomo,
    fit_unknown_rp_scipy,
    preprocess_unknown_rp,
    run_known_rp_pyomo,
    run_known_rp_scipy,
)
from tests.pyomo_solver import require_pyomo_solver

pyo = pytest.importorskip("pyomo.environ")

pytestmark = pytest.mark.pyomo


class NonOptimalSolver:
    """Return an infeasible result without changing initialized model values."""

    def solve(self, model, tee=False):
        """Return non-optimal diagnostics for a dimensionless test double."""
        del model, tee
        return SimpleNamespace(
            solver=SimpleNamespace(
                status=pyo.SolverStatus.warning,
                termination_condition=pyo.TerminationCondition.infeasible,
            )
        )


def test_original_workflow_models_construct_without_a_solver() -> None:
    """Both optional tutorial models remain available in the Pyomo-light lane."""
    scipy_output = run_known_rp_scipy()
    trajectory_model = build_known_rp_pyomo_model(scipy_output)
    _output, product_resistance = preprocess_unknown_rp()
    fitting_model = build_unknown_rp_pyomo_model(product_resistance)

    assert int(pyo.value(trajectory_model.n_steps)) == 26
    assert pyo.value(trajectory_model.dt) == pytest.approx(0.25)  # [hr]
    assert pyo.value(trajectory_model.final_dried_fraction) == pytest.approx(0.95)
    assert fitting_model.advanced_workflow == "parameter_estimation"
    assert fitting_model.estimated_parameters == ("R0", "A1", "A2")
    assert len(fitting_model.OBS) == 453


def test_known_rp_pyomo_replay_matches_scipy_endpoint() -> None:
    """Backward Euler stays within its documented endpoint discretization error."""
    solver = require_pyomo_solver("ipopt")
    scipy_output = run_known_rp_scipy()
    result = run_known_rp_pyomo(scipy_output, solver=solver)

    assert result.success, result.message
    pyomo_output = result.as_table()
    assert pyomo_output.shape == scipy_output.shape == (27, 7)
    np.testing.assert_allclose(pyomo_output[:, 4], scipy_output[:, 4], atol=1.0e-8)
    assert pyomo_output[-1, 6] == pytest.approx(
        scipy_output[-1, 6],
        abs=KNOWN_RP_ENDPOINT_TOLERANCE_PP,
    )
    assert np.max(pyomo_output[:, 2]) <= -5.0 + 1.0e-6
    assert max(
        violation or 0.0 for violation in result.constraint_violations.values()
    ) < 1.0e-5


def test_unknown_rp_hybrid_pyomo_fit_matches_scipy() -> None:
    """Pyomo fitting matches SciPy after the shared legacy inverse preprocessing."""
    solver = require_pyomo_solver("ipopt")
    _output, product_resistance = preprocess_unknown_rp()
    scipy_fit = fit_unknown_rp_scipy(product_resistance)
    pyomo_fit = fit_unknown_rp_pyomo(product_resistance, solver=solver)

    assert pyomo_fit.success, pyomo_fit.message
    assert pyomo_fit.termination_condition == "optimal"
    np.testing.assert_allclose(
        pyomo_fit.as_array(),
        scipy_fit.as_array(),
        rtol=2.0e-5,
        atol=2.0e-5,
    )
    assert pyomo_fit.objective == pytest.approx(scipy_fit.objective, abs=1.0e-6)


def test_unknown_rp_nonoptimal_result_is_not_exposed_as_a_fit() -> None:
    """Initialized parameters are not scientific output after infeasible termination."""
    _output, product_resistance = preprocess_unknown_rp()
    failed_fit = fit_unknown_rp_pyomo(
        product_resistance,
        solver=NonOptimalSolver(),
    )

    assert not failed_fit.success
    assert failed_fit.solver_status == "warning"
    assert failed_fit.termination_condition == "infeasible"
    assert failed_fit.R0 is None  # [cm^2 hr Torr/g]
    assert failed_fit.A1 is None  # [cm hr Torr/g]
    assert failed_fit.A2 is None  # [1/cm]
    assert failed_fit.objective is None  # [(cm^2 hr Torr/g)^2]
    assert "fitted parameters and objective are unavailable" in failed_fit.message
    with pytest.raises(RuntimeError, match="did not reach an optimal solution"):
        failed_fit.as_array()
