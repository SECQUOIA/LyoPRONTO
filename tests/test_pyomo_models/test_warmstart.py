"""Tests for warmstart adapters for scipy optimizers.

This module tests that _warmstart_from_scipy_output correctly handles
trajectories from opt_Tsh, opt_Pch, and opt_Pch_Tsh, with proper:
- Nearest-neighbor time alignment (not interpolation)
- Constraint-consistent assignment of Psub, Rp, Kv, dmdt
- Control variable initialization (both Pch and Tsh)
"""

import pytest
import numpy as np

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
        solver = get_solver('ipopt')
        IPOPT_AVAILABLE = True
    except:
        try:
            solver = pyo.SolverFactory('ipopt')
            IPOPT_AVAILABLE = solver.available()
        except:
            IPOPT_AVAILABLE = False

pytestmark = [
    pytest.mark.pyomo,
    pytest.mark.skipif(
        not (PYOMO_AVAILABLE and IPOPT_AVAILABLE),
        reason="Pyomo or IPOPT solver not available"
    ),
]

from lyopronto.pyomo_models.optimizers import create_optimizer_model
from lyopronto.pyomo_models.optimizers import _warmstart_from_scipy_output
from lyopronto import opt_Tsh, opt_Pch_Tsh, functions


class TestWarmstartFromOptTsh:
    """Tests for warmstart from opt_Tsh.dry() output."""
    
    @pytest.fixture
    def common_params(self):
        """Common test parameters."""
        return {
            'vial': {'Av': 3.8, 'Ap': 3.14, 'Vfill': 2.0},
            'product': {'R0': 1.4, 'A1': 16.0, 'A2': 0.0, 'T_pr_crit': -5.0, 'cSolid': 0.05},
            'ht': {'KC': 0.000275, 'KP': 0.000893, 'KD': 0.46},
            'eq_cap': {'a': -0.182, 'b': 11.7},
            'nVial': 398,
            'dt': 0.01
        }
    
    def test_warmstart_from_opt_tsh_succeeds(self, common_params):
        """Test that warmstart from opt_Tsh.dry() output succeeds."""
        Pchamber_fixed = {'setpt': [0.10], 'dt_setpt': [1800], 'ramp_rate': 0.5}
        Tshelf_opt = {'min': -45, 'max': 30, 'init': -35}
        
        # Get scipy solution
        scipy_output = opt_Tsh.dry(
            common_params['vial'],
            common_params['product'],
            common_params['ht'],
            Pchamber_fixed,
            Tshelf_opt,
            common_params['dt'],
            common_params['eq_cap'],
            common_params['nVial']
        )
        
        # Create Pyomo model
        model = create_optimizer_model(
            common_params['vial'],
            common_params['product'],
            common_params['ht'],
            common_params['vial']['Vfill'],
            common_params['eq_cap'],
            common_params['nVial'],
            Pchamber=Pchamber_fixed,
            Tshelf=Tshelf_opt,
            n_elements=8,
            control_mode='Tsh'
        )
        
        # Warmstart should not raise
        _warmstart_from_scipy_output(
            model,
            scipy_output,
            common_params['vial'],
            common_params['product'],
            common_params['ht']
        )
        
        # Verify state variables are initialized
        t0 = min(model.t)
        assert model.Lck[t0].value is not None
        assert model.Tsub[t0].value is not None
        assert model.Tbot[t0].value is not None
    
    def test_warmstart_initializes_physically_reasonable_values(self, common_params):
        """Test that warmstart initializes physically reasonable values."""
        Pchamber_fixed = {'setpt': [0.10], 'dt_setpt': [1800], 'ramp_rate': 0.5}
        Tshelf_opt = {'min': -45, 'max': 30, 'init': -35}
        
        scipy_output = opt_Tsh.dry(
            common_params['vial'],
            common_params['product'],
            common_params['ht'],
            Pchamber_fixed,
            Tshelf_opt,
            common_params['dt'],
            common_params['eq_cap'],
            common_params['nVial']
        )
        
        model = create_optimizer_model(
            common_params['vial'],
            common_params['product'],
            common_params['ht'],
            common_params['vial']['Vfill'],
            common_params['eq_cap'],
            common_params['nVial'],
            Pchamber=Pchamber_fixed,
            Tshelf=Tshelf_opt,
            n_elements=8,
            control_mode='Tsh'
        )
        
        _warmstart_from_scipy_output(
            model,
            scipy_output,
            common_params['vial'],
            common_params['product'],
            common_params['ht']
        )
        
        t0 = min(model.t)
        
        # Check physical reasonableness
        assert -60 <= model.Tsub[t0].value <= 0, "Tsub should be below freezing"
        assert -60 <= model.Tbot[t0].value <= 50, "Tbot should be reasonable"
        assert model.Lck[t0].value >= 0, "Lck should be non-negative"
    
    def test_warmstart_constraint_consistency(self, common_params):
        """Test that warmstart maintains constraint consistency for auxiliary vars."""
        Pchamber_fixed = {'setpt': [0.10], 'dt_setpt': [1800], 'ramp_rate': 0.5}
        Tshelf_opt = {'min': -45, 'max': 30, 'init': -35}
        
        scipy_output = opt_Tsh.dry(
            common_params['vial'],
            common_params['product'],
            common_params['ht'],
            Pchamber_fixed,
            Tshelf_opt,
            common_params['dt'],
            common_params['eq_cap'],
            common_params['nVial']
        )
        
        model = create_optimizer_model(
            common_params['vial'],
            common_params['product'],
            common_params['ht'],
            common_params['vial']['Vfill'],
            common_params['eq_cap'],
            common_params['nVial'],
            Pchamber=Pchamber_fixed,
            Tshelf=Tshelf_opt,
            n_elements=8,
            control_mode='Tsh'
        )
        
        _warmstart_from_scipy_output(
            model,
            scipy_output,
            common_params['vial'],
            common_params['product'],
            common_params['ht']
        )
        
        t0 = min(model.t)
        
        # Verify Psub consistency with vapor pressure equation
        Tsub_val = model.Tsub[t0].value
        Psub_calc = functions.Vapor_pressure(Tsub_val)
        Psub_model = model.Psub[t0].value
        
        assert abs(Psub_calc - Psub_model) < 1e-4, (
            f"Psub mismatch: calculated={Psub_calc:.4f}, model={Psub_model:.4f}"
        )


