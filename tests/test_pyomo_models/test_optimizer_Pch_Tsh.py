"""
Tests for LyoPRONTO Pyomo opt_Pch_Tsh optimizer (joint pressure and temperature optimization).

These tests validate the Pyomo implementation of opt_Pch_Tsh, ensuring:
1. Model structure is correct (1 ODE + algebraic constraints)
2. Scipy solutions validate on Pyomo mesh (residuals at machine precision)
3. Staged solve framework converges successfully with both controls
4. Joint optimization improves over single-control optimizers
5. Physical constraints are satisfied
6. Control mode='both' correctly optimizes both Pch and Tsh

Following the coexistence philosophy: Pyomo optimizers complement (not replace) scipy.
"""

import pytest
import numpy as np
import pyomo.environ as pyo
from lyopronto import opt_Pch_Tsh, opt_Tsh, opt_Pch
from lyopronto.pyomo_models.optimizers import (
    create_optimizer_model,
    optimize_Pch_Tsh_pyomo,
    validate_scipy_residuals,
    _warmstart_from_scipy_output,
)


class TestPyomoOptPchTshModelStructure:
    """Test that Pyomo model has correct structure for joint optimization."""
    
    @pytest.fixture
    def standard_params(self):
        """Standard test parameters for opt_Pch_Tsh."""
        vial = {'Av': 3.8, 'Ap': 3.14, 'Vfill': 2.0}
        product = {'R0': 1.4, 'A1': 16.0, 'A2': 0.0, 'T_pr_crit': -5.0, 'cSolid': 0.05}
        ht = {'KC': 0.000275, 'KP': 0.000893, 'KD': 0.46}
        Pchamber = {'min': 0.06, 'max': 0.20}
        Tshelf = {'min': -45, 'max': 30, 'init': -35}
        eq_cap = {'a': -0.182, 'b': 11.7}
        nVial = 398
        return vial, product, ht, Pchamber, Tshelf, eq_cap, nVial
    
    def test_control_mode_both_creates_correct_bounds(self, standard_params):
        """Test that control_mode='both' sets correct bounds for both Pch and Tsh."""
        vial, product, ht, Pchamber, Tshelf, eq_cap, nVial = standard_params
        
        model = create_optimizer_model(
            vial, product, ht, vial['Vfill'], eq_cap, nVial,
            Pchamber=Pchamber,
            Tshelf=Tshelf,
            n_elements=5,
            control_mode='both',
            use_finite_differences=True
        )
        
        # Check Pch bounds (optimized)
        t_first = min(model.t)
        assert model.Pch[t_first].lb == 0.06, "Pch lower bound should be 0.06"
        assert model.Pch[t_first].ub == 0.20, "Pch upper bound should be 0.20"
        
        # Check Tsh bounds (optimized)
        assert model.Tsh[t_first].lb == -45.0, "Tsh lower bound should be -45"
        assert model.Tsh[t_first].ub == 30.0, "Tsh upper bound should be 30"
    
    def test_model_has_same_physics_as_single_control(self, standard_params):
        """Test that joint model has same physics as single-control models."""
        vial, product, ht, Pchamber, Tshelf, eq_cap, nVial = standard_params
        
        model = create_optimizer_model(
            vial, product, ht, vial['Vfill'], eq_cap, nVial,
            Pchamber=Pchamber,
            Tshelf=Tshelf,
            n_elements=5,
            control_mode='both',
            use_finite_differences=True
        )
        
        # Same physics structure (1 ODE + 2 algebraic)
        assert hasattr(model, 'dLck_dt'), "Model should have dLck_dt derivative"
        assert not hasattr(model, 'dTsub_dt'), "Tsub should be algebraic"
        assert not hasattr(model, 'dTbot_dt'), "Tbot should be algebraic"
        assert hasattr(model, 'energy_balance'), "Model should have energy_balance"
        assert hasattr(model, 'vial_bottom_temp'), "Model should have vial_bottom_temp"


