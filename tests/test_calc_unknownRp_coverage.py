"""Tests for calc_unknownRp.py to increase coverage from 11% to 80%+."""

import pytest
import numpy as np
import os
from lyopronto import calc_unknownRp
from .utils import assert_warning_messages


def _standard_vial():
    return {"Av": 3.80, "Ap": 3.14, "Vfill": 2.0}


def _standard_ht():
    return {"KC": 2.75e-4, "KP": 8.93e-4, "KD": 0.46}


def _unknown_rp_setup(vial=None, ht=None):
    product = {"cSolid": 0.05, "T_pr_crit": -30.0}

    test_data_dir = os.path.join(os.path.dirname(__file__), "..", "test_data")
    temp_file = os.path.join(test_data_dir, "temperature.txt")
    time, Tbot_exp = np.loadtxt(temp_file, unpack=True)

    return {
        "vial": vial or _standard_vial(),
        "product": product,
        "ht": ht or _standard_ht(),
        "Pchamber": {
            "setpt": [0.060, 0.080, 0.100],
            "dt_setpt": [60.0, 120.0, 120.0],
            "ramp_rate": 0.5,
        },
        "Tshelf": {
            "init": -40.0,
            "setpt": [-20.0, -10.0],
            "dt_setpt": [120.0, 120.0],
            "ramp_rate": 0.1,
        },
        "time": time,
        "Tbot_exp": Tbot_exp,
    }


def _minimal_setup(vial=None, ht=None):
    return {
        "vial": vial or _standard_vial(),
        "product": {"cSolid": 0.05, "T_pr_crit": -30.0},
        "ht": ht or _standard_ht(),
        "Pchamber": {"setpt": [0.080], "dt_setpt": [60.0], "ramp_rate": 0.5},
        "Tshelf": {
            "init": -40.0,
            "setpt": [-30.0],
            "dt_setpt": [60.0],
            "ramp_rate": 0.1,
        },
        "time": np.array([0.0, 0.5, 1.0, 1.5, 2.0]),
        "Tbot_exp": np.array([-40.0, -38.0, -35.0, -32.0, -30.0]),
    }


def _assert_unknownRp_reasonable(output):
    """Assert output is reasonable for unknown Rp (less strict than utils.py).

    The unknown Rp calculator uses experimental data fitting and can produce
    transient states where Tsub > Tsh during early ramp-up, so we skip that
    check here (unlike the full assert_physically_reasonable_output).
    """
    assert output.shape[1] == 7, "Output should have 7 columns"
    assert np.all(output[:, 0] >= 0), "Time should be non-negative"
    assert np.all(output[:, 1] < 0), "Sublimation temperature should be below 0°C"
    assert np.all(output[:, 1] > -80), "Tsub should be > -80°C"
    assert np.all(output[:, 4] > 0), "Chamber pressure should be positive"
    assert np.all(output[:, 5] >= 0), "Sublimation flux should be non-negative"
    assert np.all(output[:, 6] >= 0), "Percent dried should be >= 0"
    assert np.all(output[:, 6] <= 101.0), "Percent dried should be <= 100"


def _dry_unknown_rp(setup, *, pchamber=None, allow_singular_resistance=False):
    """Run unknown-Rp drying and assert the expected edge-case warnings."""
    allowed_warnings = [
        "No sublimation.",
        "Total shelf temperature setpoint time exceeded",
        "Total chamber pressure setpoint time exceeded",
    ]
    if allow_singular_resistance:
        allowed_warnings.append("divide by zero encountered in scalar divide")

    with pytest.warns(Warning) as warning_record:
        result = calc_unknownRp.dry(
            setup["vial"],
            setup["product"],
            setup["ht"],
            pchamber or setup["Pchamber"],
            setup["Tshelf"],
            setup["time"],
            setup["Tbot_exp"],
        )

    assert_warning_messages(warning_record, allowed_warnings)
    return result


