"""Tests for fitting-data residual and objective helpers."""

from dataclasses import dataclass

import numpy as np
import pytest

from lyopronto import PrimaryDryFit, Q_, err_expT, num_errs, obj_expT


@dataclass(frozen=True)
class SyntheticSolution:
    t: np.ndarray
    y: np.ndarray
    success: bool = True
    terminated: bool = True


def _synthetic_solution():
    return SyntheticSolution(
        t=np.asarray([0.0, 1.0, 2.0, 3.0]),
        y=np.asarray(
            [
                [1.0, 0.6, 0.2, 0.0],
                [220.0, 221.0, 222.0, 223.0],
                [230.0, 231.0, 232.0, 233.0],
            ]
        ),
    )


def test_exp_temperature_residuals_interpolate_and_keep_fixed_length():
    sol = _synthetic_solution()
    fit = PrimaryDryFit(
        Q_([0.0, 0.5, 1.0, 2.0, 3.0, 4.0], "hour"),
        Q_([221.0, 219.5, 223.0, 220.0, 999.0, 999.0], "kelvin"),
    )

    errs = err_expT(sol, fit)

    assert num_errs(fit) == 6
    np.testing.assert_allclose(errs, [0.5, -0.5, 1.0, -1.0, 0.0, 0.0])
    assert obj_expT(sol, fit) == pytest.approx(2.5)


def test_exp_temperature_residuals_count_multiple_series_and_vial_wall_data():
    sol = _synthetic_solution()
    times = Q_([0.0, 1.0, 2.0, 3.0], "hour")
    tf_a = Q_([220.0, 222.0, 220.0, 999.0], "kelvin")
    tf_b = Q_([221.0, 219.0, 999.0, 999.0], "kelvin")
    tvw = Q_([231.0, 229.0, 232.0, 999.0], "kelvin")
    fit = PrimaryDryFit(
        times,
        (tf_a, tf_b),
        Tf_iend=[4, 2],
        Tvws=tvw,
        Tvw_iend=[3],
        t_end=(Q_(2.5, "hour"), Q_(3.5, "hour")),
    )

    errs = err_expT(sol, fit)

    assert num_errs(fit) == 10
    np.testing.assert_allclose(
        errs,
        [
            0.0,
            1 / np.sqrt(3),
            -2 / np.sqrt(3),
            0.0,
            1 / np.sqrt(2),
            -2 / np.sqrt(2),
            1 / np.sqrt(3),
            -2 / np.sqrt(3),
            0.0,
            0.0,
        ],
    )


def test_exp_temperature_objective_weights_tvw_and_end_time_like_julia_scalar():
    sol = _synthetic_solution()
    fit = PrimaryDryFit(
        Q_([0.0, 1.0, 2.0], "hour"),
        Q_([220.0, 221.0, 222.0], "kelvin"),
        Tvws=Q_(235.0, "kelvin"),
        t_end=Q_(5.0, "hour"),
    )

    errs = err_expT(sol, fit, tweight=3.0)

    np.testing.assert_allclose(errs, [0.0, 0.0, 0.0, -2.0, 6.0])
    assert obj_expT(sol, fit, tweight=3.0, tvw_weight=2.0) == pytest.approx(
        2.0 * 4.0 + 3.0 * 4.0
    )


def test_exp_temperature_helpers_return_nan_for_failed_or_incomplete_solutions():
    fit = PrimaryDryFit(
        Q_([0.0, 1.0, 2.0], "hour"),
        Q_([220.0, 221.0, 222.0], "kelvin"),
        t_end=Q_(3.0, "hour"),
    )
    failed = SyntheticSolution(
        t=np.asarray([0.0, 1.0]),
        y=np.asarray([[1.0, 0.5], [220.0, 221.0]]),
        success=False,
    )
    incomplete = SyntheticSolution(
        t=np.asarray([0.0, 1.0]),
        y=np.asarray([[1.0, 0.5], [220.0, 221.0]]),
        terminated=False,
    )

    assert np.all(np.isnan(err_expT(failed, fit)))
    assert np.all(np.isnan(err_expT(incomplete, fit)))
    assert len(err_expT(failed, fit)) == num_errs(fit)
    assert np.isnan(obj_expT(failed, fit))
    assert np.isnan(obj_expT(incomplete, fit))
