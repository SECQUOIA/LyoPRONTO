"""Replication of the Srisuma and Braatz (2025) lyophilization optimal-control cases.

The reference is Srisuma and Braatz, "Highly Efficient Optimal Control for
Lyophilization via Simulation of Discrete/Continuous Mixed-index
Differential-algebraic Equations", arXiv:2509.10826v1, with upstream code at
https://github.com/PrakitrSrisuma/simDAE-optimalcontrol-lyo (commit
``5bcfece23128be7e5be51b73693dc6674223ccc6``).

The paper reformulates primary-drying optimal control as a hybrid
discrete/continuous system of mixed-index DAEs and *simulates* it, instead of
solving a nonlinear program. It defines three control policies and two case
studies:

* Policy 1 maximizes heat input, ``Tb = Tb_max`` (index-1);
* Policy 2 tracks the product temperature, ``T_n = T_sp`` (index-2);
* Policy 3 tracks the interface velocity, ``dS/dt = v_sp`` (index ``n+1``);
* Problem 1 minimizes drying time subject to ``T <= 243 K`` and
  ``228 K <= Tb <= 273 K``;
* Problem 2 adds ``dS/dt <= 2.8e-7 m/s`` and tightens the limits to
  ``T <= 240 K`` and ``228 K <= Tb <= 260 K``.

This module drives two independent LyoPRONTO capabilities against those cases.

1. ``lyopronto.pyomo_models.paper_ocp`` transcribes the paper's own SI-unit
   moving-boundary model and solves both problems by simultaneous orthogonal
   collocation with IPOPT. This is the *optimization-based* route that the paper
   benchmarks its method against, so it tests whether LyoPRONTO recovers the
   published trajectories, drying times, and policy-switching structure.
2. ``lyopronto.opt_Tsh`` is LyoPRONTO's existing sequential shelf-temperature
   optimizer on the vial-scale model. It maximizes sublimation rate subject to a
   product-temperature limit, an equipment-capability limit, and shelf bounds, so
   its active constraint at each step *is* the paper's policy taxonomy expressed
   in LyoPRONTO's own units.

The two halves use different models and unit systems on purpose. The paper model
is SI (K, Pa, m, s); the vial-scale model is the legacy LyoPRONTO convention
(degC, Torr, cm, hr). Do not mix their parameters.
"""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Any, Mapping, Sequence

import numpy as np

from lyopronto import opt_Tsh
from lyopronto.pyomo_models import paper_ocp


# ---------------------------------------------------------------------------
# Published reference values
# ---------------------------------------------------------------------------

PAPER_REFERENCE: dict[str, Any] = {
    "citation": "Srisuma and Braatz, arXiv:2509.10826v1 (2025)",
    "upstream_repo": "https://github.com/PrakitrSrisuma/simDAE-optimalcontrol-lyo",
    "upstream_commit": "5bcfece23128be7e5be51b73693dc6674223ccc6",
    "hardware": "AMD Ryzen 9 5900HS (8 cores), 32 GB RAM, Windows 11",
    "problem1": {
        # Stated in the text of Section V-A.
        "switch_times_hr": (2.4,),
        "policy_sequence": ("policy_1_max_heat_input", "policy_2_temperature_tracking"),
        "simulation_based_runtime_s": 0.58,
        "simulation_based_runtime_tolerance_s": 0.01,
        # Read from Figure 2; the text does not state the final time. The
        # uncertainty is the width of the read, not a model tolerance.
        "drying_time_hr": 6.2,
        "drying_time_uncertainty_hr": 0.1,
        "drying_time_source": "read from Figure 2",
        "temperature_limit_K": 243.0,
        "shelf_temperature_bounds_K": (228.0, 273.0),
    },
    "problem2": {
        # Stated in the text of Section V-B.
        "switch_times_hr": (2.0, 3.9),
        "policy_sequence": (
            "policy_3_interface_velocity_tracking",
            "policy_1_max_heat_input",
            "policy_2_temperature_tracking",
        ),
        "drying_time_hr": 8.9,
        "drying_time_uncertainty_hr": 0.05,
        "drying_time_source": "stated in Section V-B",
        "simulation_based_runtime_s": 0.98,
        "simulation_based_runtime_tolerance_s": 0.02,
        "temperature_limit_K": 240.0,
        "interface_velocity_limit_m_per_s": 2.8e-7,
        "shelf_temperature_bounds_K": (228.0, 260.0),
    },
    # Benchmarking/Comparison.pdf in the upstream repository, for Problem 1.
    # The optimization-based scripts themselves were never released, so these
    # are the only published numbers for that route.
    "problem1_runtime_benchmark_s": {
        "opt_Ipopt1": 1015.84,
        "opt_Ipopt2": 64.60,
        "sim_DAE": 0.58,
    },
}


