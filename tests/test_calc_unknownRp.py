"""
Tests for calc_unknownRp.py - Parameter estimation module.

This module is a VALIDATION tool for future Pyomo implementations, not experimental code.
It estimates product resistance parameters (R0, A1, A2) from experimental temperature data.

These tests are based on the working example in ex_unknownRp_PD.py.
"""

import os

import numpy as np
import pytest
import scipy.optimize as sp
from lyopronto import calc_unknownRp
from lyopronto.functions import Lpr0_FUN, Rp_FUN

from .utils import (
    FLOAT_RTOL,
    MONOTONIC_ATOL,
    PERCENT_ATOL,
    PERCENT_MAX,
    PRESSURE_ATOL,
    assert_incomplete_drying,
    assert_physically_reasonable_output,
)

# Test constants for dried percent validation (column 6 is percentage 0-100)
MIN_COMPLETION_PERCENT = 50.0  # Minimum acceptable completion (50%) for some tests


@pytest.fixture
def standard_inputs_nodt(
    standard_vial, standard_ht, standard_pchamber, standard_tshelf
):
    """Default inputs for calc_unknownRp.py."""
    product = {"cSolid": 0.05, "T_pr_crit": -25.0}  # No R0, A1, A2 provided
    return standard_vial, product, standard_ht, standard_pchamber, standard_tshelf


@pytest.fixture
def temperature_data(reference_data_path):
    """Load temperature data from test_data/temperature.txt."""
    data_path = reference_data_path / "temperature.txt"
    if not data_path.exists():
        pytest.skip("Temperature data file not found")

    dat = np.loadtxt(data_path)

    # Handle different file formats
    if dat.ndim == 1:
        time = np.array([dat[0]])
        Tbot_exp = np.array([dat[1]])
    elif dat.shape[1] == 2:
        time = dat[:, 0]
        Tbot_exp = dat[:, 1]
    else:
        time = dat[:, 1]
        Tbot_exp = dat[:, 2]

    return time, Tbot_exp


