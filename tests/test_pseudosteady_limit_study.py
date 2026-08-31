"""Tests for the pseudosteady-limit continuation study.

Most of these cover the study's own logic with no solver calls, so they run in
the fast lane. The scaling-relation tests build models but do not solve them.
"""

from __future__ import annotations

import dataclasses
import os

import numpy as np
import pytest

from examples.pseudosteady_limit_study import (
    DEFAULT_LADDER,
    PROBLEMS,
    SUCCESS_TERMINATIONS,
    RungResult,
    conduction_time_s,
    endpoint_shift_percent,
    format_results,
    format_rung_progress,
    ode_residual_times_thickness_squared,
    run_ladder,
    scaled_config,
    solver_provenance,
)
from lyopronto.pyomo_models import paper_ocp

pyo = pytest.importorskip("pyomo.environ", reason="Pyomo not available")


def test_ladder_descends_toward_the_pseudosteady_limit() -> None:
    """The ladder must start at the paper's model and only ever reduce Cp."""
    assert DEFAULT_LADDER[0] == 1.0
    assert list(DEFAULT_LADDER) == sorted(DEFAULT_LADDER, reverse=True)
    assert all(factor > 0.0 for factor in DEFAULT_LADDER)


def test_scaling_touches_only_the_heat_capacity() -> None:
    """Cp_f scales exactly; every other configured quantity is untouched."""
    base = paper_ocp.PaperPrimaryDryingConfig()
    scaled = scaled_config(0.25)

    base_derived = paper_ocp.derive_primary_drying_parameters(base, n_z=5)
    scaled_derived = paper_ocp.derive_primary_drying_parameters(scaled, n_z=5)

    assert np.isclose(
        scaled_derived.frozen_heat_capacity,
        0.25 * base_derived.frozen_heat_capacity,
    )
    assert np.isclose(
        scaled_derived.frozen_conductivity, base_derived.frozen_conductivity
    )
    assert np.isclose(scaled_derived.frozen_density, base_derived.frozen_density)
    assert np.isclose(scaled_derived.product_height, base_derived.product_height)
    # alpha = k / (rho Cp), so it scales inversely.
    assert np.isclose(
        scaled_derived.frozen_diffusivity,
        base_derived.frozen_diffusivity / 0.25,
    )


def test_conduction_time_shrinks_with_the_scale_factor() -> None:
    """Smaller Cp means faster equilibration, which is the point of the ladder."""
    full = conduction_time_s(scaled_config(1.0), n_z=5)
    reduced = conduction_time_s(scaled_config(0.1), n_z=5)

    assert np.isclose(reduced, 0.1 * full)


@pytest.mark.parametrize("factor", [0.0, -1.0])
def test_scaling_rejects_a_nonpositive_factor(factor: float) -> None:
    with pytest.raises(ValueError, match="must be positive"):
        scaled_config(factor)


def test_run_ladder_rejects_an_unknown_problem_before_solving() -> None:
    with pytest.raises(ValueError, match="unsupported paper problem"):
        run_ladder("problem3")


# --------------------------------------------------------------------------
# The scaling relation the study rests on
# --------------------------------------------------------------------------

_SCALE = 0.25


def _rhs_at_shared_state(config, *, dsdt: float) -> dict:
    """Evaluate temperature_rhs on one fixed nonuniform state.

    ``temperature_ode`` is ``dT_dtau - t_final * rhs``, so pinning
    ``dT_dtau = 0`` and ``t_final = 1`` makes the constraint body ``-rhs``.
    """
    discretization = paper_ocp.PaperDiscretization(n_z=8, nfe=4, ncp=2)
    model = paper_ocp.create_paper_problem1_model(config, discretization)
    height = model._paper_derived.product_height
    for t in model.t:
        for i in model.z:
            model.T[i, t].set_value(230.0 + 8.0 * np.sin(3.0 * i + 2.0 * float(t)))
        model.S[t].set_value(0.4 * height * (0.2 + float(t)))
        model.Tb[t].set_value(250.0)
        model.dSdt[t].set_value(dsdt)
        for i in model.z:
            model.dT_dtau[i, t].set_value(0.0)
    model.t_final.set_value(1.0)
    return {key: -pyo.value(model.temperature_ode[key].body) for key in model.temperature_ode}


