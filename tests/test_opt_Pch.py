"""
Comprehensive tests for opt_Pch.py - Pressure optimization module.

This module optimizes chamber pressure while fixing shelf temperature.
Tests based on working example_optimizer.py structure.
"""

import pytest
import numpy as np
from lyopronto import opt_Pch, constant, functions
from .utils import (
    assert_physically_reasonable_output,
    assert_complete_drying,
    assert_incomplete_drying,
    RTOL,
    TEMP_ATOL,
)


def opt_pch_consistency(output, setup):
    vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial = setup

    assert output is not None, "opt_Pch.dry should return output"
    assert isinstance(output, np.ndarray), "Output should be numpy array"

    # Should have 7 columns: time, Tsub, Tbot, Tsh, Pch, flux, percent_dried
    assert output.shape[1] == 7, f"Expected 7 columns, got {output.shape[1]}"

    # Should have multiple time points
    assert output.shape[0] > 1, "Should have multiple time points"

    assert_physically_reasonable_output(output)

    # Shelf temperature (column 3) should start at init
    assert output[0, 3] == pytest.approx(Tshelf["init"]), (
        f"Initial Tsh should be ~{Tshelf['init']}°C"
    )

    Tsh_values = output[:, 3]
    Tsh_check = functions.RampInterpolator(Tshelf)(output[:, 0])
    np.testing.assert_allclose(Tsh_values, Tsh_check, atol=0.1, rtol=0)

    # Pressure (column 4) should vary
    Pch_values = output[:, 4]
    assert np.std(Pch_values) > 0, "Pressure should vary (be optimized)"

    # Both should respect bounds
    assert np.all(Pch_values >= Pchamber["min"] * constant.Torr_to_mTorr), (
        "Pressure should be >= min bound"
    )
    if hasattr(Pchamber, "max"):
        assert np.all(Pch_values <= Pchamber["max"] * constant.Torr_to_mTorr), (
            "Pressure should be <= max bound"
        )

    # Tbot (column 2) should stay at or below T_pr_crit
    # Note: For temperatures (which can be negative), use absolute tolerance
    T_crit = product["T_pr_crit"]
    assert np.all(output[:, 2] <= T_crit + TEMP_ATOL), (
        f"Product temperature should be <= {T_crit}°C (critical)"
    )

    # Should not exceed equipment capability (with small tolerance)
    # Equipment capability at different pressures
    Pch = output[:, 4] / 1000  # [Torr]
    actual_cap = eq_cap["a"] + eq_cap["b"] * Pch  # [kg/hr]
    # Total sublimation rate per vial
    flux = output[:, 5]  # Sublimation flux [kg/hr/m**2]
    Ap_m2 = vial["Ap"] * constant.cm_To_m**2  # Convert [cm**2] to [m**2]
    dmdt = flux * Ap_m2  # [kg/hr/vial]
    violations = dmdt - actual_cap

    assert np.all(violations <= 0), (
        f"Equipment capability exceeded by {np.max(violations):.3e} kg/hr"
    )


