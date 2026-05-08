# Copyright (C) 2026, SECQUOIA

"""Tests for parameter validation in create_optimizer_model.

This module tests that the Pyomo optimizer model creation properly validates
input parameters and raises appropriate errors for invalid configurations.
"""

import pytest

pyo = pytest.importorskip("pyomo.environ", reason="Pyomo not installed")

pytestmark = [
    pytest.mark.pyomo,
]

from lyopronto.pyomo_models.optimizers import create_optimizer_model


class TestParameterValidation:
    """Tests for parameter validation in create_optimizer_model."""

    @pytest.fixture
    def base_params(self):
        """Common test parameters for model creation."""
        return {
            "vial": {"Av": 3.8, "Ap": 3.14, "Vfill": 2.0},
            "product": {
                "R0": 1.4,
                "A1": 16.0,
                "A2": 0.0,
                "T_pr_crit": -5.0,
                "cSolid": 0.05,
            },
            "ht": {"KC": 0.000275, "KP": 0.000893, "KD": 0.46},
            "eq_cap": {"a": -0.182, "b": 11.7},
            "nVial": 398,
        }

    def test_invalid_control_mode_raises_error(self, base_params):
        """Test that invalid control_mode raises ValueError."""
        with pytest.raises(ValueError, match="control_mode"):
            create_optimizer_model(
                base_params["vial"],
                base_params["product"],
                base_params["ht"],
                base_params["vial"]["Vfill"],
                base_params["eq_cap"],
                base_params["nVial"],
                control_mode="invalid",
                n_elements=2,
            )

    def test_pch_mode_without_bounds_raises_error(self, base_params):
        """Test that control_mode='Pch' without Pchamber bounds raises ValueError."""
        with pytest.raises(ValueError, match="bounds|Pch"):
            create_optimizer_model(
                base_params["vial"],
                base_params["product"],
                base_params["ht"],
                base_params["vial"]["Vfill"],
                base_params["eq_cap"],
                base_params["nVial"],
                control_mode="Pch",
                Tshelf={"init": -35, "setpt": [20], "dt_setpt": [1800]},
                n_elements=2,
            )

    def test_tsh_mode_without_bounds_raises_error(self, base_params):
        """Test that control_mode='Tsh' without Tshelf bounds raises ValueError."""
        with pytest.raises(ValueError, match="bounds|Tsh"):
            create_optimizer_model(
                base_params["vial"],
                base_params["product"],
                base_params["ht"],
                base_params["vial"]["Vfill"],
                base_params["eq_cap"],
                base_params["nVial"],
                control_mode="Tsh",
                Pchamber={"setpt": [0.1], "dt_setpt": [1800], "ramp_rate": 0.5},
                n_elements=2,
            )

    def test_both_mode_without_pchamber_bounds_raises_error(self, base_params):
        """Test that control_mode='both' without Pchamber bounds raises ValueError."""
        with pytest.raises(ValueError, match="bounds|Pch"):
            create_optimizer_model(
                base_params["vial"],
                base_params["product"],
                base_params["ht"],
                base_params["vial"]["Vfill"],
                base_params["eq_cap"],
                base_params["nVial"],
                control_mode="both",
                Tshelf={"min": -45, "max": 30},
                n_elements=2,
            )

    def test_invalid_pch_bounds_min_gte_max_raises_error(self, base_params):
        """Test that Pch bounds with min >= max raises ValueError."""
        with pytest.raises(ValueError, match="min|max|bounds"):
            create_optimizer_model(
                base_params["vial"],
                base_params["product"],
                base_params["ht"],
                base_params["vial"]["Vfill"],
                base_params["eq_cap"],
                base_params["nVial"],
                control_mode="Pch",
                Pchamber={"min": 0.2, "max": 0.1},
                Tshelf={"init": -35, "setpt": [20], "dt_setpt": [1800]},
                n_elements=2,
            )

    def test_invalid_tsh_bounds_min_gte_max_raises_error(self, base_params):
        """Test that Tsh bounds with min >= max raises ValueError."""
        with pytest.raises(ValueError, match="min|max|bounds"):
            create_optimizer_model(
                base_params["vial"],
                base_params["product"],
                base_params["ht"],
                base_params["vial"]["Vfill"],
                base_params["eq_cap"],
                base_params["nVial"],
                control_mode="Tsh",
                Pchamber={"setpt": [0.1], "dt_setpt": [1800], "ramp_rate": 0.5},
                Tshelf={"min": 30, "max": -45},
                n_elements=2,
            )


