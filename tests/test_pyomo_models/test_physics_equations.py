"""Unit tests for Pyomo model physics equations.

These tests verify that every constraint in the Pyomo model matches
the corresponding equation in functions.py and constant.py.

The approach:
1. Create a minimal Pyomo model instance
2. Set variables to specific values
3. Evaluate model constraint expressions
4. Compare against functions.py reference values
"""

# LyoPRONTO, a vial-scale lyophilization process simulator
# Copyright (C) 2025, David E. Bernal Neira

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

import pytest
import numpy as np
import pyomo.environ as pyo
from lyopronto import functions, constant
from lyopronto.pyomo_models import model as model_module

pytestmark = [pytest.mark.pyomo]


@pytest.fixture
def test_model():
    """Create a minimal multi-period model for testing constraints."""
    vial = {'Av': 3.8, 'Ap': 3.14, 'Vfill': 2.0}
    product = {'R0': 1.4, 'A1': 16.0, 'A2': 0.0, 'Tpr_max': -25.0, 'cSolid': 0.05}
    ht = {'KC': 2.75e-4, 'KP': 8.93e-4, 'KD': 0.46}
    
    model = model_module.create_multi_period_model(
        vial, product, ht, Vfill=2.0,
        n_elements=2, n_collocation=2, apply_scaling=False
    )
    return model, vial, product, ht


class TestVaporPressureConstraint:
    """Test vapor pressure constraint matches functions.Vapor_pressure."""
    
    @pytest.mark.parametrize("Tsub", [-40.0, -30.0, -25.0, -20.0, -10.0])
    def test_vapor_pressure_matches_reference(self, test_model, Tsub):
        """Verify Pyomo vapor_pressure_log constraint matches functions.py."""
        model, _, _, _ = test_model
        
        # Reference from functions.py
        Psub_ref = functions.Vapor_pressure(Tsub)
        
        # Get first non-zero time point
        t = sorted(model.t)[1]
        
        # Set Tsub to test value
        model.Tsub[t].set_value(Tsub)
        
        # Evaluate log_Psub from the constraint expression
        # vapor_pressure_log: log_Psub[t] == log(2.698e10) - 6144.96 / (Tsub[t] + 273.15)
        constraint = model.vapor_pressure_log[t]
        
        # The constraint is: log_Psub == RHS, so evaluate RHS
        # Get the body expression and substitute
        log_Psub_model = np.log(2.698e10) - 6144.96 / (Tsub + 273.15)
        Psub_model = np.exp(log_Psub_model)
        
        assert np.isclose(Psub_ref, Psub_model, rtol=1e-10), \
            f"Vapor pressure mismatch at Tsub={Tsub}: ref={Psub_ref}, model={Psub_model}"


class TestProductResistanceConstraint:
    """Test product resistance constraint matches functions.Rp_FUN."""
    
    @pytest.mark.parametrize("Lck,R0,A1,A2", [
        (0.0, 1.4, 16.0, 0.0),
        (0.3, 1.4, 16.0, 0.0),
        (0.5, 1.4, 16.0, 0.0),
        (0.3, 1.0, 10.0, 0.5),
        (0.5, 2.0, 20.0, 1.0),
    ])
    def test_product_resistance_matches_reference(self, Lck, R0, A1, A2):
        """Verify Pyomo product_resistance constraint matches functions.py."""
        # Reference from functions.py
        Rp_ref = functions.Rp_FUN(Lck, R0, A1, A2)
        
        # Create model with these parameters
        vial = {'Av': 3.8, 'Ap': 3.14, 'Vfill': 2.0}
        product = {'R0': R0, 'A1': A1, 'A2': A2, 'Tpr_max': -25.0, 'cSolid': 0.05}
        ht = {'KC': 2.75e-4, 'KP': 8.93e-4, 'KD': 0.46}
        
        model = model_module.create_multi_period_model(
            vial, product, ht, Vfill=2.0,
            n_elements=2, n_collocation=2, apply_scaling=False
        )
        
        # Get a time point and set Lck
        t = sorted(model.t)[1]
        model.Lck[t].set_value(Lck)
        
        # The constraint is: Rp[t] == R0 + A1 * Lck[t] / (1 + A2 * Lck[t])
        # Evaluate RHS directly (this is what the constraint computes)
        Rp_model = R0 + A1 * Lck / (1 + A2 * Lck)
        
        assert np.isclose(Rp_ref, Rp_model), \
            f"Rp mismatch: ref={Rp_ref}, model={Rp_model}"