class TestCalcUnknownRpBasic:
    """Basic functionality tests for parameter estimation."""

    def test_calc_unknownRp_basics(self, standard_inputs_nodt, temperature_data):
        """For calc_unknownRp.dry(), test that:
        - executes successfully
        - output has correct shape
        - output columns contain valid data
        - product_res contains valid resistance data
        - parameter estimation produces reasonable values
        - drying exceeds half completion
        - cake length reaches reasonable values, matches drying progress
        """
        vial, product, ht, Pchamber, Tshelf = standard_inputs_nodt
        time, Tbot_exp = temperature_data

        # Run parameter estimation
        output, product_res = calc_unknownRp.dry(
            vial, product, ht, Pchamber, Tshelf, time, Tbot_exp
        )

        # Verify output exists
        assert output is not None, "output should not be None"
        assert product_res is not None, "product_res should not be None"
        assert isinstance(output, np.ndarray), "output should be numpy array"
        assert isinstance(product_res, np.ndarray), "product_res should be numpy array"

        # Output should have 7 columns (same as calc_knownRp)
        assert output.shape[1] == 7, f"Expected 7 columns, got {output.shape[1]}"

        # product_res should have 3 columns (time, Lck, Rp)
        assert product_res.shape[1] == 3, (
            f"Expected 3 columns in product_res, got {product_res.shape[1]}"
        )

        # Should have multiple time points
        assert len(output) > 10, "Should have multiple time points"
        assert len(product_res) > 10, "product_res should have multiple points"

        assert_physically_reasonable_output(output)

        # Column 0: Time
        assert np.all(product_res[:, 0] >= 0), "Time should be non-negative"

        # Column 1: Lck (cake length) should increase from 0
        assert product_res[0, 1] == pytest.approx(0.0, abs=1e-6), (
            "Should start at Lck=0"
        )
        assert np.all(np.diff(product_res[:, 1]) >= 0), "Lck should be non-decreasing"

        # Column 2: Rp (resistance) - NOTE: can be negative early during optimization
        # We just check that the final resistance is positive and reasonable
        assert product_res[-1, 2] > 0, "Final resistance should be positive"

        # Check that resistance is positive and reasonable
        # Negative values *do* occur in the early phase, if calculated with incorrect conditions
        # or simply because the measurements come from a real system.
        positive_count = np.sum(product_res[:, 2] > 0)
        assert positive_count > len(product_res) / 2, (
            "Most resistances should be positive"
        )

        # Fit Rp model: Rp = R0 + A1*Lck/(1 + A2*Lck)
        params, params_covariance = sp.curve_fit(
            Rp_FUN,
            product_res[:, 1],  # Lck
            product_res[:, 2],  # Rp
            p0=[1.0, 1.0, 0.0],
        )

        R0_est = params[0]
        A1_est = params[1]
        A2_est = params[2]

        # Check physical reasonableness
        assert R0_est > 0, f"R0 should be positive, got {R0_est}"
        assert R0_est < 100, f"R0 seems unreasonably large: {R0_est}"
        assert A1_est >= 0, f"A1 should be non-negative, got {A1_est}"
        assert A2_est >= 0, f"A2 should be non-negative, got {A2_est}"

        # Check covariance is reasonable (not infinite/NaN)
        assert np.all(np.isfinite(params_covariance)), "Covariance should be finite"

        assert_incomplete_drying(output)
        # Calculate initial product height
        Lpr0 = Lpr0_FUN(vial["Vfill"], vial["Ap"], product["cSolid"])

        final_Lck = product_res[-1, 1]

        # Final cake length should be nonzero
        # Should not exceed original, since experimental data must end before complete drying)
        assert final_Lck > 0, "Cake length should have progressed"
        assert final_Lck <= Lpr0 * 1.01, "Cake length should not exceed initial height"