# ---------------------------------------------------------------------------
# Paper model: Pyomo.DAE direct transcription
# ---------------------------------------------------------------------------

#: Fraction of the product height at which the interface is declared arrived.
#:
#: The paper's own termination is ``S = H`` exactly. That endpoint is not
#: reachable in this transcription: the model is written on the Landau
#: coordinate ``psi = (z - S)/(H - S)``, whose conduction term carries a
#: ``1/(H - S)^2`` factor, so the frozen-region equations are singular as
#: ``S -> H`` and ``paper_ocp`` rejects a fraction of 1. Tightening the cutoff
#: also makes the solve progressively harder for the same reason: at this mesh
#: 0.99 and 0.995 terminate optimally in about two seconds, while 0.999 and
#: 0.9995 exhaust IPOPT's iteration limit after roughly four minutes and return
#: a non-optimal point. 0.995 is therefore the tightest cutoff that still gives
#: a converged answer, and the residual to ``S = H`` is recovered by
#: extrapolation rather than by tightening further. The drying time is always
#: approached from below and must be reported with the cutoff that produced it;
#: see :func:`extrapolated_complete_drying_time_hr` and
#: :func:`terminal_fraction_sensitivity_rows`.
DEFAULT_TERMINAL_DRYING_FRACTION = 0.995


@dataclass(frozen=True)
class PaperCaseRun:
    """One timed solve of a paper case study."""

    problem: str
    solution: Mapping[str, Any]
    wall_times_s: tuple[float, ...]
    n_z: int
    nfe: int
    ncp: int
    initialization: str
    terminal_drying_fraction: float

    @property
    def wall_median_s(self) -> float:
        """Return the median wall time [s] over the timing repeats."""
        return float(np.median(self.wall_times_s))

    @property
    def drying_time_hr(self) -> float:
        """Return the optimized free final time [hr]."""
        return float(self.solution["metrics"]["drying_time_hr"])

    @property
    def switch_times_hr(self) -> tuple[float, ...]:
        """Return the policy switch times [hr]."""
        return tuple(float(t) for t in self.solution["policies"]["switch_times_hr"])

    @property
    def policy_sequence(self) -> tuple[str, ...]:
        """Return the ordered policy labels of the solved trajectory."""
        return tuple(
            str(segment["label"]) for segment in self.solution["policies"]["segments"]
        )

    @property
    def terminated_optimally(self) -> bool:
        """Return whether IPOPT reported an optimal termination."""
        return str(self.solution["metadata"]["termination_condition"]) == "optimal"


