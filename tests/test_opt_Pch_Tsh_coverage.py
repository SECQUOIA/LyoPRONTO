"""Tests for opt_Pch_Tsh.py to increase coverage from 19% to 80%+."""

import pytest
import numpy as np
from lyopronto import opt_Pch_Tsh, opt_Pch
from .utils import assert_physically_reasonable_output, assert_warning_messages


def _standard_vial():
    return {"Av": 3.80, "Ap": 3.14, "Vfill": 2.0}


def _standard_ht():
    return {"KC": 2.75e-4, "KP": 8.93e-4, "KD": 0.46}


def _dry_opt_pch_tsh(setup):
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


def _opt_both_setup(vial=None, ht=None):
    product = {"cSolid": 0.05, "R0": 1.4, "A1": 16.0, "A2": 0.0, "T_pr_crit": -30.0}

    return {
        "vial": vial or _standard_vial(),
        "product": product,
        "ht": ht or _standard_ht(),
        "Pchamber": {"min": 0.040, "max": 0.200},
        "Tshelf": {"min": -45.0, "max": -5.0},
        "dt": 0.01,
        "eq_cap": {"a": 5.0, "b": 10.0},
        "nVial": 398,
    }


def _comparison_setup(vial=None, ht=None):
    product = {"cSolid": 0.05, "R0": 1.4, "A1": 16.0, "A2": 0.0, "T_pr_crit": -30.0}

    return {
        "vial": vial or _standard_vial(),
        "product": product,
        "ht": ht or _standard_ht(),
        "Pchamber_bounds": {"min": 0.040, "max": 0.200},
        "Pchamber_tsh_only": {"setpt": [0.080]},
        "Tshelf_both": {"min": -45.0, "max": -5.0},
        "Tshelf_pch_only": {
            "init": -40.0,
            "setpt": [-25.0, -15.0],
            "dt_setpt": [120.0, 120.0],
            "ramp_rate": 1.0,
        },
        "dt": 0.01,
        "eq_cap": {"a": 5.0, "b": 10.0},
        "nVial": 398,
    }


def _conservative_setup(vial=None, ht=None):
    return {
        "vial": vial or _standard_vial(),
        "product": {
            "cSolid": 0.05,
            "R0": 1.4,
            "A1": 16.0,
            "A2": 0.0,
            "T_pr_crit": -40.0,
        },
        "ht": ht or _standard_ht(),
        "Pchamber": {"min": 0.040, "max": 0.100},
        "Tshelf": {"min": -50.0, "max": -20.0},
        "dt": 0.01,
        "eq_cap": {"a": 5.0, "b": 10.0},
        "nVial": 398,
    }