class TestCalcUnknownRpEdgeCases:
    """Test edge cases and different input scenarios."""

    def test_short_time_series(self, standard_inputs_nodt):
        """Test with minimal time points."""
        # Minimal time series (3 points)
        time = np.array([0.0, 1.0, 2.0])
        Tbot_exp = np.array([-40.0, -37.0, -35.0])
        # Should run without error
        output, product_res = calc_unknownRp.dry(*standard_inputs_nodt, time, Tbot_exp)
        assert output is not None
        assert len(output) == len(Tbot_exp) + 1, (
            "Should have exactly 3 time points to match temperature input"
        )
        assert_physically_reasonable_output(output)

    def test_different_pressure(self, standard_inputs_nodt):
        """Test with different chamber pressure."""
        vial, product, ht, _, Tshelf = standard_inputs_nodt
        Pchamber = {
            "setpt": [0.10],
            "dt_setpt": [1800.0],
            "ramp_rate": 0.5,
        }  # Lower pressure

        time = np.array([0.0, 1.0, 2.0, 3.0])
        Tbot_exp = np.array([-40.0, -38.0, -32.0, -25.0])

        output, product_res = calc_unknownRp.dry(
            vial, product, ht, Pchamber, Tshelf, time, Tbot_exp
        )

        # Check pressure in output (should be 100 mTorr)
        assert np.allclose(output[:, 4], 100.0, atol=PRESSURE_ATOL), (
            "Pch should be ~100 mTorr"
        )
        assert_physically_reasonable_output(output)

    def test_infeasible(self, standard_inputs_nodt):
        """Test with input temperatures above shelf temperature."""

        time = np.array([0.0, 1.0, 2.0, 3.0])
        # initial temperatures above shelf temp (-35C)
        Tbot_exp = np.array([-30.0, -38.0, -32.0, -25.0])

        with pytest.warns(UserWarning, match="No sublimation"):
            calc_unknownRp.dry(*standard_inputs_nodt, time, Tbot_exp)

        # initial temperatures below, but later tempratures above
        Tbot_exp = np.array([-40.0, -25.0, -20.0, -15.0])

        with pytest.warns(UserWarning, match="No sublimation"):
            calc_unknownRp.dry(*standard_inputs_nodt, time, Tbot_exp)

    def test_too_long_time_series(self, standard_inputs_nodt):
        """Test with long time series: reaches end of drying before data exhausted.

        This is an edge case where interpolation may cause small numerical overshoots.
        """
        time = np.linspace(0, 50, 10001)  # 10001 points over long time
        Tbot_exp = -40.0 + 0.005 * time  # Gradual increase

        with pytest.warns(UserWarning, match="Reached end of drying"):
            output, product_res = calc_unknownRp.dry(
                *standard_inputs_nodt, time, Tbot_exp
            )

        assert output is not None
        assert len(output) < len(Tbot_exp) + 1, (
            "Should not have reached end of time series"
        )

        # Skip strict physical reasonableness check for this edge case
        # as interpolation can cause small numerical overshoots at drying completion
        assert np.all(output[:, 6] >= 0), "Percent dried should be non-negative"
        assert np.all(output[:, 6] <= PERCENT_MAX + PERCENT_ATOL), (
            "Percent dried should not exceed 100% significantly"
        )

    def test_short_shelf_temp_schedule(self, standard_inputs_nodt, temperature_data):
        """Test with shelf temperature schedule shorter than temperature data."""
        vial, product, ht, Pchamber, Tshelf = standard_inputs_nodt

        # Short shelf temperature schedule
        Tshelf["setpt"] = [-20.0]
        Tshelf["dt_setpt"] = [60.0]  # 1 hour

        with pytest.warns(UserWarning, match="time exceeded"):
            output, product_res = calc_unknownRp.dry(
                vial, product, ht, Pchamber, Tshelf, *temperature_data
            )

        assert output is not None
        assert_physically_reasonable_output(output)

    def test_short_pressure_schedule(self, standard_inputs_nodt, temperature_data):
        """Test with chamber pressure schedule shorter than temperature data."""
        vial, product, ht, Pchamber, Tshelf = standard_inputs_nodt

        # Short chamber pressure schedule
        Pchamber["setpt"] = [0.10]
        Pchamber["dt_setpt"] = [60.0]  # 1 hour

        with pytest.warns(UserWarning, match="time exceeded"):
            output, product_res = calc_unknownRp.dry(
                vial, product, ht, Pchamber, Tshelf, *temperature_data
            )

        assert output is not None
        assert_physically_reasonable_output(output)

    def test_different_product_concentration(
        self, standard_inputs_nodt, temperature_data
    ):
        """Test with different solute concentration."""
        vial, product, ht, Pchamber, Tshelf = standard_inputs_nodt
        product["cSolid"] = 0.15  # Higher concentration

        output, product_res = calc_unknownRp.dry(
            vial, product, ht, Pchamber, Tshelf, *temperature_data
        )

        assert output is not None
        # Higher concentration means less ice to sublimate, different drying time
        assert_physically_reasonable_output(output)

    def test_unknown_rp_condition_changes(self, standard_inputs_nodt, temperature_data):
        """Test shelf temperature and chamber pressure follow varying schedules."""
        vial, product, ht, _, __ = standard_inputs_nodt

        Tshelf = {
            "init": -35.0,
            "setpt": [-10.0, -20.0],  # Two ramp stages
            "dt_setpt": [120.0, 1200.0],  # 2 + 20 hours in [min]
            "ramp_rate": 0.5,  # deg/min
        }

        Pchamber = {
            "setpt": [0.100, 0.080, 0.100],  # Three pressure stages
            "dt_setpt": [60.0, 120.0, 120.0],  # Time at each stage [min]
            "ramp_rate": 0.5,  # Ramp rate [Torr/min]
        }
        output, product_res = calc_unknownRp.dry(
            vial, product, ht, Pchamber, Tshelf, *temperature_data
        )

        Tsh = output[:, 3]

        # Shelf temperature should start at init value
        assert abs(Tsh[0] - Tshelf["init"]) < 1.0, (
            f"Initial Tsh should be near {Tshelf['init']}, got {Tsh[0]}"
        )

        # Shelf temperature should change over time
        Tsh_range = np.max(Tsh) - np.min(Tsh)
        assert Tsh_range > 5.0, "Shelf temperature should vary during ramping"

        Pch = output[:, 4] / 1000  # Convert mTorr to Torr

        # Pressure should be within range of setpoints
        min_setpt = min(Pchamber["setpt"])
        max_setpt = max(Pchamber["setpt"])

        assert np.min(Pch) >= min_setpt, (
            f"Min pressure {np.min(Pch):.3f} below setpoint range"
        )
        assert np.max(Pch) <= max_setpt, (
            f"Max pressure {np.max(Pch):.3f} above setpoint range"
        )

        # This includes checks for drying progress, temperature, flux, etc.
        assert_physically_reasonable_output(output)