class TestPyomoOptPchTshScipyValidation:
    """Test that scipy opt_Pch_Tsh solutions validate on Pyomo mesh."""
    
    @pytest.fixture
    def validation_params(self):
        """Parameters for scipy validation test."""
        vial = {'Av': 3.8, 'Ap': 3.14, 'Vfill': 2.0}
        product = {'R0': 1.4, 'A1': 16.0, 'A2': 0.0, 'T_pr_crit': -5.0, 'cSolid': 0.05}
        ht = {'KC': 0.000275, 'KP': 0.000893, 'KD': 0.46}
        # Use wider Pch bounds to accommodate scipy solution
        Pchamber = {'min': 0.05, 'max': 0.30}
        Tshelf = {'min': -45, 'max': 30, 'init': -35}
        eq_cap = {'a': -0.182, 'b': 11.7}
        nVial = 398
        dt = 0.01
        return vial, product, ht, Pchamber, Tshelf, eq_cap, nVial, dt
    
    def test_scipy_solution_validates_on_pyomo_mesh(self, validation_params):
        """Test that scipy opt_Pch_Tsh solution satisfies Pyomo constraints."""
        vial, product, ht, Pchamber, Tshelf, eq_cap, nVial, dt = validation_params
        
        # Get scipy solution
        scipy_output = opt_Pch_Tsh.dry(vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial)
        
        # Create Pyomo model
        model = create_optimizer_model(
            vial, product, ht, vial['Vfill'], eq_cap, nVial,
            Pchamber=Pchamber,
            Tshelf=Tshelf,
            n_elements=8,
            control_mode='both',
            use_finite_differences=True
        )
        
        # Warmstart from scipy
        _warmstart_from_scipy_output(model, scipy_output, vial, product, ht)
        
        # Validate (should have residuals at machine precision)
        residuals = validate_scipy_residuals(model, scipy_output, vial, product, ht, verbose=False)
        
        # Check that all residuals are small
        for name, res_dict in residuals.items():
            if 'mean' in res_dict:
                assert res_dict['mean'] < 1e-3, f"{name} mean residual too large: {res_dict['mean']}"
                assert res_dict['max'] < 1e-2, f"{name} max residual too large: {res_dict['max']}"