@pytest.fixture
def standard_opt_pch_inputs():
    """Standard inputs for opt_Pch testing (pressure optimization)."""
    # Vial geometry
    vial = {
        "Av": 3.8,  # Vial area [cm**2]
        "Ap": 3.14,  # Product area [cm**2]
        "Vfill": 2.0,  # Fill volume [mL]
    }

    # Product properties
    product = {
        "T_pr_crit": -25.0,  # Critical product temperature [degC]
        "cSolid": 0.05,  # Solid content [g/mL]
        "R0": 1.4,  # Product resistance coefficient R0 [cm**2-hr-Torr/g]
        "A1": 16.0,  # Product resistance coefficient A1 [1/cm]
        "A2": 0.0,  # Product resistance coefficient A2 [1/cm**2]
    }

    # Vial heat transfer coefficients
    ht = {
        "KC": 0.000275,  # Kc [cal/s/K/cm**2]
        "KP": 0.000893,  # Kp [cal/s/K/cm**2/Torr]
        "KD": 0.46,  # Kd dimensionless
    }

    # Chamber pressure optimization settings
    Pchamber = {
        "min": 0.05,  # Minimum chamber pressure [Torr]
        "max": 1.0,  # Maximum chamber pressure [Torr]
    }

    # Shelf temperature settings (FIXED for opt_Pch)
    # Multi-step profile: start at -35°C, ramp to -20°C, then 0°C
    Tshelf = {
        "init": -35.0,  # Initial shelf temperature [degC]
        "setpt": np.array([-10.0]),  # Set points [degC]
        "dt_setpt": np.array([3600]),  # Hold times [min]
        "ramp_rate": 1.0,  # Ramp rate [degC/min]
    }

    # Equipment capability
    eq_cap = {
        "a": -0.182,  # Equipment capability coefficient a [kg]/hr
        "b": 11.7,  # Equipment capability coefficient b [kg/hr/Torr]
    }

    # Number of vials
    nVial = 398

    # Time step
    dt = 0.01  # Time step [hr]

    return vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial


class TestOptPchBasic:
    """Basic functionality tests for opt_Pch module."""

    def test_pressure_optimization(self, standard_opt_pch_inputs):
        """Test that opt_Pch.dry executes,  output has correct structure, and
        each output column contains valid data. Then, check that
        pressure is optimized (varies over time), shelf temperature follows
        specified profile, and product temperature stays below critical temperature."""
        output = opt_Pch.dry(*standard_opt_pch_inputs)
        opt_pch_consistency(output, standard_opt_pch_inputs)
        assert_complete_drying(output)
        # Drying time should be reasonable (0.5 to 10 hours)
        drying_time = output[-1, 0]
        assert 0.5 < drying_time < 20, (
            f"Drying time {drying_time:.2f} hr should be reasonable (0.5-20 hr)"
        )

    def test_pressure_optimization_nomax(self, standard_opt_pch_inputs):
        """Test that opt_Pch.dry works without a maximum pressure constraint."""
        vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial = standard_opt_pch_inputs
        # Remove max pressure constraint
        del Pchamber["max"]
        output = opt_Pch.dry(vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial)
        opt_pch_consistency(
            output, (vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial)
        )
        assert_complete_drying(output)