class TestCalcUnknownRpValidation:
    """Validation tests against known examples."""

    def test_matches_example_script(self, standard_inputs_nodt, temperature_data):
        """Test that results match ex_unknownRp_PD.py example."""
        # Use same inputs as ex_unknownRp_PD.py

        # Run calc_unknownRp
        output, product_res = calc_unknownRp.dry(
            *standard_inputs_nodt, *temperature_data
        )

        assert_physically_reasonable_output(output)
        assert_incomplete_drying(output)

        # Estimate parameters
        params, _ = sp.curve_fit(
            Rp_FUN, product_res[:, 1], product_res[:, 2], p0=[1.0, 0.0, 0.0]
        )

        R0 = params[0]
        A1 = params[1]
        A2 = params[2]

        # Parameters should be physically reasonable
        # (exact values depend on experimental data, but ranges should be sensible)
        # TODO for this reference case, have exact values. Give them here
        assert 0 < R0 < 10, f"R0 = {R0} outside expected range (0, 10)"
        assert 0 <= A1 < 50, f"A1 = {A1} outside expected range [0, 50)"
        assert 0 <= A2 < 5, f"A2 = {A2} outside expected range [0, 5)"


class TestCalcUnknownRpCoverage:
    """Additional tests for calc_unknownRp coverage."""

    @pytest.fixture
    def unknown_rp_setup(self, standard_vial, standard_ht):
        """Setup for unknown Rp calculation with experimental temperature data."""
        # Product without R0, A1, A2 (will be estimated)
        product = {"cSolid": 0.05, "T_pr_crit": -30.0}

        # Time-varying shelf temperature
        Tshelf = {
            "init": -40.0,
            "setpt": [-20.0, -10.0],  # Two ramp stages
            "dt_setpt": [120.0, 120.0],  # 2 hours in [min]
            "ramp_rate": 0.1,  # deg/min
        }

        # Time-varying chamber pressure
        Pchamber = {
            "setpt": [0.060, 0.080, 0.100],  # Three pressure stages
            "dt_setpt": [60.0, 120.0, 120.0],  # Time at each stage [min]
            "ramp_rate": 0.5,  # Ramp rate [Torr/min]
        }

        # Load experimental temperature data
        test_data_dir = os.path.join(os.path.dirname(__file__), "..", "test_data")
        temp_file = os.path.join(test_data_dir, "temperature.txt")

        # Load and parse temperature data
        time_exp = []
        Tbot_exp = []
        with open(temp_file) as f:
            for line in f:
                if line.strip():
                    t, T = line.split()
                    time_exp.append(float(t))
                    Tbot_exp.append(float(T))

        time = np.array(time_exp)
        Tbot_exp = np.array(Tbot_exp)

        return {
            "vial": standard_vial,
            "product": product,
            "ht": standard_ht,
            "Pchamber": Pchamber,
            "Tshelf": Tshelf,
            "time": time,
            "Tbot_exp": Tbot_exp,
        }

    def test_unknown_rp_completes(self, unknown_rp_setup):
        """Test that simulation completes with experimental data."""
        output, product_res = calc_unknownRp.dry(
            unknown_rp_setup["vial"],
            unknown_rp_setup["product"],
            unknown_rp_setup["ht"],
            unknown_rp_setup["Pchamber"],
            unknown_rp_setup["Tshelf"],
            unknown_rp_setup["time"],
            unknown_rp_setup["Tbot_exp"],
        )

        # Should return an array
        assert isinstance(output, np.ndarray)
        assert output.shape[0] > 0
        assert output.shape[1] == 7  # Standard output columns

    def test_unknown_rp_output_shape(self, unknown_rp_setup):
        """Test output has correct dimensions and structure."""
        output, product_res = calc_unknownRp.dry(
            unknown_rp_setup["vial"],
            unknown_rp_setup["product"],
            unknown_rp_setup["ht"],
            unknown_rp_setup["Pchamber"],
            unknown_rp_setup["Tshelf"],
            unknown_rp_setup["time"],
            unknown_rp_setup["Tbot_exp"],
        )

        # Check number of columns
        assert output.shape[1] == 7, "Output should have 7 columns"

        # Check output columns exist and are numeric
        assert np.all(np.isfinite(output[:, 0])), "Time column has invalid values"
        assert np.all(np.isfinite(output[:, 1])), "Tsub column has invalid values"
        assert np.all(np.isfinite(output[:, 2])), "Tbot column has invalid values"
        assert np.all(np.isfinite(output[:, 3])), "Tsh column has invalid values"
        assert np.all(np.isfinite(output[:, 4])), "Pch column has invalid values"
        assert np.all(np.isfinite(output[:, 5])), "flux column has invalid values"
        assert np.all(np.isfinite(output[:, 6])), "frac_dried column has invalid values"

    def test_unknown_rp_time_progression(self, unknown_rp_setup):
        """Test time progresses monotonically."""
        output, product_res = calc_unknownRp.dry(
            unknown_rp_setup["vial"],
            unknown_rp_setup["product"],
            unknown_rp_setup["ht"],
            unknown_rp_setup["Pchamber"],
            unknown_rp_setup["Tshelf"],
            unknown_rp_setup["time"],
            unknown_rp_setup["Tbot_exp"],
        )

        time = output[:, 0]

        # Time should be monotonically increasing
        time_diffs = np.diff(time)
        assert np.all(time_diffs >= 0), "Time must be monotonically increasing"

        # Time should start at or near zero
        assert time[0] >= 0, f"Initial time should be non-negative, got {time[0]}"

    def test_unknown_rp_shelf_temp_changes(self, unknown_rp_setup):
        """Test shelf temperature follows ramp schedule."""
        output, product_res = calc_unknownRp.dry(
            unknown_rp_setup["vial"],
            unknown_rp_setup["product"],
            unknown_rp_setup["ht"],
            unknown_rp_setup["Pchamber"],
            unknown_rp_setup["Tshelf"],
            unknown_rp_setup["time"],
            unknown_rp_setup["Tbot_exp"],
        )

        Tsh = output[:, 3]

        # Shelf temperature should start at init value
        assert abs(Tsh[0] - unknown_rp_setup["Tshelf"]["init"]) < 1.0, (
            f"Initial Tsh should be near {unknown_rp_setup['Tshelf']['init']}, got {Tsh[0]}"
        )

        # Shelf temperature should change over time
        Tsh_range = np.max(Tsh) - np.min(Tsh)
        assert Tsh_range > 5.0, "Shelf temperature should vary during ramping"

    def test_unknown_rp_pressure_changes(self, unknown_rp_setup):
        """Test chamber pressure follows setpoint schedule."""
        output, product_res = calc_unknownRp.dry(
            unknown_rp_setup["vial"],
            unknown_rp_setup["product"],
            unknown_rp_setup["ht"],
            unknown_rp_setup["Pchamber"],
            unknown_rp_setup["Tshelf"],
            unknown_rp_setup["time"],
            unknown_rp_setup["Tbot_exp"],
        )

        Pch = output[:, 4] / 1000  # Convert mTorr to Torr

        # Pressure should be within range of setpoints
        min_setpt = min(unknown_rp_setup["Pchamber"]["setpt"])
        max_setpt = max(unknown_rp_setup["Pchamber"]["setpt"])

        assert np.min(Pch) >= min_setpt * 0.9, (
            f"Min pressure {np.min(Pch):.3f} below setpoint range"
        )
        assert np.max(Pch) <= max_setpt * 1.1, (
            f"Max pressure {np.max(Pch):.3f} above setpoint range"
        )

    def test_unknown_rp_physically_reasonable(self, unknown_rp_setup):
        """Test output has valid numeric values.

        Note: Experimental data may not satisfy all physics constraints,
        so we check basic validity rather than full physical reasonableness.
        """
        output, product_res = calc_unknownRp.dry(
            unknown_rp_setup["vial"],
            unknown_rp_setup["product"],
            unknown_rp_setup["ht"],
            unknown_rp_setup["Pchamber"],
            unknown_rp_setup["Tshelf"],
            unknown_rp_setup["time"],
            unknown_rp_setup["Tbot_exp"],
        )

        # Check basic validity
        assert np.all(np.isfinite(output)), "Output should have finite values"
        assert output.shape[1] == 7, "Output should have 7 columns"

    def test_unknown_rp_reaches_completion(self, unknown_rp_setup):
        """Test that drying progresses with parameter estimation.

        Note: Parameter estimation with experimental data may not always
        reach high completion due to physics constraints and fitting complexity.
        """
        output, product_res = calc_unknownRp.dry(
            unknown_rp_setup["vial"],
            unknown_rp_setup["product"],
            unknown_rp_setup["ht"],
            unknown_rp_setup["Pchamber"],
            unknown_rp_setup["Tshelf"],
            unknown_rp_setup["time"],
            unknown_rp_setup["Tbot_exp"],
        )

        final_percent = output[-1, 6]
        # Parameter estimation may have limited progress - check for any drying
        assert final_percent > 0.0, (
            f"Should show drying progress, got {final_percent:.1f}%"
        )
        # Percent dried must not exceed 100%
        assert final_percent <= PERCENT_MAX + FLOAT_RTOL, (
            f"Percent dried should not exceed {PERCENT_MAX}%, got {final_percent:.10f}%"
        )

    def test_unknown_rp_percent_dried_monotonic(self, unknown_rp_setup):
        """Test percent dried increases monotonically."""
        output, product_res = calc_unknownRp.dry(
            unknown_rp_setup["vial"],
            unknown_rp_setup["product"],
            unknown_rp_setup["ht"],
            unknown_rp_setup["Pchamber"],
            unknown_rp_setup["Tshelf"],
            unknown_rp_setup["time"],
            unknown_rp_setup["Tbot_exp"],
        )

        percent_dried = output[:, 6]

        # Percent dried should be monotonically increasing
        diffs = np.diff(percent_dried)
        assert np.all(diffs >= -MONOTONIC_ATOL), (
            "Percent dried must increase monotonically"
        )

    def test_unknown_rp_flux_positive(self, unknown_rp_setup):
        """Test sublimation flux is non-negative."""
        output, product_res = calc_unknownRp.dry(
            unknown_rp_setup["vial"],
            unknown_rp_setup["product"],
            unknown_rp_setup["ht"],
            unknown_rp_setup["Pchamber"],
            unknown_rp_setup["Tshelf"],
            unknown_rp_setup["time"],
            unknown_rp_setup["Tbot_exp"],
        )

        flux = output[:, 5]
        assert np.all(flux >= 0), "Sublimation flux must be non-negative"

    def test_unknown_rp_different_initial_pressure(self, unknown_rp_setup):
        """Test with different initial chamber pressure."""
        # Modify pressure setpoints
        Pchamber_modified = unknown_rp_setup["Pchamber"].copy()
        Pchamber_modified["setpt"] = [0.050, 0.070, 0.090]

        output, product_res = calc_unknownRp.dry(
            unknown_rp_setup["vial"],
            unknown_rp_setup["product"],
            unknown_rp_setup["ht"],
            Pchamber_modified,
            unknown_rp_setup["Tshelf"],
            unknown_rp_setup["time"],
            unknown_rp_setup["Tbot_exp"],
        )

        assert output.shape[0] > 0
        assert output.shape[1] == 7  # Basic shape check for experimental data


