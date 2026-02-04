"""Tests for staged solve framework.

This module tests the staged solve framework that runs Pyomo optimization
with warmstart from scipy and multi-element discretization.
"""

import numpy as np
import pytest
from tests.utils import PERCENT_COMPLETE

# Try to import pyomo
try:
    import pyomo.environ as pyo

    PYOMO_AVAILABLE = True
except ImportError:
    PYOMO_AVAILABLE = False

# Check for IPOPT solver
IPOPT_AVAILABLE = False
if PYOMO_AVAILABLE:
    try:
        from idaes.core.solvers import get_solver

        solver = get_solver("ipopt")
        IPOPT_AVAILABLE = True
    except:
        try:
            solver = pyo.SolverFactory("ipopt")
            IPOPT_AVAILABLE = solver.available()
        except:
            IPOPT_AVAILABLE = False

pytestmark = [
    pytest.mark.pyomo,
    pytest.mark.skipif(
        not (PYOMO_AVAILABLE and IPOPT_AVAILABLE),
        reason="Pyomo or IPOPT solver not available",
    ),
]

from lyopronto.pyomo_models.optimizers import optimize_Tsh_pyomo


class TestStagedSolve:
    """Tests for staged solve framework."""

    @pytest.fixture
    def standard_inputs(self):
        """Standard test inputs matching other test fixtures."""
        vial = {"Av": 3.8, "Ap": 3.14, "Vfill": 2.0}

        product = {"T_pr_crit": -5.0, "cSolid": 0.05, "R0": 1.4, "A1": 16.0, "A2": 0.0}

        ht = {"KC": 0.000275, "KP": 0.000893, "KD": 0.46}

        Pchamber = {
            "setpt": np.array([0.15]),
            "dt_setpt": np.array([1800]),
            "ramp_rate": 0.5,
        }

        Tshelf = {
            "min": -45.0,
            "max": 120.0,
            "init": -35.0,
            "setpt": np.array([120.0]),
            "dt_setpt": np.array([1800]),
            "ramp_rate": 1.0,
        }

        eq_cap = {"a": -0.182, "b": 11.7}

        return {
            "vial": vial,
            "product": product,
            "ht": ht,
            "Pchamber": Pchamber,
            "Tshelf": Tshelf,
            "eq_cap": eq_cap,
            "nVial": 398,
            "dt": 0.01,
        }

    @pytest.mark.slow
    def test_staged_solve_with_warmstart_completes(self, standard_inputs):
        """Test that staged solve with warmstart completes successfully."""
        output = optimize_Tsh_pyomo(
            vial=standard_inputs["vial"],
            product=standard_inputs["product"],
            ht=standard_inputs["ht"],
            Pchamber=standard_inputs["Pchamber"],
            Tshelf=standard_inputs["Tshelf"],
            dt=standard_inputs["dt"],
            eq_cap=standard_inputs["eq_cap"],
            nVial=standard_inputs["nVial"],
            n_elements=20,
            n_collocation=2,
            warmstart_scipy=True,
            solver="ipopt",
            tee=False,
            simulation_mode=False,
        )

        # Basic output validation
        assert output is not None, "Output should not be None"
        assert output.shape[0] > 0, "Output should have rows"
        assert output.shape[1] == 7, "Output should have 7 columns"

    @pytest.mark.slow
    def test_staged_solve_respects_critical_temperature(self, standard_inputs):
        """Test that staged solve respects critical temperature constraint."""
        output = optimize_Tsh_pyomo(
            vial=standard_inputs["vial"],
            product=standard_inputs["product"],
            ht=standard_inputs["ht"],
            Pchamber=standard_inputs["Pchamber"],
            Tshelf=standard_inputs["Tshelf"],
            dt=standard_inputs["dt"],
            eq_cap=standard_inputs["eq_cap"],
            nVial=standard_inputs["nVial"],
            n_elements=20,
            n_collocation=2,
            warmstart_scipy=True,
            solver="ipopt",
            tee=False,
            simulation_mode=False,
        )

        T_pr_crit = standard_inputs["product"]["T_pr_crit"]
        # Allow 0.5°C tolerance for numerical solver
        critical_temp_satisfied = np.all(output[:, 1] <= T_pr_crit + 0.5)
        assert critical_temp_satisfied, (
            f"Critical temperature violated: max Tsub = {np.max(output[:, 1]):.2f}°C, "
            f"limit = {T_pr_crit}°C"
        )

    @pytest.mark.slow
    def test_staged_solve_completes_drying(self, standard_inputs):
        """Test that staged solve achieves sufficient drying completion."""
        output = optimize_Tsh_pyomo(
            vial=standard_inputs["vial"],
            product=standard_inputs["product"],
            ht=standard_inputs["ht"],
            Pchamber=standard_inputs["Pchamber"],
            Tshelf=standard_inputs["Tshelf"],
            dt=standard_inputs["dt"],
            eq_cap=standard_inputs["eq_cap"],
            nVial=standard_inputs["nVial"],
            n_elements=20,
            n_collocation=2,
            warmstart_scipy=True,
            solver="ipopt",
            tee=False,
            simulation_mode=False,
        )

        final_percent_dried = output[-1, 6]
        assert final_percent_dried >= PERCENT_COMPLETE, (
            f"Drying incomplete: {final_percent_dried:.2f}% < {PERCENT_COMPLETE}%"
        )

    @pytest.mark.slow
    def test_staged_solve_maintains_fixed_pressure(self, standard_inputs):
        """Test that staged solve maintains fixed chamber pressure."""
        output = optimize_Tsh_pyomo(
            vial=standard_inputs["vial"],
            product=standard_inputs["product"],
            ht=standard_inputs["ht"],
            Pchamber=standard_inputs["Pchamber"],
            Tshelf=standard_inputs["Tshelf"],
            dt=standard_inputs["dt"],
            eq_cap=standard_inputs["eq_cap"],
            nVial=standard_inputs["nVial"],
            n_elements=20,
            n_collocation=2,
            warmstart_scipy=True,
            solver="ipopt",
            tee=False,
            simulation_mode=False,
        )

        # Output column 4 is Pch in mTorr, setpt is in Torr
        Pch_setpt_mTorr = standard_inputs["Pchamber"]["setpt"][0] * 1000
        Pch_fixed = np.allclose(output[:, 4], Pch_setpt_mTorr, rtol=0.01)
        assert Pch_fixed, (
            f"Chamber pressure not fixed: range = [{output[:, 4].min():.1f}, "
            f"{output[:, 4].max():.1f}] mTorr, expected = {Pch_setpt_mTorr:.1f} mTorr"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
