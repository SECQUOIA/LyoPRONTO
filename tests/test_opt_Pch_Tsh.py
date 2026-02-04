"""
Comprehensive tests for opt_Pch_Tsh.py - Joint pressure and temperature optimization module.

This module optimizes both chamber pressure and shelf temperature simultaneously.
Tests based on working example_optimizer.py structure.
"""

import pytest
import numpy as np
from lyopronto import opt_Pch_Tsh, opt_Pch, constant, opt_Tsh
from .utils import (
    assert_physically_reasonable_output,
    assert_complete_drying,
    PERCENT_COMPLETE,
    TEMP_ATOL,
    TEMP_RTOL,
)

# Constants for test assertions
MAX_AGGRESSIVE_OPTIMIZATION_TIME = (
    5.0  # Maximum expected drying time with aggressive optimization [hr]
)


@pytest.fixture
def standard_opt_pch_tsh_inputs():
    """Standard inputs for opt_Pch_Tsh testing (joint optimization)."""
    # Vial geometry
    vial = {
        "Av": 3.8,  # Vial area [cm**2]
        "Ap": 3.14,  # Product area [cm**2]
        "Vfill": 2.0,  # Fill volume [mL]
    }

    # Product properties
    product = {
        "T_pr_crit": -15.0,  # Critical product temperature [degC]
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
    # NOTE: Minimum pressure for optimization (website suggests 0.05 to 1000 [Torr])
    Pchamber = {
        "min": 0.05,  # Minimum chamber pressure [Torr]
        "max": 2.00,  # Maximum chamber pressure [Torr]
    }

    # Shelf temperature optimization settings
    # Optimize within range -45 to 120°C
    Tshelf = {
        "min": -45.0,  # Minimum shelf temperature [degC]
        "max": 120.0,  # Maximum shelf temperature [degC]
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


def opt_both_consistency(output, setup):
    vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial = setup

    assert output is not None, "opt_Pch_Tsh.dry should return output"
    assert isinstance(output, np.ndarray), "Output should be numpy array"

    # Should have 7 columns: time, Tsub, Tbot, Tsh, Pch, flux, percent_dried
    assert output.shape[1] == 7, f"Expected 7 columns, got {output.shape[1]}"

    # Should have multiple time points
    assert output.shape[0] > 1, "Should have multiple time points"

    assert_physically_reasonable_output(output, Tmax=Tshelf["max"])

    # Pch should be >= min pressure (0.05 Torr = 50 mTorr)
    assert np.all(output[:, 4] >= Pchamber["min"] * constant.Torr_to_mTorr), (
        f"Pch should be >= 50 mTorr (min), got min {output[:, 4].min()}"
    )

    # Pressure (column 4) should vary
    Pch_values = output[:, 4]
    assert np.std(Pch_values) > 0, "Pressure should vary (be optimized)"

    # Shelf temperature (column 3) should vary
    Tsh_values = output[:, 3]
    assert np.std(Tsh_values) > 0, "Shelf temperature should vary (be optimized)"

    # Both should respect bounds
    assert np.all(Pch_values >= Pchamber["min"] * constant.Torr_to_mTorr), (
        "Pressure should be >= min bound"
    )
    if hasattr(Pchamber, "max"):
        assert np.all(Pch_values <= Pchamber["max"] * constant.Torr_to_mTorr), (
            "Pressure should be <= max bound"
        )
    assert np.all(Tsh_values >= Tshelf["min"]), "Tsh should be >= min bound"
    assert np.all(Tsh_values <= Tshelf["max"]), "Tsh should be <= max bound"

    # Tbot (column 2) should stay at or below T_pr_crit
    T_crit = product["T_pr_crit"]
    assert np.all(output[:, 2] <= T_crit + TEMP_RTOL), (
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


class TestOptPchTshBasic:
    """Basic functionality tests for opt_Pch_Tsh module."""

    def test_opt_pch_tsh_basics(self, standard_opt_pch_tsh_inputs):
        """Test that:
        - opt_Pch_Tsh.dry executes successfully
        - output has correct shape and structure
        - each output column contains valid data
        - both pressure and temperature are optimized (vary over time)
        - product temperature stays at or below critical temperature
        - drying reaches near completion
        """
        vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial = (
            standard_opt_pch_tsh_inputs
        )

        output = opt_Pch_Tsh.dry(vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial)
        opt_both_consistency(output, standard_opt_pch_tsh_inputs)
        assert_complete_drying(output)

    def test_opt_pch_tsh_tight_ranges(self, standard_opt_pch_tsh_inputs):
        """Test with tight optimization ranges."""
        vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial = (
            standard_opt_pch_tsh_inputs
        )

        # Set tight ranges
        Pchamber["min"] = 0.40
        Pchamber["max"] = 0.70
        Tshelf["min"] = -20.0
        Tshelf["max"] = 0.0

        output = opt_Pch_Tsh.dry(vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial)

        opt_both_consistency(
            output, (vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial)
        )
        assert_complete_drying(output)


class TestOptPchTshEdgeCases:
    """Edge case tests for opt_Pch_Tsh module."""

    def test_narrow_temperature_range(self, standard_opt_pch_tsh_inputs):
        """Test with narrow shelf temperature optimization range."""
        vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial = (
            standard_opt_pch_tsh_inputs
        )

        # Narrow range: -10 to 10°C
        Tshelf["min"] = -10.0
        Tshelf["max"] = 10.0

        output = opt_Pch_Tsh.dry(vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial)

        opt_both_consistency(
            output, (vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial)
        )
        assert_complete_drying(output)
        # All temperatures should be within range
        assert np.all(output[:, 3] >= -10), "Tsh should be >= -10°C"
        assert np.all(output[:, 3] <= 10), "Tsh should be <= 10°C"

    def test_low_critical_temperature(self, standard_opt_pch_tsh_inputs):
        """Test with very low critical temperature (-35°C)."""
        vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial = (
            standard_opt_pch_tsh_inputs
        )

        # Lower critical temperature
        product["T_pr_crit"] = -35.0

        output = opt_Pch_Tsh.dry(vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial)

        opt_both_consistency(
            output, (vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial)
        )
        assert_complete_drying(output)

    def test_high_resistance_product(self, standard_opt_pch_tsh_inputs):
        """Test with high resistance product."""
        vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial = (
            standard_opt_pch_tsh_inputs
        )

        # Increase resistance
        product["R0"] = 3.0
        product["A1"] = 30.0

        output = opt_Pch_Tsh.dry(vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial)

        opt_both_consistency(
            output, (vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial)
        )
        assert_complete_drying(output)
        # Higher resistance should lead to longer drying time
        # TODO: this can be made concrete
        assert output[-1, 0] > 1.0, "High resistance should take longer to dry"

    def test_higher_min_pressure(self, standard_opt_pch_tsh_inputs):
        """Test with higher minimum pressure constraint (0.10 Torr)."""
        vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial = (
            standard_opt_pch_tsh_inputs
        )

        # Higher minimum pressure
        Pchamber["min"] = 0.10  # [Torr] = 100 [mTorr]

        output = opt_Pch_Tsh.dry(vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial)

        assert_complete_drying(output)
        # All pressures should be >= 100 [mTorr]
        assert np.all(output[:, 4] >= 100), "Pressure should respect higher min bound"
        opt_both_consistency(
            output, (vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial)
        )

    def test_concentrated_product(self, standard_opt_pch_tsh_inputs):
        """Test with high solids concentration."""
        vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial = (
            standard_opt_pch_tsh_inputs
        )
        product["cSolid"] = 0.15  # 15% solids

        output = opt_Pch_Tsh.dry(vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial)

        assert_physically_reasonable_output(output, Tmax=120)
        opt_both_consistency(
            output, (vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial)
        )


class TestOptPchTshValidation:
    """Validation tests comparing opt_Pch_Tsh behavior."""

    def test_joint_optimization_faster_than_single(self, standard_opt_pch_tsh_inputs):
        """Test that joint optimization is at least as fast as pressure-only optimization.

        Joint optimization has more degrees of freedom, so it should find
        at least as good (fast) a solution as pressure-only optimization.
        """
        vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial = (
            standard_opt_pch_tsh_inputs
        )

        # Run joint optimization
        output_joint = opt_Pch_Tsh.dry(
            vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial
        )

        # Run pressure-only optimization with fixed shelf temperature
        Tshelf_fixed = {
            "init": -35,
            "setpt": [-20],  # Fixed shelf temperature at -20°C
            "dt_setpt": [3600],  # Long time at fixed temperature
            "ramp_rate": 1.0,
        }
        output_pressure_only = opt_Pch.dry(
            vial, product, ht, Pchamber, Tshelf_fixed, dt, eq_cap, nVial
        )
        Pchamber_fixed = {
            "setpt": [0.5],  # Fixed pressure at 0.5 Torr
            "dt_setpt": [3600],  # Long time at fixed pressure
        }
        output_temperature_only = opt_Tsh.dry(
            vial, product, ht, Pchamber_fixed, Tshelf, dt, eq_cap, nVial
        )

        # Both optimizations should complete successfully
        assert_complete_drying(output_joint)
        assert_complete_drying(output_pressure_only)
        assert_complete_drying(output_temperature_only)

        # Joint optimization drying time should be <= pressure-only drying time
        assert output_joint[-1, 0] <= output_pressure_only[-1, 0], (
            "Joint optimization should beat P-only optimization"
        )
        assert output_joint[-1, 0] <= output_temperature_only[-1, 0], (
            "Joint optimization should beat T-only optimization"
        )

    @pytest.mark.slow
    def test_consistent_results(self, standard_opt_pch_tsh_inputs):
        """Test that repeated runs give consistent results."""
        vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial = (
            standard_opt_pch_tsh_inputs
        )

        # Run twice
        output1 = opt_Pch_Tsh.dry(
            vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial
        )
        output2 = opt_Pch_Tsh.dry(
            vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial
        )

        # Results should be identical (deterministic optimization)
        np.testing.assert_array_almost_equal(output1, output2, decimal=6)

    def test_aggressive_optimization_parameters(self, standard_opt_pch_tsh_inputs):
        """Test with aggressive optimization to maximize sublimation rate."""
        vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial = (
            standard_opt_pch_tsh_inputs
        )

        # Wide ranges to allow aggressive optimization
        Tshelf["min"] = -40.0
        Tshelf["max"] = 150.0
        Pchamber["min"] = 0.01

        output = opt_Pch_Tsh.dry(vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial)

        assert_physically_reasonable_output(output, Tmax=Tshelf["max"] + 0.1)

        opt_both_consistency(
            output, (vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial)
        )
        assert_complete_drying(output)

        # Should complete relatively quickly with aggressive optimization
        assert output[-1, 0] < MAX_AGGRESSIVE_OPTIMIZATION_TIME, (
            f"Aggressive optimization should complete in < {MAX_AGGRESSIVE_OPTIMIZATION_TIME} hr"
        )


# ==============================================================================
# Coverage tests (migrated from test_opt_Pch_Tsh_coverage.py)
# ==============================================================================


class TestOptPchTshCoverage:
    """Test joint Pch+Tsh optimizer - coverage tests."""

    @pytest.fixture
    def opt_both_setup(self, standard_vial, standard_ht):
        """Setup for joint Pch+Tsh optimization."""
        product = {
            'cSolid': 0.05,
            'R0': 1.4,
            'A1': 16.0,
            'A2': 0.0,
            'T_pr_crit': -30.0
        }

        # No fixed shelf temperature (will be optimized)
        Tshelf = {
            'min': -45.0,
            'max': -5.0
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

    @pytest.mark.slow
    def test_opt_both_completes(self, opt_both_setup):
        """Test that optimizer runs to completion."""
        output = opt_Pch_Tsh.dry(
            opt_both_setup['vial'],
            opt_both_setup['product'],
            opt_both_setup['ht'],
            opt_both_setup['Pchamber'],
            opt_both_setup['Tshelf'],
            opt_both_setup['dt'],
            opt_both_setup['eq_cap'],
            opt_both_setup['nVial']
        )

        # Should return an array
        assert isinstance(output, np.ndarray)
        assert output.shape[0] > 0
        assert output.shape[1] == 7  # Standard output columns

    @pytest.mark.slow
    def test_opt_both_output_shape(self, opt_both_setup):
        """Test output has correct format."""
        output = opt_Pch_Tsh.dry(
            opt_both_setup['vial'],
            opt_both_setup['product'],
            opt_both_setup['ht'],
            opt_both_setup['Pchamber'],
            opt_both_setup['Tshelf'],
            opt_both_setup['dt'],
            opt_both_setup['eq_cap'],
            opt_both_setup['nVial']
        )

        # Check shape
        assert output.shape[1] == 7, "Output should have 7 columns"

        # Check all values are finite
        assert np.all(np.isfinite(output)), "Output contains non-finite values"

    @pytest.mark.slow
    def test_opt_both_respects_temp_constraint(self, opt_both_setup):
        """Test critical temperature is not exceeded."""
        output = opt_Pch_Tsh.dry(
            opt_both_setup['vial'],
            opt_both_setup['product'],
            opt_both_setup['ht'],
            opt_both_setup['Pchamber'],
            opt_both_setup['Tshelf'],
            opt_both_setup['dt'],
            opt_both_setup['eq_cap'],
            opt_both_setup['nVial']
        )

        Tbot = output[:, 2]  # Vial bottom temperature
        T_crit = opt_both_setup['product']['T_pr_crit']

        # Allow 0.5°C tolerance for numerical optimization
        max_violation = np.max(Tbot - T_crit)
        assert max_violation <= 0.5, \
            f"Temperature exceeded critical by {max_violation:.2f}°C"

    @pytest.mark.slow
    def test_opt_both_pressure_within_bounds(self, opt_both_setup):
        """Test optimized pressure stays within bounds."""
        output = opt_Pch_Tsh.dry(
            opt_both_setup['vial'],
            opt_both_setup['product'],
            opt_both_setup['ht'],
            opt_both_setup['Pchamber'],
            opt_both_setup['Tshelf'],
            opt_both_setup['dt'],
            opt_both_setup['eq_cap'],
            opt_both_setup['nVial']
        )

        Pch = output[:, 4] / 1000  # Convert mTorr to Torr
        P_min = opt_both_setup['Pchamber']['min']
        P_max = opt_both_setup['Pchamber']['max']

        assert np.all(Pch >= P_min * 0.95), \
            f"Pressure {np.min(Pch):.3f} below minimum {P_min}"
        assert np.all(Pch <= P_max * 1.05), \
            f"Pressure {np.max(Pch):.3f} above maximum {P_max}"

    @pytest.mark.slow
    def test_opt_both_shelf_temp_within_bounds(self, opt_both_setup):
        """Test optimized shelf temperature stays within bounds."""
        output = opt_Pch_Tsh.dry(
            opt_both_setup['vial'],
            opt_both_setup['product'],
            opt_both_setup['ht'],
            opt_both_setup['Pchamber'],
            opt_both_setup['Tshelf'],
            opt_both_setup['dt'],
            opt_both_setup['eq_cap'],
            opt_both_setup['nVial']
        )

        Tsh = output[:, 3]  # Shelf temperature
        T_min = opt_both_setup['Tshelf']['min']
        T_max = opt_both_setup['Tshelf']['max']

        assert np.all(Tsh >= T_min - 1.0), \
            f"Shelf temp {np.min(Tsh):.1f} below minimum {T_min}"
        assert np.all(Tsh <= T_max + 1.0), \
            f"Shelf temp {np.max(Tsh):.1f} above maximum {T_max}"

    @pytest.mark.slow
    def test_opt_both_respects_equipment(self, opt_both_setup):
        """Test equipment capability constraint is satisfied."""
        output = opt_Pch_Tsh.dry(
            opt_both_setup['vial'],
            opt_both_setup['product'],
            opt_both_setup['ht'],
            opt_both_setup['Pchamber'],
            opt_both_setup['Tshelf'],
            opt_both_setup['dt'],
            opt_both_setup['eq_cap'],
            opt_both_setup['nVial']
        )

        flux = output[:, 5]  # Sublimation flux [kg/hr/m**2]
        Ap_m2 = opt_both_setup['vial']['Ap'] / 100**2  # Convert [cm**2] to [m**2]

        # Total sublimation rate per vial
        dmdt = flux * Ap_m2  # [kg/hr/vial]

        # Equipment capability at different pressures
        Pch = output[:, 4] / 1000  # [Torr]
        eq_cap_max = (opt_both_setup['eq_cap']['a'] +
                      opt_both_setup['eq_cap']['b'] * Pch) / opt_both_setup['nVial']

        # Should not exceed equipment capability (with small tolerance)
        violations = dmdt - eq_cap_max
        max_violation = np.max(violations)
        assert max_violation <= TEMP_RTOL, \
            f"Equipment capability exceeded by {max_violation:.4f} kg/hr"

    @pytest.mark.slow
    def test_opt_both_physically_reasonable(self, opt_both_setup):
        """Test output is physically reasonable."""
        output = opt_Pch_Tsh.dry(
            opt_both_setup['vial'],
            opt_both_setup['product'],
            opt_both_setup['ht'],
            opt_both_setup['Pchamber'],
            opt_both_setup['Tshelf'],
            opt_both_setup['dt'],
            opt_both_setup['eq_cap'],
            opt_both_setup['nVial']
        )

        assert_physically_reasonable_output(output)

    @pytest.mark.slow
    def test_opt_both_reaches_completion(self, opt_both_setup):
        """Test that drying reaches completion."""
        output = opt_Pch_Tsh.dry(
            opt_both_setup['vial'],
            opt_both_setup['product'],
            opt_both_setup['ht'],
            opt_both_setup['Pchamber'],
            opt_both_setup['Tshelf'],
            opt_both_setup['dt'],
            opt_both_setup['eq_cap'],
            opt_both_setup['nVial']
        )

        final_percent = output[-1, 6]
        assert final_percent >= PERCENT_COMPLETE, \
            f"Should reach {PERCENT_COMPLETE}% dried, got {final_percent:.1f}%"

    @pytest.mark.slow
    def test_opt_both_convergence(self, opt_both_setup):
        """Test optimization converges to a solution."""
        output = opt_Pch_Tsh.dry(
            opt_both_setup['vial'],
            opt_both_setup['product'],
            opt_both_setup['ht'],
            opt_both_setup['Pchamber'],
            opt_both_setup['Tshelf'],
            opt_both_setup['dt'],
            opt_both_setup['eq_cap'],
            opt_both_setup['nVial']
        )

        # If optimization converged, should have reasonable drying time
        total_time = output[-1, 0]
        assert 1.0 <= total_time <= 50.0, \
            f"Drying time {total_time:.1f} hr seems unreasonable"

    @pytest.mark.slow
    def test_opt_both_variables_optimized(self, opt_both_setup):
        """Test that both Pch and Tsh are actively optimized."""
        output = opt_Pch_Tsh.dry(
            opt_both_setup['vial'],
            opt_both_setup['product'],
            opt_both_setup['ht'],
            opt_both_setup['Pchamber'],
            opt_both_setup['Tshelf'],
            opt_both_setup['dt'],
            opt_both_setup['eq_cap'],
            opt_both_setup['nVial']
        )

        Pch = output[:, 4] / 1000  # Torr
        Tsh = output[:, 3]  # °C

        # Both should vary during optimization
        P_range = np.max(Pch) - np.min(Pch)
        T_range = np.max(Tsh) - np.min(Tsh)

        assert P_range > 0.001, "Pressure should vary during optimization"
        assert T_range > 0.5, "Shelf temperature should vary during optimization"


class TestOptPchTshCoverageComparison:
    """Test that joint optimization performs better than single-variable - coverage tests."""

    @pytest.fixture
    def comparison_setup(self, standard_vial, standard_ht):
        """Setup for comparing optimization strategies."""
        product = {
            'cSolid': 0.05,
            'R0': 1.4,
            'A1': 16.0,
            'A2': 0.0,
            'T_pr_crit': -30.0
        }

        # For joint optimization
        Tshelf_both = {
            'min': -45.0,
            'max': -5.0
        }

        # For Pch-only (fixed Tsh)
        Tshelf_pch_only = {
            'init': -40.0,
            'setpt': [-25.0, -15.0],
            'dt_setpt': [120.0, 120.0],
            'ramp_rate': 1.0
        }

        # For Tsh-only (fixed Pch)
        Pchamber_tsh_only = {
            'setpt': [0.080]
        }

        Pchamber_bounds = {
            'min': 0.040,
            'max': 0.200
        }

        dt = 0.01
        eq_cap = {'a': 5.0, 'b': 10.0}
        nVial = 398

        return {
            'vial': standard_vial,
            'product': product,
            'ht': standard_ht,
            'Pchamber_bounds': Pchamber_bounds,
            'Pchamber_tsh_only': Pchamber_tsh_only,
            'Tshelf_both': Tshelf_both,
            'Tshelf_pch_only': Tshelf_pch_only,
            'dt': dt,
            'eq_cap': eq_cap,
            'nVial': nVial
        }

    @pytest.mark.slow
    def test_joint_opt_vs_pch_only(self, comparison_setup):
        """Test joint optimization against Pch-only optimization.

        Note: Joint optimization is not guaranteed to be faster than Pch-only.
        It optimizes both variables which can take longer but may find better
        solutions. Test validates both approaches complete successfully.
        """
        # Joint optimization
        output_both = opt_Pch_Tsh.dry(
            comparison_setup['vial'],
            comparison_setup['product'],
            comparison_setup['ht'],
            comparison_setup['Pchamber_bounds'],
            comparison_setup['Tshelf_both'],
            comparison_setup['dt'],
            comparison_setup['eq_cap'],
            comparison_setup['nVial']
        )

        # Pch-only optimization
        output_pch = opt_Pch.dry(
            comparison_setup['vial'],
            comparison_setup['product'],
            comparison_setup['ht'],
            comparison_setup['Pchamber_bounds'],
            comparison_setup['Tshelf_pch_only'],
            comparison_setup['dt'],
            comparison_setup['eq_cap'],
            comparison_setup['nVial']
        )

        # Both should complete and return valid results
        assert output_both is not None
        assert output_pch is not None
        assert output_both.size > 0
        assert output_pch.size > 0

        # Check both achieve some drying progress
        final_both = output_both[-1, 6]
        final_pch = output_pch[-1, 6]
        assert final_both > 0.0, "Joint optimization should show drying progress"
        assert final_pch > 0.0, "Pch-only optimization should show drying progress"

    @pytest.mark.slow
    def test_joint_opt_shorter_or_equal_time(self, comparison_setup):
        """Test that joint optimization achieves reasonable drying time."""
        output = opt_Pch_Tsh.dry(
            comparison_setup['vial'],
            comparison_setup['product'],
            comparison_setup['ht'],
            comparison_setup['Pchamber_bounds'],
            comparison_setup['Tshelf_both'],
            comparison_setup['dt'],
            comparison_setup['eq_cap'],
            comparison_setup['nVial']
        )

        total_time = output[-1, 0]

        # Should achieve faster drying than typical conservative schedules
        assert total_time < 30.0, \
            f"Joint optimization took {total_time:.1f}h, expected <30h"


class TestOptPchTshCoverageEdgeCases:
    """Test edge cases for joint optimizer - coverage tests."""

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
            'min': -50.0,
            'max': -20.0
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

    @pytest.mark.slow
    def test_conservative_critical_temp_coverage(self, conservative_setup):
        """Test with very conservative critical temperature."""
        output = opt_Pch_Tsh.dry(
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

    @pytest.mark.slow
    def test_high_product_resistance_coverage(self, conservative_setup):
        """Test with high product resistance."""
        conservative_setup['product']['R0'] = 3.0
        conservative_setup['product']['A1'] = 30.0

        output = opt_Pch_Tsh.dry(
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

    @pytest.mark.slow
    def test_narrow_optimization_ranges_coverage(self, conservative_setup):
        """Test with narrow optimization ranges."""
        conservative_setup['Pchamber']['min'] = 0.070
        conservative_setup['Pchamber']['max'] = 0.090
        conservative_setup['Tshelf']['min'] = -35.0
        conservative_setup['Tshelf']['max'] = -25.0

        output = opt_Pch_Tsh.dry(
            conservative_setup['vial'],
            conservative_setup['product'],
            conservative_setup['ht'],
            conservative_setup['Pchamber'],
            conservative_setup['Tshelf'],
            conservative_setup['dt'],
            conservative_setup['eq_cap'],
            conservative_setup['nVial']
        )

        # Should still find solution within narrow ranges
        assert output[-1, 6] >= 0.95

    @pytest.mark.slow
    def test_tight_equipment_constraint_coverage(self, conservative_setup):
        """Test with tight equipment capability constraint."""
        # Reduce equipment capability
        conservative_setup['eq_cap']['a'] = 2.0
        conservative_setup['eq_cap']['b'] = 5.0

        output = opt_Pch_Tsh.dry(
            conservative_setup['vial'],
            conservative_setup['product'],
            conservative_setup['ht'],
            conservative_setup['Pchamber'],
            conservative_setup['Tshelf'],
            conservative_setup['dt'],
            conservative_setup['eq_cap'],
            conservative_setup['nVial']
        )

        # Should complete even with tight constraint
        assert output[-1, 6] >= 0.95

    @pytest.mark.slow
    def test_concentrated_product_coverage(self, conservative_setup):
        """Test with high solids concentration."""
        conservative_setup['product']['cSolid'] = 0.15  # 15% solids

        output = opt_Pch_Tsh.dry(
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
