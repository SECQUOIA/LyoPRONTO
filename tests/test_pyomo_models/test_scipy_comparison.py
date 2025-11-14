"""Comparison tests between Pyomo and scipy optimization results.

This module verifies that Pyomo single-step optimization produces results
consistent with the scipy baseline implementation.
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
from lyopronto import functions, constant, opt_Pch_Tsh
from lyopronto.pyomo_models import single_step, utils

# Try to import pyomo - skip tests if not available
try:
    import pyomo.environ as pyo
    PYOMO_AVAILABLE = True
except ImportError:
    PYOMO_AVAILABLE = False

pytestmark = pytest.mark.skipif(not PYOMO_AVAILABLE, reason="Pyomo not installed")


class TestPyomoScipyComparison:
    """Tests comparing Pyomo and scipy optimization results."""
    
    @pytest.mark.slow
    def test_pyomo_matches_scipy_single_step(self, standard_vial, standard_product, standard_ht):
        """Test that Pyomo single-step matches scipy for one time step.
        
        This test runs a full scipy optimization, extracts a single time step,
        and verifies that Pyomo produces the same result when solving that step.
        """
        # Setup
        Lpr0 = functions.Lpr0_FUN(2.0, standard_vial['Ap'], standard_product['cSolid'])
        eq_cap = {'a': -0.182, 'b': 11.7}
        nVial = 398
        dt = 0.01
        
        # Run scipy optimization
        Pchamber = {'min': 0.05}
        Tshelf = {'min': -45.0, 'max': 120.0}
        
        scipy_output = opt_Pch_Tsh.dry(
            standard_vial,
            standard_product,
            standard_ht,
            Pchamber,
            Tshelf,
            dt,
            eq_cap,
            nVial
        )
        
        # Test at multiple time points
        test_indices = [0, len(scipy_output)//4, len(scipy_output)//2, 3*len(scipy_output)//4, -1]
        
        for idx in test_indices:
            # Extract scipy results for this time step
            scipy_Pch = scipy_output[idx, 4] / constant.Torr_to_mTorr  # mTorr → Torr
            scipy_Tsh = scipy_output[idx, 3]
            scipy_Tsub = scipy_output[idx, 1]
            scipy_Tbot = scipy_output[idx, 2]
            frac_dried = scipy_output[idx, 6]
            Lck = frac_dried * Lpr0
            
            # Skip if not significantly dried (numerical issues at start)
            if Lck < 0.01:
                continue
            
            # Solve with Pyomo using warmstart from scipy
            warmstart = utils.initialize_from_scipy(
                scipy_output, idx, standard_vial, standard_product, Lpr0, ht=standard_ht
            )
            
            pyomo_solution = single_step.optimize_single_step(
                standard_vial,
                standard_product,
                standard_ht,
                Lpr0,
                Lck,
                Pch_bounds=(0.05, 0.5),
                Tsh_bounds=(-45.0, 120.0),
                eq_cap=eq_cap,
                nVial=nVial,
                warmstart_data=warmstart,
                tee=False
            )
            
            # Compare results (allow 5% tolerance for numerical differences)
            rtol = 0.05
            atol_temp = 1.0  # 1°C absolute tolerance for temperatures
            
            assert np.isclose(pyomo_solution['Pch'], scipy_Pch, rtol=rtol), \
                f"Pch mismatch at idx {idx}: Pyomo={pyomo_solution['Pch']:.4f}, scipy={scipy_Pch:.4f}"
            
            assert np.isclose(pyomo_solution['Tsh'], scipy_Tsh, rtol=rtol, atol=atol_temp), \
                f"Tsh mismatch at idx {idx}: Pyomo={pyomo_solution['Tsh']:.2f}, scipy={scipy_Tsh:.2f}"
            
            assert np.isclose(pyomo_solution['Tsub'], scipy_Tsub, rtol=rtol, atol=atol_temp), \
                f"Tsub mismatch at idx {idx}: Pyomo={pyomo_solution['Tsub']:.2f}, scipy={scipy_Tsub:.2f}"
            
            assert np.isclose(pyomo_solution['Tbot'], scipy_Tbot, rtol=rtol, atol=atol_temp), \
                f"Tbot mismatch at idx {idx}: Pyomo={pyomo_solution['Tbot']:.2f}, scipy={scipy_Tbot:.2f}"
    
    @pytest.mark.slow
    def test_pyomo_matches_scipy_mid_drying(self, standard_vial, standard_product, standard_ht):
        """Test Pyomo vs scipy at mid-drying (most interesting physics).
        
        Mid-drying has the most interesting physics with balanced heat transfer,
        sublimation, and resistance effects.
        """
        Lpr0 = functions.Lpr0_FUN(2.0, standard_vial['Ap'], standard_product['cSolid'])
        Lck = Lpr0 * 0.5  # Half dried
        
        # Run scipy optimization to get baseline
        eq_cap = {'a': -0.182, 'b': 11.7}
        nVial = 398
        dt = 0.01
        Pchamber = {'min': 0.05}
        Tshelf = {'min': -45.0, 'max': 120.0}
        
        scipy_output = opt_Pch_Tsh.dry(
            standard_vial,
            standard_product,
            standard_ht,
            Pchamber,
            Tshelf,
            dt,
            eq_cap,
            nVial
        )
        
        # Find scipy result closest to 50% dried
        frac_dried_array = scipy_output[:, 6]
        idx = np.argmin(np.abs(frac_dried_array - 0.5))
        
        # Warmstart Pyomo from scipy
        warmstart = utils.initialize_from_scipy(
            scipy_output, idx, standard_vial, standard_product, Lpr0, ht=standard_ht
        )
        
        # Solve with Pyomo
        pyomo_solution = single_step.optimize_single_step(
            standard_vial,
            standard_product,
            standard_ht,
            Lpr0,
            Lck,
            Pch_bounds=(0.05, 0.5),
            Tsh_bounds=(-45.0, 120.0),
            eq_cap=eq_cap,
            nVial=nVial,
            warmstart_data=warmstart,
            tee=False
        )
        
        # Extract scipy values
        scipy_Pch = scipy_output[idx, 4] / constant.Torr_to_mTorr
        scipy_Tsh = scipy_output[idx, 3]
        scipy_Tsub = scipy_output[idx, 1]
        
        # Stricter tolerance for mid-drying (well-conditioned problem)
        assert np.isclose(pyomo_solution['Pch'], scipy_Pch, rtol=0.03), \
            f"Pch: Pyomo={pyomo_solution['Pch']:.4f}, scipy={scipy_Pch:.4f}"
        
        assert np.isclose(pyomo_solution['Tsh'], scipy_Tsh, rtol=0.03, atol=0.5), \
            f"Tsh: Pyomo={pyomo_solution['Tsh']:.2f}, scipy={scipy_Tsh:.2f}"
        
        assert np.isclose(pyomo_solution['Tsub'], scipy_Tsub, rtol=0.03, atol=0.5), \
            f"Tsub: Pyomo={pyomo_solution['Tsub']:.2f}, scipy={scipy_Tsub:.2f}"
    
    @pytest.mark.slow
    def test_pyomo_scipy_energy_balance(self, standard_vial, standard_product, standard_ht):
        """Verify both Pyomo and scipy satisfy energy balance.
        
        Both optimizers should produce results that satisfy the physical
        energy balance constraint.
        """
        Lpr0 = functions.Lpr0_FUN(2.0, standard_vial['Ap'], standard_product['cSolid'])
        Lck = Lpr0 * 0.6
        
        # Scipy solution
        eq_cap = {'a': -0.182, 'b': 11.7}
        nVial = 398
        dt = 0.01
        Pchamber = {'min': 0.05}
        Tshelf = {'min': -45.0, 'max': 120.0}
        
        scipy_output = opt_Pch_Tsh.dry(
            standard_vial,
            standard_product,
            standard_ht,
            Pchamber,
            Tshelf,
            dt,
            eq_cap,
            nVial
        )
        
        # Find closest to 60% dried
        frac_dried_array = scipy_output[:, 6]
        idx = np.argmin(np.abs(frac_dried_array - 0.6))
        
        # Pyomo solution
        warmstart = utils.initialize_from_scipy(
            scipy_output, idx, standard_vial, standard_product, Lpr0, ht=standard_ht
        )
        
        pyomo_solution = single_step.optimize_single_step(
            standard_vial,
            standard_product,
            standard_ht,
            Lpr0,
            Lck,
            eq_cap=eq_cap,
            nVial=nVial,
            warmstart_data=warmstart,
            tee=False
        )
        
        # Check energy balance for Pyomo solution
        # Q_shelf = Kv * Av * (Tsh - Tbot) [cal/s]
        Q_shelf = (pyomo_solution['Kv'] * standard_vial['Av'] * 
                   (pyomo_solution['Tsh'] - pyomo_solution['Tbot']))
        
        # Q_sublimation = dmdt * kg_To_g / hr_To_s * dHs [cal/s]
        # dmdt is in kg/hr, need to convert to g/s
        Q_sub = pyomo_solution['dmdt'] * constant.kg_To_g / constant.hr_To_s * constant.dHs
        
        # Energy balance should be satisfied (within 2% for numerical tolerance)
        energy_balance_error = abs(Q_shelf - Q_sub) / Q_shelf
        assert energy_balance_error < 0.02, \
            f"Energy balance error: {energy_balance_error*100:.2f}%"
        
        # Compare with scipy energy balance
        scipy_Tsh = scipy_output[idx, 3]
        scipy_Tbot = scipy_output[idx, 2]
        scipy_flux = scipy_output[idx, 5]  # kg/hr/m²
        scipy_dmdt = scipy_flux * standard_vial['Ap'] * constant.cm_To_m**2
        
        Rp = functions.Rp_FUN(Lck, standard_product['R0'], 
                             standard_product['A1'], standard_product['A2'])
        Pch_scipy = scipy_output[idx, 4] / constant.Torr_to_mTorr
        Kv_scipy = functions.Kv_FUN(standard_ht['KC'], standard_ht['KP'], 
                                    standard_ht['KD'], Pch_scipy)
        
        Q_shelf_scipy = Kv_scipy * standard_vial['Av'] * (scipy_Tsh - scipy_Tbot)
        Q_sub_scipy = scipy_dmdt * constant.kg_To_g / constant.hr_To_s * constant.dHs
        
        scipy_energy_balance_error = abs(Q_shelf_scipy - Q_sub_scipy) / Q_shelf_scipy
        
        # Both should have similar energy balance errors
        assert abs(energy_balance_error - scipy_energy_balance_error) < 0.01, \
            f"Energy balance consistency: Pyomo={energy_balance_error:.4f}, scipy={scipy_energy_balance_error:.4f}"
    
    @pytest.mark.slow  
    def test_pyomo_without_warmstart_converges(self, standard_vial, standard_product, standard_ht):
        """Test that Pyomo can solve without scipy warmstart (cold start).
        
        This verifies the model is well-formulated and can converge from
        default initialization, not just when warmstarted from scipy.
        """
        Lpr0 = functions.Lpr0_FUN(2.0, standard_vial['Ap'], standard_product['cSolid'])
        Lck = Lpr0 * 0.5
        
        # Solve without warmstart
        pyomo_solution = single_step.optimize_single_step(
            standard_vial,
            standard_product,
            standard_ht,
            Lpr0,
            Lck,
            Pch_bounds=(0.05, 0.5),
            Tsh_bounds=(-45.0, 120.0),
            tee=False
        )
        
        # Should converge to optimal
        assert 'optimal' in pyomo_solution['status'].lower(), \
            f"Pyomo failed to converge: {pyomo_solution['status']}"
        
        # Solution should be physically valid
        is_valid, violations = utils.check_solution_validity(pyomo_solution)
        assert is_valid, f"Invalid solution: {violations}"
        
        # Now solve scipy for comparison
        eq_cap = {'a': -0.182, 'b': 11.7}
        nVial = 398
        dt = 0.01
        Pchamber = {'min': 0.05}
        Tshelf = {'min': -45.0, 'max': 120.0}
        
        scipy_output = opt_Pch_Tsh.dry(
            standard_vial,
            standard_product,
            standard_ht,
            Pchamber,
            Tshelf,
            dt,
            eq_cap,
            nVial
        )
        
        # Find scipy result near 50% dried
        frac_dried_array = scipy_output[:, 6]
        idx = np.argmin(np.abs(frac_dried_array - 0.5))
        
        scipy_Pch = scipy_output[idx, 4] / constant.Torr_to_mTorr
        scipy_Tsh = scipy_output[idx, 3]
        
        # Should be in same ballpark (within 10% without warmstart)
        assert np.isclose(pyomo_solution['Pch'], scipy_Pch, rtol=0.10), \
            f"Cold start Pch: Pyomo={pyomo_solution['Pch']:.4f}, scipy={scipy_Pch:.4f}"
        
        assert np.isclose(pyomo_solution['Tsh'], scipy_Tsh, rtol=0.10, atol=2.0), \
            f"Cold start Tsh: Pyomo={pyomo_solution['Tsh']:.2f}, scipy={scipy_Tsh:.2f}"