def test_scaling_is_exact_only_when_the_front_is_stationary() -> None:
    """With dS/dt = 0 the transformed RHS scales exactly by 1/f.

    This is the precise form of the study's premise. The moving-coordinate term
    is the only part of temperature_rhs that does not carry 1/(rho Cp).
    """
    base = _rhs_at_shared_state(paper_ocp.PaperPrimaryDryingConfig(), dsdt=0.0)
    scaled = _rhs_at_shared_state(scaled_config(_SCALE), dsdt=0.0)

    mismatch = max(abs(_SCALE * scaled[k] - base[k]) for k in base)

    assert mismatch == 0.0


def test_a_moving_front_breaks_the_naive_scaling_claim() -> None:
    """With dS/dt != 0 the relation is f*rhs_scaled = rhs_base + (f-1)*convection.

    Pinned so nobody restores the simpler but false claim that scaling Cp is
    equivalent to solving f*dT/dt = RHS.
    """
    base = _rhs_at_shared_state(paper_ocp.PaperPrimaryDryingConfig(), dsdt=3.0e-7)
    scaled = _rhs_at_shared_state(scaled_config(_SCALE), dsdt=3.0e-7)

    mismatch = max(abs(_SCALE * scaled[k] - base[k]) for k in base)

    assert mismatch > 1.0e-6, "the moving-front term must show up as a real mismatch"
    typical = np.median([abs(v) for v in base.values()])
    assert mismatch / typical < 1.0e-3, (
        "the deviation should stay small relative to the RHS for this vial"
    )


# --------------------------------------------------------------------------
# The ODE diagnostic is not a feasibility test
# --------------------------------------------------------------------------


def test_ode_diagnostic_would_accept_a_huge_residual_near_the_cutoff() -> None:
    """Document why this quantity carries no feasibility verdict.

    At the default terminal thickness the (H - S)^2 factor is about 1.3e-9, so
    even a 100 K residual maps below any small threshold. This is the
    over-acceptance the metric must never be used to decide.
    """
    discretization = paper_ocp.PaperDiscretization(n_z=5, nfe=2, ncp=2)
    model = paper_ocp.create_paper_problem1_model(None, discretization)
    height = model._paper_derived.product_height
    terminal_thickness = height * (1.0 - discretization.terminal_drying_fraction)

    scaled_residual = 100.0 * terminal_thickness**2

    assert terminal_thickness < 1.0e-4
    assert scaled_residual < 1.0e-6, (
        "a 100 K residual maps under 1e-6, which is why there is no verdict here"
    )


def test_constraint_violation_covers_bounds_not_just_constraints() -> None:
    """A bound violation is a feasibility failure no Constraint object reports.

    The reviewer's point on #141: an interface position driven past the product
    height must not pass a feasibility measure. Pyomo records that as a variable
    bound, so a constraints-only scan would miss it entirely. Checked on a
    minimal model so the assertion isolates bound handling rather than competing
    with residuals from an arbitrary state of the paper model.
    """
    from examples.pseudosteady_limit_study import max_constraint_violation

    model = pyo.ConcreteModel()
    model.x = pyo.Var(bounds=(0.0, 1.0), initialize=0.5)
    model.y = pyo.Var(initialize=0.5)
    model.balance = pyo.Constraint(expr=model.x == model.y)

    assert max_constraint_violation(model) == pytest.approx(0.0)

    # Constraint still satisfied; only the upper bound is broken.
    model.x.set_value(4.0)
    model.y.set_value(4.0)

    assert max_constraint_violation(model) == pytest.approx(3.0)


def test_ode_diagnostic_returns_nan_without_the_constraint() -> None:
    """A model lacking temperature_ode must not silently report zero."""

    class _Bare:
        pass

    assert np.isnan(ode_residual_times_thickness_squared(_Bare()))