def run_paper_case(
    problem: str,
    *,
    n_z: int = 20,
    nfe: int = 24,
    ncp: int = 3,
    initialization: str | None = None,
    terminal_drying_fraction: float = DEFAULT_TERMINAL_DRYING_FRACTION,
    solver: str = "ipopt",
    timing_repeats: int = 1,
) -> PaperCaseRun:
    """Solve one paper case study by simultaneous collocation and time it.

    ``n_z`` is the number of spatial nodes in the frozen region; the paper uses
    20. ``initialization`` defaults to a cold start (``None``) so that the
    recovered policy sequence is not seeded from the published one; pass
    ``"policy"`` for the deterministic policy-sequenced warm start.
    ``terminal_drying_fraction`` is the fraction of the product height at which
    the interface is declared arrived; see
    :data:`DEFAULT_TERMINAL_DRYING_FRACTION` for why it cannot be 1.
    """
    if problem not in {"problem1", "problem2"}:
        raise ValueError(f"unsupported paper problem: {problem!r}")
    if timing_repeats < 1:
        raise ValueError("timing_repeats must be at least 1")

    discretization = paper_ocp.PaperDiscretization(
        n_z=int(n_z),
        nfe=int(nfe),
        ncp=int(ncp),
        terminal_drying_fraction=float(terminal_drying_fraction),
    )
    solve = (
        paper_ocp.solve_paper_problem1
        if problem == "problem1"
        else paper_ocp.solve_paper_problem2
    )

    wall_times: list[float] = []
    solution: Mapping[str, Any] | None = None
    for _ in range(int(timing_repeats)):
        start = perf_counter()
        solution = solve(
            discretization=discretization,
            initialization=initialization,
            solver=solver,
            require_success=False,
        )
        wall_times.append(perf_counter() - start)

    assert solution is not None
    return PaperCaseRun(
        problem=problem,
        solution=solution,
        wall_times_s=tuple(wall_times),
        n_z=int(n_z),
        nfe=int(nfe),
        ncp=int(ncp),
        initialization="cold" if initialization is None else str(initialization),
        terminal_drying_fraction=float(terminal_drying_fraction),
    )


def shelf_bound_switch_brackets_hr(
    run: PaperCaseRun,
    *,
    tolerance_K: float = 1.0e-3,
) -> list[tuple[float, float]]:
    """Return the time brackets [hr] in which the policy switches occur.

    The shelf temperature sits exactly on its upper bound for the whole of the
    Policy 1 interval and strictly inside its bounds during Policies 2 and 3, so
    the edges of that interval locate the switches. This is the same signal the
    upstream event function watches (``Tb - Tb_max``), and unlike a tolerance on
    the product temperature it does not fire early: the product temperature
    approaches its limit asymptotically, so "within 0.35 K of the limit" is
    reached well before the shelf actually starts backing off.

    A switch is reported as the bracket between the two mesh points that straddle
    it, because a collocation solution only resolves it to that interval. If the
    shelf starts on its bound, as in Problem 1, only the exit bracket is
    returned.

    The window is the *longest* contiguous run of bound contact, not simply the
    first and last contact points. Two things put stray contact outside the real
    window. At the initial mesh point the control is degenerate: the shelf has
    had no time to influence the interface, so nothing in the objective pins
    ``Tb(0)`` and the solver parks it on whichever bound its initialization
    favours -- the cold start leaves Problem 2 at 260 K there while the policy
    warm start leaves it at 228 K, and the two trajectories are identical from
    the next mesh point onward. At fine time meshes the control polynomial can
    also ring inside the window, briefly leaving the bound at interior points;
    see :func:`shelf_bound_contact_is_contiguous`. Neither moves the switch
    itself, which is where the control settles onto or leaves the bound for good.
    """
    time_hr = np.asarray(run.solution["states"]["time_hr"], dtype=float)
    window = _longest_shelf_bound_window(run, tolerance_K=tolerance_K)
    if window is None:
        return []

    first, last = window
    brackets: list[tuple[float, float]] = []
    if first > 0:
        brackets.append((float(time_hr[first - 1]), float(time_hr[first])))
    if last < time_hr.size - 1:
        brackets.append((float(time_hr[last]), float(time_hr[last + 1])))
    return brackets


def _shelf_bound_contact_indices(
    run: PaperCaseRun,
    *,
    tolerance_K: float = 1.0e-3,
) -> np.ndarray:
    """Return the indices at which the shelf control sits on its upper bound."""
    shelf_K = np.asarray(run.solution["controls"]["shelf_temperature_K"], dtype=float)
    shelf_max = float(run.solution["problem"]["shelf_temperature_max_K"])
    return np.flatnonzero(shelf_K >= shelf_max - tolerance_K)