class TestWarmstartFromOptPchTsh:
    """Tests for warmstart from opt_Pch_Tsh.dry() output."""
    
    @pytest.fixture
    def common_params(self):
        """Common test parameters."""
        return {
            'vial': {'Av': 3.8, 'Ap': 3.14, 'Vfill': 2.0},
            'product': {'R0': 1.4, 'A1': 16.0, 'A2': 0.0, 'T_pr_crit': -5.0, 'cSolid': 0.05},
            'ht': {'KC': 0.000275, 'KP': 0.000893, 'KD': 0.46},
            'eq_cap': {'a': -0.182, 'b': 11.7},
            'nVial': 398,
            'dt': 0.01
        }
    
    def test_warmstart_from_opt_pch_tsh_succeeds(self, common_params):
        """Test that warmstart from opt_Pch_Tsh.dry() output succeeds."""
        # Use wide bounds to accommodate scipy solution
        Pchamber_opt = {'min': 0.06, 'max': 0.30}
        Tshelf_opt = {'min': -45, 'max': 30, 'init': -35}
        
        scipy_output = opt_Pch_Tsh.dry(
            common_params['vial'],
            common_params['product'],
            common_params['ht'],
            Pchamber_opt,
            Tshelf_opt,
            common_params['dt'],
            common_params['eq_cap'],
            common_params['nVial']
        )
        
        model = create_optimizer_model(
            common_params['vial'],
            common_params['product'],
            common_params['ht'],
            common_params['vial']['Vfill'],
            common_params['eq_cap'],
            common_params['nVial'],
            Pchamber=Pchamber_opt,
            Tshelf=Tshelf_opt,
            n_elements=8,
            control_mode='both'
        )
        
        # Warmstart should not raise
        _warmstart_from_scipy_output(
            model,
            scipy_output,
            common_params['vial'],
            common_params['product'],
            common_params['ht']
        )
        
        # Verify state variables are initialized
        t0 = min(model.t)
        assert model.Lck[t0].value is not None
        assert model.Tsub[t0].value is not None
        assert model.Pch[t0].value is not None
        assert model.Tsh[t0].value is not None
    
    def test_warmstart_initializes_both_controls(self, common_params):
        """Test that warmstart initializes both Pch and Tsh controls.
        
        Note: scipy opt_Pch_Tsh doesn't strictly respect pressure bounds,
        so we only verify values are initialized (not that they're in bounds).
        The Pyomo optimizer will then optimize starting from this initial point.
        """
        Pchamber_opt = {'min': 0.06, 'max': 0.30}
        Tshelf_opt = {'min': -45, 'max': 30, 'init': -35}
        
        scipy_output = opt_Pch_Tsh.dry(
            common_params['vial'],
            common_params['product'],
            common_params['ht'],
            Pchamber_opt,
            Tshelf_opt,
            common_params['dt'],
            common_params['eq_cap'],
            common_params['nVial']
        )
        
        model = create_optimizer_model(
            common_params['vial'],
            common_params['product'],
            common_params['ht'],
            common_params['vial']['Vfill'],
            common_params['eq_cap'],
            common_params['nVial'],
            Pchamber=Pchamber_opt,
            Tshelf=Tshelf_opt,
            n_elements=8,
            control_mode='both'
        )
        
        _warmstart_from_scipy_output(
            model,
            scipy_output,
            common_params['vial'],
            common_params['product'],
            common_params['ht']
        )
        
        # Check multiple time points have values for both controls
        # Note: We only check that values are initialized, not that they're
        # in bounds, because scipy doesn't strictly respect pressure bounds
        t_points = sorted(model.t)
        for t in t_points[:5]:
            assert model.Pch[t].value is not None, f"Pch[{t}] not initialized"
            assert model.Tsh[t].value is not None, f"Tsh[{t}] not initialized"
            # Verify values are positive/reasonable (not that they match bounds)
            assert model.Pch[t].value > 0, f"Pch[{t}] should be positive"
            assert -100 <= model.Tsh[t].value <= 200, f"Tsh[{t}] unreasonable"


