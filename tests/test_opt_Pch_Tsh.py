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
    assert_warning_messages,
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
    if "max" in Pchamber:
        assert np.all(Pch_values <= Pchamber["max"] * constant.Torr_to_mTorr), (
            "Pressure should be <= max bound"
        )
    assert np.all(Tsh_values >= Tshelf["min"]), "Tsh should be >= min bound"
    assert np.all(Tsh_values <= Tshelf["max"]), "Tsh should be <= max bound"

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


@pytest.mark.slow
class TestOptPchTshRegressionBaseline:
    """Pin the joint-optimizer trajectory against a committed baseline.

    Unlike ``reference_opt_Tsh.csv`` and ``reference_opt_Pch.csv``, which hold
    independent web-interface output, this baseline is generated from this
    repository's own code. It therefore demonstrates stability, not
    correctness: it catches unintended trajectory drift from solver or
    formulation changes, and says nothing about whether the trajectory is
    physically right. The physical claims are covered by the other tests in
    this module.
    """

    #: Relative tolerance for the trajectory comparison.
    #:
    #: The baseline is produced by the same code on the same fixture, so
    #: repeated runs in one process agree bitwise. Across platforms and SciPy
    #: micro-versions SLSQP can differ in the last bits, which is why this is
    #: not an exact comparison. 1e-6 is far tighter than the independent
    #: reference tests (5% percent-dried, 1% final time, 0.5 degC maximum
    #: temperature) while still leaving room for that noise: any real change of
    #: solver path or physics moves these values by orders of magnitude more.
    TRAJECTORY_RTOL = 1.0e-6

    #: Absolute floor, for the columns that legitimately start at exactly zero
    #: (time and percent dried), where a relative tolerance has no meaning.
    TRAJECTORY_ATOL = 1.0e-9

    def test_joint_trajectory_matches_committed_baseline(
        self, standard_opt_pch_tsh_inputs, reference_data_path
    ):
        """The solved trajectory must still match the recorded baseline."""
        baseline_path = reference_data_path / "regression_opt_Pch_Tsh.csv"
        assert baseline_path.exists(), (
            f"Regression baseline missing: {baseline_path}. It is tracked, so a "
            "missing file means the working tree is incomplete rather than that "
            "the check should be skipped."
        )
        baseline = np.loadtxt(baseline_path, delimiter=";", skiprows=1)

        output = opt_Pch_Tsh.dry(*standard_opt_pch_tsh_inputs)

        # A trajectory that needs a different number of steps has changed
        # behavior regardless of how close the individual values are.
        assert output.shape == baseline.shape, (
            f"Trajectory shape {output.shape} does not match baseline "
            f"{baseline.shape}; the solver took a different number of steps."
        )
        np.testing.assert_allclose(
            output,
            baseline,
            rtol=self.TRAJECTORY_RTOL,
            atol=self.TRAJECTORY_ATOL,
            err_msg=(
                "Joint-optimizer trajectory drifted from "
                "test_data/regression_opt_Pch_Tsh.csv. Check the installed "
                "SciPy against the version recorded in test_data/README.md "
                "first: the baseline pins SLSQP behavior and scipy is not "
                "upper-bounded, so a dependency upgrade moves these values "
                "without any change here. If the change is intended, "
                "regenerate the baseline and record the new generating commit "
                "and environment in test_data/README.md."
            ),
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


@pytest.mark.slow
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


@pytest.mark.slow
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
        with pytest.warns(Warning) as warning_record:
            output_pressure_only = opt_Pch.dry(
                vial, product, ht, Pchamber, Tshelf_fixed, dt, eq_cap, nVial
            )
        assert_warning_messages(warning_record, ["Optimization failed"])
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


def _joint_regression_setup(vial=None, ht=None):
    """Inputs for the bounded joint-optimizer regression scenario."""
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
        "Tshelf": {"min": -45.0, "max": -5.0},
        "dt": 0.01,
        "eq_cap": {"a": 5.0, "b": 10.0},
        "nVial": 398,
    }


def _joint_comparison_setup(vial=None, ht=None):
    """Inputs comparing the joint optimizer with pressure-only control."""
    setup = _joint_regression_setup(vial, ht)
    return {
        "vial": setup["vial"],
        "product": setup["product"],
        "ht": setup["ht"],
        "Pchamber_bounds": setup["Pchamber"],
        "Tshelf_both": setup["Tshelf"],
        "Tshelf_pch_only": {
            "init": -40.0,
            "setpt": [-25.0, -15.0],
            "dt_setpt": [120.0, 120.0],
            "ramp_rate": 1.0,
        },
        "dt": setup["dt"],
        "eq_cap": setup["eq_cap"],
        "nVial": setup["nVial"],
    }


def _conservative_joint_setup(vial=None, ht=None):
    """Inputs for the expensive conservative joint-optimizer scenarios."""
    setup = _joint_regression_setup(vial, ht)
    setup["product"]["T_pr_crit"] = -40.0
    setup["Pchamber"] = {"min": 0.040, "max": 0.100}
    setup["Tshelf"] = {"min": -50.0, "max": -20.0}
    # These scenarios assert coarse constraint behavior, so the established
    # 0.05 hr step preserves their paths without pathological runtime.
    setup["dt"] = 0.05
    return setup