def _longest_shelf_bound_window(
    run: PaperCaseRun,
    *,
    tolerance_K: float = 1.0e-3,
) -> tuple[int, int] | None:
    """Return the index span of the longest unbroken run of bound contact."""
    indices = _shelf_bound_contact_indices(run, tolerance_K=tolerance_K)
    if indices.size == 0:
        return None

    breaks = np.flatnonzero(np.diff(indices) != 1)
    starts = np.concatenate(([0], breaks + 1))
    ends = np.concatenate((breaks, [indices.size - 1]))
    longest = int(np.argmax(ends - starts))
    return int(indices[starts[longest]]), int(indices[ends[longest]])


def shelf_bound_contact_is_contiguous(
    run: PaperCaseRun,
    *,
    tolerance_K: float = 1.0e-3,
) -> bool:
    """Return whether the Policy 1 window is one unbroken run of interior points.

    The optimal control is exactly constant at the bound through Policy 1, so a
    broken contact set means the transcribed control polynomial is ringing
    within its finite elements rather than that the policy is switching back and
    forth. It is a discretization-quality signal, not a physical one: the states
    and the objective stay converged while it happens.

    The initial mesh point is excluded because the control is degenerate there
    (see :func:`shelf_bound_switch_brackets_hr`), so a lone contact at ``t = 0``
    is expected rather than a sign of ringing.
    """
    indices = _shelf_bound_contact_indices(run, tolerance_K=tolerance_K)
    interior = indices[indices > 0]
    if interior.size == 0:
        return False
    return bool(np.all(np.diff(interior) == 1))


def paper_comparison_rows(run: PaperCaseRun) -> list[dict[str, Any]]:
    """Return published-versus-LyoPRONTO rows for one solved case."""
    reference = PAPER_REFERENCE[run.problem]
    fraction = run.terminal_drying_fraction
    rows: list[dict[str, Any]] = [
        {
            "quantity": f"drying time to S={fraction:g}H [hr]",
            "paper": float("nan"),
            "lyopronto_low": run.drying_time_hr,
            "lyopronto_high": run.drying_time_hr,
            "note": "solver endpoint, short of the paper's S=H",
        },
        {
            "quantity": "drying time to S=H [hr]",
            "paper": float(reference["drying_time_hr"]),
            "lyopronto_low": extrapolated_complete_drying_time_hr(run),
            "lyopronto_high": extrapolated_complete_drying_time_hr(run),
            "note": str(reference["drying_time_source"]),
        },
    ]

    paper_switches = tuple(reference["switch_times_hr"])
    brackets = shelf_bound_switch_brackets_hr(run)
    for index, paper_switch in enumerate(paper_switches):
        low, high = brackets[index] if index < len(brackets) else (float("nan"), float("nan"))
        rows.append(
            {
                "quantity": f"policy switch {index + 1} [hr]",
                "paper": float(paper_switch),
                "lyopronto_low": float(low),
                "lyopronto_high": float(high),
                "note": "stated in Section V",
            }
        )
    return rows


def switch_brackets_contain_published(run: PaperCaseRun) -> list[bool]:
    """Return whether each published switch time falls inside its solved bracket."""
    published = tuple(PAPER_REFERENCE[run.problem]["switch_times_hr"])
    brackets = shelf_bound_switch_brackets_hr(run)
    return [
        bool(brackets[index][0] <= value <= brackets[index][1])
        if index < len(brackets)
        else False
        for index, value in enumerate(published)
    ]


def complete_drying_residual_hr(run: PaperCaseRun) -> float:
    """Return the time [hr] still needed to carry the interface from ``S`` to ``H``.

    The solved trajectory stops at ``terminal_drying_fraction`` of the product
    height, so it is short of the paper's ``S = H`` endpoint by the remaining
    frozen thickness. Late in primary drying the interface velocity is smooth
    and slowly varying, so holding it at its terminal value over that last
    sliver is an accurate first-order estimate of the missing time.
    """
    metrics = run.solution["metrics"]
    height_m = float(run.solution["derived"]["product_height"])
    remaining_m = height_m - float(metrics["terminal_interface_position_m"])
    terminal_velocity = float(
        np.asarray(run.solution["states"]["interface_velocity_m_per_s"])[-1]
    )
    if terminal_velocity <= 0.0:
        return float("nan")
    return remaining_m / terminal_velocity / 3600.0


