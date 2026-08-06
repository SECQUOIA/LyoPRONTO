"""Tests for the pseudosteady-limit continuation study.

These cover the study's own logic (scaling, reporting, argument handling) with
no solver calls, so they run in the fast lane. The solves themselves are
exercised by the recorded baselines under ``benchmarks/results/``.
"""

from __future__ import annotations

import numpy as np
import pytest

from examples.pseudosteady_limit_study import (
    DEFAULT_LADDER,
    FEASIBILITY_TOL,
    PROBLEMS,
    RungResult,
    conduction_time_s,
    endpoint_shift_percent,
    format_results,
    run_ladder,
    scaled_config,
)
from lyopronto.pyomo_models import paper_ocp


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
    # Conductivity, densities, and geometry must not move with the scale factor,
    # otherwise the ladder would vary more than the transient term.
    assert np.isclose(scaled_derived.frozen_conductivity, base_derived.frozen_conductivity)
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


def _rung(
    factor: float,
    endpoint: float | None,
    converged: bool = True,
    violation: float | None = 1.0e-9,
    cleared: float | None = 1.0e-13,
) -> RungResult:
    return RungResult(
        problem="problem1",
        factor=factor,
        conduction_time_s=46.9 * factor,
        converged=converged,
        endpoint_hr=endpoint,
        max_product_temperature_K=243.0 if converged else None,
        termination_condition="optimal" if converged else None,
        solver_status="ok" if converged else None,
        max_constraint_violation=violation if converged else None,
        max_landau_cleared_violation=cleared if converged else None,
        failure=None if converged else "RuntimeError: did not converge",
    )


def test_endpoint_shift_uses_the_converged_rungs_only() -> None:
    """A failed tail rung must not be read as an endpoint."""
    rungs = [_rung(1.0, 6.1865), _rung(0.5, 6.1669), _rung(0.2, None, converged=False)]

    shift = endpoint_shift_percent(rungs)

    assert shift == pytest.approx((6.1669 - 6.1865) / 6.1865 * 100.0)


def test_endpoint_shift_is_undefined_with_fewer_than_two_solves() -> None:
    assert endpoint_shift_percent([_rung(1.0, 6.1865)]) is None
    assert endpoint_shift_percent([]) is None


def test_format_reports_a_failed_rung_rather_than_hiding_it() -> None:
    """Where the ladder stops is a result, so it must appear in the output."""
    rungs = [_rung(1.0, 6.1865), _rung(0.5, None, converged=False)]

    text = format_results({"problem1": rungs})

    assert "DID NOT CONVERGE" in text
    assert "did not converge" in text
    assert "f=1" in text


def test_format_reports_termination_and_status_per_rung() -> None:
    """Acceptable-level terminations must stay visible, not collapse to success."""
    rung = RungResult(
        problem="problem1",
        factor=1.0,
        conduction_time_s=46.9,
        converged=True,
        endpoint_hr=6.1865,
        max_product_temperature_K=243.0,
        termination_condition="optimal",
        solver_status="warning",
    )

    text = format_results({"problem1": [rung]})

    assert "optimal/warning" in text


def test_problems_cover_both_paper_cases() -> None:
    assert set(PROBLEMS) == {"problem1", "problem2"}


def test_feasibility_verdict_uses_the_scale_corrected_residual() -> None:
    """The absolute violation cannot decide feasibility for this transcription.

    The Landau coordinate makes the conduction term carry ``1/(H - S)^2``, so a
    well-converged solve still shows an absolute violation around 1e-4. Judging
    on that number would mark every rung infeasible; judging on the cleared one
    reflects what the solver actually achieved.
    """
    rung = _rung(1.0, 6.1865, violation=2.48e-4, cleared=4.95e-13)

    assert rung.max_constraint_violation > FEASIBILITY_TOL
    assert rung.feasible is True


def test_a_genuinely_bad_solve_is_reported_infeasible() -> None:
    """A large cleared residual must still fail the verdict."""
    rung = _rung(1.0, 6.1865, violation=2.48e-4, cleared=1.0e-2)

    assert rung.feasible is False


def test_rung_dict_carries_both_residual_measures() -> None:
    """Recorded baselines must keep both numbers, not just the verdict."""
    record = _rung(1.0, 6.1865, violation=2.48e-4, cleared=4.95e-13).as_dict()

    assert record["max_constraint_violation"] == pytest.approx(2.48e-4)
    assert record["max_landau_cleared_violation"] == pytest.approx(4.95e-13)
    assert record["feasible"] is True