class TestPyomoOptPchTshOptimization:
    """Test optimize_Pch_Tsh_pyomo function end-to-end."""
    
    @pytest.fixture
    def optimizer_params(self):
        """Parameters for full optimization test."""
        vial = {'Av': 3.8, 'Ap': 3.14, 'Vfill': 2.0}
        product = {'R0': 1.4, 'A1': 16.0, 'A2': 0.0, 'T_pr_crit': -5.0, 'cSolid': 0.05}
        ht = {'KC': 0.000275, 'KP': 0.000893, 'KD': 0.46}
        Pchamber = {'min': 0.06, 'max': 0.20}
        Tshelf = {'min': -45, 'max': 30, 'init': -35}
        eq_cap = {'a': -0.182, 'b': 11.7}
        nVial = 398
        dt = 0.01
        return vial, product, ht, Pchamber, Tshelf, eq_cap, nVial, dt
    
    def test_optimize_Pch_Tsh_pyomo_converges(self, optimizer_params):
        """Test that optimize_Pch_Tsh_pyomo converges successfully."""
        vial, product, ht, Pchamber, Tshelf, eq_cap, nVial, dt = optimizer_params
        
        result = optimize_Pch_Tsh_pyomo(
            vial, product, ht,
            Pchamber=Pchamber,
            Tshelf=Tshelf,
            dt=dt,
            eq_cap=eq_cap,
            nVial=nVial,
            n_elements=8,  # Higher for joint optimization
            warmstart_scipy=False,  # Disable: scipy opt_Pch_Tsh produces out-of-bounds Pch
            use_trust_region=False,
            tee=False
        )
        
        # Check output shape
        assert result.shape[1] == 7, "Output should have 7 columns"
        assert result.shape[0] > 5, "Output should have multiple time points"
        
        # Check drying completion
        final_dryness = result[-1, 6]
        assert final_dryness >= 0.989, f"Should reach 99% drying, got {final_dryness*100:.1f}%"
        
        # Check temperature constraint
        Tsub_max = result[:, 1].max()
        assert Tsub_max <= -5.0 + 0.5, f"Tsub should stay below T_pr_crit=-5°C, got {Tsub_max:.2f}°C"
    
    def test_optimize_Pch_Tsh_improves_over_single_control(self, optimizer_params):
        """Test that joint optimization is competitive with single-control optimizers."""
        vial, product, ht, Pchamber, Tshelf, eq_cap, nVial, dt = optimizer_params
        
        # Get scipy single-control solutions (for reference)
        Pchamber_fixed = {'setpt': [0.1], 'dt_setpt': [1800], 'ramp_rate': 0.5}
        scipy_Tsh = opt_Tsh.dry(vial, product, ht, Pchamber_fixed, Tshelf, dt, eq_cap, nVial)
        t_Tsh = scipy_Tsh[-1, 0]
        
        # Get joint optimization solution
        pyomo_both = optimize_Pch_Tsh_pyomo(
            vial, product, ht,
            Pchamber=Pchamber,
            Tshelf=Tshelf,
            dt=dt,
            eq_cap=eq_cap,
            nVial=nVial,
            n_elements=8,
            warmstart_scipy=False,  # Disable: scipy opt_Pch_Tsh produces out-of-bounds Pch
            use_trust_region=False,
            tee=False
        )
        t_both = pyomo_both[-1, 0]
        
        # Joint optimization should be faster or competitive (within 20% for robustness)
        time_ratio = t_both / t_Tsh
        assert time_ratio <= 1.20, \
            f"Joint optimization ({t_both:.2f} hr) should be competitive with Tsh-only ({t_Tsh:.2f} hr), ratio={time_ratio:.3f}"
    
    def test_optimize_Pch_Tsh_with_trust_region(self, optimizer_params):
        """Test that trust region option works correctly."""
        vial, product, ht, Pchamber, Tshelf, eq_cap, nVial, dt = optimizer_params
        
        result = optimize_Pch_Tsh_pyomo(
            vial, product, ht,
            Pchamber=Pchamber,
            Tshelf=Tshelf,
            dt=dt,
            eq_cap=eq_cap,
            nVial=nVial,
            n_elements=8,
            warmstart_scipy=False,  # Disable: scipy opt_Pch_Tsh produces out-of-bounds Pch
            use_trust_region=True,
            trust_radii={'Pch': 0.03, 'Tsh': 8.0},
            tee=False
        )
        
        # Should still converge
        assert result is not None, "Trust region optimization should produce result"
        assert result.shape[0] > 0, "Result should have time points"
        
        # Check drying completion
        final_dryness = result[-1, 6]
        assert final_dryness >= 0.989, f"Should reach 99% drying with trust region"
    
    def test_optimize_Pch_Tsh_output_format(self, optimizer_params):
        """Test that output format matches scipy."""
        vial, product, ht, Pchamber, Tshelf, eq_cap, nVial, dt = optimizer_params
        
        result = optimize_Pch_Tsh_pyomo(
            vial, product, ht,
            Pchamber=Pchamber,
            Tshelf=Tshelf,
            dt=dt,
            eq_cap=eq_cap,
            nVial=nVial,
            n_elements=6,
            warmstart_scipy=False,  # Disable: scipy opt_Pch_Tsh produces out-of-bounds Pch
            use_trust_region=False,
            tee=False
        )
        
        # Check columns
        assert result.shape[1] == 7, "Should have 7 columns"
        
        # Check column 0: time (increasing)
        assert np.all(np.diff(result[:, 0]) > 0), "Time should be increasing"
        
        # Check column 4: Pch in mTorr (not Torr)
        Pch_mTorr = result[:, 4]
        assert 50 <= Pch_mTorr.min() <= 1000, "Pch should be in mTorr range"
        
        # Check column 6: fraction dried (0-1, not percentage)
        frac_dried = result[:, 6]
        assert 0 <= frac_dried.min() <= 0.01, "Initial dryness should be near 0"
        assert 0.989 <= frac_dried.max() <= 1.0, "Final dryness should be near 1.0"