class TestValidConfigurations:
    """Tests for valid parameter configurations."""

    @pytest.fixture
    def base_params(self):
        """Common test parameters for model creation."""
        return {
            "vial": {"Av": 3.8, "Ap": 3.14, "Vfill": 2.0},
            "product": {
                "R0": 1.4,
                "A1": 16.0,
                "A2": 0.0,
                "T_pr_crit": -5.0,
                "cSolid": 0.05,
            },
            "ht": {"KC": 0.000275, "KP": 0.000893, "KD": 0.46},
            "eq_cap": {"a": -0.182, "b": 11.7},
            "nVial": 398,
        }

    def test_valid_tsh_mode_creates_model(self, base_params):
        """Test that valid control_mode='Tsh' creates model successfully."""
        model = create_optimizer_model(
            base_params["vial"],
            base_params["product"],
            base_params["ht"],
            base_params["vial"]["Vfill"],
            base_params["eq_cap"],
            base_params["nVial"],
            control_mode="Tsh",
            Pchamber={"setpt": [0.1], "dt_setpt": [1800], "ramp_rate": 0.5},
            Tshelf={"min": -45, "max": 30},
            n_elements=2,
        )

        assert model is not None
        assert hasattr(model, "Tsh")
        assert hasattr(model, "Pch")

    def test_valid_pch_mode_creates_model(self, base_params):
        """Test that valid control_mode='Pch' creates model successfully."""
        model = create_optimizer_model(
            base_params["vial"],
            base_params["product"],
            base_params["ht"],
            base_params["vial"]["Vfill"],
            base_params["eq_cap"],
            base_params["nVial"],
            control_mode="Pch",
            Pchamber={"min": 0.06, "max": 0.20},
            Tshelf={"init": -35, "setpt": [20], "dt_setpt": [1800]},
            n_elements=2,
        )

        assert model is not None
        assert hasattr(model, "Pch")
        assert hasattr(model, "Tsh")

    def test_valid_both_mode_creates_model(self, base_params):
        """Test that valid control_mode='both' creates model successfully."""
        model = create_optimizer_model(
            base_params["vial"],
            base_params["product"],
            base_params["ht"],
            base_params["vial"]["Vfill"],
            base_params["eq_cap"],
            base_params["nVial"],
            control_mode="both",
            Pchamber={"min": 0.06, "max": 0.20},
            Tshelf={"min": -45, "max": 30},
            n_elements=2,
        )

        assert model is not None
        assert hasattr(model, "Pch")
        assert hasattr(model, "Tsh")


class TestBoundsValidation:
    """Tests for bounds validation and defaults."""

    @pytest.fixture
    def base_params(self):
        """Common test parameters for model creation."""
        return {
            "vial": {"Av": 3.8, "Ap": 3.14, "Vfill": 2.0},
            "product": {
                "R0": 1.4,
                "A1": 16.0,
                "A2": 0.0,
                "T_pr_crit": -5.0,
                "cSolid": 0.05,
            },
            "ht": {"KC": 0.000275, "KP": 0.000893, "KD": 0.46},
            "eq_cap": {"a": -0.182, "b": 11.7},
            "nVial": 398,
        }

    def test_pch_max_defaults_to_half_torr(self, base_params):
        """Test that Pch max defaults to 0.5 Torr when not specified."""
        model = create_optimizer_model(
            base_params["vial"],
            base_params["product"],
            base_params["ht"],
            base_params["vial"]["Vfill"],
            base_params["eq_cap"],
            base_params["nVial"],
            control_mode="Pch",
            Pchamber={"min": 0.06},  # No 'max' specified
            Tshelf={"init": -35, "setpt": [20], "dt_setpt": [1800]},
            n_elements=2,
        )

        assert model is not None
        # Check bounds on Pch variable
        t0 = min(model.t)
        assert model.Pch[t0].ub == 0.5, (
            f"Expected Pch max = 0.5, got {model.Pch[t0].ub}"
        )

    def test_pch_bounds_out_of_range_raises_error(self, base_params):
        """Test that Pch bounds outside valid range raises ValueError."""
        with pytest.raises(ValueError, match="bounds|range|Pch"):
            create_optimizer_model(
                base_params["vial"],
                base_params["product"],
                base_params["ht"],
                base_params["vial"]["Vfill"],
                base_params["eq_cap"],
                base_params["nVial"],
                control_mode="Pch",
                Pchamber={"min": 0.001, "max": 2.0},  # Both out of valid range
                Tshelf={"init": -35, "setpt": [20], "dt_setpt": [1800]},
                n_elements=2,
            )

    def test_tsh_bounds_out_of_range_raises_error(self, base_params):
        """Test that Tsh bounds outside valid range raises ValueError."""
        with pytest.raises(ValueError, match="bounds|range|Tsh"):
            create_optimizer_model(
                base_params["vial"],
                base_params["product"],
                base_params["ht"],
                base_params["vial"]["Vfill"],
                base_params["eq_cap"],
                base_params["nVial"],
                control_mode="Tsh",
                Pchamber={"setpt": [0.1], "dt_setpt": [1800], "ramp_rate": 0.5},
                Tshelf={"min": -100, "max": 200},  # Both out of valid range
                n_elements=2,
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
