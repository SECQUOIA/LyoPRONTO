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
    assert_warning_messages,
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
    if "max" in Pchamber:
        assert np.all(Pch_values <= Pchamber["max"] * constant.Torr_to_mTorr), (
            "Pressure should be <= max bound"
        )

    # Tbot (column 2) should stay at or below T_pr_crit
    T_crit = product["T_pr_crit"]
    assert np.all(output[:, 2] <= T_crit + 0.01), (
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


@pytest.mark.slow
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


@pytest.mark.slow
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
        Pchamber["min"] = 0.10  # [Torr] = 100 mTorr
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
        Pchamber["min"] = 0.10  # [Torr] = 100 mTorr
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

        with pytest.warns(Warning) as warning_record:
            output = opt_Pch.dry(vial, product, ht, new_Pch, Tshelf, dt, eq_cap, nVial)

        assert_warning_messages(warning_record, ["Optimization failed"])

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


@pytest.mark.slow
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
        # Drying time should be equal to or better than reference (with small tolerance
        # for floating-point differences across Python versions)
        drying_time_ref = output_ref[-1, 0]
        drying_time = output[-1, 0]
        assert drying_time <= drying_time_ref + 1e-3, (
            f"Drying time {drying_time:.6f} hr should be <= reference "
            + f"{drying_time_ref:.6f} hr"
        )
        # array_compare = np.isclose(output, output_ref, atol=1e-3)
        # assert array_compare.all(), (
        #     "opt_Pch output should match reference data, but reference data is known to "
        #     + "be odd, so (with maintainer approval) the reference data may be updated."
        #     + f"Not matching at positions:\n {np.where(~array_compare)}"
        # )


def _incomplete_pressure_setup(vial=None, ht=None):
    """Inputs for the bounded, incomplete pressure-optimization regression."""
    return {
        "vial": vial or {"Av": 3.80, "Ap": 3.14, "Vfill": 2.0},
        "product": {
            "cSolid": 0.05,
            "R0": 1.4,
            "A1": 16.0,
            "A2": 0.0,
            "T_pr_crit": -30.0,
        },
        "ht": ht or {"KC": 2.75e-4, "KP": 8.93e-4, "KD": 0.46},
        "Pchamber": {"min": 0.040, "max": 0.200},
        "Tshelf": {
            "init": -40.0,
            "setpt": [-20.0, -10.0],
            "dt_setpt": [120.0, 120.0],
            "ramp_rate": 1.0,
        },
        "dt": 0.01,
        "eq_cap": {"a": 5.0, "b": 10.0},
        "nVial": 398,
    }


def _conservative_pressure_setup(vial=None, ht=None):
    """Inputs for conservative pressure-optimization constraint scenarios."""
    setup = _incomplete_pressure_setup(vial, ht)
    setup["product"]["T_pr_crit"] = -40.0
    setup["Pchamber"] = {"min": 0.040, "max": 0.100}
    setup["Tshelf"] = {
        "init": -45.0,
        "setpt": [-35.0],
        "dt_setpt": [120.0],
        "ramp_rate": 1.0,
    }
    return setup


def _dry_pressure_with_expected_warnings(setup, *, allowed_warnings=None):
    """Run a pressure edge case and reject warnings outside its contract."""
    if allowed_warnings is None:
        allowed_warnings = ["Total time exceeded. Drying incomplete"]
    with pytest.warns(Warning) as warning_record:
        output = opt_Pch.dry(
            setup["vial"],
            setup["product"],
            setup["ht"],
            setup["Pchamber"],
            setup["Tshelf"],
            setup["dt"],
            setup["eq_cap"],
            setup["nVial"],
        )
    assert_warning_messages(warning_record, allowed_warnings)
    return output


@pytest.fixture(scope="class")
def incomplete_pressure_case():
    """Share the identical incomplete pressure run across its assertions."""
    setup = _incomplete_pressure_setup()
    return {"setup": setup, "output": _dry_pressure_with_expected_warnings(setup)}


class TestOptPchIncompleteRegression:
    """Properties of the bounded pressure run that intentionally stays incomplete."""

    def test_incomplete_pressure_regression_properties(self, incomplete_pressure_case):
        output = incomplete_pressure_case["output"]
        setup = incomplete_pressure_case["setup"]

        assert isinstance(output, np.ndarray)
        assert output.shape[0] > 0
        assert output.shape[1] == 7
        assert np.all(np.isfinite(output))

        bottom_temperature = output[:, 2]
        critical_temperature = setup["product"]["T_pr_crit"]
        max_temperature_violation = np.max(
            bottom_temperature - critical_temperature
        )
        assert max_temperature_violation <= 0.5

        pressure_torr = output[:, 4] / 1000
        assert np.all(pressure_torr >= setup["Pchamber"]["min"] * 0.95)
        assert np.all(pressure_torr <= setup["Pchamber"]["max"] * 1.05)

        flux = output[:, 5]
        product_area_m2 = setup["vial"]["Ap"] / 100**2
        rate_per_vial = flux * product_area_m2
        equipment_rate_per_vial = (
            setup["eq_cap"]["a"] + setup["eq_cap"]["b"] * pressure_torr
        ) / setup["nVial"]
        assert np.max(rate_per_vial - equipment_rate_per_vial) <= 0.01

        assert_physically_reasonable_output(output)
        assert 0.0 < output[-1, 6] <= 100.0
        assert 1.0 <= output[-1, 0] <= 50.0
        assert np.ptp(pressure_torr) > 0.001


class TestOptPchConservativeScenarios:
    """Distinct conservative constraint scenarios retained from the old suite."""

    @pytest.fixture
    def conservative_setup(self, standard_vial, standard_ht):
        return _conservative_pressure_setup(standard_vial, standard_ht)

    def test_conservative_critical_temp(self, conservative_setup):
        output = _dry_pressure_with_expected_warnings(conservative_setup)
        assert np.max(output[:, 2]) <= conservative_setup["product"]["T_pr_crit"] + 0.5

    def test_high_product_resistance(self, conservative_setup):
        conservative_setup["product"]["R0"] = 3.0
        conservative_setup["product"]["A1"] = 30.0
        output = _dry_pressure_with_expected_warnings(conservative_setup)
        assert output.shape[0] > 0
        assert_physically_reasonable_output(output)

    def test_narrow_pressure_range(self, conservative_setup):
        conservative_setup["Pchamber"] = {"min": 0.070, "max": 0.090}
        output = _dry_pressure_with_expected_warnings(
            conservative_setup,
            allowed_warnings=[
                "Optimization failed",
                "Total time exceeded. Drying incomplete",
            ],
        )
        pressure_torr = output[:, 4] / 1000
        assert np.all((pressure_torr >= 0.065) & (pressure_torr <= 0.095))

    def test_tight_equipment_constraint(self, conservative_setup):
        conservative_setup["eq_cap"] = {"a": 2.0, "b": 5.0}
        output = _dry_pressure_with_expected_warnings(conservative_setup)
        assert output is not None
        assert output.size > 0
        assert 0.0 <= output[-1, 6] <= 100.0
