"""Tests for opt_Pch.py to increase coverage from 14% to 80%+."""

import pytest
import numpy as np
from lyopronto import opt_Pch
from .utils import assert_physically_reasonable_output, assert_warning_messages


def _standard_vial():
    return {"Av": 3.80, "Ap": 3.14, "Vfill": 2.0}


def _standard_ht():
    return {"KC": 2.75e-4, "KP": 8.93e-4, "KD": 0.46}


def _opt_pch_setup(vial=None, ht=None):
    product = {"cSolid": 0.05, "R0": 1.4, "A1": 16.0, "A2": 0.0, "T_pr_crit": -30.0}

    return {
        "vial": vial or _standard_vial(),
        "product": product,
        "ht": ht or _standard_ht(),
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
        "Tshelf": {
            "init": -45.0,
            "setpt": [-35.0],
            "dt_setpt": [120.0],
            "ramp_rate": 1.0,
        },
        "dt": 0.01,
        "eq_cap": {"a": 5.0, "b": 10.0},
        "nVial": 398,
    }


def _dry_opt_pch(setup, *, allowed_warnings=None):
    """Run pressure-only optimization and assert expected edge-case warnings."""
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


class TestOptPchOnly:
    """Test pressure-only optimizer (fixed shelf temperature)."""

    @pytest.fixture(scope="class")
    def opt_pch_case(self):
        """Shared result for identical pressure-only optimization checks."""
        setup = _opt_pch_setup()
        return {"setup": setup, "output": _dry_opt_pch(setup)}

    def test_opt_pch_regression_properties(self, opt_pch_case):
        """Test the shared pressure-only optimizer result preserves properties."""
        output = opt_pch_case["output"]
        setup = opt_pch_case["setup"]

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

        # Drying progress checks
        final_percent = output[-1, 6]
        # Optimizer should show progress, but may not reach full completion
        assert (
            final_percent > 0.0
        ), f"Should show drying progress, got {final_percent:.1f}%"
        assert (
            final_percent <= 100.0
        ), f"Percent dried should not exceed 100%, got {final_percent:.1f}%"

        # Convergence checks
        total_time = output[-1, 0]
        assert (
            1.0 <= total_time <= 50.0
        ), f"Drying time {total_time:.1f} hr seems unreasonable"

        # Pressure optimization checks
        P_range = np.max(Pch) - np.min(Pch)
        assert P_range > 0.001, "Pressure should vary during optimization"


class TestOptPchEdgeCases:
    """Test edge cases for Pch-only optimizer."""

    @pytest.fixture
    def conservative_setup(self, standard_vial, standard_ht):
        """Setup with very conservative critical temperature."""
        return _conservative_setup(standard_vial, standard_ht)

    def test_conservative_critical_temp(self, conservative_setup):
        """Test with very conservative critical temperature."""
        output = _dry_opt_pch(conservative_setup)

        Tbot = output[:, 2]
        T_crit = conservative_setup["product"]["T_pr_crit"]

        # Should respect conservative constraint
        assert np.max(Tbot) <= T_crit + 0.5

    def test_high_product_resistance(self, conservative_setup):
        """Test with high product resistance."""
        conservative_setup["product"]["R0"] = 3.0
        conservative_setup["product"]["A1"] = 30.0

        output = _dry_opt_pch(conservative_setup)

        assert output.shape[0] > 0
        assert_physically_reasonable_output(output)

    def test_narrow_pressure_range(self, conservative_setup):
        """Test with narrow pressure optimization range."""
        conservative_setup["Pchamber"]["min"] = 0.070
        conservative_setup["Pchamber"]["max"] = 0.090

        output = _dry_opt_pch(
            conservative_setup,
            allowed_warnings=[
                "Optimization failed",
                "Total time exceeded. Drying incomplete",
            ],
        )

        Pch = output[:, 4] / 1000
        assert np.all((Pch >= 0.065) & (Pch <= 0.095))

    def test_tight_equipment_constraint(self, conservative_setup):
        """Test with tight equipment capability constraint.

        Note: Tight constraints significantly limit optimization and may prevent
        high completion rates. Test validates optimizer handles constraints gracefully.
        """
        # Reduce equipment capability
        conservative_setup["eq_cap"]["a"] = 2.0
        conservative_setup["eq_cap"]["b"] = 5.0

        output = _dry_opt_pch(conservative_setup)

        # Should run without errors and show some progress despite tight constraint
        assert output is not None
        assert output.size > 0
        final_percent = output[-1, 6]
        assert final_percent >= 0.0, "Should have non-negative drying progress"
        assert final_percent <= 100.0, "Percent should not exceed 100%"
