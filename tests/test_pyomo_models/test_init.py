# Copyright (C) 2026, SECQUOIA

"""Tests for the Pyomo models package initializer."""

from importlib.machinery import ModuleSpec

from lyopronto import pyomo_models


def test_pyomo_available_is_bool():
    assert isinstance(pyomo_models.PYOMO_AVAILABLE, bool)


def test_pyomo_available_exported():
    assert "PYOMO_AVAILABLE" in pyomo_models.__all__


def test_pyomo_exports_optimizers_when_pyomo_available():
    expected_exports = {
        "create_single_step_model",
        "solve_single_step",
        "optimize_single_step",
        "create_multi_period_model",
        "optimize_multi_period",
        "warmstart_from_scipy_trajectory",
        "optimize_Tsh_pyomo",
        "optimize_Pch_pyomo",
        "optimize_Pch_Tsh_pyomo",
        "PaperPrimaryDryingConfig",
        "PaperDiscretization",
        "create_paper_problem1_model",
        "generate_problem1_policy_initialization",
        "initialize_paper_problem1_from_trajectory",
        "load_upstream_matlab_trajectory",
        "compare_paper_problem1_trajectories",
        "solve_paper_problem1",
        "classify_paper_policies",
    }

    if pyomo_models.PYOMO_AVAILABLE:
        assert expected_exports.issubset(pyomo_models.__all__)
    else:
        assert expected_exports.isdisjoint(pyomo_models.__all__)


def test_pyomo_available_false_when_pyomo_missing(monkeypatch):
    monkeypatch.setattr(pyomo_models, "find_spec", lambda name: None)

    assert pyomo_models._is_pyomo_available() is False


def test_pyomo_available_true_when_pyomo_present(monkeypatch):
    monkeypatch.setattr(
        pyomo_models,
        "find_spec",
        lambda name: ModuleSpec(name="pyomo", loader=None),
    )

    assert pyomo_models._is_pyomo_available() is True
