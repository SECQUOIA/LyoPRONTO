"""Cheap tests for the paper GDP comparison example."""

from __future__ import annotations

import numpy as np
import pytest

from examples.paper_gdp_validation import run_paper_gdp_validation
from lyopronto.pyomo_models.paper_gdp import paper_gdp_comparison_rows


def test_validation_example_rejects_an_unknown_problem_before_solver_use() -> None:
    with pytest.raises(ValueError, match="unsupported paper problem"):
        run_paper_gdp_validation("problem3")


def _comparison_fixtures() -> tuple[dict, dict, dict]:
    gdp = {
        "problem": {"terminal_drying_fraction": 0.995},
        "metrics": {
            "solver_endpoint_time_hr": 6.18,
            "complete_drying_time_hr": 6.24,
        },
        "policies": {
            "indicator_sequence": ("policy_1", "policy_2"),
            "switch_times_hr": (2.37,),
        },
    }
    continuous = {
        "derived": {"product_height": 1.0},
        "problem": {"terminal_drying_fraction_target": 0.995},
        "metrics": {
            "drying_time_hr": 6.18,
            "terminal_interface_position_m": 0.99,
        },
        "states": {"interface_velocity_m_per_s": [1.0, 1.0 / 3600.0]},
        "policies": {
            "segments": [{"label": "policy_1"}, {"label": "policy_2"}],
            "switch_times_hr": (2.35,),
        },
    }
    paper = {
        "drying_time_hr": 6.2,
        "policy_sequence": ("policy_1", "policy_2"),
        "switch_times_hr": (2.4,),
    }
    return gdp, continuous, paper


def test_comparison_rows_keep_paper_nlp_and_gdp_results_distinct() -> None:
    """The compact table preserves endpoint and policy provenance."""
    gdp, continuous, paper = _comparison_fixtures()

    rows = paper_gdp_comparison_rows(gdp, continuous, paper)

    assert rows[0]["quantity"] == "drying time to S=0.995H [hr]"
    assert np.isnan(rows[0]["paper"])
    assert np.isclose(rows[0]["continuous_nlp"], 6.18)
    assert np.isclose(rows[0]["gdp"], 6.18)
    assert rows[1]["quantity"] == "drying time to S=H [hr]"
    assert np.isclose(rows[1]["paper"], 6.2)
    assert np.isclose(rows[1]["continuous_nlp"], 6.19)
    assert np.isclose(rows[1]["gdp"], 6.24)
    assert rows[2:] == [
        {
            "quantity": "policy sequence",
            "paper": ("policy_1", "policy_2"),
            "continuous_nlp": ("policy_1", "policy_2"),
            "gdp": ("policy_1", "policy_2"),
        },
        {
            "quantity": "switch times [hr]",
            "paper": (2.4,),
            "continuous_nlp": (2.35,),
            "gdp": (2.37,),
        },
    ]



def test_comparison_rows_reject_mismatched_terminal_fractions() -> None:
    """Endpoint rows from differently targeted runs must not be mixed."""
    gdp, continuous, paper = _comparison_fixtures()
    continuous["problem"]["terminal_drying_fraction_target"] = 0.99

    with pytest.raises(ValueError, match="different terminal drying"):
        paper_gdp_comparison_rows(gdp, continuous, paper)