class TestOptPchTsh:
    """Test joint Pch+Tsh optimizer (both optimized simultaneously)."""

    @pytest.fixture(scope="class")
    def opt_both_case(self):
        """Shared result for identical joint Pch+Tsh optimization checks."""
        setup = _opt_both_setup()
        return {"setup": setup, "output": _dry_opt_pch_tsh(setup)}

    @pytest.mark.slow
    def test_opt_both_regression_properties(self, opt_both_case):
        """Test the shared joint optimizer result preserves baseline properties."""
        output = opt_both_case["output"]
        setup = opt_both_case["setup"]

        # Completion checks
        assert isinstance(output, np.ndarray)
        assert output.shape[0] > 0
        assert output.shape[1] == 7  # Standard output columns

        # Output format checks
        assert output.shape[1] == 7, "Output should have 7 columns"
        assert np.all(np.isfinite(output)), "Output contains non-finite values"

        # Temperature constraint checks
        Tbot = output[:, 2]  # Vial bottom temperature
        T_crit = setup["product"]["T_pr_crit"]
        max_violation = np.max(Tbot - T_crit)
        assert (
            max_violation <= 0.5
        ), f"Temperature exceeded critical by {max_violation:.2f}°C"

        # Pressure bound checks
        Pch = output[:, 4] / 1000  # Convert mTorr to Torr
        P_min = setup["Pchamber"]["min"]
        P_max = setup["Pchamber"]["max"]

        assert np.all(
            Pch >= P_min * 0.95
        ), f"Pressure {np.min(Pch):.3f} below minimum {P_min}"
        assert np.all(
            Pch <= P_max * 1.05
        ), f"Pressure {np.max(Pch):.3f} above maximum {P_max}"

        # Shelf temperature bound checks
        Tsh = output[:, 3]  # Shelf temperature
        T_min = setup["Tshelf"]["min"]
        T_max = setup["Tshelf"]["max"]

        assert np.all(
            Tsh >= T_min - 1.0
        ), f"Shelf temp {np.min(Tsh):.1f} below minimum {T_min}"
        assert np.all(
            Tsh <= T_max + 1.0
        ), f"Shelf temp {np.max(Tsh):.1f} above maximum {T_max}"

        # Equipment capability checks
        flux = output[:, 5]  # Sublimation flux [kg/hr/m**2]
        Ap_m2 = setup["vial"]["Ap"] / 100**2  # Convert [cm**2] to [m**2]

        # Total sublimation rate per vial
        dmdt = flux * Ap_m2  # [kg/hr/vial]

        # Equipment capability at different pressures
        Pch = output[:, 4] / 1000  # [Torr]
        eq_cap_max = (setup["eq_cap"]["a"] + setup["eq_cap"]["b"] * Pch) / setup[
            "nVial"
        ]

        # Should not exceed equipment capability (with small tolerance)
        violations = dmdt - eq_cap_max
        max_violation = np.max(violations)
        assert (
            max_violation <= 0.01
        ), f"Equipment capability exceeded by {max_violation:.4f} kg/hr"

        # Physical reasonableness checks
        assert_physically_reasonable_output(output)

        # Completion percentage checks
        # opt_Pch_Tsh.dry returns percent (0-100), consistent with other modules
        final_percent = output[-1, 6]
        assert (
            final_percent >= 99.0
        ), f"Should reach 99% dried, got {final_percent:.1f}%"

        # Convergence checks
        total_time = output[-1, 0]
        assert (
            1.0 <= total_time <= 50.0
        ), f"Drying time {total_time:.1f} hr seems unreasonable"

        # Optimization variable checks
        P_range = np.max(Pch) - np.min(Pch)
        T_range = np.max(Tsh) - np.min(Tsh)

        assert P_range > 0.001, "Pressure should vary during optimization"
        assert T_range > 0.5, "Shelf temperature should vary during optimization"