def extrapolated_complete_drying_time_hr(run: PaperCaseRun) -> float:
    """Return the drying time [hr] extrapolated to the paper's ``S = H`` endpoint."""
    return run.drying_time_hr + complete_drying_residual_hr(run)


def paper_reference_deviation_percent(
    run: PaperCaseRun,
    *,
    extrapolated: bool = True,
) -> float:
    """Return the drying-time deviation from the published value [%].

    Compares the extrapolated complete-drying time by default, because that is
    the quantity the paper reports; pass ``extrapolated=False`` to compare the
    truncated value the solver actually returned.
    """
    published = float(PAPER_REFERENCE[run.problem]["drying_time_hr"])
    solved = (
        extrapolated_complete_drying_time_hr(run) if extrapolated else run.drying_time_hr
    )
    return 100.0 * (solved - published) / published


def terminal_fraction_sensitivity_rows(
    problem: str,
    fractions: Sequence[float],
    *,
    n_z: int = 20,
    nfe: int = 36,
    ncp: int = 3,
    solver: str = "ipopt",
) -> list[dict[str, Any]]:
    """Return how the drying time moves with the terminal-cutoff fraction.

    The extrapolated column should be flat across fractions if the linear
    residual estimate is sound, while the raw column rises toward it.
    """
    rows: list[dict[str, Any]] = []
    for fraction in fractions:
        run = run_paper_case(
            problem,
            n_z=n_z,
            nfe=nfe,
            ncp=ncp,
            terminal_drying_fraction=fraction,
            solver=solver,
        )
        rows.append(
            {
                "terminal_drying_fraction": float(fraction),
                "drying_time_hr": run.drying_time_hr,
                "residual_hr": complete_drying_residual_hr(run),
                "extrapolated_hr": extrapolated_complete_drying_time_hr(run),
                "termination": str(run.solution["metadata"]["termination_condition"]),
                "wall_time_s": run.wall_median_s,
            }
        )
    return rows


def mesh_sensitivity_rows(
    problem: str,
    meshes: Sequence[tuple[int, int]],
    *,
    ncp: int = 3,
    solver: str = "ipopt",
) -> list[dict[str, Any]]:
    """Return per-mesh convergence diagnostics across ``(n_z, nfe)`` pairs.

    Each row carries the drying time, the bracket around the *first* policy
    switch and whether it contains the published value, whether the transcribed
    control stayed cleanly on its bound, the recovered policy sequence, and the
    solve time.
    """
    rows: list[dict[str, Any]] = []
    for n_z, nfe in meshes:
        run = run_paper_case(problem, n_z=n_z, nfe=nfe, ncp=ncp, solver=solver)
        brackets = shelf_bound_switch_brackets_hr(run)
        contains = switch_brackets_contain_published(run)
        rows.append(
            {
                "n_z": int(n_z),
                "nfe": int(nfe),
                "drying_time_hr": run.drying_time_hr,
                "switch_bracket_hr": brackets[0] if brackets else (float("nan"), float("nan")),
                "bracket_contains_published": contains[0] if contains else False,
                "control_contact_contiguous": shelf_bound_contact_is_contiguous(run),
                "policy_sequence": run.policy_sequence,
                "wall_time_s": run.wall_median_s,
                "termination": str(run.solution["metadata"]["termination_condition"]),
            }
        )
    return rows


# ---------------------------------------------------------------------------
# Vial-scale model: the same policy taxonomy in LyoPRONTO's own units
# ---------------------------------------------------------------------------

