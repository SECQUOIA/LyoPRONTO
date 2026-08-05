"""Reusable computations for the original known- and unknown-Rp tutorials.

The original LyoPRONTO notebooks are reader-facing wrappers around this
module.  Legacy calculations remain available without optional dependencies;
Pyomo is imported only by the functions that build or solve Pyomo models.

All inputs use the legacy unit convention: time [hr], temperature [degC],
pressure [Torr], length [cm], product resistance [cm^2 hr Torr/g], and heat
transfer [cal/s/K/cm^2].  Legacy trajectory tables retain pressure [mTorr],
sublimation flux [kg/hr/m^2], and percent dried [0-100].
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import numpy as np
from scipy.optimize import curve_fit

from lyopronto import calc_knownRp, calc_unknownRp, constant, functions


ROOT = Path(__file__).resolve().parents[1]
TEMPERATURE_DATA = ROOT / "test_data" / "temperature.txt"
KNOWN_RP_ENDPOINT_TOLERANCE_PP = 1.5  # [percentage points], first-order BE error
KnownRpCase = Tuple[
    Dict[str, float],
    Dict[str, float],
    Dict[str, float],
    Dict[str, Any],
    Dict[str, Any],
]


@dataclass(frozen=True)
class ResistanceFit:
    """Product-resistance fit in the legacy ``Rp(Lck)`` parameterization.

    ``parameter_stderr`` contains SciPy covariance-derived standard errors in
    ``R0``, ``A1``, ``A2`` order. It is unavailable for the current Pyomo fit.
    """

    success: bool
    solver_status: str
    termination_condition: str
    message: str
    R0: Optional[float]  # [cm^2 hr Torr/g]
    A1: Optional[float]  # [cm hr Torr/g]
    A2: Optional[float]  # [1/cm]
    objective: Optional[float]  # sum of squared Rp residuals [(cm^2 hr Torr/g)^2]
    parameter_stderr: Optional[Tuple[float, float, float]]

    def as_array(self) -> np.ndarray:
        """Return successful ``R0``, ``A1``, and ``A2`` in parameter order."""
        if (
            not self.success
            or self.R0 is None
            or self.A1 is None
            or self.A2 is None
        ):
            raise RuntimeError(self.message)
        return np.array([self.R0, self.A1, self.A2], dtype=float)


def known_rp_case() -> KnownRpCase:
    """Return fresh dictionaries for the original known-Rp drying case."""
    vial = {"Av": 3.80, "Ap": 3.14, "Vfill": 2.0}
    product = {
        "cSolid": 0.05,
        "R0": 1.4,
        "A1": 16.0,
        "A2": 0.0,
        "T_pr_crit": -5.0,
    }
    ht = {"KC": 2.75e-4, "KP": 8.93e-4, "KD": 0.46}
    pchamber = {"setpt": [0.15], "dt_setpt": [1800.0], "ramp_rate": 0.5}
    tshelf = {
        "init": -35.0,
        "setpt": [20.0],
        "dt_setpt": [1800.0],
        "ramp_rate": 1.0,
    }
    return vial, product, ht, pchamber, tshelf


def unknown_rp_case() -> KnownRpCase:
    """Return fresh dictionaries for the original unknown-Rp drying case."""
    vial, _known_product, ht, pchamber, tshelf = known_rp_case()
    product = {"cSolid": 0.05, "T_pr_crit": -5.0}
    return vial, product, ht, pchamber, tshelf


def load_temperature_data(path: Path | str = TEMPERATURE_DATA) -> Tuple[np.ndarray, np.ndarray]:
    """Load measured time [hr] and vial-bottom temperature [degC]."""
    data = np.loadtxt(path, dtype=float)
    if data.ndim != 2 or data.shape[1] != 2:
        raise ValueError("temperature data must contain exactly two columns")
    return data[:, 0], data[:, 1]


def run_known_rp_scipy(
    dt: float = 0.25,
    case: Optional[KnownRpCase] = None,
) -> np.ndarray:
    """Run a known-Rp case with the legacy SciPy calculator.

    ``case`` defaults to :func:`known_rp_case`. Pass an edited case tuple when
    reader-supplied dictionaries should drive the calculation.
    """
    vial, product, ht, pchamber, tshelf = case if case is not None else known_rp_case()
    return calc_knownRp.dry(vial, product, ht, pchamber, tshelf, dt)


def build_known_rp_pyomo_model(
    scipy_output: np.ndarray,
    *,
    n_steps: int = 26,
    dt: float = 0.25,
    final_dried_fraction: float = 0.95,
) -> Any:
    """Build the fixed-horizon Pyomo replay of the known-Rp case.

    The default grid has 26 backward-Euler intervals of 0.25 hr (a 6.5 hr
    horizon) and constrains the terminal dried fraction to at least 0.95.  It
    is therefore a discretized fixed-control parity replay, not a replacement
    for the legacy calculator's event-terminated integration.
    """
    from lyopronto.pyomo_models import (
        create_trajectory_model,
        sample_ramp_profile,
        trajectory_initialization_from_scipy_output,
    )

    vial, product, ht, pchamber, tshelf = known_rp_case()
    time_points = np.arange(n_steps + 1, dtype=float) * dt
    lpr0 = float(functions.Lpr0_FUN(vial["Vfill"], vial["Ap"], product["cSolid"]))
    initialization = trajectory_initialization_from_scipy_output(
        scipy_output,
        lpr0=lpr0,
        ap=vial["Ap"],
        ht=ht,
        time_points=time_points,
    )
    return create_trajectory_model(
        vial,
        product,
        ht,
        n_steps=n_steps,
        dt=dt,
        final_dried_fraction=final_dried_fraction,
        fixed_pch_profile=sample_ramp_profile(pchamber, time_points),
        fixed_tsh_profile=sample_ramp_profile(tshelf, time_points),
        pch_ramp_rate=pchamber["ramp_rate"] * constant.hr_To_min,
        tsh_ramp_rate=tshelf["ramp_rate"] * constant.hr_To_min,
        initialize=initialization,
    )


def run_known_rp_pyomo(
    scipy_output: np.ndarray,
    *,
    solver: Any = "ipopt",
    n_steps: int = 26,
    dt: float = 0.25,
    final_dried_fraction: float = 0.95,
) -> Any:
    """Solve the fixed-horizon Pyomo replay and return a ``TrajectoryResult``."""
    from lyopronto.pyomo_models import solve_trajectory

    model = build_known_rp_pyomo_model(
        scipy_output,
        n_steps=n_steps,
        dt=dt,
        final_dried_fraction=final_dried_fraction,
    )
    return solve_trajectory(model, solver=solver)


def preprocess_unknown_rp(
    path: Path | str = TEMPERATURE_DATA,
) -> Tuple[np.ndarray, np.ndarray]:
    """Infer trajectory and ``(time, Lck, Rp)`` observations from temperature.

    This is the legacy inverse-temperature preprocessing step shared by both
    fitting backends.  The returned cake length is [cm] and product resistance
    is [cm^2 hr Torr/g].
    """
    vial, product, ht, pchamber, tshelf = unknown_rp_case()
    time_hr, tbot_degc = load_temperature_data(path)
    return calc_unknownRp.dry(
        vial,
        product,
        ht,
        pchamber,
        tshelf,
        time_hr,
        tbot_degc,
    )


def fit_unknown_rp_scipy(product_resistance: np.ndarray) -> ResistanceFit:
    """Fit ``Rp(Lck)`` observations with SciPy ``curve_fit``."""
    lck_cm = np.asarray(product_resistance[:, 1], dtype=float)
    rp_observed = np.asarray(product_resistance[:, 2], dtype=float)
    params, covariance = curve_fit(
        lambda length, r0, a1, a2: r0 + length * a1 / (1.0 + length * a2),
        lck_cm,
        rp_observed,
        p0=[1.0, 0.0, 0.0],
    )
    parameter_stderr = np.sqrt(np.diag(covariance))
    if not np.all(np.isfinite(params)) or not np.all(np.isfinite(parameter_stderr)):
        return ResistanceFit(
            success=False,
            solver_status="failure",
            termination_condition="non_finite_covariance",
            message=(
                "SciPy curve_fit did not return finite parameters and standard errors; "
                "the fit is not identifiable from these observations."
            ),
            R0=None,
            A1=None,
            A2=None,
            objective=None,
            parameter_stderr=None,
        )
    residual = rp_observed - functions.Rp_FUN(lck_cm, *params)
    objective = float(np.dot(residual, residual))
    if not np.isfinite(objective):
        return ResistanceFit(
            success=False,
            solver_status="failure",
            termination_condition="non_finite_objective",
            message="SciPy curve_fit returned a non-finite residual objective.",
            R0=None,
            A1=None,
            A2=None,
            objective=None,
            parameter_stderr=None,
        )
    return ResistanceFit(
        success=True,
        solver_status="success",
        termination_condition="curve_fit converged",
        message="SciPy curve_fit converged.",
        R0=float(params[0]),
        A1=float(params[1]),
        A2=float(params[2]),
        objective=objective,
        parameter_stderr=tuple(float(value) for value in parameter_stderr),
    )


def build_unknown_rp_pyomo_model(product_resistance: np.ndarray) -> Any:
    """Build the hybrid Pyomo least-squares fit from legacy Rp observations."""
    from lyopronto.pyomo_models import create_parameter_estimation_model

    vial, _product, ht, pchamber, _tshelf = unknown_rp_case()
    observations = [
        {"Lck": float(row[1]), "Pch": float(pchamber["setpt"][0]), "Rp": float(row[2])}
        for row in np.asarray(product_resistance, dtype=float)
    ]
    initial_product = {"R0": 1.0, "A1": 8.0, "A2": 0.5}
    return create_parameter_estimation_model(
        vial,
        initial_product,
        ht,
        observations,
        estimate_product_resistance=True,
        estimate_heat_transfer=False,
        parameter_bounds={"R0": (0.0, 5.0), "A1": (0.0, 50.0), "A2": (0.0, 5.0)},
    )


def fit_unknown_rp_pyomo(
    product_resistance: np.ndarray,
    *,
    solver: Any = "ipopt",
) -> ResistanceFit:
    """Fit shared legacy Rp observations with the optional Pyomo model.

    Non-optimal solver outcomes return diagnostics with ``success=False`` and
    no fitted parameters or objective.  This prevents initialized model values
    from being mistaken for a scientific fit.
    """
    from lyopronto.pyomo_models import solve_parameter_estimation

    model = build_unknown_rp_pyomo_model(product_resistance)
    result = solve_parameter_estimation(model, solver=solver)
    if not result.success or result.objective is None:
        return ResistanceFit(
            success=False,
            solver_status=result.solver_status,
            termination_condition=result.termination_condition,
            message=result.message,
            R0=None,
            A1=None,
            A2=None,
            objective=None,
            parameter_stderr=None,
        )

    values = result.as_dict()
    return ResistanceFit(
        success=True,
        solver_status=result.solver_status,
        termination_condition=result.termination_condition,
        message=result.message,
        R0=values["R0"],
        A1=values["A1"],
        A2=values["A2"],
        objective=result.objective,
        parameter_stderr=None,
    )


def pyomo_ipopt_status() -> Tuple[bool, str]:
    """Report whether the optional Pyomo/IPOPT tutorial path can run."""
    try:
        import pyomo.environ as pyo
    except ImportError:
        return False, 'Install the optional stack with `python -m pip install -e ".[pyomo]"`.'

    if not pyo.SolverFactory("ipopt").available(exception_flag=False):
        return False, "Install IPOPT with `idaes get-extensions --extra petsc` or conda-forge."
    return True, "Pyomo and IPOPT are available."
