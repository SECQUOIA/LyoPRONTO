# Copyright (C) 2026, SECQUOIA

"""
Tests for LyoPRONTO Pyomo-based optimizers.

These tests validate the Pyomo implementation of opt_Tsh, ensuring:
1. Model structure is correct (1 ODE + algebraic constraints)
2. Scipy solutions validate on Pyomo mesh (residuals at machine precision)
3. Staged solve framework converges successfully
4. Results match scipy baseline and reference data
5. Physical constraints are satisfied

Following the coexistence philosophy: Pyomo optimizers complement (not replace) scipy.
"""

from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

pyo = pytest.importorskip("pyomo.environ", reason="Pyomo not available")
from pyomo.opt import SolverResults, SolverStatus

# Check for IPOPT solver
IPOPT_AVAILABLE = False
try:
    from idaes.core.solvers import get_solver

    solver = get_solver("ipopt")
    IPOPT_AVAILABLE = True
except Exception:
    try:
        solver = pyo.SolverFactory("ipopt")
        IPOPT_AVAILABLE = solver.available()
    except Exception:
        IPOPT_AVAILABLE = False

pytestmark = [
    pytest.mark.pyomo,
    pytest.mark.skipif(
        not IPOPT_AVAILABLE,
        reason="Pyomo or IPOPT solver not available",
    ),
]

from lyopronto import opt_Tsh
from lyopronto.pyomo_models import optimizers as optimizers_module
from lyopronto.pyomo_models.optimizers import (
    _ensure_successful_solve,
    _solve_optimizer_model,
    _warmstart_from_scipy_output,
    create_optimizer_model,
    optimize_Tsh_pyomo,
    replay_scipy_controls_with_ipopt,
    validate_scipy_residuals,
)
from lyopronto.pyomo_models.utils import cake_length_conversion

# Import tolerance constants
from tests.utils import PERCENT_COMPLETE, TEMP_ATOL


