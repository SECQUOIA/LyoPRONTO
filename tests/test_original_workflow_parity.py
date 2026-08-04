"""Tests for canonical computations shared by the original workflow tutorials."""

from __future__ import annotations

import numpy as np
import pytest

from examples.original_workflow_parity import (
    TEMPERATURE_DATA,
    fit_unknown_rp_scipy,
    known_rp_case,
    load_temperature_data,
    preprocess_unknown_rp,
    run_known_rp_scipy,
)


def test_known_rp_scipy_result_keeps_legacy_output_contract() -> None:
    """The canonical example preserves seven columns and legacy output units."""
    output = run_known_rp_scipy()

    assert output.shape == (27, 7)
    assert output[0, 0] == pytest.approx(0.0)  # time [hr]
    assert output[-1, 0] == pytest.approx(6.5)  # time [hr]
    np.testing.assert_allclose(output[:, 4], 150.0)  # chamber pressure [mTorr]
    assert np.all((output[:, 6] >= 0.0) & (output[:, 6] <= 100.0))
    assert output[-1, 6] == pytest.approx(97.75344125, abs=1.0e-6)


def test_temperature_data_has_one_canonical_two_column_contract() -> None:
    """The measured input is loaded from its documented external-fixture owner."""
    time_hr, tbot_degc = load_temperature_data()

    assert TEMPERATURE_DATA.name == "temperature.txt"
    assert len(time_hr) == len(tbot_degc) == 452
    assert time_hr[0] == pytest.approx(0.0)
    assert time_hr[-1] == pytest.approx(4.509673182)
    assert np.all(np.diff(time_hr) > 0.0)


def test_unknown_rp_scipy_fit_uses_shared_legacy_preprocessing() -> None:
    """The canonical hybrid workflow reproduces the original SciPy fit."""
    output, product_resistance = preprocess_unknown_rp()
    fit = fit_unknown_rp_scipy(product_resistance)

    assert fit.success, fit.message
    assert output.shape == (453, 7)
    assert product_resistance.shape == (453, 3)
    np.testing.assert_allclose(
        fit.as_array(),
        [0.0208928040371, 7.8433178163, 0.508139910271],
        rtol=0.0,
        atol=1.0e-6,
    )
    assert fit.objective == pytest.approx(58.1005977409558, abs=1.0e-6)


def test_case_factories_return_independent_dictionaries() -> None:
    """Tutorial mutation cannot leak into a later case construction."""
    first = known_rp_case()
    second = known_rp_case()

    first[0]["Av"] = 99.0
    assert second[0]["Av"] == pytest.approx(3.80)
