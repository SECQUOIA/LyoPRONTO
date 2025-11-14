"""Tests for multi-period Pyomo DAE model.

This module tests the dynamic optimization model using orthogonal collocation.
"""

# LyoPRONTO, a vial-scale lyophilization process simulator
# Nonlinear optimization
# Copyright (C) 2025, David E. Bernal Neira

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import pytest
import numpy as np
from lyopronto.pyomo_models import multi_period

# Try to import pyomo and dae
try:
    import pyomo.environ as pyo
    import pyomo.dae as dae
    PYOMO_AVAILABLE = True
except ImportError:
    PYOMO_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not PYOMO_AVAILABLE,
    reason="Pyomo not available"
)


class TestMultiPeriodModelStructure:
    """Tests for multi-period model construction."""
    
    def test_model_creates_successfully(self, standard_vial, standard_product, standard_ht):
        """Verify model can be created without errors."""
        model = multi_period.create_multi_period_model(
            standard_vial,
            standard_product,
            standard_ht,
            Vfill=2.0,
            n_elements=3,  # Small for testing
            n_collocation=2,
            apply_scaling=False
        )
        
        assert model is not None
        assert hasattr(model, 't')
        assert hasattr(model, 'Tsub')
        assert hasattr(model, 'Pch')
        assert hasattr(model, 'Tsh')
        
    def test_model_has_continuous_set(self, standard_vial, standard_product, standard_ht):
        """Verify time is a continuous set."""
        model = multi_period.create_multi_period_model(
            standard_vial,
            standard_product,
            standard_ht,
            Vfill=2.0,
            n_elements=3,
            n_collocation=2,
            apply_scaling=False
        )
        
        # Check that t is a ContinuousSet
        assert isinstance(model.t, dae.ContinuousSet)
        
        # Check bounds
        t_points = sorted(model.t)
        assert t_points[0] == 0.0
        assert t_points[-1] == 1.0
        
    def test_model_has_state_variables(self, standard_vial, standard_product, standard_ht):
        """Verify all state variables exist."""
        model = multi_period.create_multi_period_model(
            standard_vial,
            standard_product,
            standard_ht,
            Vfill=2.0,
            n_elements=3,
            n_collocation=2,
            apply_scaling=False
        )
        
        # State variables (with derivatives)
        assert hasattr(model, 'Tsub')
        assert hasattr(model, 'Tbot')
        assert hasattr(model, 'Lck')
        assert hasattr(model, 'dTsub_dt')
        assert hasattr(model, 'dTbot_dt')
        assert hasattr(model, 'dLck_dt')
        
    def test_model_has_control_variables(self, standard_vial, standard_product, standard_ht):
        """Verify control variables exist."""
        model = multi_period.create_multi_period_model(
            standard_vial,
            standard_product,
            standard_ht,
            Vfill=2.0,
            n_elements=3,
            n_collocation=2,
            apply_scaling=False
        )
        
        assert hasattr(model, 'Pch')
        assert hasattr(model, 'Tsh')
        assert hasattr(model, 't_final')
        
    def test_model_has_algebraic_variables(self, standard_vial, standard_product, standard_ht):
        """Verify algebraic variables exist."""
        model = multi_period.create_multi_period_model(
            standard_vial,
            standard_product,
            standard_ht,
            Vfill=2.0,
            n_elements=3,
            n_collocation=2,
            apply_scaling=False
        )
        
        assert hasattr(model, 'Psub')
        assert hasattr(model, 'log_Psub')
        assert hasattr(model, 'dmdt')
        assert hasattr(model, 'Kv')
        assert hasattr(model, 'Rp')
        
    def test_model_has_constraints(self, standard_vial, standard_product, standard_ht):
        """Verify key constraints exist."""
        model = multi_period.create_multi_period_model(
            standard_vial,
            standard_product,
            standard_ht,
            Vfill=2.0,
            n_elements=3,
            n_collocation=2,
            apply_scaling=False
        )
        
        # Algebraic constraints
        assert hasattr(model, 'vapor_pressure_log')
        assert hasattr(model, 'vapor_pressure_exp')
        assert hasattr(model, 'product_resistance')
        assert hasattr(model, 'kv_calc')
        assert hasattr(model, 'sublimation_rate')
        
        # Differential equations
        assert hasattr(model, 'heat_balance_ode')
        assert hasattr(model, 'vial_bottom_temp_ode')
        assert hasattr(model, 'cake_length_ode')
        
        # Initial conditions
        assert hasattr(model, 'tsub_ic')
        assert hasattr(model, 'tbot_ic')
        assert hasattr(model, 'lck_ic')
        
        # Terminal constraints
        assert hasattr(model, 'final_dryness')
        
        # Path constraints
        assert hasattr(model, 'temp_limit')
        
    def test_model_has_objective(self, standard_vial, standard_product, standard_ht):
        """Verify objective function exists."""
        model = multi_period.create_multi_period_model(
            standard_vial,
            standard_product,
            standard_ht,
            Vfill=2.0,
            n_elements=3,
            n_collocation=2,
            apply_scaling=False
        )
        
        assert hasattr(model, 'obj')
        assert isinstance(model.obj, pyo.Objective)
        
    def test_collocation_creates_multiple_time_points(self, standard_vial, standard_product, standard_ht):
        """Verify collocation creates appropriate discretization."""
        model = multi_period.create_multi_period_model(
            standard_vial,
            standard_product,
            standard_ht,
            Vfill=2.0,
            n_elements=5,
            n_collocation=3,
            apply_scaling=False
        )
        
        t_points = sorted(model.t)
        
        # Should have: 1 (t=0) + n_elements * n_collocation
        # Actually for Radau: 1 + n_elements * (n_collocation + 1) points
        # But Pyomo handles this internally
        
        print(f"\nNumber of time points: {len(t_points)}")
        print(f"First 5 points: {t_points[:5]}")
        print(f"Last 5 points: {t_points[-5:]}")
        
        # Should have more than just the element boundaries
        assert len(t_points) > 5, "Should have collocation points within elements"
        
    def test_scaling_applied_when_requested(self, standard_vial, standard_product, standard_ht):
        """Verify scaling is applied when requested."""
        model_scaled = multi_period.create_multi_period_model(
            standard_vial,
            standard_product,
            standard_ht,
            Vfill=2.0,
            n_elements=3,
            n_collocation=2,
            apply_scaling=True
        )
        
        model_unscaled = multi_period.create_multi_period_model(
            standard_vial,
            standard_product,
            standard_ht,
            Vfill=2.0,
            n_elements=3,
            n_collocation=2,
            apply_scaling=False
        )
        
        # Scaled model should have scaling_factor suffix
        assert hasattr(model_scaled, 'scaling_factor')
        assert not hasattr(model_unscaled, 'scaling_factor')


