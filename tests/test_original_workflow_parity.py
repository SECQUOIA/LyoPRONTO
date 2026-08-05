"""Tests for canonical computations shared by the original workflow tutorials."""

from __future__ import annotations

import csv

import numpy as np
import pytest

from examples import original_workflow_parity
from examples.example_parameter_estimation import save_results
from examples.original_workflow_parity import (
    ResistanceFit,
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


def test_known_rp_scipy_uses_an_edited_caller_case() -> None:
    """Reader edits to the web-style input dictionaries drive the simulation."""
    default_case = known_rp_case()
    edited_case = known_rp_case()
    edited_case[1]["R0"] = 5.0  # [cm^2 hr Torr/g]

    default_output = run_known_rp_scipy(dt=0.01, case=default_case)
    edited_output = run_known_rp_scipy(dt=0.01, case=edited_case)

    assert default_output[-1, 0] == pytest.approx(6.65)  # [hr]
    assert edited_output[-1, 0] == pytest.approx(7.22)  # [hr]


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
    assert fit.parameter_stderr is not None
    np.testing.assert_allclose(
        fit.parameter_stderr,
        [0.04157828, 0.47963972, 0.14421647],
        rtol=0.0,
        atol=1.0e-6,
    )


def test_unknown_rp_scipy_fit_rejects_non_finite_covariance(monkeypatch) -> None:
    """An unidentifiable SciPy fit is diagnostics, not clean scientific output."""

    def non_identifiable_fit(*args, **kwargs):
        del args, kwargs
        return np.array([1.0, 8.0, 0.5]), np.full((3, 3), np.inf)

    monkeypatch.setattr(original_workflow_parity, "curve_fit", non_identifiable_fit)
    product_resistance = np.array(
        [
            [0.0, 0.0, 1.0],
            [1.0, 0.5, 2.0],
        ]
    )
    fit = fit_unknown_rp_scipy(product_resistance)

    assert not fit.success
    assert fit.termination_condition == "non_finite_covariance"
    assert fit.parameter_stderr is None
    assert fit.R0 is fit.A1 is fit.A2 is fit.objective is None
    with pytest.raises(RuntimeError, match="not identifiable"):
        fit.as_array()


def test_parameter_estimation_csv_keeps_uncertainty_schema(tmp_path) -> None:
    """Maintained CSV output retains fit uncertainty and correct dried units."""
    fit = ResistanceFit(
        success=True,
        solver_status="success",
        termination_condition="curve_fit converged",
        message="SciPy curve_fit converged.",
        R0=1.0,
        A1=8.0,
        A2=0.5,
        objective=0.25,
        parameter_stderr=(0.1, 0.2, 0.3),
    )
    output = np.zeros((1, 7))

    csv_path = save_results(output, fit, output_dir=tmp_path)
    with csv_path.open(newline="") as stream:
        rows = list(csv.reader(stream))

    assert rows[0] == ["LyoPRONTO Parameter Estimation Results"]
    assert rows[1][0].startswith("Generated: ")
    assert ["Standard Errors"] in rows
    assert ["sigma(R0) [cm^2 hr Torr/g]", "0.1"] in rows
    assert rows[-2][-1] == "Percent Dried [0-100]"


def test_case_factories_return_independent_dictionaries() -> None:
    """Tutorial mutation cannot leak into a later case construction."""
    first = known_rp_case()
    second = known_rp_case()

    first[0]["Av"] = 99.0
    assert second[0]["Av"] == pytest.approx(3.80)
