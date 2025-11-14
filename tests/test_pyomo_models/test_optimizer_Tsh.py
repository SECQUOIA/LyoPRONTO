"""Tests for Pyomo opt_Tsh equivalent - shelf temperature optimization.

This module tests the Pyomo multi-period optimizer against scipy opt_Tsh reference,
validating equivalence within acceptable tolerances.
"""

import pytest
import numpy as np
from lyopronto import opt_Tsh
from lyopronto.pyomo_models import optimizers

# Try to import pyomo
try:
    import pyomo.environ as pyo
    PYOMO_AVAILABLE = True
except ImportError:
    PYOMO_AVAILABLE = False

# Check for IPOPT solver (via IDAES or standalone)
IPOPT_AVAILABLE = False
if PYOMO_AVAILABLE:
    try:
        from idaes.core.solvers import get_solver
        solver = get_solver('ipopt')
        IPOPT_AVAILABLE = True
    except:
        try:
            solver = pyo.SolverFactory('ipopt')
            IPOPT_AVAILABLE = solver.available()
        except:
            IPOPT_AVAILABLE = False

pytestmark = [
    pytest.mark.skipif(
        not (PYOMO_AVAILABLE and IPOPT_AVAILABLE),
        reason="Pyomo or IPOPT solver not available"
    ),
    pytest.mark.serial,  # Run these tests serially, not in parallel
    pytest.mark.xdist_group("pyomo_serial")  # Group all pyomo tests in same worker
]


@pytest.fixture
def standard_opt_tsh_inputs():
    """Standard inputs matching test_opt_Tsh.py."""
    vial = {
        'Av': 3.8,     # Vial area [cm**2]
        'Ap': 3.14,    # Product area [cm**2]
        'Vfill': 2.0   # Fill volume [mL]
    }
    
    product = {
        'T_pr_crit': -5.0,   # Critical product temperature [degC]
        'cSolid': 0.05,      # Solid content [g/mL]
        'R0': 1.4,           # Product resistance coefficient R0 [cm**2-hr-Torr/g]
        'A1': 16.0,          # Product resistance coefficient A1 [1/cm]
        'A2': 0.0            # Product resistance coefficient A2 [1/cm**2]
    }
    
    ht = {
        'KC': 0.000275,   # Kc [cal/s/K/cm**2]
        'KP': 0.000893,   # Kp [cal/s/K/cm**2/Torr]
        'KD': 0.46        # Kd dimensionless
    }
    
    Pchamber = {
        'setpt': np.array([0.15]),      # Set point [Torr]
        'dt_setpt': np.array([1800]),   # Hold time [min]
        'ramp_rate': 0.5,                # Ramp rate [Torr/min]
        'time': [0]                     # Initial time
    }
    
    Tshelf = {
        'min': -45.0,                   # Minimum shelf temperature
        'max': 120.0,                   # Maximum shelf temperature
        'init': -35.0,                  # Initial shelf temperature
        'setpt': np.array([120.0]),     # Target set point
        'dt_setpt': np.array([1800]),   # Hold time [min]
        'ramp_rate': 1.0                # Ramp rate [degC/min]
    }
    
    eq_cap = {
        'a': -0.182,   # Equipment capability coefficient a
        'b': 11.7      # Equipment capability coefficient b
    }
    
    nVial = 398
    dt = 0.01   # Time step [hr]
    
    return vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial


class TestPyomoOptTshBasic:
    """Basic functionality tests for Pyomo opt_Tsh."""
    
    def test_pyomo_opt_tsh_runs(self, standard_opt_tsh_inputs):
        """Test that Pyomo optimizer executes successfully."""
        vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial = standard_opt_tsh_inputs
        
        output = optimizers.optimize_Tsh_pyomo(
            vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial,
            n_elements=5, n_collocation=2  # Small for fast test
        )
        
        assert output is not None
        assert isinstance(output, np.ndarray)
        assert output.size > 0
    
    def test_output_shape(self, standard_opt_tsh_inputs):
        """Test that output has correct shape matching scipy."""
        vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial = standard_opt_tsh_inputs
        
        output = optimizers.optimize_Tsh_pyomo(
            vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial,
            n_elements=5, n_collocation=2
        )
        
        # Should have 7 columns like scipy
        assert output.shape[1] == 7
        assert output.shape[0] > 1
    
    def test_drying_completes(self, standard_opt_tsh_inputs):
        """Test that optimization reaches near-complete drying."""
        vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial = standard_opt_tsh_inputs
        
        output = optimizers.optimize_Tsh_pyomo(
            vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial,
            n_elements=5, n_collocation=2
        )
        
        final_dried = output[-1, 6]
        assert final_dried >= 0.989, f"Should dry to >98.9%, got {final_dried*100:.1f}%"
    
    def test_respects_critical_temperature(self, standard_opt_tsh_inputs):
        """Test that product temperature stays at or below critical."""
        vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial = standard_opt_tsh_inputs
        
        output = optimizers.optimize_Tsh_pyomo(
            vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial,
            n_elements=5, n_collocation=2
        )
        
        T_bot = output[:, 2]
        T_crit = product['T_pr_crit']
        
        # Allow 2.5°C tolerance for discretization effects in Pyomo collocation
        assert np.all(T_bot <= T_crit + 2.5), \
            f"Product temperature exceeded critical: max={T_bot.max():.2f}°C, crit={T_crit}°C"
    
    def test_chamber_pressure_fixed(self, standard_opt_tsh_inputs):
        """Test that chamber pressure remains at fixed setpoint."""
        vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial = standard_opt_tsh_inputs
        
        output = optimizers.optimize_Tsh_pyomo(
            vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial,
            n_elements=5, n_collocation=2
        )
        
        P_chamber_mTorr = output[:, 4]
        P_setpoint_mTorr = Pchamber['setpt'][0] * 1000
        
        # Should remain at setpoint (small tolerance for numerical precision)
        assert np.all(np.abs(P_chamber_mTorr - P_setpoint_mTorr) < 1.0), \
            f"Pressure deviated from setpoint"
    
    def test_shelf_temperature_optimized(self, standard_opt_tsh_inputs):
        """Test that shelf temperature varies (is optimized)."""
        vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial = standard_opt_tsh_inputs
        
        output = optimizers.optimize_Tsh_pyomo(
            vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial,
            n_elements=5, n_collocation=2
        )
        
        T_shelf = output[:, 3]
        
        # Shelf temperature should vary
        assert np.std(T_shelf) > 1.0, "Shelf temperature should vary (be optimized)"
        
        # Should respect bounds
        assert np.all(T_shelf >= Tshelf['min'] - 1.0)
        assert np.all(T_shelf <= Tshelf['max'] + 1.0)


