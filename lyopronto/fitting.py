"""Fitting helpers for typed primary-drying solutions."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
import math
from typing import Any, cast

import numpy as np
from scipy.optimize import least_squares, minimize

from .pikal import PikalParams, solve_pikal
from .rf import RFParams, solve_rf
from .typed import ConstPhysProp, PrimaryDryFit, RpFormFit, is_quantity, to_magnitude

_FITTING_FAILURES = (ArithmeticError, RuntimeError, ValueError, OverflowError)


@dataclass(frozen=True)
class RpTransform:
    """Log-space positive transform for ``RpFormFit`` coefficients."""

    R0: Any
    A1: Any | None = None
    A2: Any | None = None

    def __post_init__(self) -> None:
        if isinstance(self.R0, RpFormFit) and self.A1 is None and self.A2 is None:
            object.__setattr__(self, "A1", self.R0.A1)
            object.__setattr__(self, "A2", self.R0.A2)
            object.__setattr__(self, "R0", self.R0.R0)
        if self.A1 is None or self.A2 is None:
            raise ValueError("RpTransform requires R0, A1, and A2 guesses")

    @property
    def dimension(self) -> int:
        """Number of unconstrained parameters consumed by this transform."""

        return 3

    def transform(self, theta: Any) -> dict[str, Any]:
        """Return fitted parameter updates for unconstrained ``theta``."""

        values = _theta_array(theta, self.dimension)
        assert self.A1 is not None
        assert self.A2 is not None
        return {
            "Rp": RpFormFit(
                self.R0 * math.exp(float(values[0])),
                self.A1 * math.exp(float(values[1])),
                self.A2 * math.exp(float(values[2])),
            )
        }

    __call__ = transform


@dataclass(frozen=True)
class KTransform:
    """Log-space positive transform for constant heat-transfer coefficient."""

    Kshf: Any

    @property
    def dimension(self) -> int:
        """Number of unconstrained parameters consumed by this transform."""

        return 1

    def transform(self, theta: Any) -> dict[str, Any]:
        """Return fitted parameter updates for unconstrained ``theta``."""

        values = _theta_array(theta, self.dimension)
        return {"Kshf": ConstPhysProp(_const_value(self.Kshf) * math.exp(values[0]))}

    __call__ = transform


@dataclass(frozen=True)
class KBBTransform:
    """Log-space positive transform for RF ``Kvwf``, ``Bf``, and ``Bvw``."""

    Kvwf: Any
    Bf: Any | None = None
    Bvw: Any | None = None

    def __post_init__(self) -> None:
        if isinstance(self.Kvwf, RFParams) and self.Bf is None and self.Bvw is None:
            object.__setattr__(self, "Bf", self.Kvwf.Bf)
            object.__setattr__(self, "Bvw", self.Kvwf.Bvw)
            object.__setattr__(self, "Kvwf", self.Kvwf.Kvwf)
        if self.Bf is None or self.Bvw is None:
            raise ValueError("KBBTransform requires Kvwf, Bf, and Bvw guesses")

    @property
    def dimension(self) -> int:
        """Number of unconstrained parameters consumed by this transform."""

        return 3

    def transform(self, theta: Any) -> dict[str, Any]:
        """Return RF fitted parameter updates for unconstrained ``theta``."""

        values = _theta_array(theta, self.dimension)
        assert self.Bf is not None
        assert self.Bvw is not None
        return {
            "Kvwf": self.Kvwf * math.exp(float(values[0])),
            "Bf": self.Bf * math.exp(float(values[1])),
            "Bvw": self.Bvw * math.exp(float(values[2])),
        }

    __call__ = transform


@dataclass(frozen=True)
class BoundedKBBTransform:
    """Julia-style bounded logistic transform for RF ``Kvwf``, ``Bf``, ``Bvw``.

    The transform maps zero-valued unconstrained parameters back to the supplied
    guesses and asymptotically caps each value at ``guess * scale_factor``.
    """

    Kvwf: Any
    Bf: Any | None = None
    Bvw: Any | None = None
    Kvwf_scalefac: float = 1e2
    Bf_scalefac: float = 1e4
    Bvw_scalefac: float = 1e4

    def __post_init__(self) -> None:
        if isinstance(self.Kvwf, RFParams) and self.Bf is None and self.Bvw is None:
            object.__setattr__(self, "Bf", self.Kvwf.Bf)
            object.__setattr__(self, "Bvw", self.Kvwf.Bvw)
            object.__setattr__(self, "Kvwf", self.Kvwf.Kvwf)
        if self.Bf is None or self.Bvw is None:
            raise ValueError(
                "BoundedKBBTransform requires Kvwf, Bf, and Bvw guesses"
            )
        _validate_scale_factor(self.Kvwf_scalefac, "Kvwf_scalefac")
        _validate_scale_factor(self.Bf_scalefac, "Bf_scalefac")
        _validate_scale_factor(self.Bvw_scalefac, "Bvw_scalefac")

    @property
    def dimension(self) -> int:
        """Number of unconstrained parameters consumed by this transform."""

        return 3

    def transform(self, theta: Any) -> dict[str, Any]:
        """Return bounded RF fitted parameter updates for ``theta``."""

        values = _theta_array(theta, self.dimension)
        return {
            "Kvwf": _bounded_kbb_value(
                self.Kvwf, float(values[0]), self.Kvwf_scalefac
            ),
            "Bf": _bounded_kbb_value(self.Bf, float(values[1]), self.Bf_scalefac),
            "Bvw": _bounded_kbb_value(self.Bvw, float(values[2]), self.Bvw_scalefac),
        }

    __call__ = transform


@dataclass(frozen=True)
class KRpTransform:
    """Log-space positive transform for constant ``Kshf`` and ``RpFormFit``."""

    Kshf: Any
    R0: Any
    A1: Any
    A2: Any

    @property
    def dimension(self) -> int:
        """Number of unconstrained parameters consumed by this transform."""

        return 4

    def transform(self, theta: Any) -> dict[str, Any]:
        """Return fitted parameter updates for unconstrained ``theta``."""

        values = _theta_array(theta, self.dimension)
        updates = KTransform(self.Kshf).transform(values[:1])
        updates.update(RpTransform(self.R0, self.A1, self.A2).transform(values[1:]))
        return updates

    __call__ = transform


@dataclass(frozen=True)
class SharedSeparateTransform:
    """Compose shared and per-experiment parameter transforms."""

    shared: Any
    separate: Any
    n_separate: int
    sep_inds: tuple[int, ...] | None = None

    def __post_init__(self) -> None:
        if int(self.n_separate) <= 0:
            raise ValueError("n_separate must be positive")
        if self.sep_inds is not None:
            object.__setattr__(self, "sep_inds", tuple(int(i) for i in self.sep_inds))

    @property
    def dimension(self) -> int:
        """Number of unconstrained parameters consumed by this transform."""

        return _transform_dimension(
            self.shared
        ) + self.n_separate * _transform_dimension(self.separate)

    def transform(self, theta: Any) -> "SharedSeparateUpdates":
        """Return grouped updates for multi-experiment fitting."""

        values = _theta_array(theta, self.dimension)
        cursor = 0
        shared_dim = _transform_dimension(self.shared)
        shared_updates = _call_transform_dict(
            self.shared, values[cursor : cursor + shared_dim]
        )
        cursor += shared_dim

        separate_dim = _transform_dimension(self.separate)
        separate_updates: list[dict[str, Any]] = []
        for _ in range(self.n_separate):
            separate_updates.append(
                _call_transform_dict(
                    self.separate, values[cursor : cursor + separate_dim]
                )
            )
            cursor += separate_dim

        return SharedSeparateUpdates(
            shared=shared_updates,
            separate=tuple(separate_updates),
            sep_inds=self.sep_inds,
        )

    __call__ = transform


@dataclass(frozen=True)
class SharedSeparateUpdates:
    """Fitted updates split into shared and per-experiment groups."""

    shared: dict[str, Any]
    separate: tuple[dict[str, Any], ...]
    sep_inds: tuple[int, ...] | None = None


def gen_sol_pd(
    theta: Any,
    transform: Any,
    params: Any,
    fitdat: PrimaryDryFit | None = None,
    *,
    badprms: Any = None,
    save_at: Any = None,
    **solve_options: Any,
) -> Any:
    """Generate a typed primary-drying solution for fitted Pikal or RF params."""

    try:
        updates = _call_transform_dict(transform, theta)
        fitted_params = _replace_params(params, updates)
        if badprms is not None and badprms(fitted_params):
            return np.nan
        if fitdat is not None:
            save_at = fitdat.t_hr
        return _solve_primary_drying(
            fitted_params, save_at=save_at, **solve_options
        )
    except _FITTING_FAILURES:
        return np.nan


def gen_nsol_pd(
    theta: Any,
    transform: Any,
    params: Any | Sequence[Any],
    fitdats: Sequence[PrimaryDryFit] | None = None,
    *,
    badprms: Any = None,
    save_ats: Sequence[Any] | None = None,
    **solve_options: Any,
) -> list[Any]:
    """Generate typed Pikal or RF solutions for several drying experiments."""

    pos, save_values = _normalize_multi_inputs(params, fitdats, save_ats)
    try:
        updates = _call_transform(transform, theta)
        update_groups = _multi_update_groups(updates, len(pos))
        fitted_params = [
            _replace_params(param, update) for param, update in zip(pos, update_groups)
        ]
        if badprms is not None and any(badprms(param) for param in fitted_params):
            return [np.nan for _ in pos]
    except _FITTING_FAILURES:
        return [np.nan for _ in pos]

    sols = []
    for param, save_at in zip(fitted_params, save_values):
        try:
            sols.append(
                _solve_primary_drying(param, save_at=save_at, **solve_options)
            )
        except _FITTING_FAILURES:
            sols.append(np.nan)
    return sols


def err_pd(
    theta: Any,
    transform: Any,
    params: Any,
    fitdat: PrimaryDryFit,
    *,
    tweight: float = 1.0,
    badprms: Any = None,
    verbose: bool = False,
    **solve_options: Any,
) -> np.ndarray:
    """Return residuals for one fitted primary-drying experiment."""

    sol = gen_sol_pd(
        theta,
        transform,
        params,
        fitdat,
        badprms=badprms,
        **solve_options,
    )
    return err_expT(sol, fitdat, tweight=tweight, verbose=verbose)


def errn_pd(
    theta: Any,
    transform: Any,
    params: Any | Sequence[Any],
    fitdats: Sequence[PrimaryDryFit],
    *,
    tweight: float = 1.0,
    badprms: Any = None,
    verbose: bool = False,
    **solve_options: Any,
) -> np.ndarray:
    """Return concatenated residuals for several fitted experiments."""

    sols = gen_nsol_pd(
        theta,
        transform,
        params,
        fitdats,
        badprms=badprms,
        **solve_options,
    )
    residuals = [
        err_expT(sol, fitdat, tweight=tweight, verbose=verbose)
        for sol, fitdat in zip(sols, fitdats)
    ]
    return np.concatenate(residuals) if residuals else np.asarray([], dtype=float)


def obj_pd(
    theta: Any,
    transform: Any,
    params: Any,
    fitdat: PrimaryDryFit,
    *,
    tweight: float = 1.0,
    tvw_weight: float = 1.0,
    badprms: Any = None,
    verbose: bool = False,
    **solve_options: Any,
) -> float:
    """Return scalar objective for one fitted primary-drying experiment."""

    sol = gen_sol_pd(
        theta,
        transform,
        params,
        fitdat,
        badprms=badprms,
        **solve_options,
    )
    return obj_expT(
        sol,
        fitdat,
        tweight=tweight,
        tvw_weight=tvw_weight,
        verbose=verbose,
    )


def objn_pd(
    theta: Any,
    transform: Any,
    params: Any | Sequence[Any],
    fitdats: Sequence[PrimaryDryFit],
    *,
    tweight: float = 1.0,
    tvw_weight: float = 1.0,
    badprms: Any = None,
    verbose: bool = False,
    **solve_options: Any,
) -> float:
    """Return summed scalar objective for several fitted experiments."""

    sols = gen_nsol_pd(
        theta,
        transform,
        params,
        fitdats,
        badprms=badprms,
        **solve_options,
    )
    value = 0.0
    for sol, fitdat in zip(sols, fitdats):
        obj = obj_expT(
            sol,
            fitdat,
            tweight=tweight,
            tvw_weight=tvw_weight,
            verbose=verbose,
        )
        if not np.isfinite(obj):
            return np.nan
        value += float(obj)
    return value


def gen_sol_rf(
    theta: Any,
    transform: Any,
    params: RFParams,
    fitdat: PrimaryDryFit | None = None,
    *,
    badprms: Any = None,
    save_at: Any = None,
    **solve_options: Any,
) -> Any:
    """Generate a typed RF primary-drying solution for fitted params."""

    return gen_sol_pd(
        theta,
        transform,
        params,
        fitdat,
        badprms=badprms,
        save_at=save_at,
        **solve_options,
    )


def err_rf(
    theta: Any,
    transform: Any,
    params: RFParams,
    fitdat: PrimaryDryFit,
    *,
    tweight: float = 1.0,
    badprms: Any = None,
    verbose: bool = False,
    **solve_options: Any,
) -> np.ndarray:
    """Return residuals for one fitted RF primary-drying experiment."""

    return err_pd(
        theta,
        transform,
        params,
        fitdat,
        tweight=tweight,
        badprms=badprms,
        verbose=verbose,
        **solve_options,
    )


def obj_rf(
    theta: Any,
    transform: Any,
    params: RFParams,
    fitdat: PrimaryDryFit,
    *,
    tweight: float = 1.0,
    tvw_weight: float = 1.0,
    badprms: Any = None,
    verbose: bool = False,
    **solve_options: Any,
) -> float:
    """Return scalar objective for one fitted RF primary-drying experiment."""

    return obj_pd(
        theta,
        transform,
        params,
        fitdat,
        tweight=tweight,
        tvw_weight=tvw_weight,
        badprms=badprms,
        verbose=verbose,
        **solve_options,
    )


def fit_primary_drying(
    params: Any | Sequence[Any],
    fitdat: PrimaryDryFit | Sequence[PrimaryDryFit],
    transform: Any,
    theta0: Any | None = None,
    *,
    method: str = "least_squares",
    tweight: float = 1.0,
    tvw_weight: float = 1.0,
    badprms: Any = None,
    nan_penalty: float = 1e12,
    optimizer_method: str | None = None,
    **optimizer_options: Any,
) -> Any:
    """Fit primary-drying parameters with SciPy optimizers.

    Notes
    -----
    ``method="least_squares"`` applies ``tweight`` to the end-time residual,
    so the end-time contribution is squared after residual scaling. The
    ``method="minimize"`` path uses ``obj_expT``, which applies ``tweight``
    directly to the squared end-time error. This matches the Julia residual
    and scalar-objective split and only differs when ``tweight != 1``.
    When provided, ``optimizer_method`` is forwarded to the selected SciPy
    optimizer as its ``method`` argument.
    """

    theta_start = _initial_theta(transform, theta0)
    multi = _is_multi_fit(fitdat)

    if method == "least_squares":
        if multi:

            def residual_fun(theta: Any) -> np.ndarray:
                return errn_pd(
                    theta,
                    transform,
                    params,
                    cast(Sequence[PrimaryDryFit], fitdat),
                    tweight=tweight,
                    badprms=badprms,
                )

        else:

            def residual_fun(theta: Any) -> np.ndarray:
                return err_pd(
                    theta,
                    transform,
                    cast(PikalParams, params),
                    cast(PrimaryDryFit, fitdat),
                    tweight=tweight,
                    badprms=badprms,
                )

        if optimizer_method is not None:
            optimizer_options = dict(optimizer_options)
            optimizer_options["method"] = optimizer_method

        raw = least_squares(
            lambda theta: _finite_or_penalty(residual_fun(theta), nan_penalty),
            theta_start,
            **optimizer_options,
        )
    elif method == "minimize":
        if multi:

            def obj_fun(theta: Any) -> float:
                return objn_pd(
                    theta,
                    transform,
                    params,
                    cast(Sequence[PrimaryDryFit], fitdat),
                    tweight=tweight,
                    tvw_weight=tvw_weight,
                    badprms=badprms,
                )

        else:

            def obj_fun(theta: Any) -> float:
                return obj_pd(
                    theta,
                    transform,
                    cast(PikalParams, params),
                    cast(PrimaryDryFit, fitdat),
                    tweight=tweight,
                    tvw_weight=tvw_weight,
                    badprms=badprms,
                )

        raw = minimize(
            lambda theta: _finite_scalar_or_penalty(obj_fun(theta), nan_penalty),
            theta_start,
            method=optimizer_method,
            **optimizer_options,
        )
    else:
        raise ValueError('method must be "least_squares" or "minimize"')

    _attach_fit_result(
        raw,
        params,
        fitdat,
        transform,
        method,
        tweight,
        tvw_weight,
        badprms,
    )
    return raw


def fit_rf_primary_drying(
    params: RFParams,
    fitdat: PrimaryDryFit,
    transform: Any,
    theta0: Any | None = None,
    *,
    method: str = "least_squares",
    tweight: float = 1.0,
    tvw_weight: float = 1.0,
    badprms: Any = None,
    nan_penalty: float = 1e12,
    optimizer_method: str | None = None,
    **optimizer_options: Any,
) -> Any:
    """Fit one RF experiment's wall/product coupling and absorption parameters.

    Use :func:`fit_primary_drying` directly for multi-experiment RF fitting.
    """

    return fit_primary_drying(
        params,
        fitdat,
        transform,
        theta0,
        method=method,
        tweight=tweight,
        tvw_weight=tvw_weight,
        badprms=badprms,
        nan_penalty=nan_penalty,
        optimizer_method=optimizer_method,
        **optimizer_options,
    )


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


def _theta_array(theta: Any, dimension: int) -> np.ndarray:
    values = np.asarray(theta, dtype=float).reshape(-1)
    if values.size != dimension:
        raise ValueError(f"expected {dimension} fitting parameters, got {values.size}")
    return values


def _const_value(value: Any) -> Any:
    if isinstance(value, ConstPhysProp):
        return value.value
    return value


def _validate_scale_factor(value: Any, name: str) -> None:
    scale = float(value)
    if not math.isfinite(scale) or scale <= 1.0:
        raise ValueError(f"{name} must be greater than 1")


def _logit(value: float) -> float:
    return math.log(value / (1.0 - value))


def _logistic(value: float) -> float:
    if value >= 0.0:
        return 1.0 / (1.0 + math.exp(-value))
    exp_value = math.exp(value)
    return exp_value / (1.0 + exp_value)


def _bounded_kbb_value(guess: Any, theta: float, scale_factor: float) -> Any:
    scale = float(scale_factor)
    shifted = theta + _logit(1.0 / scale)
    return guess * scale * _logistic(shifted)


def _transform_dimension(transform: Any) -> int:
    if transform is None:
        return 0
    if hasattr(transform, "dimension"):
        return int(transform.dimension)
    raise TypeError("transform must expose a dimension property")


def _call_transform(
    transform: Any, theta: Any
) -> dict[str, Any] | SharedSeparateUpdates:
    if transform is None:
        _theta_array(theta, 0)
        return {}
    if hasattr(transform, "transform"):
        updates = transform.transform(theta)
    elif callable(transform):
        updates = transform(theta)
    else:
        raise TypeError("transform must be callable or expose transform()")

    if isinstance(updates, SharedSeparateUpdates):
        return updates
    if isinstance(updates, dict):
        return dict(updates)
    raise TypeError("transforms must return parameter-update dicts")


def _call_transform_dict(transform: Any, theta: Any) -> dict[str, Any]:
    updates = _call_transform(transform, theta)
    if isinstance(updates, SharedSeparateUpdates):
        raise TypeError("transform must return a parameter-update dict")
    return updates


def _replace_params(params: Any, updates: dict[str, Any]) -> Any:
    if not hasattr(params, "__dataclass_fields__"):
        raise TypeError("params must be a dataclass parameter object")
    allowed = set(params.__dataclass_fields__)
    unknown = set(updates) - allowed
    if unknown:
        names = ", ".join(sorted(unknown))
        raise ValueError(f"unknown {type(params).__name__} update field(s): {names}")
    return replace(params, **updates)


def _solve_primary_drying(params: Any, *, save_at: Any = None, **solve_options: Any) -> Any:
    if isinstance(params, RFParams):
        return solve_rf(params, save_at=save_at, **solve_options)
    if isinstance(params, PikalParams):
        return solve_pikal(params, save_at=save_at, **solve_options)
    raise TypeError("params must be PikalParams or RFParams")


def _normalize_multi_inputs(
    params: Any | Sequence[Any],
    fitdats: Sequence[PrimaryDryFit] | None,
    save_ats: Sequence[Any] | None,
) -> tuple[list[Any], list[Any]]:
    fit_list = list(fitdats) if fitdats is not None else None
    save_list = list(save_ats) if save_ats is not None else None

    if isinstance(params, (PikalParams, RFParams)):
        if fit_list is not None:
            n_exp = len(fit_list)
        elif save_list is not None:
            n_exp = len(save_list)
        else:
            n_exp = 1
        pos = [params for _ in range(n_exp)]
    else:
        pos = list(params)

    if not pos:
        raise ValueError("at least one parameter object is required")

    save_values: list[Any]
    if fit_list is not None:
        if len(fit_list) != len(pos):
            raise ValueError("fitdats length must match the number of experiments")
        save_values = [fitdat.t_hr for fitdat in fit_list]
    elif save_list is not None:
        if len(save_list) != len(pos):
            raise ValueError("save_ats length must match the number of experiments")
        save_values = save_list
    else:
        save_values = [None for _ in pos]
    return pos, save_values


def _multi_update_groups(
    updates: dict[str, Any] | SharedSeparateUpdates,
    n_experiments: int,
) -> list[dict[str, Any]]:
    if isinstance(updates, SharedSeparateUpdates):
        if updates.sep_inds is None:
            sep_inds = tuple(range(len(updates.separate)))
        else:
            sep_inds = updates.sep_inds
        if len(sep_inds) != n_experiments:
            raise ValueError("sep_inds length must match the number of experiments")

        groups = []
        for index in sep_inds:
            if index < 0 or index >= len(updates.separate):
                raise ValueError("sep_inds contains an out-of-range group index")
            group = dict(updates.separate[index])
            group.update(updates.shared)
            groups.append(group)
        return groups

    return [dict(updates) for _ in range(n_experiments)]


def _initial_theta(transform: Any, theta0: Any | None) -> np.ndarray:
    dimension = _transform_dimension(transform)
    if theta0 is None:
        return np.zeros(dimension, dtype=float)
    return _theta_array(theta0, dimension)


def _is_multi_fit(fitdat: Any) -> bool:
    return isinstance(fitdat, Sequence) and not isinstance(fitdat, PrimaryDryFit)


def _finite_or_penalty(values: Any, penalty: float) -> np.ndarray:
    arr = np.asarray(values, dtype=float).reshape(-1)
    if np.any(~np.isfinite(arr)):
        return np.full(arr.shape, float(penalty), dtype=float)
    return arr


def _finite_scalar_or_penalty(value: Any, penalty: float) -> float:
    scalar = float(value)
    if not math.isfinite(scalar):
        return float(penalty)
    return scalar


def _attach_fit_result(
    result: Any,
    params: Any | Sequence[Any],
    fitdat: PrimaryDryFit | Sequence[PrimaryDryFit],
    transform: Any,
    method: str,
    tweight: float,
    tvw_weight: float,
    badprms: Any,
) -> None:
    result.fit_method = method
    result.transform = transform
    result.tweight = tweight
    result.tvw_weight = tvw_weight

    if _is_multi_fit(fitdat):
        fitdats = cast(Sequence[PrimaryDryFit], fitdat)
        pos, _save_values = _normalize_multi_inputs(params, fitdats, None)
        updates = _call_transform(transform, result.x)
        update_groups = _multi_update_groups(updates, len(pos))
        result.fitted_params = tuple(
            _replace_params(param, update) for param, update in zip(pos, update_groups)
        )
        result.solution = tuple(
            gen_nsol_pd(
                result.x,
                transform,
                params,
                fitdats,
                badprms=badprms,
            )
        )
        result.objective = objn_pd(
            result.x,
            transform,
            params,
            fitdats,
            tweight=tweight,
            tvw_weight=tvw_weight,
            badprms=badprms,
        )
    else:
        fit = cast(PrimaryDryFit, fitdat)
        param = params
        updates = cast(dict[str, Any], _call_transform(transform, result.x))
        result.fitted_params = _replace_params(param, updates)
        result.solution = gen_sol_pd(
            result.x,
            transform,
            param,
            fit,
            badprms=badprms,
        )
        result.objective = obj_pd(
            result.x,
            transform,
            param,
            fit,
            tweight=tweight,
            tvw_weight=tvw_weight,
            badprms=badprms,
        )


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
    errs: np.ndarray = np.zeros(iend, dtype=float)
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
    if hasattr(solution, "terminated_by_drying") and not bool(
        solution.terminated_by_drying
    ):
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
    "BoundedKBBTransform",
    "KBBTransform",
    "RpTransform",
    "KTransform",
    "KRpTransform",
    "SharedSeparateTransform",
    "SharedSeparateUpdates",
    "gen_sol_pd",
    "gen_nsol_pd",
    "err_pd",
    "errn_pd",
    "obj_pd",
    "objn_pd",
    "gen_sol_rf",
    "err_rf",
    "obj_rf",
    "fit_primary_drying",
    "fit_rf_primary_drying",
    "num_errs",
    "err_expT",
    "obj_expT",
]
