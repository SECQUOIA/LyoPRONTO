"""Fitting residual and objective helpers for typed primary-drying solutions."""

from __future__ import annotations

import math
from typing import Any, cast

import numpy as np

from .typed import PrimaryDryFit, is_quantity, to_magnitude


def num_errs(fit: PrimaryDryFit) -> int:
    """Return the fixed residual-vector length for ``fit``."""

    tvw_len = 0
    if fit.Tvws is not None:
        tvw_len = 1 if fit.Tvw_iend is None else int(sum(fit.Tvw_iend))
    return int(sum(fit.Tf_iend) + tvw_len + (0 if fit.t_end is None else 1))


def err_expT(
    solution: Any,
    fit: PrimaryDryFit,
    *,
    tweight: float = 1.0,
    verbose: bool = False,
) -> np.ndarray:
    """Return temperature and end-time residuals for SciPy least-squares.

    Product-temperature and vial-wall time series are compared after
    interpolating model states onto measured times. Each individual time series
    is divided by the square root of its compared point count, matching Julia's
    equal-series weighting. Invalid or incomplete solutions return a
    ``num_errs(fit)`` vector filled with ``NaN``.

    Interpolation uses ``numpy.interp`` over the time points saved on the
    solution. For the closest comparison to measured data, solve or save the
    model at the measured fit times, for example with ``save_at=fit.t``.
    Measurements at the first saved model time are included; measurements at or
    after the terminal model time are omitted because the terminal time is
    represented by the separate end-time residual.
    """

    del verbose
    if not _valid_solution(solution, fit):
        return np.full(num_errs(fit), np.nan)

    residuals: list[np.ndarray] = []
    times = fit.t_hr
    t_model = _solution_times(solution)

    tf_model = _interp_state(solution, 1, times)
    for series, iend in zip(fit.Tfs_K, fit.Tf_iend):
        residuals.append(
            _series_residuals(
                series,
                int(iend),
                times,
                t_model,
                tf_model,
            )
        )

    if fit.Tvws is not None:
        tvw_values = fit.Tvws_K
        if fit.Tvw_iend is None:
            tvw_endpoint = float(cast(float, tvw_values))
            residuals.append(np.asarray([_state_value(solution, 2, -1) - tvw_endpoint]))
        else:
            tvw_model = _interp_state(solution, 2, times)
            tvw_series = cast(tuple[np.ndarray, ...], tvw_values)
            for series, iend in zip(tvw_series, fit.Tvw_iend):
                residuals.append(
                    _series_residuals(
                        series,
                        int(iend),
                        times,
                        t_model,
                        tvw_model,
                    )
                )

    if fit.t_end is not None:
        residuals.append(np.asarray([_time_error(solution, fit.t_end) * tweight]))

    if not residuals:
        return np.asarray([], dtype=float)
    return np.concatenate(residuals).astype(float)


def obj_expT(
    solution: Any,
    fit: PrimaryDryFit,
    *,
    tweight: float = 1.0,
    tvw_weight: float = 1.0,
    verbose: bool = False,
) -> float:
    """Return the scalar temperature/end-time objective for ``solution``."""

    del verbose
    if not _valid_solution(solution, fit):
        return np.nan

    residuals = err_expT(solution, fit, tweight=1.0)
    if np.any(~np.isfinite(residuals)):
        return np.nan

    n_tf = int(sum(fit.Tf_iend))
    n_tvw = _num_tvw_errs(fit)
    value = float(np.sum(residuals[:n_tf] ** 2))
    if n_tvw:
        value += float(tvw_weight) * float(np.sum(residuals[n_tf : n_tf + n_tvw] ** 2))
    if fit.t_end is not None:
        value += float(tweight) * float(residuals[-1] ** 2)
    return value


def _num_tvw_errs(fit: PrimaryDryFit) -> int:
    if fit.Tvws is None:
        return 0
    if fit.Tvw_iend is None:
        return 1
    return int(sum(fit.Tvw_iend))


def _series_residuals(
    series: np.ndarray,
    iend: int,
    fit_times: np.ndarray,
    model_times: np.ndarray,
    model_values: np.ndarray,
) -> np.ndarray:
    errs = np.zeros(iend, dtype=float)
    ndata = min(iend, len(series), len(fit_times))
    if ndata == 0:
        return errs

    usable = _usable_fit_positions(fit_times[:ndata], model_times)
    if usable.size == 0:
        return errs

    compared = series[usable] - model_values[usable]
    errs[usable] = compared / math.sqrt(float(usable.size))
    return errs


def _usable_fit_positions(fit_times: np.ndarray, model_times: np.ndarray) -> np.ndarray:
    start = float(model_times[0])
    end = float(model_times[-1])
    tol = 1e-12
    mask = (fit_times >= start - tol) & (fit_times < end - tol)
    return np.flatnonzero(mask)


def _interp_state(solution: Any, index: int, times: np.ndarray) -> np.ndarray:
    return np.interp(times, _solution_times(solution), _state_array(solution, index))


def _solution_times(solution: Any) -> np.ndarray:
    return np.asarray(solution.t, dtype=float)


def _state_array(solution: Any, index: int) -> np.ndarray:
    y = np.asarray(solution.y, dtype=float)
    return y[index]


def _state_value(solution: Any, row: int, column: int) -> float:
    return float(np.asarray(solution.y, dtype=float)[row, column])


def _time_error(solution: Any, t_end: Any) -> float:
    t_model = float(_solution_times(solution)[-1])
    if isinstance(t_end, tuple):
        lower = _to_hours(t_end[0])
        upper = _to_hours(t_end[1])
        if lower <= t_model <= upper:
            return 0.0
        return (lower + upper) / 2.0 - t_model
    return _to_hours(t_end) - t_model


def _to_hours(value: Any) -> float:
    return to_magnitude(value, "hour") if is_quantity(value) else float(value)


def _valid_solution(solution: Any, fit: PrimaryDryFit) -> bool:
    if solution is None:
        return False
    try:
        if np.isscalar(solution) and np.isnan(solution):
            return False
    except TypeError:
        pass

    if hasattr(solution, "success") and not bool(solution.success):
        return False
    if hasattr(solution, "terminated") and not bool(solution.terminated):
        return False
    if not hasattr(solution, "t") or not hasattr(solution, "y"):
        return False

    try:
        t = _solution_times(solution)
        y = np.asarray(solution.y, dtype=float)
    except (TypeError, ValueError):
        return False
    if t.size <= 1 or y.ndim != 2 or y.shape[1] != t.size:
        return False
    if y.shape[0] <= 1:
        return False
    if fit.Tvws is not None and y.shape[0] <= 2:
        return False
    if not np.all(np.isfinite(t)) or not np.all(np.isfinite(y)):
        return False

    if hasattr(solution, "hf"):
        try:
            final_hf = solution.hf[-1]
            final_hf_cm = (
                to_magnitude(final_hf, "centimeter")
                if is_quantity(final_hf)
                else float(final_hf)
            )
        except (TypeError, ValueError):
            return False
        if final_hf_cm > 1e-8:
            return False

    return True


__all__ = [
    "num_errs",
    "err_expT",
    "obj_expT",
]
