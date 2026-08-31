"""Regression contracts for the recorded IPOPT/POUNCE continuation baselines."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest


BASELINE_DIR = Path(__file__).resolve().parents[1] / "benchmarks/results/pseudosteady_limit"


def _baseline(solver: str) -> dict[str, Any]:
    return json.loads((BASELINE_DIR / f"{solver}.json").read_text(encoding="utf-8"))


def _by_factor(payload: dict[str, Any], problem: str) -> dict[float, dict[str, Any]]:
    return {float(row["factor"]): row for row in payload["results"][problem]}


def test_pounce_baseline_pins_the_release_and_same_nlp_interface() -> None:
    ipopt = _baseline("ipopt")
    pounce = _baseline("pounce")

    assert ipopt["solver"]["solver_name"] == "ipopt"
    assert ipopt["solver"]["solver_version"] == "3.14.16.0"
    assert pounce["solver"] == {
        "pyomo_interface": "ipopt",
        "solver_name": "pounce",
        "solver_version": "0.10.0.0",
        "solver_executable_basename": "pounce",
    }
    assert pounce["discretization"] == ipopt["discretization"]
    assert pounce["nlp_scaling_method"] == ipopt["nlp_scaling_method"]


@pytest.mark.parametrize("problem", ["problem1", "problem2"])
def test_pounce_matches_ipopt_on_every_shared_successful_rung(problem: str) -> None:
    ipopt = _by_factor(_baseline("ipopt"), problem)
    pounce = _by_factor(_baseline("pounce"), problem)
    shared_successes = [
        factor
        for factor in ipopt.keys() & pounce.keys()
        if ipopt[factor]["converged"] and pounce[factor]["converged"]
    ]

    assert sorted(shared_successes, reverse=True) == [1.0, 0.5, 0.2, 0.1, 0.05]
    for factor in shared_successes:
        ipopt_row = ipopt[factor]
        pounce_row = pounce[factor]
        assert pounce_row["endpoint_hr"] == pytest.approx(
            ipopt_row["endpoint_hr"], abs=2.0e-5
        )
        assert pounce_row["max_product_temperature_K"] == pytest.approx(
            ipopt_row["max_product_temperature_K"], abs=2.0e-6
        )
        assert (
            pounce_row["convergence_quality"]
            == ipopt_row["convergence_quality"]
            == "accepted_at_acceptable_tol"
        )
        # Pyomo maps the same acceptable-level termination to different status
        # fields for these two ASL binaries. The scientific comparison keys on
        # termination, quality, feasibility, and the extracted solution.
        assert ipopt_row["solver_status"] == "ok"
        assert pounce_row["solver_status"] == "warning"


def test_pounce_0100_stops_one_rung_before_ipopt_on_problem1() -> None:
    ipopt = _by_factor(_baseline("ipopt"), "problem1")
    pounce = _by_factor(_baseline("pounce"), "problem1")

    assert ipopt[0.02]["converged"] is True
    assert pounce[0.02]["converged"] is False
    assert pounce[0.02]["termination_condition"] == "infeasible"
    assert "InfeasibleProblemDetected" in pounce[0.02]["solver_message"]
    assert 0.01 in ipopt
    assert 0.01 not in pounce


def test_both_solvers_stop_at_the_same_problem2_rung() -> None:
    ipopt = _by_factor(_baseline("ipopt"), "problem2")
    pounce = _by_factor(_baseline("pounce"), "problem2")

    assert ipopt[0.02]["converged"] is False
    assert pounce[0.02]["converged"] is False
    assert pounce[0.02]["termination_condition"] == "infeasible"