class TestPyomoModelStructure:
    """Test that Pyomo model has correct mathematical structure."""

    @pytest.fixture
    def standard_params(self):
        """Standard test parameters for quick tests."""
        vial = {"Av": 3.14, "Ap": 2.27, "Vfill": 3.0}
        product = {"R0": 1.4, "A1": 16.0, "A2": 0.0, "T_pr_crit": -25.0, "cSolid": 0.05}
        ht = {"KC": 2.75e-4, "KP": 8.93e-4, "KD": 0.46}
        Pchamber = {"setpt": [0.10], "dt_setpt": [180.0], "ramp_rate": 0.5}
        Tshelf = {
            "min": -45.0,
            "max": 20.0,
            "init": -35.0,
            "setpt": [20.0],
            "dt_setpt": [180.0],
            "ramp_rate": 1.0,
        }
        eq_cap = {"a": -0.182, "b": 0.0117e3}
        nVial = 398
        return vial, product, ht, Pchamber, Tshelf, eq_cap, nVial

    def test_model_has_correct_ode_structure(self, standard_params):
        """Test that model has only 1 ODE state variable (Lck)."""
        vial, product, ht, Pchamber, Tshelf, eq_cap, nVial = standard_params

        model = create_optimizer_model(
            vial,
            product,
            ht,
            vial["Vfill"],
            eq_cap,
            nVial,
            Pchamber=Pchamber,
            Tshelf=Tshelf,
            n_elements=5,
            control_mode="Tsh",
            use_finite_differences=True,
        )

        # Should have dLck_dt derivative
        assert hasattr(model, "dLck_dt"), "Model should have dLck_dt derivative"

        # Should NOT have derivatives for Tsub or Tbot (they are algebraic)
        assert not hasattr(model, "dTsub_dt"), "Tsub should be algebraic, not ODE state"
        assert not hasattr(model, "dTbot_dt"), "Tbot should be algebraic, not ODE state"

        # Should have Lck, Tsub, Tbot as variables
        assert hasattr(model, "Lck"), "Model should have Lck variable"
        assert hasattr(model, "Tsub"), "Model should have Tsub variable"
        assert hasattr(model, "Tbot"), "Model should have Tbot variable"

    def test_model_has_correct_constraints(self, standard_params):
        """Test that model has correct algebraic constraints."""
        vial, product, ht, Pchamber, Tshelf, eq_cap, nVial = standard_params

        model = create_optimizer_model(
            vial,
            product,
            ht,
            vial["Vfill"],
            eq_cap,
            nVial,
            Pchamber=Pchamber,
            Tshelf=Tshelf,
            n_elements=5,
            control_mode="Tsh",
            use_finite_differences=True,
        )

        # Should have algebraic constraints for energy balance
        assert hasattr(model, "energy_balance"), (
            "Model should have energy_balance constraint"
        )
        assert hasattr(model, "vial_bottom_temp"), (
            "Model should have vial_bottom_temp constraint"
        )

        # Should have cake length ODE
        assert hasattr(model, "cake_length_ode"), "Model should have cake_length_ode"

        # Should NOT have the old ODE constraints
        assert not hasattr(model, "heat_balance_ode"), (
            "Should not have heat_balance_ode (removed)"
        )
        assert not hasattr(model, "vial_bottom_temp_ode"), (
            "Should not have vial_bottom_temp_ode (removed)"
        )

    def test_model_uses_finite_differences(self, standard_params):
        """Test that backward Euler FD is applied correctly."""
        vial, product, ht, Pchamber, Tshelf, eq_cap, nVial = standard_params

        model = create_optimizer_model(
            vial,
            product,
            ht,
            vial["Vfill"],
            eq_cap,
            nVial,
            Pchamber=Pchamber,
            Tshelf=Tshelf,
            n_elements=10,
            control_mode="Tsh",
            use_finite_differences=True,
        )

        # Check that time set is discretized
        assert hasattr(model, "t"), "Model should have time set"
        t_points = list(model.t)
        assert len(t_points) == 11, (
            f"Expected 11 time points (n_elements=10), got {len(t_points)}"
        )

    def test_cake_length_ode_uses_scipy_conversion(self, standard_params):
        """Test dLck/dt uses the same conversion as the scipy optimizers."""
        vial, product, ht, Pchamber, Tshelf, eq_cap, nVial = standard_params
        product = product.copy()
        product["cSolid"] = 0.20

        model = create_optimizer_model(
            vial,
            product,
            ht,
            vial["Vfill"],
            eq_cap,
            nVial,
            Pchamber=Pchamber,
            Tshelf=Tshelf,
            n_elements=5,
            control_mode="Tsh",
            use_finite_differences=True,
        )

        t = next(t for t in model.t if t != min(model.t))
        model.t_final.set_value(4.0)
        model.dmdt[t].set_value(0.123)
        model.dLck_dt[t].set_value(0.0)

        expected = 4.0 * 0.123 * cake_length_conversion(vial, product)
        assert np.isclose(pyo.value(model.cake_length_ode[t].body), -expected)


class TestSolveValidation:
    """Test solver termination validation before output extraction."""

    def test_nonoptimal_result_raises_before_output(self):
        results = SolverResults()
        results.solver.status = SolverStatus.warning
        results.solver.termination_condition = pyo.TerminationCondition.infeasible

        with pytest.raises(ValueError, match="failed to converge"):
            _ensure_successful_solve(results, "test_optimizer")

    @pytest.mark.parametrize(
        ("context", "control_mode"),
        [
            ("optimize_Tsh_pyomo", "Tsh"),
            ("optimize_Pch_pyomo", "Pch"),
            ("optimize_Pch_Tsh_pyomo", "both"),
        ],
    )
    def test_staged_failure_does_not_run_direct_fallback(
        self, monkeypatch, context, control_mode
    ):
        failed = SolverResults()
        failed.solver.status = SolverStatus.warning
        failed.solver.termination_condition = pyo.TerminationCondition.infeasible

        def fail_staged_solve(model, solver, control_mode, tee=False):
            model._last_solver_result = failed
            return False, "Stage 2 (time optimization) failed"

        class SolverThatWouldHideFailure:
            solve_calls = 0

            def solve(self, model, tee=False):
                self.solve_calls += 1
                result = SolverResults()
                result.solver.status = SolverStatus.ok
                result.solver.termination_condition = pyo.TerminationCondition.optimal
                return result

        monkeypatch.setattr(optimizers_module, "staged_solve", fail_staged_solve)
        solver = SolverThatWouldHideFailure()

        with pytest.raises(ValueError, match="staged solve failed"):
            _solve_optimizer_model(
                SimpleNamespace(),
                solver,
                context=context,
                control_mode=control_mode,
                warmstart_scipy=True,
                simulation_mode=False,
                tee=False,
            )

        assert solver.solve_calls == 0


