"""Tests for Pyomo single-step optimization model.

This module tests the Pyomo-based single time-step optimization against
the scipy baseline to ensure correctness and consistency.
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
from lyopronto import functions, constant
from lyopronto.pyomo_models import single_step, utils

# Try to import pyomo - skip tests if not available
try:
    import pyomo.environ as pyo
    PYOMO_AVAILABLE = True
except ImportError:
    PYOMO_AVAILABLE = False

pytestmark = pytest.mark.skipif(not PYOMO_AVAILABLE, reason="Pyomo not installed")


class TestSingleStepModel:
    """Tests for Pyomo single-step model creation and structure."""
    
    def test_model_creation_basic(self, standard_vial, standard_product, standard_ht):
        """Test that model can be created with standard inputs."""
        Lpr0 = functions.Lpr0_FUN(2.0, standard_vial['Ap'], standard_product['cSolid'])
        Lck = 0.5  # Half dried
        
        model = single_step.create_single_step_model(
            standard_vial, 
            standard_product, 
            standard_ht, 
            Lpr0, 
            Lck
        )
        
        # Check model type
        assert isinstance(model, pyo.ConcreteModel)
        
        # Check key variables exist
        assert hasattr(model, 'Pch')
        assert hasattr(model, 'Tsh')
        assert hasattr(model, 'Tsub')
        assert hasattr(model, 'Tbot')
        assert hasattr(model, 'Psub')
        assert hasattr(model, 'dmdt')
        assert hasattr(model, 'Kv')
        
        # Check constraints exist
        assert hasattr(model, 'vapor_pressure_log')
        assert hasattr(model, 'vapor_pressure_exp')
        assert hasattr(model, 'sublimation_rate')
        assert hasattr(model, 'heat_balance')
        assert hasattr(model, 'shelf_temp')
        assert hasattr(model, 'kv_calc')
        assert hasattr(model, 'temp_limit')
        
        # Check log_Psub variable exists
        assert hasattr(model, 'log_Psub')
        
        # Check objective exists
        assert hasattr(model, 'obj')
    
    def test_model_with_equipment_constraint(self, standard_vial, standard_product, standard_ht):
        """Test model creation with equipment capability constraint."""
        Lpr0 = functions.Lpr0_FUN(2.0, standard_vial['Ap'], standard_product['cSolid'])
        Lck = 0.5
        eq_cap = {'a': -0.182, 'b': 11.7}
        nVial = 398
        
        model = single_step.create_single_step_model(
            standard_vial,
            standard_product,
            standard_ht,
            Lpr0,
            Lck,
            eq_cap=eq_cap,
            nVial=nVial
        )
        
        # Check equipment constraint exists
        assert hasattr(model, 'equipment_capability')
        assert hasattr(model, 'a_eq')
        assert hasattr(model, 'b_eq')
        assert hasattr(model, 'nVial')
    
    def test_variable_bounds(self, standard_vial, standard_product, standard_ht):
        """Test that variable bounds are correctly set."""
        Lpr0 = functions.Lpr0_FUN(2.0, standard_vial['Ap'], standard_product['cSolid'])
        Lck = 0.5
        Pch_bounds = (0.1, 0.3)
        Tsh_bounds = (-40, 30)
        
        model = single_step.create_single_step_model(
            standard_vial,
            standard_product,
            standard_ht,
            Lpr0,
            Lck,
            Pch_bounds=Pch_bounds,
            Tsh_bounds=Tsh_bounds
        )
        
        # Check bounds
        assert model.Pch.bounds == Pch_bounds
        assert model.Tsh.bounds == Tsh_bounds
        assert model.Tsub.bounds == (-60, 0)
        assert model.dmdt.bounds[0] == 0  # Lower bound must be non-negative


class TestSingleStepSolver:
    """Tests for solving Pyomo single-step model."""
    
    @pytest.mark.slow
    def test_solve_basic(self, standard_vial, standard_product, standard_ht):
        """Test that model can be solved successfully."""
        Lpr0 = functions.Lpr0_FUN(2.0, standard_vial['Ap'], standard_product['cSolid'])
        Lck = 0.5
        
        model = single_step.create_single_step_model(
            standard_vial,
            standard_product,
            standard_ht,
            Lpr0,
            Lck
        )
        
        solution = single_step.solve_single_step(model, tee=False)
        
        # Check solution structure
        assert 'status' in solution
        assert 'Pch' in solution
        assert 'Tsh' in solution
        assert 'Tsub' in solution
        assert 'Tbot' in solution
        assert 'Psub' in solution
        assert 'dmdt' in solution
        assert 'Kv' in solution
        
        # Check physical validity
        assert solution['Tsub'] < 0, "Sublimation temp should be below freezing"
        assert solution['Tsub'] <= solution['Tbot'], "Tsub should be <= Tbot"
        assert solution['Tbot'] <= solution['Tsh'], "Tbot should be <= Tsh"
        assert solution['Pch'] > 0, "Chamber pressure should be positive"
        assert solution['Psub'] > 0, "Vapor pressure should be positive"
        assert solution['dmdt'] >= 0, "Sublimation rate should be non-negative"
    
    @pytest.mark.slow
    def test_solve_with_warmstart(self, standard_vial, standard_product, standard_ht):
        """Test solving with warmstart initialization."""
        Lpr0 = functions.Lpr0_FUN(2.0, standard_vial['Ap'], standard_product['cSolid'])
        Lck = 0.5
        
        # Create warmstart data with reasonable initial guess
        warmstart = {
            'Pch': 0.15,
            'Tsh': -10.0,
            'Tsub': -25.0,
            'Tbot': -20.0,
            'Psub': 0.5,
            'dmdt': 0.5,
            'Kv': 5e-4,
        }
        
        model = single_step.create_single_step_model(
            standard_vial,
            standard_product,
            standard_ht,
            Lpr0,
            Lck
        )
        
        solution = single_step.solve_single_step(
            model, 
            warmstart_data=warmstart,
            tee=False
        )
        
        # Should solve successfully
        assert 'Pch' in solution
        assert solution['dmdt'] >= 0
    
    @pytest.mark.slow
    def test_optimize_convenience_function(self, standard_vial, standard_product, standard_ht):
        """Test the optimize_single_step convenience function."""
        Lpr0 = functions.Lpr0_FUN(2.0, standard_vial['Ap'], standard_product['cSolid'])
        Lck = 0.5
        
        solution = single_step.optimize_single_step(
            standard_vial,
            standard_product,
            standard_ht,
            Lpr0,
            Lck,
            tee=False
        )
        
        # Check solution is valid
        assert 'Pch' in solution
        assert 'Tsh' in solution
        assert solution['dmdt'] >= 0


class TestSolutionValidity:
    """Tests for solution validation utilities."""
    
    def test_check_valid_solution(self):
        """Test validation of a physically reasonable solution."""
        solution = {
            'Pch': 0.15,
            'Tsh': -5.0,
            'Tsub': -25.0,
            'Tbot': -20.0,
            'Psub': 0.5,
            'dmdt': 0.5,
            'Kv': 5e-4,
        }
        
        is_valid, violations = utils.check_solution_validity(solution)
        
        assert is_valid, f"Valid solution flagged as invalid: {violations}"
        assert len(violations) == 0
    
    def test_check_invalid_temperature_ordering(self):
        """Test detection of invalid temperature ordering."""
        solution = {
            'Pch': 0.15,
            'Tsh': -5.0,
            'Tsub': -10.0,  # Invalid: Tsub > Tbot
            'Tbot': -20.0,
            'Psub': 0.5,
            'dmdt': 0.5,
            'Kv': 5e-4,
        }
        
        is_valid, violations = utils.check_solution_validity(solution)
        
        assert not is_valid
        assert any('Tsub' in v and 'Tbot' in v for v in violations)
    
    def test_check_invalid_driving_force(self):
        """Test detection of invalid driving force (Psub < Pch)."""
        solution = {
            'Pch': 0.5,   # Invalid: Pch > Psub
            'Tsh': -5.0,
            'Tsub': -25.0,
            'Tbot': -20.0,
            'Psub': 0.3,
            'dmdt': 0.0,
            'Kv': 5e-4,
        }
        
        is_valid, violations = utils.check_solution_validity(solution)
        
        assert not is_valid
        assert any('Psub' in v and 'Pch' in v for v in violations)


class TestWarmstartUtilities:
    """Tests for warmstart initialization from scipy."""
    
    def test_initialize_from_scipy_format(self, standard_vial, standard_product):
        """Test that warmstart data can be created from scipy output format."""
        # Create mock scipy output (7 columns)
        scipy_output = np.array([
            [0.0, -25.0, -20.0, -5.0, 150.0, 0.5, 0.3],  # time=0
            [0.5, -23.0, -18.0, -3.0, 140.0, 0.55, 0.5], # time=0.5
        ])
        
        Lpr0 = functions.Lpr0_FUN(2.0, standard_vial['Ap'], standard_product['cSolid'])
        
        warmstart = utils.initialize_from_scipy(
            scipy_output,
            time_index=1,
            vial=standard_vial,
            product=standard_product,
            Lpr0=Lpr0
        )
        
        # Check structure
        assert 'Pch' in warmstart
        assert 'Tsh' in warmstart
        assert 'Tsub' in warmstart
        assert 'Tbot' in warmstart
        assert 'Psub' in warmstart
        assert 'dmdt' in warmstart
        assert 'Kv' in warmstart
        
        # Check values match scipy output (accounting for unit conversions)
        assert np.isclose(warmstart['Tsub'], -23.0, atol=0.1)
        assert np.isclose(warmstart['Tbot'], -18.0, atol=0.1)
        assert np.isclose(warmstart['Tsh'], -3.0, atol=0.1)
        assert np.isclose(warmstart['Pch'], 0.14, rtol=0.1)  # 140 mTorr → 0.14 Torr
        
        # Check derived quantities are reasonable
        assert warmstart['Psub'] > 0
        assert warmstart['dmdt'] >= 0
        assert warmstart['Kv'] > 0