# --------------------------------------------------------------------------
# Result records and reporting
# --------------------------------------------------------------------------


def _rung(factor: float, endpoint: float | None, converged: bool = True) -> RungResult:
    message = (
        "Ipopt 3.14.16: Solved To Acceptable Level."
        if converged
        else "Ipopt 3.14.16: Maximum Number of Iterations Exceeded."
    )
    return RungResult(
        problem="problem1",
        factor=factor,
        conduction_time_s=46.9 * factor,
        converged=converged,
        endpoint_hr=endpoint,
        max_product_temperature_K=243.0,
        termination_condition="optimal" if converged else "maxIterations",
        solver_status="ok" if converged else "warning",
        solver_message=message,
        max_constraint_violation=2.48e-4,
        ode_residual_times_thickness_squared_K_m2=4.95e-13,
        # Classified rather than hard-coded so the fixture cannot claim a
        # quality its own message does not support.
        convergence_quality=paper_ocp.classify_convergence_quality(message),
    )


def test_success_terminations_exclude_failure_states() -> None:
    assert "optimal" in SUCCESS_TERMINATIONS
    for bad in ("infeasible", "maxiterations", "maxtimelimit", "error", "unbounded"):
        assert bad not in SUCCESS_TERMINATIONS


def test_endpoint_shift_uses_the_converged_rungs_only() -> None:
    rungs = [_rung(1.0, 6.1865), _rung(0.5, 6.1669), _rung(0.2, 6.10, converged=False)]

    shift = endpoint_shift_percent(rungs)

    assert shift == pytest.approx((6.1669 - 6.1865) / 6.1865 * 100.0)


def test_endpoint_shift_is_undefined_with_fewer_than_two_solves() -> None:
    assert endpoint_shift_percent([_rung(1.0, 6.1865)]) is None
    assert endpoint_shift_percent([]) is None


def test_a_non_success_rung_keeps_its_solver_metadata() -> None:
    """Issue #140 requires per-rung termination and message, including failures."""
    rung = _rung(0.2, 6.10, converged=False)
    record = rung.as_dict()

    assert record["converged"] is False
    assert record["termination_condition"] == "maxIterations"
    assert record["solver_status"] == "warning"
    assert "Maximum Number of Iterations" in record["solver_message"]
    assert record["max_constraint_violation"] is not None


def test_format_reports_a_failed_rung_and_its_message() -> None:
    rungs = [_rung(1.0, 6.1865), _rung(0.5, 6.10, converged=False)]

    text = format_results({"problem1": rungs})

    assert "NOT CONVERGED" in text
    assert "Maximum Number of Iterations" in text


def test_format_labels_the_ode_diagnostic_with_its_units() -> None:
    """The column must not read as a dimensionless feasibility measure."""
    text = format_results({"problem1": [_rung(1.0, 6.1865)]})

    assert "odeK_m2=" in text
    assert "feasible" not in text


def test_an_acceptable_level_rung_is_reported_as_such_not_only_as_converged() -> None:
    """Issue #146: `converged` alone reads as convergence to `tol`.

    Every converged rung of the recorded IPOPT baseline stopped at
    `acceptable_tol` while reporting `optimal/ok`, so the record and the report
    line must both name the level rather than leaving it to the raw message.
    """
    rung = _rung(1.0, 6.1865)
    record = rung.as_dict()

    assert record["converged"] is True
    assert record["termination_condition"] == "optimal"
    assert record["convergence_quality"] == paper_ocp.ACCEPTED_AT_ACCEPTABLE_TOL

    text = format_results({"problem1": [rung]})
    assert f"quality={paper_ocp.ACCEPTED_AT_ACCEPTABLE_TOL}" in text
    # The distinction is worthless if the tighter label also appears.
    assert paper_ocp.CONVERGED_TO_TOLERANCE not in text