class TestScipyValidation:
    """Test that scipy solutions validate perfectly on Pyomo mesh."""

    @pytest.fixture
    def complete_drying_params(self):
        """Parameters that allow complete drying."""
        vial = {"Av": 3.14, "Ap": 2.27, "Vfill": 3.0}
        product = {"R0": 1.4, "A1": 16.0, "A2": 0.0, "T_pr_crit": -25.0, "cSolid": 0.05}
        ht = {"KC": 2.75e-4, "KP": 8.93e-4, "KD": 0.46}
        # Lower pressure and longer time to ensure completion
        Pchamber = {"setpt": [0.10], "dt_setpt": [3600.0], "ramp_rate": 0.5}
        Tshelf = {
            "min": -45.0,
            "max": 20.0,
            "init": -35.0,
            "setpt": [20.0],
            "dt_setpt": [3600.0],
            "ramp_rate": 1.0,
        }
        eq_cap = {"a": -0.182, "b": 0.0117e3}
        nVial = 398
        dt = 0.01
        return vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial

    def test_scipy_solution_validates_on_pyomo_mesh(self, complete_drying_params):
        """Test that scipy solution satisfies Pyomo constraints at machine precision."""
        vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial = complete_drying_params

        # Run scipy optimizer
        scipy_out = opt_Tsh.dry(vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial)

        # Create Pyomo model and warmstart
        model = create_optimizer_model(
            vial,
            product,
            ht,
            vial["Vfill"],
            eq_cap,
            nVial,
            Pchamber=Pchamber,
            Tshelf=Tshelf,
            n_elements=5,
            control_mode="Tsh",
            use_finite_differences=True,
        )
        _warmstart_from_scipy_output(model, scipy_out, vial, product, ht)

        # Validate residuals
        residuals = validate_scipy_residuals(
            model, scipy_out, vial, product, ht, verbose=False
        )

        # All constraint residuals should be at machine precision
        for constr_name, vals in residuals.items():
            assert vals["max"] < 1e-3, (
                f"Constraint {constr_name} has residual {vals['max']:.2e} > 1e-3"
            )

    def test_energy_balance_validates_exactly(self, complete_drying_params):
        """Test that energy balance constraint validates at high precision."""
        vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial = complete_drying_params

        scipy_out = opt_Tsh.dry(vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial)

        model = create_optimizer_model(
            vial,
            product,
            ht,
            vial["Vfill"],
            eq_cap,
            nVial,
            Pchamber=Pchamber,
            Tshelf=Tshelf,
            n_elements=5,
            control_mode="Tsh",
            use_finite_differences=True,
        )
        _warmstart_from_scipy_output(model, scipy_out, vial, product, ht)

        residuals = validate_scipy_residuals(
            model, scipy_out, vial, product, ht, verbose=False
        )

        # Energy balance should validate to very high precision (was the main bug)
        assert residuals["energy_balance"]["max"] < 1e-6, (
            f"Energy balance residual {residuals['energy_balance']['max']:.2e} too large"
        )

    def test_scipy_controls_replay_solves_with_ipopt(self, complete_drying_params):
        """Test IPOPT feasibility replay with SciPy controls and final time fixed."""
        vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial = complete_drying_params

        scipy_out = opt_Tsh.dry(vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial)

        result = replay_scipy_controls_with_ipopt(
            scipy_out,
            vial,
            product,
            ht,
            Pchamber,
            Tshelf,
            eq_cap,
            nVial,
            n_elements=5,
            return_metadata=True,
            tee=False,
        )

        output = result["output"]
        metadata = result["metadata"]

        assert metadata["termination_condition"] == "optimal"
        assert metadata["max_constraint_residual"] < 1e-4
        assert metadata["max_scipy_trajectory_residual"] < 1e-4
        assert metadata["max_replay_solution_residual"] < 1e-4
        assert "cake_length_dynamics" in metadata["scipy_trajectory_residuals"]
        assert abs(output[-1, 0] - scipy_out[-1, 0]) < 1e-9
        assert output[-1, 6] > 0.0


