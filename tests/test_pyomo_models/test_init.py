# Copyright (C) 2026, SECQUOIA

"""Tests for the Pyomo models package initializer."""

from importlib.machinery import ModuleSpec

from lyopronto import pyomo_models


def test_pyomo_available_is_bool():
    assert isinstance(pyomo_models.PYOMO_AVAILABLE, bool)


def test_pyomo_available_exported():
    assert pyomo_models.__all__ == ["PYOMO_AVAILABLE"]


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