def _dry_joint_setup(setup):
    return opt_Pch_Tsh.dry(
        setup["vial"],
        setup["product"],
        setup["ht"],
        setup["Pchamber"],
        setup["Tshelf"],
        setup["dt"],
        setup["eq_cap"],
        setup["nVial"],
    )


@pytest.fixture(scope="class")
def joint_regression_case():
    """Share the identical bounded joint run across its assertions."""
    setup = _joint_regression_setup()
    return {"setup": setup, "output": _dry_joint_setup(setup)}


@pytest.fixture(scope="class")
def alternative_joint_comparison_case():
    """Share the joint half of the alternative comparison scenario."""
    setup = _joint_comparison_setup()
    output = opt_Pch_Tsh.dry(
        setup["vial"],
        setup["product"],
        setup["ht"],
        setup["Pchamber_bounds"],
        setup["Tshelf_both"],
        setup["dt"],
        setup["eq_cap"],
        setup["nVial"],
    )
    return {"setup": setup, "output": output}


class TestOptPchTshBoundedRegression:
    """Properties of the distinct bounded joint-optimization scenario."""

    @pytest.mark.slow
    def test_joint_regression_properties(self, joint_regression_case):
        output = joint_regression_case["output"]
        setup = joint_regression_case["setup"]

        assert isinstance(output, np.ndarray)
        assert output.shape[0] > 0
        assert output.shape[1] == 7
        assert np.all(np.isfinite(output))

        bottom_temperature = output[:, 2]
        assert np.max(bottom_temperature - setup["product"]["T_pr_crit"]) <= 0.5

        pressure_torr = output[:, 4] / 1000
        assert np.all(pressure_torr >= setup["Pchamber"]["min"] * 0.95)
        assert np.all(pressure_torr <= setup["Pchamber"]["max"] * 1.05)

        shelf_temperature = output[:, 3]
        assert np.all(shelf_temperature >= setup["Tshelf"]["min"] - 1.0)
        assert np.all(shelf_temperature <= setup["Tshelf"]["max"] + 1.0)

        rate_per_vial = output[:, 5] * (setup["vial"]["Ap"] / 100**2)
        equipment_rate_per_vial = (
            setup["eq_cap"]["a"] + setup["eq_cap"]["b"] * pressure_torr
        ) / setup["nVial"]
        assert np.max(rate_per_vial - equipment_rate_per_vial) <= 0.01

        assert_physically_reasonable_output(output)
        assert output[-1, 6] >= 99.0
        assert 1.0 <= output[-1, 0] <= 50.0
        assert np.ptp(pressure_torr) > 0.001
        assert np.ptp(shelf_temperature) > 0.5


class TestOptPchTshAlternativeComparison:
    """Alternative bounded comparison retained as a separate scientific scenario."""

    @pytest.mark.slow
    def test_joint_and_pressure_only_progress(self, alternative_joint_comparison_case):
        setup = alternative_joint_comparison_case["setup"]
        output_joint = alternative_joint_comparison_case["output"]
        with pytest.warns(Warning) as warning_record:
            output_pressure = opt_Pch.dry(
                setup["vial"],
                setup["product"],
                setup["ht"],
                setup["Pchamber_bounds"],
                setup["Tshelf_pch_only"],
                setup["dt"],
                setup["eq_cap"],
                setup["nVial"],
            )
        assert_warning_messages(
            warning_record, ["Total time exceeded. Drying incomplete"]
        )
        assert output_joint is not None and output_joint.size > 0
        assert output_pressure is not None and output_pressure.size > 0
        assert output_joint[-1, 6] > 0.0
        assert output_pressure[-1, 6] > 0.0
        assert output_joint[-1, 0] < 30.0


class TestOptPchTshConservativeScenarios:
    """Expensive conservative scenarios retained from the old coverage suite."""

    @pytest.fixture
    def conservative_setup(self, standard_vial, standard_ht):
        return _conservative_joint_setup(standard_vial, standard_ht)

    @pytest.mark.slow
    def test_conservative_critical_temp(self, conservative_setup):
        output = _dry_joint_setup(conservative_setup)
        assert np.max(output[:, 2]) <= conservative_setup["product"]["T_pr_crit"] + 0.5

    @pytest.mark.slow
    def test_high_product_resistance(self, conservative_setup):
        conservative_setup["product"]["R0"] = 3.0
        conservative_setup["product"]["A1"] = 30.0
        output = _dry_joint_setup(conservative_setup)
        assert output.shape[0] > 0
        assert_physically_reasonable_output(output)

    @pytest.mark.slow
    def test_narrow_optimization_ranges(self, conservative_setup):
        conservative_setup["Pchamber"] = {"min": 0.070, "max": 0.090}
        conservative_setup["Tshelf"] = {"min": -35.0, "max": -25.0}
        output = _dry_joint_setup(conservative_setup)
        assert output[-1, 6] >= 95.0

    @pytest.mark.slow
    def test_tight_equipment_constraint(self, conservative_setup):
        conservative_setup["eq_cap"] = {"a": 2.0, "b": 5.0}
        output = _dry_joint_setup(conservative_setup)
        assert output[-1, 6] >= 95.0

    @pytest.mark.slow
    def test_concentrated_product(self, conservative_setup):
        conservative_setup["product"]["cSolid"] = 0.15
        output = _dry_joint_setup(conservative_setup)
        assert output.shape[0] > 0
        assert_physically_reasonable_output(output)