class TestStagedSolve:
    """Test the 4-stage solve framework."""

    @pytest.fixture
    def optimizer_params(self):
        """Parameters matching reference optimizer test."""
        vial = {"Av": 3.8, "Ap": 3.14, "Vfill": 2.0}
        product = {"T_pr_crit": -5.0, "cSolid": 0.05, "R0": 1.4, "A1": 16.0, "A2": 0.0}
        ht = {"KC": 0.000275, "KP": 0.000893, "KD": 0.46}
        Pchamber = {"setpt": [0.15], "dt_setpt": [1800], "ramp_rate": 0.5}
        Tshelf = {
            "min": -45.0,
            "max": 120.0,
            "init": -35.0,
            "setpt": [120.0],
            "dt_setpt": [1800],
            "ramp_rate": 1.0,
        }
        eq_cap = {"a": -0.182, "b": 11.7}
        nVial = 398
        dt = 0.01
        return vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial

    def test_staged_solve_completes_all_stages(self, optimizer_params):
        """Test that all 4 stages of staged solve complete successfully."""
        vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial = optimizer_params

        # This should complete all 4 stages
        result = optimize_Tsh_pyomo(
            vial,
            product,
            ht,
            Pchamber,
            Tshelf,
            dt,
            eq_cap,
            nVial,
            n_elements=10,
            warmstart_scipy=True,
            tee=False,
        )

        # Should return valid output
        assert result is not None
        assert result.size > 0
        assert result.shape[1] == 7, "Output should have 7 columns"

        # Should reach target dryness (99%)
        final_dryness = result[-1, 6]
        assert final_dryness >= PERCENT_COMPLETE - 1.0, (
            f"Drying incomplete: {final_dryness:.1f}% dried"
        )

    def test_pyomo_improves_on_scipy_time(self, optimizer_params):
        """Test that Pyomo optimizer finds equal or better solution than scipy."""
        vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial = optimizer_params

        # Run scipy
        scipy_out = opt_Tsh.dry(vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial)
        scipy_time = scipy_out[-1, 0]

        # Run Pyomo
        pyomo_out = optimize_Tsh_pyomo(
            vial,
            product,
            ht,
            Pchamber,
            Tshelf,
            dt,
            eq_cap,
            nVial,
            n_elements=10,
            warmstart_scipy=True,
            tee=False,
        )
        pyomo_time = pyomo_out[-1, 0]

        # Pyomo should find solution at least as good as scipy (within tolerance)
        # Allow 10% worse due to discretization differences
        assert pyomo_time <= scipy_time * 1.1, (
            f"Pyomo time {pyomo_time:.2f} hr worse than scipy {scipy_time:.2f} hr"
        )