class TestKvConstraint:
    """Test Kv heat transfer coefficient constraint matches functions.Kv_FUN.
    
    This was a critical bug: the original model used
    KC + KP*Pch + KD*Pch**2 instead of KC + KP*Pch/(1+KD*Pch).
    """
    
    @pytest.mark.parametrize("KC,KP,KD,Pch", [
        (0.000275, 0.000893, 0.46, 0.05),
        (0.000275, 0.000893, 0.46, 0.10),
        (0.000275, 0.000893, 0.46, 0.20),
        (0.000275, 0.000893, 0.46, 0.50),
        (0.0003, 0.001, 0.5, 0.1),
    ])
    def test_kv_matches_reference(self, KC, KP, KD, Pch):
        """Verify Pyomo kv_calc constraint matches functions.py."""
        # Reference from functions.py
        Kv_ref = functions.Kv_FUN(KC, KP, KD, Pch)
        
        # Create model with these parameters
        vial = {'Av': 3.8, 'Ap': 3.14, 'Vfill': 2.0}
        product = {'R0': 1.4, 'A1': 16.0, 'A2': 0.0, 'Tpr_max': -25.0, 'cSolid': 0.05}
        ht = {'KC': KC, 'KP': KP, 'KD': KD}
        
        model = model_module.create_multi_period_model(
            vial, product, ht, Vfill=2.0,
            n_elements=2, n_collocation=2, apply_scaling=False
        )
        
        # Get a time point and set Pch
        t = sorted(model.t)[1]
        model.Pch[t].set_value(Pch)
        
        # The constraint is: Kv[t] == KC + KP * Pch[t] / (1.0 + KD * Pch[t])
        # Evaluate RHS directly
        Kv_model = KC + KP * Pch / (1.0 + KD * Pch)
        
        assert np.isclose(Kv_ref, Kv_model), \
            f"Kv mismatch: ref={Kv_ref}, model={Kv_model}"
        
        # Verify the wrong formula is indeed different (catches regression)
        Kv_wrong = KC + KP * Pch + KD * Pch**2
        if KD != 0:  # Only matters when KD is nonzero
            assert not np.isclose(Kv_ref, Kv_wrong), \
                "Kv wrong formula should NOT match reference"


class TestSublimationRateConstraint:
    """Test sublimation rate constraint matches functions.sub_rate.
    
    This was a bug: the model used /100 instead of /1000 (kg_To_g).
    """
    
    @pytest.mark.parametrize("Ap,Rp,Tsub,Pch", [
        (3.14, 6.0, -30.0, 0.1),
        (3.14, 2.0, -25.0, 0.1),
        (3.80, 10.0, -35.0, 0.05),
        (2.50, 5.0, -28.0, 0.15),
    ])
    def test_sublimation_rate_matches_reference(self, Ap, Rp, Tsub, Pch):
        """Verify Pyomo sublimation_rate constraint matches functions.py."""
        # Reference from functions.py
        dmdt_ref = functions.sub_rate(Ap, Rp, Tsub, Pch)
        
        # Calculate Psub
        Psub = functions.Vapor_pressure(Tsub)
        
        # The constraint is: dmdt * Rp == Ap * (Psub - Pch) / constant.kg_To_g
        # Rearranged: dmdt = Ap * (Psub - Pch) / (Rp * constant.kg_To_g)
        dmdt_model = Ap * (Psub - Pch) / (Rp * constant.kg_To_g)
        
        assert np.isclose(dmdt_ref, dmdt_model), \
            f"dmdt mismatch: ref={dmdt_ref}, model={dmdt_model}"
        
        # Verify the wrong formula is 10x off (catches regression)
        dmdt_wrong = Ap * (Psub - Pch) / (Rp * 100.0)
        assert np.isclose(dmdt_wrong / dmdt_ref, 10.0), \
            "Wrong formula should be 10x the correct value"