def test_the_report_separates_the_two_convergence_levels() -> None:
    """A tolerance-converged rung and an acceptable-level one must not read alike."""
    tight_message = "Ipopt 3.14.16: Optimal Solution Found"
    tight = dataclasses.replace(
        _rung(1.0, 6.1865),
        solver_message=tight_message,
        # Classified from the message, as `_rung` does, so neither side of the
        # comparison can claim a quality its own message does not support.
        convergence_quality=paper_ocp.classify_convergence_quality(tight_message),
    )
    loose = _rung(0.5, 6.1669)

    text = format_results({"problem1": [tight, loose]})
    # The trailing summary line also names both factors, so select the rung
    # lines by the column under test rather than by the factor.
    tight_line, loose_line = [line for line in text.splitlines() if "quality=" in line]

    # Both are `optimal/ok ok`; only the quality tells them apart.
    assert "optimal/ok ok" in tight_line and "optimal/ok ok" in loose_line
    assert f"quality={paper_ocp.CONVERGED_TO_TOLERANCE}" in tight_line
    assert f"quality={paper_ocp.ACCEPTED_AT_ACCEPTABLE_TOL}" in loose_line


def test_the_streamed_progress_line_states_the_convergence_level_too() -> None:
    """The line watched during a long run must not read `optimal/ok` alone.

    It is emitted per rung while the ladder is still solving, so it is where an
    operator first reads the result of a rung.
    """
    line = format_rung_progress(_rung(0.5, 6.1669))

    assert "optimal/ok ok" in line
    assert f"quality={paper_ocp.ACCEPTED_AT_ACCEPTABLE_TOL}" in line
    assert "endpoint=6.1669 hr" in line


def test_the_streamed_progress_line_handles_a_rung_with_no_endpoint() -> None:
    """An `error` rung streams before the ladder stops, so it must not raise."""
    line = format_rung_progress(
        RungResult(
            problem="problem1",
            factor=0.01,
            conduction_time_s=0.469,
            converged=False,
            termination_condition="error",
            solver_status="error",
        )
    )

    assert "NOT CONVERGED" in line
    assert "endpoint=n/a" in line
    assert f"quality={paper_ocp.CONVERGENCE_QUALITY_UNKNOWN}" in line


def test_a_rung_with_no_solve_reports_unknown_quality() -> None:
    """An `error` rung met no tolerance at all, so it must claim none."""
    error_rung = RungResult(
        problem="problem1",
        factor=0.01,
        conduction_time_s=0.469,
        converged=False,
        termination_condition="error",
        solver_status="error",
        solver_message="Cannot load a SolverResults object with bad status: error",
    )

    assert error_rung.convergence_quality == paper_ocp.CONVERGENCE_QUALITY_UNKNOWN
    assert (
        f"quality={paper_ocp.CONVERGENCE_QUALITY_UNKNOWN}"
        in format_results({"problem1": [error_rung]})
    )


def test_rung_record_has_no_feasibility_verdict() -> None:
    """Removed deliberately: see RungResult's docstring."""
    record = _rung(1.0, 6.1865).as_dict()

    assert "feasible" not in record
    assert "ode_residual_times_thickness_squared_K_m2" in record


def test_problems_cover_both_paper_cases() -> None:
    assert set(PROBLEMS) == {"problem1", "problem2"}


# --------------------------------------------------------------------------
# Provenance
# --------------------------------------------------------------------------


def test_provenance_separates_interface_from_solver_identity() -> None:
    """A POUNCE run driven through the ipopt interface must not report as IPOPT."""
    record = solver_provenance("ipopt", "/somewhere/else/pounce")

    assert record["pyomo_interface"] == "ipopt"
    assert record["solver_executable_basename"] == "pounce"
    assert "/somewhere/else" not in json_safe(record)


def test_provenance_records_no_absolute_host_paths() -> None:
    """Baselines are committed, so host-specific paths must not leak into them."""
    record = solver_provenance("ipopt", None)

    text = json_safe(record)
    assert "/home/" not in text
    assert "/tmp/" not in text