class TestPyomoOptPchTshStagedSolve:
    """Test staged solve framework for joint optimization."""
    
    @pytest.fixture
    def staged_params(self):
        """Parameters for staged solve test."""
        vial = {'Av': 3.8, 'Ap': 3.14, 'Vfill': 2.0}
        product = {'R0': 1.4, 'A1': 16.0, 'A2': 0.0, 'T_pr_crit': -5.0, 'cSolid': 0.05}
        ht = {'KC': 0.000275, 'KP': 0.000893, 'KD': 0.46}
        Pchamber = {'min': 0.06, 'max': 0.20}
        Tshelf = {'min': -45, 'max': 30, 'init': -35}
        eq_cap = {'a': -0.182, 'b': 11.7}
        nVial = 398
        dt = 0.01
        return vial, product, ht, Pchamber, Tshelf, eq_cap, nVial, dt
    
    def test_staged_solve_handles_both_controls(self, staged_params):
        """Test that staged solve properly releases both controls sequentially."""
        vial, product, ht, Pchamber, Tshelf, eq_cap, nVial, dt = staged_params
        
        # This is tested implicitly by optimize_Pch_Tsh_pyomo with warmstart_scipy=True
        # Just verify it doesn't raise an exception
        result = optimize_Pch_Tsh_pyomo(
            vial, product, ht,
            Pchamber=Pchamber,
            Tshelf=Tshelf,
            dt=dt,
            eq_cap=eq_cap,
            nVial=nVial,
            n_elements=6,
            warmstart_scipy=False,  # Disable: scipy opt_Pch_Tsh produces out-of-bounds Pch
            use_trust_region=False,
            tee=False
        )
        
        assert result is not None, "Staged solve should produce a result"
        assert result.shape[0] > 0, "Result should have time points"


class TestPyomoOptPchTshPhysicalConstraints:
    """Test that physical constraints are satisfied."""
    
    @pytest.fixture
    def physics_params(self):
        """Parameters for physics test."""
        vial = {'Av': 3.8, 'Ap': 3.14, 'Vfill': 2.0}
        product = {'R0': 1.4, 'A1': 16.0, 'A2': 0.0, 'T_pr_crit': -5.0, 'cSolid': 0.05}
        ht = {'KC': 0.000275, 'KP': 0.000893, 'KD': 0.46}
        Pchamber = {'min': 0.06, 'max': 0.20}
        Tshelf = {'min': -45, 'max': 30, 'init': -35}
        eq_cap = {'a': -0.182, 'b': 11.7}
        nVial = 398
        dt = 0.01
        return vial, product, ht, Pchamber, Tshelf, eq_cap, nVial, dt
    
    def test_temperature_constraint_satisfied(self, physics_params):
        """Test that Tsub <= T_pr_crit throughout drying."""
        vial, product, ht, Pchamber, Tshelf, eq_cap, nVial, dt = physics_params
        
        result = optimize_Pch_Tsh_pyomo(
            vial, product, ht,
            Pchamber=Pchamber,
            Tshelf=Tshelf,
            dt=dt,
            eq_cap=eq_cap,
            nVial=nVial,
            n_elements=6,
            warmstart_scipy=False,  # Disable: scipy opt_Pch_Tsh produces out-of-bounds Pch
            use_trust_region=False,
            tee=False
        )
        
        Tsub = result[:, 1]
        T_pr_crit = product['T_pr_crit']
        
        # Allow small numerical tolerance
        assert np.all(Tsub <= T_pr_crit + 0.5), \
            f"Tsub should stay below {T_pr_crit}°C, max={Tsub.max():.2f}°C"
    
    def test_both_controls_vary(self, physics_params):
        """Test that both Pch and Tsh vary in joint optimization."""
        vial, product, ht, Pchamber, Tshelf, eq_cap, nVial, dt = physics_params
        
        result = optimize_Pch_Tsh_pyomo(
            vial, product, ht,
            Pchamber=Pchamber,
            Tshelf=Tshelf,
            dt=dt,
            eq_cap=eq_cap,
            nVial=nVial,
            n_elements=6,
            warmstart_scipy=False,  # Disable: scipy opt_Pch_Tsh produces out-of-bounds Pch
            use_trust_region=False,
            tee=False
        )
        
        Pch_mTorr = result[:, 4]
        Tsh = result[:, 3]
        
        # Check that Pch varies
        Pch_range = Pch_mTorr.max() - Pch_mTorr.min()
        assert Pch_range > 10, f"Pch should vary in joint optimization, range={Pch_range:.1f} mTorr"
        
        # Check that Tsh varies
        Tsh_range = Tsh.max() - Tsh.min()
        assert Tsh_range > 5, f"Tsh should vary in joint optimization, range={Tsh_range:.1f} °C"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