#: Scale factor applied to the measured Millrock REVO equipment-capability line
#: so the condenser becomes an actively binding constraint. The unscaled line
#: (``a = -0.182``, ``b = 11.7``) never binds for this vial load, so Policy 3
#: would be unreachable and only Policies 1 and 2 would appear.
DEFAULT_CAPABILITY_SCALE = 0.16

#: Shelf-temperature ceiling [degC]. High enough that the equipment limit binds
#: first, low enough that the shelf bound is active before the product
#: temperature limit takes over.
DEFAULT_SHELF_TEMPERATURE_MAX_C = 70.0


def vial_policy_inputs(
    *,
    capability_scale: float = DEFAULT_CAPABILITY_SCALE,
    shelf_temperature_max_c: float = DEFAULT_SHELF_TEMPERATURE_MAX_C,
) -> dict[str, Any]:
    """Return legacy LyoPRONTO dictionaries for the three-policy vial case.

    The product, vial, and heat-transfer values are the 5 % mannitol case used
    throughout the LyoPRONTO comparisons. Only the equipment-capability line and
    the shelf ceiling are retuned, so that all three of the paper's policies
    become active in sequence on the vial-scale model.
    """
    return {
        "vial": {"Av": 3.80, "Ap": 3.14, "Vfill": 3.0},
        "product": {
            "cSolid": 0.05,
            "R0": 1.4,
            "A1": 16.0,
            "A2": 0.0,
            "T_pr_crit": -5.0,
        },
        "ht": {"KC": 2.75e-4, "KP": 8.93e-4, "KD": 0.46},
        "pchamber": {"setpt": [0.15], "dt_setpt": [1800.0], "ramp_rate": 0.5},
        "tshelf": {"min": -45.0, "max": float(shelf_temperature_max_c), "init": -35.0},
        "eq_cap": {
            "a": -0.182 * float(capability_scale),
            "b": 11.7 * float(capability_scale),
        },
        "nvial": 398,
    }


def classify_vial_policies(
    trajectory: np.ndarray,
    data: Mapping[str, Any],
    *,
    temperature_tolerance_c: float = 1.0e-3,
    shelf_tolerance_c: float = 1.0e-3,
    capability_tolerance_kg_hr: float = 1.0e-6,
) -> dict[str, Any]:
    """Label each step of a legacy trajectory with the paper's active policy.

    ``trajectory`` is the seven-column legacy primary-drying array. The columns
    used are 2 (vial-bottom temperature [degC]), 3 (shelf temperature [degC]),
    4 (chamber pressure [mTorr]), and 5 (sublimation flux [kg/hr/m^2]).

    Policy 2 takes precedence over Policy 3 when both limits are simultaneously
    active, matching ``paper_ocp.classify_paper_policies``.
    """
    table = np.asarray(trajectory, dtype=float)
    if table.ndim != 2 or table.shape[1] != 7:
        raise ValueError("trajectory must be a seven-column legacy array")

    time_hr = table[:, 0]
    bottom_temperature_c = table[:, 2]
    shelf_temperature_c = table[:, 3]
    pressure_torr = table[:, 4] / 1000.0
    flux_kg_hr_m2 = table[:, 5]

    eq_cap = data["eq_cap"]
    product_area_m2 = float(data["vial"]["Ap"]) * 1.0e-4
    load_kg_hr = float(data["nvial"]) * flux_kg_hr_m2 * product_area_m2
    capability_kg_hr = float(eq_cap["a"]) + float(eq_cap["b"]) * pressure_torr

    temperature_limit_c = float(data["product"]["T_pr_crit"])
    shelf_max_c = float(data["tshelf"]["max"])

    labels: list[str] = []
    for index in range(table.shape[0]):
        temperature_active = (
            bottom_temperature_c[index] >= temperature_limit_c - temperature_tolerance_c
        )
        capability_active = (
            load_kg_hr[index] >= capability_kg_hr[index] - capability_tolerance_kg_hr
        )
        shelf_active = abs(shelf_temperature_c[index] - shelf_max_c) <= shelf_tolerance_c
        if temperature_active:
            labels.append("policy_2_temperature_tracking")
        elif capability_active:
            labels.append("policy_3_interface_velocity_tracking")
        elif shelf_active:
            labels.append("policy_1_max_heat_input")
        else:
            labels.append("unclassified")

    segments = _compress_labels(time_hr, labels)
    return {
        "labels": labels,
        "segments": segments,
        "switch_times_hr": [segment["start_time_hr"] for segment in segments[1:]],
        "load_kg_hr": load_kg_hr,
        "capability_kg_hr": capability_kg_hr,
    }