def json_safe(record: dict) -> str:
    import json

    return json.dumps(record)


def test_rung_dataclass_is_frozen() -> None:
    """Recorded results must not be mutated after the fact."""
    rung = _rung(1.0, 6.1865)
    with pytest.raises(dataclasses.FrozenInstanceError):
        rung.factor = 2.0  # type: ignore[misc]


# --------------------------------------------------------------------------
# run_ladder against solver outcomes
# --------------------------------------------------------------------------


def _stub_solution(termination: str, status: str, message: str) -> dict:
    """A solve return shaped like paper_ocp's, carrying a chosen termination."""
    model = paper_ocp.create_paper_problem1_model(
        None, paper_ocp.PaperDiscretization(n_z=5, nfe=2, ncp=2)
    )
    for t in model.t:
        for i in model.z:
            model.T[i, t].set_value(230.0)
            model.dT_dtau[i, t].set_value(0.0)
        model.S[t].set_value(0.0)
        model.dSdt[t].set_value(0.0)
        model.Tb[t].set_value(250.0)
    model.t_final.set_value(3600.0)
    return {
        "states": {"time_hr": [0.0, 1.0], "temperature_K": [[230.0], [230.0]]},
        "metrics": {"max_product_temperature_K": 243.0},
        "metadata": {
            "termination_condition": termination,
            "status": status,
            "message": message,
            "convergence_quality": paper_ocp.classify_convergence_quality(message),
        },
        "model": model,
    }


