"""Shared orchestration for the current-main optimizer comparisons.

This module owns only formulation-independent comparison mechanics. The
shelf-temperature, chamber-pressure, and joint-control helpers keep their
physical inputs, units, optimizer calls, solver options, and diagnostics at
their public entry points.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence, Tuple

import numpy as np


@dataclass
class SolverRun:
    """One timed optimizer execution and its normalized trajectory."""

    trajectory: np.ndarray
    wall_time_s: float
    objective_time_hr: float
    success: bool
    solver_status: str
    termination_condition: str
    max_constraint_violation: float
    n_time_points: int
    n_variables: int | None
    n_constraints: int | None
    solver_iterations: int | None
    shadow_prices: Mapping[str, float] = field(default_factory=dict)
    """Pass-through of ``DaeOptimizationResult.shadow_prices``, which documents the per-limit units."""


@dataclass
class CaseComparison:
    """Repeated SciPy, finite-difference, and collocation measurements."""

    a1: float
    kc: float
    scipy_trajectory: np.ndarray
    finite_difference_trajectory: np.ndarray
    collocation_trajectory: np.ndarray
    scipy_wall_times_s: Tuple[float, ...]
    finite_difference_wall_times_s: Tuple[float, ...]
    collocation_wall_times_s: Tuple[float, ...]
    finite_difference_status: str
    finite_difference_termination: str
    collocation_status: str
    collocation_termination: str
    finite_difference_max_constraint_violation: float
    collocation_max_constraint_violation: float
    finite_difference_n_variables: int
    finite_difference_n_constraints: int
    finite_difference_solver_iterations: int | None
    collocation_n_variables: int
    collocation_n_constraints: int
    collocation_solver_iterations: int | None

    @property
    def scipy_objective_time_hr(self) -> float:
        """Return the SciPy completion-time objective [hr]."""
        return float(self.scipy_trajectory[-1, 0])

    @property
    def finite_difference_objective_time_hr(self) -> float:
        """Return the finite-difference Pyomo.DAE final-time objective [hr]."""
        return float(self.finite_difference_trajectory[-1, 0])

    @property
    def collocation_objective_time_hr(self) -> float:
        """Return the collocation Pyomo.DAE final-time objective [hr]."""
        return float(self.collocation_trajectory[-1, 0])

    @property
    def scipy_wall_median_s(self) -> float:
        """Return the median SciPy wall time [s]."""
        return float(np.median(self.scipy_wall_times_s))

    @property
    def finite_difference_wall_median_s(self) -> float:
        """Return the median finite-difference wall time [s]."""
        return float(np.median(self.finite_difference_wall_times_s))

    @property
    def collocation_wall_median_s(self) -> float:
        """Return the median collocation wall time [s]."""
        return float(np.median(self.collocation_wall_times_s))

    @property
    def finite_difference_speedup(self) -> float:
        """Return SciPy/finite-difference median runtime [-]."""
        return self.scipy_wall_median_s / self.finite_difference_wall_median_s

    @property
    def collocation_speedup(self) -> float:
        """Return SciPy/collocation median runtime [-]."""
        return self.scipy_wall_median_s / self.collocation_wall_median_s

    @property
    def finite_difference_objective_gap_percent(self) -> float:
        """Return the finite-difference drying-time gap from SciPy [%]."""
        return (
            100.0
            * (self.finite_difference_objective_time_hr - self.scipy_objective_time_hr)
            / self.scipy_objective_time_hr
        )

    @property
    def collocation_objective_gap_percent(self) -> float:
        """Return the collocation drying-time gap from SciPy [%]."""
        return (
            100.0
            * (self.collocation_objective_time_hr - self.scipy_objective_time_hr)
            / self.scipy_objective_time_hr
        )


ScipyRunner = Callable[..., SolverRun]
DaeRunner = Callable[..., SolverRun]
SensitivityRowValues = Callable[[SolverRun], Mapping[str, Any]]


def matched_nfe_for_point_budget(point_budget: int, ncp: int = 3) -> tuple[int, int]:
    """Return FD and collocation finite elements for an equal point budget.

    Backward finite differences create ``nfe + 1`` time points, while Radau
    collocation creates ``nfe * ncp + 1``. Therefore an exactly matched budget
    requires ``point_budget - 1`` to be divisible by ``ncp``.
    """
    if point_budget < 2:
        raise ValueError("point_budget must be at least two")
    if ncp < 1:
        raise ValueError("ncp must be at least one")
    intervals = int(point_budget) - 1
    if intervals % int(ncp):
        raise ValueError("point_budget - 1 must be divisible by ncp")
    return intervals, intervals // int(ncp)


def solver_run_from_dae_result(result: Any, *, wall_time_s: float) -> SolverRun:
    """Normalize one DAE result and measured wall time [s]."""
    trajectory = result.as_table()
    max_violation = max(
        (float(value) if value is not None else 0.0)
        for value in result.constraint_violations.values()
    )
    objective = (
        float(result.objective_time_hr) if result.objective_time_hr is not None else float("nan")
    )
    return SolverRun(
        trajectory=trajectory,
        wall_time_s=float(wall_time_s),
        objective_time_hr=objective,
        success=bool(result.success),
        solver_status=str(result.solver_status),
        termination_condition=str(result.termination_condition),
        max_constraint_violation=max_violation,
        n_time_points=int(result.discretization["n_time_points"]),
        n_variables=int(result.discretization["n_variables"]),
        n_constraints=int(result.discretization["n_constraints"]),
        solver_iterations=result.discretization["solver_iterations"],
        shadow_prices=dict(result.shadow_prices),
    )


def _require_success(run: SolverRun, label: str, a1: float, kc: float) -> None:
    if not run.success:
        raise RuntimeError(
            f"{label} failed for A1={a1}, KC={kc}: "
            f"{run.solver_status}/{run.termination_condition}"
        )


def collect_case_comparison(
    a1: float,
    kc: float,
    *,
    run_scipy: ScipyRunner,
    run_dae: DaeRunner,
    scipy_dt: float,
    finite_difference_nfe: int,
    collocation_nfe: int,
    ncp: int,
    final_dried_fraction: float,
    timing_repeats: int,
    warmstart_from_scipy: bool,
    solver: Any,
) -> CaseComparison:
    """Run repeated equivalent optimizations at a matched DAE point budget."""
    if timing_repeats < 1:
        raise ValueError("timing_repeats must be at least one")
    finite_difference_points = int(finite_difference_nfe) + 1
    collocation_points = int(collocation_nfe) * int(ncp) + 1
    if finite_difference_points != collocation_points:
        raise ValueError(
            "finite_difference_nfe and collocation_nfe must create the same "
            "number of transcription points"
        )

    scipy_runs = []
    finite_difference_runs = []
    collocation_runs = []
    for _ in range(int(timing_repeats)):
        scipy_run = run_scipy(a1, kc, dt=scipy_dt)
        _require_success(scipy_run, "SciPy", a1, kc)
        initialization = scipy_run.trajectory if warmstart_from_scipy else None
        finite_difference_run = run_dae(
            a1,
            kc,
            discretization="finite_difference",
            nfe=finite_difference_nfe,
            ncp=ncp,
            final_dried_fraction=final_dried_fraction,
            initialize=initialization,
            solver=solver,
        )
        collocation_run = run_dae(
            a1,
            kc,
            discretization="collocation",
            nfe=collocation_nfe,
            ncp=ncp,
            final_dried_fraction=final_dried_fraction,
            initialize=initialization,
            solver=solver,
        )
        _require_success(finite_difference_run, "Pyomo.DAE finite difference", a1, kc)
        _require_success(collocation_run, "Pyomo.DAE collocation", a1, kc)
        scipy_runs.append(scipy_run)
        finite_difference_runs.append(finite_difference_run)
        collocation_runs.append(collocation_run)

    return CaseComparison(
        a1=float(a1),
        kc=float(kc),
        scipy_trajectory=scipy_runs[-1].trajectory,
        finite_difference_trajectory=finite_difference_runs[-1].trajectory,
        collocation_trajectory=collocation_runs[-1].trajectory,
        scipy_wall_times_s=tuple(run.wall_time_s for run in scipy_runs),
        finite_difference_wall_times_s=tuple(run.wall_time_s for run in finite_difference_runs),
        collocation_wall_times_s=tuple(run.wall_time_s for run in collocation_runs),
        finite_difference_status=finite_difference_runs[-1].solver_status,
        finite_difference_termination=finite_difference_runs[-1].termination_condition,
        collocation_status=collocation_runs[-1].solver_status,
        collocation_termination=collocation_runs[-1].termination_condition,
        finite_difference_max_constraint_violation=max(
            run.max_constraint_violation for run in finite_difference_runs
        ),
        collocation_max_constraint_violation=max(
            run.max_constraint_violation for run in collocation_runs
        ),
        finite_difference_n_variables=int(finite_difference_runs[-1].n_variables),
        finite_difference_n_constraints=int(finite_difference_runs[-1].n_constraints),
        finite_difference_solver_iterations=finite_difference_runs[-1].solver_iterations,
        collocation_n_variables=int(collocation_runs[-1].n_variables),
        collocation_n_constraints=int(collocation_runs[-1].n_constraints),
        collocation_solver_iterations=collocation_runs[-1].solver_iterations,
    )


def collect_discretization_sensitivity(
    a1: float,
    kc: float,
    scipy_trajectory: np.ndarray,
    *,
    run_dae: DaeRunner,
    point_budgets: Sequence[int],
    ncp: int,
    final_dried_fraction: float,
    solver: Any,
    extra_row_values: SensitivityRowValues | None,
) -> list[dict[str, Any]]:
    """Evaluate both DAE transformations at exactly matched point budgets."""
    scipy_objective = float(np.asarray(scipy_trajectory)[-1, 0])  # [hr]
    rows: list[dict[str, Any]] = []
    for point_budget in point_budgets:
        finite_difference_nfe, collocation_nfe = matched_nfe_for_point_budget(
            int(point_budget), ncp
        )
        for method, nfe in (
            ("finite_difference", finite_difference_nfe),
            ("collocation", collocation_nfe),
        ):
            run = run_dae(
                a1,
                kc,
                discretization=method,
                nfe=int(nfe),
                ncp=ncp,
                final_dried_fraction=final_dried_fraction,
                solver=solver,
            )
            if not run.success:
                raise RuntimeError(f"Pyomo.DAE {method} solve failed for nfe={nfe}")
            row = {
                "method": method,
                "point_budget": int(point_budget),
                "nfe": int(nfe),
                "ncp": None if method == "finite_difference" else int(ncp),
                "n_time_points": run.n_time_points,
                "objective_time_hr": run.objective_time_hr,
                "objective_gap_percent": 100.0
                * (run.objective_time_hr - scipy_objective)
                / scipy_objective,
            }
            if extra_row_values is not None:
                row.update(extra_row_values(run))
            row.update(
                {
                    "final_percent_dried": float(run.trajectory[-1, 6]),
                    "wall_time_s": run.wall_time_s,
                    "n_variables": run.n_variables,
                    "n_constraints": run.n_constraints,
                    "solver_iterations": run.solver_iterations,
                    "max_constraint_violation": run.max_constraint_violation,
                }
            )
            rows.append(row)
    return rows


#: Legacy equality constraints returned by ``functions.Eq_Constraints``, with
#: the unit each residual carries and the term used to normalize it.
#:
#: The four residuals are dimensionally distinct, so a single absolute
#: tolerance over all of them is meaningless: the same numeric threshold is
#: loose for one equation and impossibly tight for another. Each is therefore
#: divided by a representative magnitude of its own terms, which makes the
#: reported quantity a dimensionless relative residual comparable across
#: equations.
LEGACY_EQUALITY_CONSTRAINTS: Tuple[Tuple[str, str, str], ...] = (
    ("vapor_pressure", "Torr", "sublimation-front pressure"),
    ("sublimation_rate", "kg/hr", "sublimation rate"),
    ("vial_heat_balance", "cal cm/s", "conducted heat through the frozen layer"),
    ("shelf_temperature", "degC", "shelf-to-bottom temperature difference"),
)


def legacy_equality_residuals(
    trajectory: np.ndarray,
    data: Mapping[str, Any],
) -> dict[str, dict[str, float]]:
    """Evaluate the legacy SciPy equality constraints along a DAE trajectory.

    The Pyomo.DAE models restate the physics that ``functions.Eq_Constraints``
    encodes for the sequential optimizers, so those legacy residuals must
    vanish at a DAE solution even though the DAE never calls them. This
    evaluates them independently and reports each equation separately.

    ``trajectory`` uses the package's seven-column contract: time [hr],
    temperatures [degC], chamber pressure [mTorr], sublimation flux
    [kg/hr/m^2], and dried percentage [0-100]. ``data`` is one of the
    ``comparison_inputs`` mappings.

    Returns one entry per equation in :data:`LEGACY_EQUALITY_CONSTRAINTS`,
    each carrying ``max_absolute`` in that equation's own unit, the
    ``scale`` [same unit] it was normalized by, and the dimensionless
    ``max_relative`` residual. Compare ``max_relative`` across equations;
    ``max_absolute`` alone is not comparable between them.
    """
    from lyopronto import constant, functions

    table = np.asarray(trajectory, dtype=float)
    if table.ndim != 2 or table.shape[1] != 7 or not np.all(np.isfinite(table)):
        raise ValueError("trajectory must be a finite two-dimensional, seven-column table")

    vial, product, ht = data["vial"], data["product"], data["ht"]
    lpr0_cm = functions.Lpr0_FUN(vial["Vfill"], vial["Ap"], product["cSolid"])

    residuals: list[Tuple[float, ...]] = []
    scales: list[Tuple[float, ...]] = []
    for row in table:
        pressure_torr = row[4] / constant.Torr_to_mTorr
        rate_kg_per_hr = row[5] * vial["Ap"] * constant.cm_To_m**2
        cake_length_cm = row[6] / 100.0 * lpr0_cm
        front_pressure_torr = functions.Vapor_pressure(row[1])
        kv = functions.Kv_FUN(ht["KC"], ht["KP"], ht["KD"], pressure_torr)
        rp = functions.Rp_FUN(cake_length_cm, product["R0"], product["A1"], product["A2"])
        residuals.append(
            functions.Eq_Constraints(
                pressure_torr,
                rate_kg_per_hr,
                row[2],
                row[3],
                front_pressure_torr,
                row[1],
                kv,
                lpr0_cm,
                cake_length_cm,
                vial["Av"],
                vial["Ap"],
                rp,
            )
        )
        # One representative magnitude per equation, taken from the same row.
        scales.append(
            (
                abs(front_pressure_torr),
                abs(rate_kg_per_hr),
                abs(vial["Ap"] * (row[2] - row[1]) * constant.k_ice),
                abs(row[3] - row[2]),
            )
        )

    absolute = np.abs(np.asarray(residuals, dtype=float))
    magnitude = np.abs(np.asarray(scales, dtype=float))

    # Normalize by the largest magnitude each equation reaches anywhere on the
    # trajectory, not row by row. Several of these terms legitimately vanish at
    # an endpoint -- the frozen layer disappears at complete drying, so the
    # conducted-heat term and its residual both go to zero -- and a row-local
    # ratio there is 0/0, which reports a meaningless O(1) relative residual on
    # a perfectly converged solve. A trajectory-level scale keeps the quantity
    # interpretable: residual as a fraction of the largest value that equation
    # actually takes on this solution.
    scale = np.maximum(magnitude.max(axis=0), np.finfo(float).tiny)
    relative = absolute / scale

    return {
        name: {
            "unit": unit,
            "scale_term": scale_term,
            "max_absolute": float(absolute[:, index].max()),
            "scale": float(scale[index]),
            "max_relative": float(relative[:, index].max()),
        }
        for index, (name, unit, scale_term) in enumerate(LEGACY_EQUALITY_CONSTRAINTS)
    }


__all__ = [
    "CaseComparison",
    "DaeRunner",
    "LEGACY_EQUALITY_CONSTRAINTS",
    "ScipyRunner",
    "SensitivityRowValues",
    "SolverRun",
    "collect_case_comparison",
    "collect_discretization_sensitivity",
    "legacy_equality_residuals",
    "matched_nfe_for_point_budget",
    "solver_run_from_dae_result",
]
