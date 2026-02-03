"""Helper functions for test validation."""
import numpy as np

# Import tolerance constants from single source of truth
from tests.utils import (
    FLOAT_RTOL,
    INITIAL_PERCENT_ATOL,
    MONOTONIC_ATOL,
    PERCENT_ATOL,
    PERCENT_COMPLETE,
    PERCENT_MAX,
    PRESSURE_ATOL,
    PYOMO_PERCENT_COMPLETE,
    PYOMO_SOLVER_TOL,
    TEMP_ATOL,
    TEMP_RTOL,
)


def assert_physically_reasonable_output(output):
    """Assert that simulation output has physically reasonable values.
    
    Args:
        output: Numpy array with shape (n_steps, 7) containing simulation results
                Columns: time, Tsub, Tbot, Tsh, Pch, flux, percent_dried (0-100%)
    """
    # Column 0: Time should be non-negative and increasing
    assert np.all(output[:, 0] >= 0), "Time should be non-negative"
    # Allow last time value to be repeated (simulation completion/timeout)
    time_diffs = np.diff(output[:, 0])
    assert np.all(time_diffs[:-1] > 0), "Time should be strictly increasing (except possibly last step)"
    assert time_diffs[-1] >= 0, "Last time step should be non-negative"
    
    # Column 1: Tsub should be below freezing
    assert np.all(output[:, 1] < 0), "Sublimation temperature should be < 0°C"
    assert np.all(output[:, 1] > -80), "Tsub should be > -80°C (reasonable range)"
    
    # Column 2: Tbot should be reasonable
    assert np.all(output[:, 2] > -80), "Tbot should be > -80°C"
    assert np.all(output[:, 2] < 60), "Tbot should be < 60°C"
    
    # Column 3: Tsh (shelf temperature) should be reasonable
    assert np.all(output[:, 3] > -80), "Tsh should be > -80°C"
    assert np.all(output[:, 3] < 60), "Tsh should be < 60°C"
    
    # Column 4: Pch should be positive (in mTorr)
    assert np.all(output[:, 4] > 0), "Chamber pressure should be positive"
    assert np.all(output[:, 4] < 1000), "Pch should be < 1000 mTorr (1.3 Torr)"
    
    # Column 5: Flux should be non-negative
    assert np.all(output[:, 5] >= 0), "Sublimation flux should be non-negative"
    
    # Column 6: Percent dried should be between 0 and 100 (allow tiny float precision)
    assert np.all(output[:, 6] >= 0), "Percent dried should be >= 0"
    assert np.all(output[:, 6] <= PERCENT_MAX + FLOAT_RTOL), \
        f"Percent dried should not exceed {PERCENT_MAX}%, got {output[:, 6].max():.10f}%"
    
    # Percent dried should be monotonically increasing
    assert np.all(np.diff(output[:, 6]) >= -MONOTONIC_ATOL), \
        "Percent dried should increase over time (allowing small numerical errors)"