def test_run_ladder_records_a_non_success_result_and_stops(monkeypatch) -> None:
    """A genuine non-success return must be recorded, not raised past or dropped.

    Issue #140 requires per-rung termination and message on the rung that ends
    the ladder. Restoring require_success=True would raise here instead.
    """
    calls: list[dict] = []

    def fake_solve(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            return _stub_solution("optimal", "ok", "Ipopt: Optimal Solution Found.")
        return _stub_solution(
            "maxIterations", "warning", "Ipopt: Maximum Number of Iterations Exceeded."
        )

    monkeypatch.setattr(paper_ocp, "solve_paper_problem1", fake_solve)

    results = run_ladder("problem1", ladder=(1.0, 0.5, 0.2))

    # Stopped at the failure rather than continuing down the ladder.
    assert len(results) == 2
    assert [r.converged for r in results] == [True, False]

    failed = results[-1]
    assert failed.termination_condition == "maxIterations"
    assert failed.solver_status == "warning"
    assert "Maximum Number of Iterations" in failed.solver_message
    assert failed.max_constraint_violation is not None

    # The solve must have been asked not to raise, or this rung never returns.
    assert calls[0]["require_success"] is False


def test_run_ladder_carries_the_quality_extraction_already_computed(
    monkeypatch,
) -> None:
    """Issue #146: the study reads `paper_ocp`'s label, not the solver text.

    Both rungs return `optimal/ok`, so the recorded quality is the only field
    that separates the acceptable-level solve from the tolerance-converged one.
    """
    messages = iter(
        [
            "Ipopt 3.14.16: Optimal Solution Found",
            "Ipopt 3.14.16: Solved To Acceptable Level.",
        ]
    )

    def fake_solve(**kwargs):
        return _stub_solution("optimal", "ok", next(messages))

    monkeypatch.setattr(paper_ocp, "solve_paper_problem1", fake_solve)

    results = run_ladder("problem1", ladder=(1.0, 0.5))

    assert [r.converged for r in results] == [True, True]
    assert [r.convergence_quality for r in results] == [
        paper_ocp.CONVERGED_TO_TOLERANCE,
        paper_ocp.ACCEPTED_AT_ACCEPTABLE_TOL,
    ]


def test_run_ladder_propagates_an_invalid_executable() -> None:
    """A configuration error must abort the study rather than become a datum.

    Recording it as a non-converged rung would publish a benchmark artifact
    describing a solver that never ran.
    """
    with pytest.raises(Exception) as failure:
        run_ladder(
            "problem1",
            ladder=(1.0,),
            discretization=paper_ocp.PaperDiscretization(n_z=5, nfe=2, ncp=2),
            solver_executable="/nonexistent/definitely-not-a-solver",
        )

    # Not the study's own ValueError guard: this must come from solver resolution.
    assert not isinstance(failure.value, ValueError) or "unsupported" not in str(
        failure.value
    )


# --------------------------------------------------------------------------
# Provenance against the real solver
# --------------------------------------------------------------------------


@pytest.mark.pyomo
def test_provenance_reports_the_real_installed_solver_version() -> None:
    """Assert the actual identity and version, so a corrupted record fails.

    A provenance test that only checks the keys exist would pass with the name
    and version replaced by anything at all.
    """
    opt = pyo.SolverFactory("ipopt")
    if not opt.available(exception_flag=False):
        pytest.skip("IPOPT is not installed in this environment")

    expected_version = ".".join(str(part) for part in opt.version())
    record = solver_provenance("ipopt", None)

    assert record["solver_version"] == expected_version
    assert record["solver_name"] == "ipopt"
    assert record["pyomo_interface"] == "ipopt"


@pytest.mark.pyomo
def test_provenance_names_the_executable_not_the_interface() -> None:
    """A solver driven through the ipopt interface must report its own identity."""
    opt = pyo.SolverFactory("ipopt")
    if not opt.available(exception_flag=False):
        pytest.skip("IPOPT is not installed in this environment")
    executable = opt.executable()

    record = solver_provenance("ipopt", executable)

    assert record["solver_name"] == os.path.basename(executable)
    assert record["solver_version"] == ".".join(str(p) for p in opt.version())
    assert record["solver_executable_basename"] == os.path.basename(executable)


def test_unloadable_solver_result_is_recorded_not_raised(monkeypatch) -> None:
    """A solver that runs and returns garbage is an endpoint, not a crash.

    Pyomo raises `bad status` when the solver produced a result it refuses to
    load. That is how the IPOPT ladder actually ends at the paper mesh, so it
    must be recorded rather than discarding every rung solved before it.
    """
    calls: list[int] = []

    def fake_solve(**kwargs):
        calls.append(1)
        if len(calls) == 1:
            return _stub_solution("optimal", "ok", "Ipopt: Optimal Solution Found.")
        raise ValueError("Cannot load a SolverResults object with bad status: error")

    monkeypatch.setattr(paper_ocp, "solve_paper_problem1", fake_solve)

    results = run_ladder("problem1", ladder=(1.0, 0.5, 0.2))

    assert len(results) == 2
    terminal = results[-1]
    assert terminal.converged is False
    assert terminal.termination_condition == "error"
    assert terminal.solver_status == "error"
    assert "bad status" in terminal.solver_message
    # The rung that solved is preserved, which is the point.
    assert results[0].converged is True


def test_other_value_errors_still_propagate(monkeypatch) -> None:
    """Only the solver-returned-garbage case is absorbed; bugs must surface."""

    def fake_solve(**kwargs):
        raise ValueError("some programming error in the model builder")

    monkeypatch.setattr(paper_ocp, "solve_paper_problem1", fake_solve)

    with pytest.raises(ValueError, match="programming error"):
        run_ladder("problem1", ladder=(1.0,))


def test_format_handles_a_rung_with_no_solution_values() -> None:
    """An `error` rung carries no endpoint, temperature, or residuals.

    Formatting it must not raise: that would discard the whole ladder at the
    point the study is trying to report where it stopped.
    """
    error_rung = RungResult(
        problem="problem1",
        factor=0.01,
        conduction_time_s=0.469,
        converged=False,
        termination_condition="error",
        solver_status="error",
        solver_message="Cannot load a SolverResults object with bad status: error",
    )

    text = format_results({"problem1": [_rung(1.0, 6.1865), error_rung]})

    assert "endpoint=n/a" in text
    assert "maxT=n/a" in text
    assert "viol=n/a" in text
    assert "error/error" in text
    assert "bad status" in text