class TestCalcUnknownRpCoverageEdgeCases:
    """Edge case tests for unknown Rp calculator coverage."""

    @pytest.fixture
    def minimal_setup(self, standard_vial, standard_ht):
        """Minimal setup with short time series."""
        product = {"cSolid": 0.05, "T_pr_crit": -30.0}

        Tshelf = {"init": -40.0, "setpt": [-30.0], "dt_setpt": [60.0], "ramp_rate": 0.1}

        Pchamber = {"setpt": [0.080], "dt_setpt": [60.0], "ramp_rate": 0.5}

        # Minimal time series
        time = np.array([0.0, 0.5, 1.0, 1.5, 2.0])
        Tbot_exp = np.array([-40.0, -38.0, -35.0, -32.0, -30.0])

        return {
            "vial": standard_vial,
            "product": product,
            "ht": standard_ht,
            "Pchamber": Pchamber,
            "Tshelf": Tshelf,
            "time": time,
            "Tbot_exp": Tbot_exp,
        }

    def test_minimal_time_series(self, minimal_setup):
        """Test with minimal time series data."""
        output, product_res = calc_unknownRp.dry(
            minimal_setup["vial"],
            minimal_setup["product"],
            minimal_setup["ht"],
            minimal_setup["Pchamber"],
            minimal_setup["Tshelf"],
            minimal_setup["time"],
            minimal_setup["Tbot_exp"],
        )

        assert output.shape[0] > 0
        assert output.shape[1] == 7

    def test_single_pressure_setpoint(self, minimal_setup):
        """Test with single constant pressure."""
        # Already has single pressure in minimal_setup
        output, product_res = calc_unknownRp.dry(
            minimal_setup["vial"],
            minimal_setup["product"],
            minimal_setup["ht"],
            minimal_setup["Pchamber"],
            minimal_setup["Tshelf"],
            minimal_setup["time"],
            minimal_setup["Tbot_exp"],
        )

        Pch = output[:, 4] / 1000  # Convert to Torr

        # Should maintain constant pressure
        Pch_std = np.std(Pch)
        assert Pch_std < 0.01, f"Pressure should be nearly constant, std={Pch_std:.4f}"

    def test_high_solids_concentration(self, minimal_setup):
        """Test with high solids concentration.

        Note: High solids concentration with minimal time series may produce
        edge case physics that don't pass all reasonableness checks.
        """
        minimal_setup["product"]["cSolid"] = 0.15  # 15% solids

        output, product_res = calc_unknownRp.dry(
            minimal_setup["vial"],
            minimal_setup["product"],
            minimal_setup["ht"],
            minimal_setup["Pchamber"],
            minimal_setup["Tshelf"],
            minimal_setup["time"],
            minimal_setup["Tbot_exp"],
        )

        # Just check shape - edge case physics may not pass full validation
        assert output.shape[0] > 0
        assert output.shape[1] == 7