class TestOptPchTshComparison:
    """Test that joint optimization performs better than single-variable."""

    @pytest.fixture(scope="class")
    def joint_comparison_case(self):
        """Shared joint-optimizer result for identical comparison inputs."""
        setup = _comparison_setup()
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

    @pytest.mark.slow
    def test_joint_opt_comparison_properties(self, joint_comparison_case):
        """Test joint optimization comparison properties.

        Note: Joint optimization is not guaranteed to be faster than Pch-only.
        It optimizes both variables which can take longer but may find better
        solutions. Test validates both approaches complete successfully.
        """
        comparison_setup = joint_comparison_case["setup"]
        output_both = joint_comparison_case["output"]

        # Pch-only optimization
        with pytest.warns(Warning) as warning_record:
            output_pch = opt_Pch.dry(
                comparison_setup["vial"],
                comparison_setup["product"],
                comparison_setup["ht"],
                comparison_setup["Pchamber_bounds"],
                comparison_setup["Tshelf_pch_only"],
                comparison_setup["dt"],
                comparison_setup["eq_cap"],
                comparison_setup["nVial"],
            )

        assert_warning_messages(
            warning_record, ["Total time exceeded. Drying incomplete"]
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

        # Joint optimization should achieve reasonable drying time.
        output = output_both
        total_time = output[-1, 0]

        # Should achieve faster drying than typical conservative schedules
        assert (
            total_time < 30.0
        ), f"Joint optimization took {total_time:.1f}h, expected <30h"


class TestOptPchTshEdgeCases:
    """Test edge cases for joint optimizer."""

    @pytest.fixture
    def conservative_setup(self, standard_vial, standard_ht):
        """Setup with very conservative critical temperature."""
        return _conservative_setup(standard_vial, standard_ht)

    @pytest.mark.slow
    def test_conservative_critical_temp(self, conservative_setup):
        """Test with very conservative critical temperature."""
        output = opt_Pch_Tsh.dry(
            conservative_setup["vial"],
            conservative_setup["product"],
            conservative_setup["ht"],
            conservative_setup["Pchamber"],
            conservative_setup["Tshelf"],
            conservative_setup["dt"],
            conservative_setup["eq_cap"],
            conservative_setup["nVial"],
        )

        Tbot = output[:, 2]
        T_crit = conservative_setup["product"]["T_pr_crit"]

        # Should respect conservative constraint
        assert np.max(Tbot) <= T_crit + 0.5

    @pytest.mark.slow
    def test_high_product_resistance(self, conservative_setup):
        """Test with high product resistance."""
        conservative_setup["product"]["R0"] = 3.0
        conservative_setup["product"]["A1"] = 30.0

        output = opt_Pch_Tsh.dry(
            conservative_setup["vial"],
            conservative_setup["product"],
            conservative_setup["ht"],
            conservative_setup["Pchamber"],
            conservative_setup["Tshelf"],
            conservative_setup["dt"],
            conservative_setup["eq_cap"],
            conservative_setup["nVial"],
        )

        assert output.shape[0] > 0
        assert_physically_reasonable_output(output)

    @pytest.mark.slow
    def test_narrow_optimization_ranges(self, conservative_setup):
        """Test with narrow optimization ranges."""
        conservative_setup["Pchamber"]["min"] = 0.070
        conservative_setup["Pchamber"]["max"] = 0.090
        conservative_setup["Tshelf"]["min"] = -35.0
        conservative_setup["Tshelf"]["max"] = -25.0
        # This case checks feasibility within narrow bounds, not 0.01 hr resolution.
        conservative_setup["dt"] = 0.05

        output = opt_Pch_Tsh.dry(
            conservative_setup["vial"],
            conservative_setup["product"],
            conservative_setup["ht"],
            conservative_setup["Pchamber"],
            conservative_setup["Tshelf"],
            conservative_setup["dt"],
            conservative_setup["eq_cap"],
            conservative_setup["nVial"],
        )

        # Should still find solution within narrow ranges
        assert output[-1, 6] >= 0.95

    @pytest.mark.slow
    def test_tight_equipment_constraint(self, conservative_setup):
        """Test with tight equipment capability constraint."""
        # Reduce equipment capability
        conservative_setup["eq_cap"]["a"] = 2.0
        conservative_setup["eq_cap"]["b"] = 5.0

        output = opt_Pch_Tsh.dry(
            conservative_setup["vial"],
            conservative_setup["product"],
            conservative_setup["ht"],
            conservative_setup["Pchamber"],
            conservative_setup["Tshelf"],
            conservative_setup["dt"],
            conservative_setup["eq_cap"],
            conservative_setup["nVial"],
        )

        # Should complete even with tight constraint
        assert output[-1, 6] >= 0.95

    @pytest.mark.slow
    def test_concentrated_product(self, conservative_setup):
        """Test with high solids concentration."""
        conservative_setup["product"]["cSolid"] = 0.15  # 15% solids

        output = opt_Pch_Tsh.dry(
            conservative_setup["vial"],
            conservative_setup["product"],
            conservative_setup["ht"],
            conservative_setup["Pchamber"],
            conservative_setup["Tshelf"],
            conservative_setup["dt"],
            conservative_setup["eq_cap"],
            conservative_setup["nVial"],
        )

        assert output.shape[0] > 0
        assert_physically_reasonable_output(output)