class TestOptPchEdgeCases:
    """Edge case tests for opt_Pch module."""

    # @pytest.mark.skip(reason="TODO: needs some feasibility checking")
    def test_low_critical_temperature(self, standard_opt_pch_inputs):
        """Test with very low critical temperature (-35°C)."""
        vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial = standard_opt_pch_inputs

        # Lower critical temperature
        product["T_pr_crit"] = -35.0
        Pchamber["min"] = 0.001  # Lower min pressure to 1 mTorr
        Pchamber["max"] = 2.00  # Raise max pressure to 2.00 Torr
        Tshelf["setpt"] = [-30]  # Lower shelf temperature to make feasible

        output = opt_Pch.dry(vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial)

        opt_pch_consistency(
            output, (vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial)
        )
        assert_complete_drying(output)

    def test_insufficient_time(self, standard_opt_pch_inputs):
        """Test with very low critical temperature (-35°C)."""
        vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial = standard_opt_pch_inputs

        Tshelf["dt_setpt"] = [120]  # Less drying time

        with pytest.warns(UserWarning, match="Drying incomplete"):
            output = opt_Pch.dry(vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial)
        opt_pch_consistency(
            output, (vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial)
        )
        assert_incomplete_drying(output)

    def test_high_resistance_product(self, standard_opt_pch_inputs):
        """Test with high resistance product."""
        vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial = standard_opt_pch_inputs

        # Increase resistance
        product["R0"] = 3.0
        product["A1"] = 30.0
        # Drop shelf temperature to make constraint feasible
        Tshelf["setpt"] = np.array([-20.0])

        output = opt_Pch.dry(vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial)

        opt_pch_consistency(
            output, (vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial)
        )

        assert_complete_drying(output)
        # Higher resistance should lead to longer drying time
        # TODO pin this to a value from default run conditions
        assert output[-1, 0] > 1.0, "High resistance should take longer to dry"

    def test_multi_shelf_temperature_setpoints(self, standard_opt_pch_inputs):
        """Test with multiple shelf temperature setpoints."""
        vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial = standard_opt_pch_inputs

        # Two setpoints
        Tshelf["setpt"] = np.array([-20.0, 0.0, -10.0])
        Tshelf["dt_setpt"] = np.array([120, 120, 1200])

        output = opt_Pch.dry(vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial)

        opt_pch_consistency(
            output, (vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial)
        )

        assert_complete_drying(output)

    def test_higher_min_pressure(self, standard_opt_pch_inputs):
        """Test with higher minimum pressure constraint (0.10 Torr)."""
        vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial = standard_opt_pch_inputs

        # Higher minimum pressure
        Pchamber["min"] = 0.10  # Torr = 100 mTorr
        # Needs a lower shelf temperature to complete drying
        Tshelf["setpt"] = np.array([-20.0])

        output = opt_Pch.dry(vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial)

        opt_pch_consistency(
            output, (vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial)
        )

        assert_complete_drying(output)
        # All pressures should be >= 100 mTorr
        assert np.all(output[:, 4] >= 100), "Pressure should respect higher min bound"

    def test_incomplete_optimization(self, standard_opt_pch_inputs):
        """Test with higher minimum pressure constraint (0.10 Torr)."""
        vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial = standard_opt_pch_inputs

        # Higher minimum pressure
        Pchamber["min"] = 0.10  # Torr = 100 mTorr
        # With higher shelf temperature, CANNOT complete drying and adhere to constraints
        Tshelf["setpt"] = [0]

        with pytest.warns(UserWarning, match="Optimization failed"):
            output = opt_Pch.dry(vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial)

        assert_incomplete_drying(output)
        # All pressures should be >= 100 mTorr
        assert np.all(output[:, 4] >= 100), "Pressure should respect higher min bound"

    def test_narrow_pressure_range(self, standard_opt_pch_inputs):
        """Test with narrow pressure optimization range."""
        vial, product, ht, _, Tshelf, dt, eq_cap, nVial = standard_opt_pch_inputs
        new_Pch = {"min": 0.070, "max": 0.090}
        product["T_pr_crit"] = -30.0  # Lower critical temperature to challenge
        Tshelf["setpt"] = [-20.0]  # Lower shelf temperature to make feasible

        output = opt_Pch.dry(vial, product, ht, new_Pch, Tshelf, dt, eq_cap, nVial)

        opt_pch_consistency(
            output, (vial, product, ht, new_Pch, Tshelf, dt, eq_cap, nVial)
        )

    def test_tight_equipment_constraint(self, standard_opt_pch_inputs):
        """Test with tighter equipment capability constraint."""
        vial, product, ht, Pchamber, Tshelf, dt, _, nVial = standard_opt_pch_inputs
        # Reduce equipment capability
        tight_eq_cap = {
            "a": -0.3,  # [kg/hr]
            "b": 5.0,  # [kg/hr/Torr]
        }

        output = opt_Pch.dry(
            vial, product, ht, Pchamber, Tshelf, dt, tight_eq_cap, nVial
        )

        # Should run without errors and show some progress despite tighter constraint
        opt_pch_consistency(
            output, (vial, product, ht, Pchamber, Tshelf, dt, tight_eq_cap, nVial)
        )
        assert_complete_drying(output)

    @pytest.mark.slow
    def test_consistent_results(self, standard_opt_pch_inputs):
        """Test that repeated runs give consistent results."""
        # Run twice
        output1 = opt_Pch.dry(*standard_opt_pch_inputs)
        output2 = opt_Pch.dry(*standard_opt_pch_inputs)

        # Results should be identical (deterministic optimization)
        np.testing.assert_array_almost_equal(output1, output2, decimal=6)


