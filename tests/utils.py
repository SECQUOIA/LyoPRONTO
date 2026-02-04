"""Helper functions for test validation."""

import numpy as np


# =============================================================================
# Test Tolerance Constants
# =============================================================================
# These tolerances are used consistently across all tests to ensure disciplined
# assertions while accounting for numerical precision.

# Machine precision tolerance for floating point comparisons
FLOAT_RTOL = 1e-10

# General relative tolerance for proportional comparisons (times, temperatures, percentages)
# Accounts for numerical differences in sequential optimization paths
RTOL = 0.001  # 0.1% relative tolerance

# Tolerance for checking monotonicity (allows small numerical wobbles from integration)
MONOTONIC_ATOL = 1e-6

# Tolerance for numerical precision in temperature comparisons
TEMP_RTOL = 0.01  # °C - for tight numerical precision checks

# Tolerance for temperature constraint checks (numerical optimization tolerance)
TEMP_ATOL = 0.5  # °C - for looser optimization tolerance

# Tolerance for initial percent values (should be near zero)
INITIAL_PERCENT_ATOL = 1.0  # percent

# Tolerance for percent dried comparisons (allows small interpolation/numerical error)
PERCENT_ATOL = 0.5  # percent - for looser percentage checks

# Tolerance for pressure comparisons in mTorr
PRESSURE_ATOL = 1.0  # mTorr

# Percent dried threshold for considering drying "complete" (scipy)
PERCENT_COMPLETE = 99.0

# Pyomo solver tolerance (relative to PERCENT_COMPLETE)
PYOMO_SOLVER_TOL = 0.01  # Pyomo may return 98.999... instead of 99.0

# Percent dried threshold for Pyomo solver
PYOMO_PERCENT_COMPLETE = PERCENT_COMPLETE - PYOMO_SOLVER_TOL

# Maximum percent dried value (should never exceed 100% except for float precision)
PERCENT_MAX = 100.0


def assert_physically_reasonable_output(output, Tmax=60):
    """
    Assert that simulation output is physically reasonable.

    Args:
        output: numpy array with columns [time, Tsub, Tbot, Tsh, Pch_mTorr, flux, percent_dried]

    Column descriptions:
        [0] time [hr]
        [1] Tsub - sublimation temperature [degC]
        [2] Tbot - vial bottom temperature [degC]
        [3] Tsh - shelf temperature [degC]
        [4] Pch - chamber pressure [mTorr]
        [5] flux - sublimation flux [kg/hr/m**2]
        [6] percent_dried - percent dried (0-100%)
    """
    assert output.shape[1] == 7, "Output should have 7 columns"

    # Check output columns exist and are numeric
    assert np.all(np.isfinite(output[:, 0])), "Time column has invalid values"
    assert np.all(np.isfinite(output[:, 1])), "Tsub column has invalid values"
    assert np.all(np.isfinite(output[:, 2])), "Tbot column has invalid values"
    assert np.all(np.isfinite(output[:, 3])), "Tsh column has invalid values"
    assert np.all(np.isfinite(output[:, 4])), "Pch column has invalid values"
    assert np.all(np.isfinite(output[:, 5])), "flux column has invalid values"
    assert np.all(np.isfinite(output[:, 6])), "percent_dried column has invalid values"

    # Time should be non-negative and monotonically increasing
    assert np.all(output[:, 0] >= 0), "Time should be non-negative"
    assert np.all(np.diff(output[:, 0]) >= 0), "Time should be monotonically increasing"

    # Total time should be reasonable
    assert 0.1 < output[-1, 0] < 200, "Total drying time seems unreasonable"

    # Sublimation temperature should be below freezing
    assert np.all(output[:, 1] < 0), "Sublimation temperature should be below 0°C"
    assert np.all(output[:, 1] > -80), "Tsub should be > -80°C (reasonable range)"

    # Sublimation flux should be non-negative
    assert np.all(output[:, 5] >= 0), "Sublimation flux should be non-negative"

    # Sublimation temperature should be below shelf temperature
    assert np.all(output[:, 3] >= output[:, 1]), (
        "Sublimation temp should be <= shelf temp"
    )

    # Bottom temperature should be >= sublimation temperature
    assert np.all(output[:, 2] >= output[:, 1]), (
        "Bottom temp should be >= sublimation temp"
    )

    # Shelf temperature should be reasonable
    assert np.all(output[:, 3] >= -80) and np.all(output[:, 3] <= Tmax), (
        f"Shelf temperature should be between -80 and {Tmax}°C"
    )

    # Chamber pressure should be positive (in mTorr, so typically 50-500)
    assert np.all(output[:, 4] > 0), "Chamber pressure should be positive"
    assert np.all(output[:, 4] < 2000), (
        "Chamber pressure unreasonably high (check units)"
    )

    # Percent dried should be between 0 and 100 (allow tiny floating point tolerance)
    assert np.all(output[:, 6] >= 0) and np.all(output[:, 6] <= PERCENT_MAX + FLOAT_RTOL), (
        f"Percent dried should be between 0 and {PERCENT_MAX}, got max={output[:, 6].max():.10f}"
    )

    # Percent dried should be monotonically increasing
    assert np.all(np.diff(output[:, 6]) >= -MONOTONIC_ATOL), (
        "Percent dried should be monotonically increasing (allowing small numerical errors)"
    )


def assert_complete_drying(output):
    """
    Assert that drying completed for given simulation output.

    Args:
        output: numpy array with columns [time, Tsub, Tbot, Tsh, Pch_mTorr, flux, percent_dried]
    """
    final_percent_dried = output[-1, 6]
    assert final_percent_dried >= PERCENT_COMPLETE, (
        f"Drying did not complete, reached only {final_percent_dried:.1f}%"
    )


def assert_incomplete_drying(output):
    """
    Assert that drying did not complete for given simulation output.

    Args:
        output: numpy array with columns [time, Tsub, Tbot, Tsh, Pch_mTorr, flux, percent_dried]
    """
    final_percent_dried = output[-1, 6]
    assert final_percent_dried < PERCENT_COMPLETE, (
        f"Drying unexpectedly completed, reached {final_percent_dried:.1f}%"
    )