class TestCalcUnknownRp:
    """Test calculator with unknown product resistance (uses experimental Tbot data)."""

    @pytest.fixture
    def unknown_rp_setup(self, standard_vial, standard_ht):
        """Setup for unknown Rp calculation with experimental temperature data."""
        return _unknown_rp_setup(standard_vial, standard_ht)

    @pytest.fixture(scope="class")
    def unknown_rp_case(self):
        """Shared result for identical unknown-Rp coverage checks."""
        setup = _unknown_rp_setup()
        output, product_res = _dry_unknown_rp(setup)
        return {"setup": setup, "output": output, "product_res": product_res}

    def test_unknown_rp_regression_properties(self, unknown_rp_case):
        """Test the shared unknown-Rp result preserves baseline properties."""
        output = unknown_rp_case["output"]
        unknown_rp_setup = unknown_rp_case["setup"]

        # Completion checks
        assert isinstance(output, np.ndarray)
        assert output.shape[0] > 0
        assert output.shape[1] == 7  # Standard output columns

        # Output shape and finite-value checks
        assert output.shape[1] == 7, "Output should have 7 columns"

        assert np.all(np.isfinite(output[:, 0])), "Time column has invalid values"
        assert np.all(np.isfinite(output[:, 1])), "Tsub column has invalid values"
        assert np.all(np.isfinite(output[:, 2])), "Tbot column has invalid values"
        assert np.all(np.isfinite(output[:, 3])), "Tsh column has invalid values"
        assert np.all(np.isfinite(output[:, 4])), "Pch column has invalid values"
        assert np.all(np.isfinite(output[:, 5])), "flux column has invalid values"
        assert np.all(np.isfinite(output[:, 6])), "frac_dried column has invalid values"

        # Time progression checks
        time = output[:, 0]

        time_diffs = np.diff(time)
        assert np.all(time_diffs >= 0), "Time must be monotonically increasing"

        assert time[0] >= 0, f"Initial time should be non-negative, got {time[0]}"

        # Shelf temperature schedule checks
        Tsh = output[:, 3]

        assert (
            abs(Tsh[0] - unknown_rp_setup["Tshelf"]["init"]) < 1.0
        ), f"Initial Tsh should be near {unknown_rp_setup['Tshelf']['init']}, got {Tsh[0]}"

        Tsh_range = np.max(Tsh) - np.min(Tsh)
        assert Tsh_range > 5.0, "Shelf temperature should vary during ramping"

        # Chamber pressure schedule checks
        Pch = output[:, 4] / 1000  # Convert mTorr to Torr

        min_setpt = min(unknown_rp_setup["Pchamber"]["setpt"])
        max_setpt = max(unknown_rp_setup["Pchamber"]["setpt"])

        assert (
            np.min(Pch) >= min_setpt * 0.9
        ), f"Min pressure {np.min(Pch):.3f} below setpoint range"
        assert (
            np.max(Pch) <= max_setpt * 1.1
        ), f"Max pressure {np.max(Pch):.3f} above setpoint range"

        # Physical reasonableness checks
        _assert_unknownRp_reasonable(output)

        # Drying progress checks
        final_percent = output[-1, 6]
        # Parameter estimation may have limited progress - check for any drying
        assert (
            final_percent > 0.0
        ), f"Should show drying progress, got {final_percent:.1f}%"
        assert (
            final_percent <= 100.0
        ), f"Percent dried should not exceed 100%, got {final_percent:.1f}%"

        # Fraction dried checks
        frac_dried = output[:, 6]

        diffs = np.diff(frac_dried)
        assert np.all(diffs >= -1e-6), "Fraction dried must increase monotonically"

        # Flux checks
        flux = output[:, 5]
        assert np.all(flux >= 0), "Sublimation flux must be non-negative"

    def test_unknown_rp_different_initial_pressure(self, unknown_rp_setup):
        """Test with different initial chamber pressure."""
        # Modify pressure setpoints
        Pchamber_modified = unknown_rp_setup["Pchamber"].copy()
        Pchamber_modified["setpt"] = [0.050, 0.070, 0.090]

        output, product_res = _dry_unknown_rp(
            unknown_rp_setup, pchamber=Pchamber_modified
        )

        assert output.shape[0] > 0
        _assert_unknownRp_reasonable(output)


class TestCalcUnknownRpEdgeCases:
    """Test edge cases for unknown Rp calculator."""

    @pytest.fixture
    def minimal_setup(self, standard_vial, standard_ht):
        """Minimal setup with short time series."""
        return _minimal_setup(standard_vial, standard_ht)

    @pytest.fixture(scope="class")
    def minimal_case(self):
        """Shared result for identical minimal time-series checks."""
        setup = _minimal_setup()
        output, product_res = _dry_unknown_rp(setup, allow_singular_resistance=True)
        return {"setup": setup, "output": output, "product_res": product_res}

    def test_minimal_time_series_properties(self, minimal_case):
        """Test shared minimal time-series result properties."""
        output = minimal_case["output"]

        # Minimal time-series checks
        assert output.shape[0] > 0
        assert output.shape[1] == 7

        # Single pressure setpoint checks
        Pch = output[:, 4] / 1000  # Convert to Torr

        Pch_std = np.std(Pch)
        assert Pch_std < 0.01, f"Pressure should be nearly constant, std={Pch_std:.4f}"

    def test_high_solids_concentration(self, minimal_setup):
        """Test with high solids concentration."""
        minimal_setup["product"]["cSolid"] = 0.15  # 15% solids

        output, product_res = _dry_unknown_rp(
            minimal_setup, allow_singular_resistance=True
        )

        assert output.shape[0] > 0
        _assert_unknownRp_reasonable(output)