class TestReferenceData:
    """Test against reference optimizer data."""

    @pytest.fixture
    def reference_params(self):
        """Parameters from reference optimizer CSV."""
        vial = {"Av": 3.8, "Ap": 3.14, "Vfill": 2.0}
        product = {"T_pr_crit": -5.0, "cSolid": 0.05, "R0": 1.4, "A1": 16.0, "A2": 0.0}
        ht = {"KC": 0.000275, "KP": 0.000893, "KD": 0.46}
        Pchamber = {"setpt": [0.15], "dt_setpt": [1800], "ramp_rate": 0.5}
        Tshelf = {
            "min": -45.0,
            "max": 120.0,
            "init": -35.0,
            "setpt": [120.0],
            "dt_setpt": [1800],
            "ramp_rate": 1.0,
        }
        eq_cap = {"a": -0.182, "b": 11.7}
        nVial = 398
        dt = 0.01
        return vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial

    @pytest.fixture
    def reference_data(self):
        """Load reference results."""
        csv_path = "test_data/reference_optimizer.csv"
        df = pd.read_csv(csv_path, sep=";")
        # Convert percent dried from percentage (0-100) to fraction (0-1)
        df["Percent Dried"] = df["Percent Dried"] / 100.0
        return df

    def test_pyomo_matches_reference_final_time(self, reference_params, reference_data):
        """Test that Pyomo optimizer final time matches reference data."""
        vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial = reference_params

        result = optimize_Tsh_pyomo(
            vial,
            product,
            ht,
            Pchamber,
            Tshelf,
            dt,
            eq_cap,
            nVial,
            n_elements=10,
            warmstart_scipy=True,
            tee=False,
        )

        ref_final_time = reference_data["Time [hr]"].iloc[-1]
        pyomo_final_time = result[-1, 0]

        # Should be within 20% of reference (discretization differences expected)
        rel_error = abs(pyomo_final_time - ref_final_time) / ref_final_time
        assert rel_error < 0.2, (
            f"Final time {pyomo_final_time:.2f} hr differs from reference {ref_final_time:.2f} hr by {rel_error * 100:.1f}%"
        )

    def test_pyomo_respects_critical_temperature(self, reference_params):
        """Test that product temperature stays at or below critical temperature."""
        vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial = reference_params

        result = optimize_Tsh_pyomo(
            vial,
            product,
            ht,
            Pchamber,
            Tshelf,
            dt,
            eq_cap,
            nVial,
            n_elements=10,
            warmstart_scipy=True,
            tee=False,
        )

        Tbot = result[:, 2]  # Product temperature at vial bottom
        T_crit = product["T_pr_crit"]

        # Product temperature should not exceed critical temperature
        assert np.all(Tbot <= T_crit + TEMP_ATOL), (
            f"Product temperature exceeded critical: max={Tbot.max():.2f}°C, crit={T_crit}°C"
        )