def _compress_labels(time_hr: np.ndarray, labels: Sequence[str]) -> list[dict[str, Any]]:
    """Return contiguous label segments with their time spans [hr]."""
    if not len(labels):
        return []

    segments: list[dict[str, Any]] = []
    current = labels[0]
    start_index = 0
    for index in range(1, len(labels)):
        if labels[index] != current:
            segments.append(
                {
                    "label": current,
                    "start_time_hr": float(time_hr[start_index]),
                    "end_time_hr": float(time_hr[index - 1]),
                }
            )
            current = labels[index]
            start_index = index
    segments.append(
        {
            "label": current,
            "start_time_hr": float(time_hr[start_index]),
            "end_time_hr": float(time_hr[-1]),
        }
    )
    return segments


@dataclass(frozen=True)
class VialPolicyRun:
    """A sequential vial-scale optimizer run with its policy classification."""

    trajectory: np.ndarray
    policies: Mapping[str, Any]
    wall_time_s: float
    inputs: Mapping[str, Any]

    @property
    def drying_time_hr(self) -> float:
        """Return the completed drying time [hr]."""
        return float(self.trajectory[-1, 0])

    @property
    def switch_times_hr(self) -> tuple[float, ...]:
        """Return the policy switch times [hr]."""
        return tuple(float(t) for t in self.policies["switch_times_hr"])

    @property
    def policy_sequence(self) -> tuple[str, ...]:
        """Return the ordered policy labels of the run."""
        return tuple(str(segment["label"]) for segment in self.policies["segments"])


def run_vial_policy_case(
    *,
    dt: float = 0.02,
    capability_scale: float = DEFAULT_CAPABILITY_SCALE,
    shelf_temperature_max_c: float = DEFAULT_SHELF_TEMPERATURE_MAX_C,
) -> VialPolicyRun:
    """Run LyoPRONTO's sequential shelf-temperature optimizer and label policies.

    ``opt_Tsh.dry`` maximizes the sublimation rate at each dried-cake state
    subject to the product-temperature limit, the equipment-capability limit, and
    the shelf bounds. That makes it a simulation-based policy method in the same
    sense as the paper's algorithm: the active constraint selects the policy, and
    the policy changes when the active set changes.
    """
    data = vial_policy_inputs(
        capability_scale=capability_scale,
        shelf_temperature_max_c=shelf_temperature_max_c,
    )
    start = perf_counter()
    trajectory = opt_Tsh.dry(
        data["vial"],
        dict(data["product"]),
        data["ht"],
        dict(data["pchamber"]),
        dict(data["tshelf"]),
        float(dt),
        data["eq_cap"],
        data["nvial"],
    )
    wall_time_s = perf_counter() - start
    table = np.asarray(trajectory, dtype=float)
    return VialPolicyRun(
        trajectory=table,
        policies=classify_vial_policies(table, data),
        wall_time_s=float(wall_time_s),
        inputs=data,
    )


POLICY_DISPLAY_NAMES: dict[str, str] = {
    "policy_1_max_heat_input": "Policy 1: maximum heat input",
    "policy_2_temperature_tracking": "Policy 2: product temperature tracking",
    "policy_3_interface_velocity_tracking": "Policy 3: sublimation flux tracking",
    "unclassified": "no active path constraint",
}


def policy_label(name: str) -> str:
    """Return a readable name for a policy label."""
    return POLICY_DISPLAY_NAMES.get(name, name)