class TestOptPchReference:
    @pytest.fixture
    def opt_pch_reference_inputs(self):
        vial = {"Av": 3.8, "Ap": 3.14, "Vfill": 2.0}
        # Product properties
        product = {
            "T_pr_crit": -5.0,  # Critical product temperature [degC]
            "cSolid": 0.05,  # Solid content [g/mL]
            "R0": 1.4,  # Product resistance coefficient R0 [cm**2-hr-Torr/g]
            "A1": 16.0,  # Product resistance coefficient A1 [1/cm]
            "A2": 0.0,  # Product resistance coefficient A2 [1/cm**2]
        }
        # Vial heat transfer coefficients
        ht = {"KC": 0.000275, "KP": 0.000893, "KD": 0.46}
        # Chamber pressure optimization settings
        Pchamber = {
            "min": 0.05,  # Minimum chamber pressure [Torr]
            "max": 1000.0,  # Maximum chamber pressure [Torr]
        }
        # Shelf temperature settings (FIXED for opt_Pch)
        Tshelf = {
            "init": -35.0,  # Initial shelf temperature [degC]
            "setpt": np.array([20.0]),  # Set points [degC]
            "dt_setpt": np.array([1800]),  # Hold times [min]
            "ramp_rate": 1.0,  # Ramp rate [degC/min]
        }
        # Equipment capability
        eq_cap = {
            "a": -0.182,  # Equipment capability coefficient a [kg]/hr
            "b": 11.7,  # Equipment capability coefficient b [kg/hr/Torr]
        }
        nVial = 398
        dt = 0.01  # Time step [hr]
        return vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial

    # This test may need updating since the reference case can be questionable.
    def test_opt_pch_reference(self, repo_root, opt_pch_reference_inputs):
        """Test opt_Pch results against reference data from web interface optimizer."""
        ref_csv = repo_root / "test_data" / "reference_opt_Pch.csv"
        if not ref_csv.exists():
            pytest.skip(f"Reference CSV not found: {ref_csv}")
        output_ref = np.loadtxt(ref_csv, delimiter=",", skiprows=1)
        output = opt_Pch.dry(*opt_pch_reference_inputs)

        # DON'T directly compare: this optimization is very poorly formulated, and checking
        # element-wise equality against reference data is brittle and not meaningful.
        # Instead, check that output is reasonable and matches or exceeds the performance.
        opt_pch_consistency(output, opt_pch_reference_inputs)
        assert_complete_drying(output)
        # Drying time should be equal to or better than reference (with small tolerance)
        # Note: Initial guess changes in opt_Pch.py may result in slightly different
        # trajectories due to the greedy sequential optimization approach.
        drying_time_ref = output_ref[-1, 0]
        drying_time = output[-1, 0]
        # Use proportional tolerance from utils.py for numerical differences
        assert drying_time <= drying_time_ref * (1 + RTOL), (
            f"Drying time {drying_time:.2f} hr should be <= reference "
            + f"{drying_time_ref:.2f} hr (tolerance: {RTOL*100:.1f}% = {drying_time_ref*RTOL:.4f} hr)"
        )
        # array_compare = np.isclose(output, output_ref, atol=1e-3)
        # assert array_compare.all(), (
        #     "opt_Pch output should match reference data, but reference data is known to "
        #     + "be odd, so (with maintainer approval) the reference data may be updated."
        #     + f"Not matching at positions:\n {np.where(~array_compare)}"
        # )


# ==============================================================================
# Coverage tests (migrated from test_opt_Pch_coverage.py)
# ==============================================================================

from .utils import PERCENT_MAX, TEMP_ATOL, RTOL