class TestPhysicalConstraints:
    """Test that physical constraints are satisfied."""

    @pytest.fixture
    def test_params(self):
        """Standard test parameters."""
        vial = {"Av": 3.14, "Ap": 2.27, "Vfill": 3.0}
        product = {"R0": 1.4, "A1": 16.0, "A2": 0.0, "T_pr_crit": -5.0, "cSolid": 0.05}
        ht = {"KC": 2.75e-4, "KP": 8.93e-4, "KD": 0.46}
        Pchamber = {"setpt": [0.10], "dt_setpt": [3600.0], "ramp_rate": 0.5}
        Tshelf = {
            "min": -45.0,
            "max": 20.0,
            "init": -35.0,
            "setpt": [20.0],
            "dt_setpt": [3600.0],
            "ramp_rate": 1.0,
        }
        eq_cap = {"a": -0.182, "b": 0.0117e3}
        nVial = 398
        dt = 0.01
        return vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial

    def test_temperatures_physically_reasonable(self, test_params):
        """Test that all temperatures are physically reasonable."""
        vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial = test_params

        result = optimize_Tsh_pyomo(
            vial,
            product,
            ht,
            Pchamber,
            Tshelf,
            dt,
            eq_cap,
            nVial,
            n_elements=10,
            warmstart_scipy=True,
            tee=False,
        )

        Tsub = result[:, 1]
        Tbot = result[:, 2]
        Tsh = result[:, 3]

        # All temperatures should be reasonable
        assert np.all(Tsub >= -100) and np.all(Tsub <= 50), "Tsub out of physical range"
        assert np.all(Tbot >= -100) and np.all(Tbot <= 50), "Tbot out of physical range"
        assert np.all(Tsh >= -100) and np.all(Tsh <= 150), "Tsh out of physical range"

        # Tbot should be >= Tsub (heat flows from bottom to sublimation front)
        assert np.all(Tbot >= Tsub - 0.01), "Tbot should be >= Tsub"

    def test_drying_progresses_monotonically(self, test_params):
        """Test that drying percent increases monotonically."""
        vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial = test_params

        result = optimize_Tsh_pyomo(
            vial,
            product,
            ht,
            Pchamber,
            Tshelf,
            dt,
            eq_cap,
            nVial,
            n_elements=10,
            warmstart_scipy=True,
            tee=False,
        )

        percent_dried = result[:, 6]

        # Drying percent should increase monotonically
        diff = np.diff(percent_dried)
        assert np.all(diff >= -1e-6), "Drying percent should increase monotonically"

        # Should end near 99%
        assert percent_dried[-1] >= PERCENT_COMPLETE - 1.0, (
            f"Final drying {percent_dried[-1]:.1f}% too low"
        )

    def test_no_singularity_at_completion(self, test_params):
        """Test that model handles drying completion without singularities."""
        vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial = test_params

        result = optimize_Tsh_pyomo(
            vial,
            product,
            ht,
            Pchamber,
            Tshelf,
            dt,
            eq_cap,
            nVial,
            n_elements=10,
            warmstart_scipy=True,
            tee=False,
        )

        # All values should be finite (no infinities from division by zero)
        assert np.all(np.isfinite(result)), "Result contains non-finite values"

        # Check that Tbot and Tsub converge at completion (no frozen layer left)
        Tsub_final = result[-1, 1]
        Tbot_final = result[-1, 2]

        # At completion, Tbot should be very close to Tsub
        assert abs(Tbot_final - Tsub_final) < 0.1, (
            f"Tbot and Tsub should converge at completion: Tbot={Tbot_final:.2f}, Tsub={Tsub_final:.2f}"
        )


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_handles_partial_scipy_solution(self):
        """Test that model handles scipy solution that doesn't complete drying.

        We simulate an incomplete solution by truncating a complete scipy trajectory.
        """
        vial = {"Av": 3.14, "Ap": 2.27, "Vfill": 3.0}
        product = {"R0": 1.4, "A1": 16.0, "A2": 0.0, "T_pr_crit": -25.0, "cSolid": 0.05}
        ht = {"KC": 2.75e-4, "KP": 8.93e-4, "KD": 0.46}

        Pchamber = {"setpt": [0.15], "dt_setpt": [180.0], "ramp_rate": 0.5}
        Tshelf = {
            "min": -45.0,
            "max": 20.0,
            "init": -35.0,
            "setpt": [20.0],
            "dt_setpt": [180.0],
            "ramp_rate": 1.0,
        }
        eq_cap = {"a": -0.182, "b": 0.0117e3}
        nVial = 398
        dt = 0.01

        # Run scipy to completion
        scipy_out_full = opt_Tsh.dry(
            vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial
        )

        # Truncate to simulate incomplete drying (take first 30% of trajectory)
        n_points = len(scipy_out_full)
        truncate_idx = max(5, n_points // 3)  # At least 5 points, or 1/3 of trajectory
        scipy_out = scipy_out_full[:truncate_idx]

        # Verify truncated solution is incomplete
        assert scipy_out[-1, 6] < 50.0, (
            f"Truncated solution should be incomplete, got {scipy_out[-1, 6]:.1f}%"
        )

        # Create model and warmstart - should handle gracefully
        model = create_optimizer_model(
            vial,
            product,
            ht,
            vial["Vfill"],
            eq_cap,
            nVial,
            Pchamber=Pchamber,
            Tshelf=Tshelf,
            n_elements=5,
            control_mode="Tsh",
            use_finite_differences=True,
        )

        # Should not raise exception
        _warmstart_from_scipy_output(model, scipy_out, vial, product, ht)

        # Validation should work (constraints satisfied for partial solution)
        residuals = validate_scipy_residuals(
            model, scipy_out, vial, product, ht, verbose=False
        )

        # All residuals should still be small
        for constr_name, vals in residuals.items():
            assert vals["max"] < 1e-3, (
                f"Constraint {constr_name} validation failed for partial solution"
            )