class TestNearestNeighborMapping:
    """Tests for nearest-neighbor time mapping in warmstart."""
    
    @pytest.fixture
    def common_params(self):
        """Common test parameters."""
        return {
            'vial': {'Av': 3.8, 'Ap': 3.14, 'Vfill': 2.0},
            'product': {'R0': 1.4, 'A1': 16.0, 'A2': 0.0, 'T_pr_crit': -5.0, 'cSolid': 0.05},
            'ht': {'KC': 0.000275, 'KP': 0.000893, 'KD': 0.46},
            'eq_cap': {'a': -0.182, 'b': 11.7},
            'nVial': 398,
            'dt': 0.01
        }
    
    def test_coarse_mesh_uses_nearest_neighbor(self, common_params):
        """Test that coarse Pyomo mesh uses nearest-neighbor mapping."""
        Pchamber_opt = {'min': 0.06, 'max': 0.30}
        Tshelf_opt = {'min': -45, 'max': 30, 'init': -35}
        
        scipy_output = opt_Pch_Tsh.dry(
            common_params['vial'],
            common_params['product'],
            common_params['ht'],
            Pchamber_opt,
            Tshelf_opt,
            common_params['dt'],
            common_params['eq_cap'],
            common_params['nVial']
        )
        
        # Use very coarse mesh
        model = create_optimizer_model(
            common_params['vial'],
            common_params['product'],
            common_params['ht'],
            common_params['vial']['Vfill'],
            common_params['eq_cap'],
            common_params['nVial'],
            Pchamber=Pchamber_opt,
            Tshelf=Tshelf_opt,
            n_elements=4,  # Very coarse
            control_mode='both'
        )
        
        _warmstart_from_scipy_output(
            model,
            scipy_output,
            common_params['vial'],
            common_params['product'],
            common_params['ht']
        )
        
        t_pyomo = sorted(model.t)
        t_final_scipy = scipy_output[-1, 0]
        
        # Verify values match scipy at nearest points (not interpolated)
        for t_norm in t_pyomo[:3]:
            t_actual = t_norm * t_final_scipy
            scipy_idx = np.argmin(np.abs(scipy_output[:, 0] - t_actual))
            
            Tsub_pyomo = model.Tsub[t_norm].value
            Tsub_scipy = scipy_output[scipy_idx, 1]
            
            # Should match exactly (within numerical tolerance)
            assert abs(Tsub_pyomo - Tsub_scipy) < 1e-3, (
                f"Tsub not matching at t_norm={t_norm}: "
                f"Pyomo={Tsub_pyomo:.2f}, Scipy={Tsub_scipy:.2f}"
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