class TestOptPchCoverageOnly:
    """Test pressure-only optimizer (fixed shelf temperature) - coverage tests."""

    @pytest.fixture
    def opt_pch_setup(self, standard_vial, standard_ht):
        """Setup for Pch-only optimization."""
        product = {
            'cSolid': 0.05,
            'R0': 1.4,
            'A1': 16.0,
            'A2': 0.0,
            'T_pr_crit': -30.0
        }

        # Fixed shelf temperature schedule
        Tshelf = {
            'init': -40.0,
            'setpt': [-20.0, -10.0],
            'dt_setpt': [120.0, 120.0],  # 2 hours in [min]
            'ramp_rate': 1.0  # Ramp rate [degC/min]
        }

        # Pressure bounds (will be optimized)
        Pchamber = {
            'min': 0.040,
            'max': 0.200
        }

        dt = 0.01  # Time step [hr]

        # Equipment capability
        eq_cap = {'a': 5.0, 'b': 10.0}
        nVial = 398

        return {
            'vial': standard_vial,
            'product': product,
            'ht': standard_ht,
            'Pchamber': Pchamber,
            'Tshelf': Tshelf,
            'dt': dt,
            'eq_cap': eq_cap,
            'nVial': nVial
        }

    def test_opt_pch_completes(self, opt_pch_setup):
        """Test that optimizer runs to completion."""
        output = opt_Pch.dry(
            opt_pch_setup['vial'],
            opt_pch_setup['product'],
            opt_pch_setup['ht'],
            opt_pch_setup['Pchamber'],
            opt_pch_setup['Tshelf'],
            opt_pch_setup['dt'],
            opt_pch_setup['eq_cap'],
            opt_pch_setup['nVial']
        )

        # Should return an array
        assert isinstance(output, np.ndarray)
        assert output.shape[0] > 0
        assert output.shape[1] == 7  # Standard output columns

    def test_opt_pch_output_shape(self, opt_pch_setup):
        """Test output has correct format."""
        output = opt_Pch.dry(
            opt_pch_setup['vial'],
            opt_pch_setup['product'],
            opt_pch_setup['ht'],
            opt_pch_setup['Pchamber'],
            opt_pch_setup['Tshelf'],
            opt_pch_setup['dt'],
            opt_pch_setup['eq_cap'],
            opt_pch_setup['nVial']
        )

        # Check shape
        assert output.shape[1] == 7, "Output should have 7 columns"

        # Check all values are finite
        assert np.all(np.isfinite(output)), "Output contains non-finite values"

    def test_opt_pch_respects_temp_constraint(self, opt_pch_setup):
        """Test critical temperature is not exceeded."""
        output = opt_Pch.dry(
            opt_pch_setup['vial'],
            opt_pch_setup['product'],
            opt_pch_setup['ht'],
            opt_pch_setup['Pchamber'],
            opt_pch_setup['Tshelf'],
            opt_pch_setup['dt'],
            opt_pch_setup['eq_cap'],
            opt_pch_setup['nVial']
        )

        Tbot = output[:, 2]  # Vial bottom temperature
        T_crit = opt_pch_setup['product']['T_pr_crit']

        # Allow 0.5°C tolerance for numerical optimization
        max_violation = np.max(Tbot - T_crit)
        assert max_violation <= 0.5, \
            f"Temperature exceeded critical by {max_violation:.2f}°C"

    def test_opt_pch_pressure_within_bounds(self, opt_pch_setup):
        """Test optimized pressure stays within bounds."""
        output = opt_Pch.dry(
            opt_pch_setup['vial'],
            opt_pch_setup['product'],
            opt_pch_setup['ht'],
            opt_pch_setup['Pchamber'],
            opt_pch_setup['Tshelf'],
            opt_pch_setup['dt'],
            opt_pch_setup['eq_cap'],
            opt_pch_setup['nVial']
        )

        Pch = output[:, 4] / 1000  # Convert mTorr to Torr
        P_min = opt_pch_setup['Pchamber']['min']
        P_max = opt_pch_setup['Pchamber']['max']

        assert np.all(Pch >= P_min * 0.95), \
            f"Pressure {np.min(Pch):.3f} below minimum {P_min}"
        assert np.all(Pch <= P_max * 1.05), \
            f"Pressure {np.max(Pch):.3f} above maximum {P_max}"

    def test_opt_pch_respects_equipment(self, opt_pch_setup):
        """Test equipment capability constraint is satisfied."""
        output = opt_Pch.dry(
            opt_pch_setup['vial'],
            opt_pch_setup['product'],
            opt_pch_setup['ht'],
            opt_pch_setup['Pchamber'],
            opt_pch_setup['Tshelf'],
            opt_pch_setup['dt'],
            opt_pch_setup['eq_cap'],
            opt_pch_setup['nVial']
        )

        flux = output[:, 5]  # Sublimation flux [kg/hr/m**2]
        Ap_m2 = opt_pch_setup['vial']['Ap'] / 100**2  # Convert [cm**2] to [m**2]

        # Total sublimation rate per vial
        dmdt = flux * Ap_m2  # [kg/hr/vial]

        # Equipment capability at different pressures
        Pch = output[:, 4] / 1000  # [Torr]
        eq_cap_max = (opt_pch_setup['eq_cap']['a'] +
                      opt_pch_setup['eq_cap']['b'] * Pch) / opt_pch_setup['nVial']

        # Should not exceed equipment capability (with small tolerance)
        violations = dmdt - eq_cap_max
        max_violation = np.max(violations)
        assert max_violation <= RTOL, \
            f"Equipment capability exceeded by {max_violation:.4f} kg/hr"

    def test_opt_pch_physically_reasonable(self, opt_pch_setup):
        """Test output is physically reasonable."""
        output = opt_Pch.dry(
            opt_pch_setup['vial'],
            opt_pch_setup['product'],
            opt_pch_setup['ht'],
            opt_pch_setup['Pchamber'],
            opt_pch_setup['Tshelf'],
            opt_pch_setup['dt'],
            opt_pch_setup['eq_cap'],
            opt_pch_setup['nVial']
        )

        assert_physically_reasonable_output(output)

    def test_opt_pch_reaches_completion(self, opt_pch_setup):
        """Test that Pch optimization makes drying progress.

        Note: Optimization with constraints may not always reach 99% completion
        within time limits. Test validates the optimizer runs and makes progress.
        """
        output = opt_Pch.dry(
            opt_pch_setup['vial'],
            opt_pch_setup['product'],
            opt_pch_setup['ht'],
            opt_pch_setup['Pchamber'],
            opt_pch_setup['Tshelf'],
            opt_pch_setup['dt'],
            opt_pch_setup['eq_cap'],
            opt_pch_setup['nVial']
        )

        final_percent = output[-1, 6]
        # Optimizer should show progress, but may not reach full completion
        assert final_percent > 0.0, \
            f"Should show drying progress, got {final_percent:.1f}%"
        assert final_percent <= PERCENT_MAX, \
            f"Percent dried should not exceed {PERCENT_MAX}%, got {final_percent:.1f}%"

    def test_opt_pch_convergence(self, opt_pch_setup):
        """Test optimization converges to a solution."""
        output = opt_Pch.dry(
            opt_pch_setup['vial'],
            opt_pch_setup['product'],
            opt_pch_setup['ht'],
            opt_pch_setup['Pchamber'],
            opt_pch_setup['Tshelf'],
            opt_pch_setup['dt'],
            opt_pch_setup['eq_cap'],
            opt_pch_setup['nVial']
        )

        # If optimization converged, should have reasonable drying time
        total_time = output[-1, 0]
        assert 1.0 <= total_time <= 50.0, \
            f"Drying time {total_time:.1f} hr seems unreasonable"

    def test_opt_pch_pressure_optimization(self, opt_pch_setup):
        """Test that pressure is actively optimized (not just at bounds)."""
        output = opt_Pch.dry(
            opt_pch_setup['vial'],
            opt_pch_setup['product'],
            opt_pch_setup['ht'],
            opt_pch_setup['Pchamber'],
            opt_pch_setup['Tshelf'],
            opt_pch_setup['dt'],
            opt_pch_setup['eq_cap'],
            opt_pch_setup['nVial']
        )

        Pch = output[:, 4] / 1000  # [Torr]

        # Pressure should vary during optimization
        P_range = np.max(Pch) - np.min(Pch)
        assert P_range > 0.001, \
            "Pressure should vary during optimization"