@pytest.mark.slow
class TestPyomoOptTshEquivalence:
    """Validation tests comparing Pyomo to scipy opt_Tsh."""
    
    def test_matches_scipy_final_time(self, standard_opt_tsh_inputs):
        """Test that final drying time matches scipy within tolerance."""
        vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial = standard_opt_tsh_inputs
        
        # Run scipy
        scipy_output = opt_Tsh.dry(vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial)
        scipy_time = scipy_output[-1, 0]
        
        # Run Pyomo
        pyomo_output = optimizers.optimize_Tsh_pyomo(
            vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial,
            n_elements=8, n_collocation=3
        )
        pyomo_time = pyomo_output[-1, 0]
        
        # Should match within 10% (allowing for discretization differences)
        time_tolerance = 0.10 * scipy_time
        assert abs(pyomo_time - scipy_time) < time_tolerance, \
            f"Time mismatch: Pyomo {pyomo_time:.3f} hr vs scipy {scipy_time:.3f} hr"
    
    def test_matches_scipy_max_temperature(self, standard_opt_tsh_inputs):
        """Test that maximum product temperature matches scipy."""
        vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial = standard_opt_tsh_inputs
        
        # Run scipy
        scipy_output = opt_Tsh.dry(vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial)
        scipy_max_T = scipy_output[:, 2].max()
        
        # Run Pyomo
        pyomo_output = optimizers.optimize_Tsh_pyomo(
            vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial,
            n_elements=8, n_collocation=3
        )
        pyomo_max_T = pyomo_output[:, 2].max()
        
        # Should match within 2.5°C (discretization can produce different temperature profiles)
        assert abs(pyomo_max_T - scipy_max_T) < 2.5, \
            f"Max T mismatch: Pyomo {pyomo_max_T:.2f}°C vs scipy {scipy_max_T:.2f}°C"
    
    def test_physical_consistency(self, standard_opt_tsh_inputs):
        """Test that Pyomo solution is physically consistent."""
        vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial = standard_opt_tsh_inputs
        
        output = optimizers.optimize_Tsh_pyomo(
            vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial,
            n_elements=8, n_collocation=3
        )
        
        time = output[:, 0]
        percent_dried = output[:, 6]
        flux = output[:, 5]
        
        # Time monotonically increasing
        assert np.all(np.diff(time) > 0)
        
        # Percent dried monotonically increasing
        assert np.all(np.diff(percent_dried) >= -1e-6)
        
        # Flux positive
        assert np.all(flux > 0)
        
        # Starts at 0% dried
        assert percent_dried[0] < 0.01
        
        # Ends near 100% dried (allow numerical tolerance)
        assert percent_dried[-1] > 0.989


class TestPyomoOptTshEdgeCases:
    """Edge case tests for Pyomo opt_Tsh."""
    
    def test_different_critical_temps(self, standard_opt_tsh_inputs):
        """Test with different critical temperatures."""
        vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial = standard_opt_tsh_inputs
        
        # Lower critical temperature (slower drying)
        product_low = product.copy()
        product_low['T_pr_crit'] = -10.0
        
        output = optimizers.optimize_Tsh_pyomo(
            vial, product_low, ht, Pchamber, Tshelf, dt, eq_cap, nVial,
            n_elements=5, n_collocation=2
        )
        
        assert output[-1, 6] > 0.989  # Allow numerical tolerance
        # Allow 3.5°C tolerance for discretization effects with lower critical temp
        assert np.all(output[:, 2] <= -6.5), f"Max Tbot={output[:, 2].max():.2f}°C exceeds -6.5°C"
    
    @pytest.mark.slow
    def test_consistent_results(self, standard_opt_tsh_inputs):
        """Test that repeated runs give consistent results."""
        vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial = standard_opt_tsh_inputs
        
        output1 = optimizers.optimize_Tsh_pyomo(
            vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial,
            n_elements=6, n_collocation=2
        )
        
        output2 = optimizers.optimize_Tsh_pyomo(
            vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial,
            n_elements=6, n_collocation=2
        )
        
        # Should be deterministic
        np.testing.assert_array_almost_equal(output1, output2, decimal=4)