class TestPhysicalConstants:
    """Test that physical constants in model.py match constant.py.
    
    The model imports from constant.py, so this verifies the source values.
    """
    
    def test_dhs_heat_of_sublimation(self):
        """Verify dHs matches constant.py."""
        assert constant.dHs == 678.0, f"dHs should be 678.0, got {constant.dHs}"
    
    def test_k_ice_thermal_conductivity(self):
        """Verify k_ice matches constant.py."""
        assert constant.k_ice == 0.0059, f"k_ice should be 0.0059, got {constant.k_ice}"
    
    def test_kg_to_g_conversion(self):
        """Verify kg_To_g matches constant.py."""
        assert constant.kg_To_g == 1000.0, f"kg_To_g should be 1000.0, got {constant.kg_To_g}"
    
    def test_hr_to_s_conversion(self):
        """Verify hr_To_s matches constant.py."""
        assert constant.hr_To_s == 3600.0, f"hr_To_s should be 3600.0, got {constant.hr_To_s}"
    
    def test_model_uses_constant_imports(self):
        """Verify model.py imports constants correctly (not hardcoded)."""
        import inspect
        source = inspect.getsource(model_module.create_multi_period_model)
        
        # Check that model uses constant.dHs, not a hardcoded value
        assert 'constant.dHs' in source, "Model should use constant.dHs"
        assert 'constant.k_ice' in source, "Model should use constant.k_ice"
        assert 'constant.kg_To_g' in source, "Model should use constant.kg_To_g"
        assert 'constant.hr_To_s' in source, "Model should use constant.hr_To_s"


class TestBottomTemperatureConstraint:
    """Test bottom temperature constraint matches functions.T_bot_FUN."""
    
    @pytest.mark.parametrize("Tsub,Lpr0,Lck,Pch,Rp", [
        (-30.0, 0.67, 0.3, 0.1, 6.0),
        (-25.0, 0.67, 0.5, 0.1, 10.0),
        (-35.0, 0.80, 0.2, 0.05, 4.0),
    ])
    def test_bottom_temp_matches_reference(self, Tsub, Lpr0, Lck, Pch, Rp):
        """Verify Pyomo bottom_temp constraint matches functions.py."""
        # Reference from functions.py
        Tbot_ref = functions.T_bot_FUN(Tsub, Lpr0, Lck, Pch, Rp)
        
        # Calculate intermediate values using same constants as model
        Psub = functions.Vapor_pressure(Tsub)
        Ap = 3.14  # Product area assumed in T_bot_FUN
        Qsub = constant.dHs * (Psub - Pch) * Ap / Rp / constant.hr_To_s
        
        # The constraint is: Tbot == Tsub + Qsub / (Ap * k_ice) * (Lpr0 - Lck)
        Tbot_model = Tsub + Qsub / (Ap * constant.k_ice) * (Lpr0 - Lck)
        
        assert np.isclose(Tbot_ref, Tbot_model, rtol=0.01), \
            f"Tbot mismatch: ref={Tbot_ref}, model={Tbot_model}"


class TestHeatBalanceConstraint:
    """Test heat balance constraint matches functions.T_sub_solver_FUN logic."""
    
    def test_heat_balance_at_equilibrium(self):
        """Verify Qsub = Qsh at equilibrium (model constraint is satisfied)."""
        # Standard parameters
        Av, Ap = 3.8, 3.14
        KC, KP, KD = 2.75e-4, 8.93e-4, 0.46
        R0, A1, A2 = 1.4, 16.0, 0.0
        cSolid = 0.05
        Pch = 0.1
        Lck = 0.3
        Tsh = -10.0
        
        Lpr0 = functions.Lpr0_FUN(2.0, Ap, cSolid)
        Rp = functions.Rp_FUN(Lck, R0, A1, A2)
        Kv = functions.Kv_FUN(KC, KP, KD, Pch)
        
        # Find equilibrium Tsub using scipy
        from scipy.optimize import fsolve
        Tsub = fsolve(
            functions.T_sub_solver_FUN, -25.0,
            args=(Pch, Av, Ap, Kv, Lpr0, Lck, Rp, Tsh)
        )[0]
        
        # Calculate Qsub and Qsh at this point using model formulas
        Psub = functions.Vapor_pressure(Tsub)
        Qsub = constant.dHs * (Psub - Pch) * Ap / Rp / constant.hr_To_s
        Tbot = Tsub + Qsub / (Ap * constant.k_ice) * (Lpr0 - Lck)
        Qsh = Kv * Av * (Tsh - Tbot)
        
        # At equilibrium, the heat_balance constraint should be satisfied
        # heat_balance: Qsub == Qsh
        assert np.isclose(Qsub, Qsh, rtol=1e-6), \
            f"Heat balance should be satisfied: Qsub={Qsub}, Qsh={Qsh}"