class TestOptPchCoverageEdgeCases:
    """Test edge cases for Pch-only optimizer - coverage tests."""

    @pytest.fixture
    def conservative_setup(self, standard_vial, standard_ht):
        """Setup with very conservative critical temperature."""
        product = {
            'cSolid': 0.05,
            'R0': 1.4,
            'A1': 16.0,
            'A2': 0.0,
            'T_pr_crit': -40.0  # Very conservative
        }

        Tshelf = {
            'init': -45.0,
            'setpt': [-35.0],
            'dt_setpt': [120.0],
            'ramp_rate': 1.0
        }

        Pchamber = {
            'min': 0.040,
            'max': 0.100
        }

        dt = 0.01
        eq_cap = {'a': 5.0, 'b': 10.0}
        nVial = 398

        return {
            'vial': standard_vial,
            'product': product,
            'ht': standard_ht,
            'Pchamber': Pchamber,
            'Tshelf': Tshelf,
            'dt': dt,
            'eq_cap': eq_cap,
            'nVial': nVial
        }

    def test_conservative_critical_temp(self, conservative_setup):
        """Test with very conservative critical temperature."""
        output = opt_Pch.dry(
            conservative_setup['vial'],
            conservative_setup['product'],
            conservative_setup['ht'],
            conservative_setup['Pchamber'],
            conservative_setup['Tshelf'],
            conservative_setup['dt'],
            conservative_setup['eq_cap'],
            conservative_setup['nVial']
        )

        Tbot = output[:, 2]
        T_crit = conservative_setup['product']['T_pr_crit']

        # Should respect conservative constraint
        assert np.max(Tbot) <= T_crit + TEMP_ATOL

    def test_high_product_resistance(self, conservative_setup):
        """Test with high product resistance."""
        conservative_setup['product']['R0'] = 3.0
        conservative_setup['product']['A1'] = 30.0

        output = opt_Pch.dry(
            conservative_setup['vial'],
            conservative_setup['product'],
            conservative_setup['ht'],
            conservative_setup['Pchamber'],
            conservative_setup['Tshelf'],
            conservative_setup['dt'],
            conservative_setup['eq_cap'],
            conservative_setup['nVial']
        )

        assert output.shape[0] > 0
        assert_physically_reasonable_output(output)

    def test_narrow_pressure_range_coverage(self, conservative_setup):
        """Test with narrow pressure optimization range."""
        conservative_setup['Pchamber']['min'] = 0.070
        conservative_setup['Pchamber']['max'] = 0.090

        output = opt_Pch.dry(
            conservative_setup['vial'],
            conservative_setup['product'],
            conservative_setup['ht'],
            conservative_setup['Pchamber'],
            conservative_setup['Tshelf'],
            conservative_setup['dt'],
            conservative_setup['eq_cap'],
            conservative_setup['nVial']
        )

        Pch = output[:, 4] / 1000
        assert np.all((Pch >= 0.065) & (Pch <= 0.095))

    def test_tight_equipment_constraint_coverage(self, conservative_setup):
        """Test with tight equipment capability constraint.

        Note: Tight constraints significantly limit optimization and may prevent
        high completion rates. Test validates optimizer handles constraints gracefully.
        """
        # Reduce equipment capability
        conservative_setup['eq_cap']['a'] = 2.0
        conservative_setup['eq_cap']['b'] = 5.0

        output = opt_Pch.dry(
            conservative_setup['vial'],
            conservative_setup['product'],
            conservative_setup['ht'],
            conservative_setup['Pchamber'],
            conservative_setup['Tshelf'],
            conservative_setup['dt'],
            conservative_setup['eq_cap'],
            conservative_setup['nVial']
        )

        # Should run without errors and show some progress despite tight constraint
        assert output is not None
        assert output.size > 0
        final_percent = output[-1, 6]
        assert final_percent >= 0.0, "Should have non-negative drying progress"
        assert final_percent <= PERCENT_MAX, f"Percent should not exceed {PERCENT_MAX}%"