class TestMultiPeriodWarmstart:
    """Tests for warmstart functionality."""
    
    def test_warmstart_from_scipy_runs(self, standard_vial, standard_product, standard_ht):
        """Verify warmstart function runs without errors."""
        from lyopronto import calc_knownRp
        
        # Get scipy trajectory - need to match the API
        Pchamber = {'setpt': [0.1], 'time': [0]}
        Tshelf = {'setpt': [-10.0], 'time': [0], 'ramp_rate': 1.0, 'init': -40.0}
        dt = 1.0
        
        scipy_traj = calc_knownRp.dry(
            standard_vial,
            standard_product,
            standard_ht,
            Pchamber,
            Tshelf,
            dt
        )
        
        # Create model
        model = multi_period.create_multi_period_model(
            standard_vial,
            standard_product,
            standard_ht,
            Vfill=standard_vial['Vfill'],
            n_elements=3,
            n_collocation=2,
            apply_scaling=False
        )
        
        # Apply warmstart
        multi_period.warmstart_from_scipy_trajectory(
            model,
            scipy_traj,
            standard_vial,
            standard_product,
            standard_ht
        )
        
        # Check that some variables were initialized
        t_points = sorted(model.t)
        
        # Check a few values are not default
        Tsub_vals = [pyo.value(model.Tsub[t]) for t in t_points]
        print(f"\nTsub values after warmstart: {Tsub_vals[:3]}")
        
        # Should have reasonable values (not all the same)
        assert len(set(Tsub_vals)) > 1, "Tsub should vary across time"


@pytest.mark.slow
class TestMultiPeriodOptimization:
    """Tests for full optimization (slow, marked for optional execution)."""
    
    @pytest.mark.skip(reason="Full optimization is slow, enable manually for integration testing")
    def test_optimization_runs(self, standard_vial, standard_product, standard_ht):
        """Verify optimization completes (slow test)."""
        from lyopronto import calc_knownRp
        
        # Get warmstart
        scipy_traj = calc_knownRp.dry(
            standard_vial,
            standard_product,
            standard_ht,
            Vfill=2.0,
            Tsh=-10.0,
            Pch=0.1
        )
        
        # Run optimization (small problem for testing)
        solution = multi_period.optimize_multi_period(
            standard_vial,
            standard_product,
            standard_ht,
            Vfill=2.0,
            n_elements=3,
            n_collocation=2,
            warmstart_data=scipy_traj,
            tee=True
        )
        
        # Check solution structure
        assert 't' in solution
        assert 'Pch' in solution
        assert 'Tsh' in solution
        assert 'Tsub' in solution
        assert 't_final' in solution
        assert 'status' in solution
        
        print(f"\nOptimization status: {solution['status']}")
        print(f"Optimal drying time: {solution['t_final']:.2f} hr")
