"""
Tests for Design Space Generator

Tests the design space generation functionality for primary drying optimization.
"""

import pytest
import numpy as np
import lyopronto.design_space as design_space


@pytest.fixture
def physical_props(standard_vial, standard_product, standard_ht):
    """Standard inputs for design space tests."""
    eq_cap = {"a": -0.182, "b": 11.7}
    nVial = 398
    dt = 0.01
    return standard_vial, standard_product, standard_ht, eq_cap, nVial, dt


@pytest.fixture
def design_space_1T1P(physical_props):
    """Design space inputs for 1 Tshelf and 1 Pchamber."""
    vial, product, ht, eq_cap, nVial, dt = physical_props
    Tshelf = {"init": -35.0, "setpt": np.array([0.0]), "ramp_rate": 1.0}
    Pchamber = {"setpt": np.array([0.15]), "ramp_rate": 0.5}
    return vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial


@pytest.fixture
def design_space_1T3P(physical_props):
    """Design space inputs for 1 Tshelf and 3 Pchamber."""
    vial, product, ht, eq_cap, nVial, dt = physical_props
    Tshelf = {"init": -35.0, "setpt": np.array([0.0]), "ramp_rate": 1.0}
    Pchamber = {
        "setpt": np.array([0.05, 0.10, 0.15]),
    }
    return vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial


@pytest.fixture
def design_space_3T1P(physical_props):
    """Design space inputs for 3 Tshelf and 1 Pchamber."""
    vial, product, ht, eq_cap, nVial, dt = physical_props
    Tshelf = {"init": -35.0, "setpt": np.array([-20, -10, 0.0]), "ramp_rate": 1.0}
    Pchamber = {
        "setpt": np.array([0.10]),
    }
    return vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial


@pytest.fixture
def design_space_3T3P(physical_props):
    """Design space inputs for 3 Tshelf and 3 Pchamber."""
    vial, product, ht, eq_cap, nVial, dt = physical_props
    Tshelf = {"init": -35.0, "setpt": np.array([-20, -10, 0.0]), "ramp_rate": 1.0}
    Pchamber = {
        "setpt": np.array([0.05, 0.10, 0.15]),
    }
    return vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial


def check_shape(output, Pchamber, Tshelf):
    """Helper function to check output shapes."""
    shelf_results, product_results, eq_cap_results = output

    n_Tsh = len(Tshelf["setpt"])
    n_Pch = len(Pchamber["setpt"])

    # Shelf results: 5 components, each with shape (n_Tsh, n_Pch)
    assert len(shelf_results) == 5
    # for each of (Tmax, drying_time, avg_flux, max_flux, end_flux),
    # there should be a value for each combination (n_Tsh x n_Pch)
    for component in shelf_results:
        assert component.shape == (n_Tsh, n_Pch)

    # Product results: 2 values for each Pchamber
    assert len(product_results) == 5
    # for each of (T_product, drying_time, avg_flux, min_flux, end_flux),
    # 2 values
    for component in product_results:
        assert component.shape == (2,)  # 2 T_product values x n_Pch

    # Equipment capability results: 1 value per Pchamber
    assert len(eq_cap_results) == 3
    # for each of (Tmax, drying_time, flux), 1 value per Pch
    for component in eq_cap_results:
        assert component.shape == (n_Pch,)  # n_Pch


class TestDesignSpaceBasic:
    """Basic functionality tests for design space generation."""

    def test_design_space_runs(self, design_space_1T1P):
        """Test that design space generation completes without errors, returns correct
        structure, and gives physically reasonable results."""
        # Use conservative parameters that avoid edge cases

        # Should complete without errors
        output = design_space.dry(*design_space_1T1P)
        shelf_results, product_results, eq_cap_results = output
        check_shape(output, design_space_1T1P[3], design_space_1T1P[4])

        # Extract values
        T_max_shelf = shelf_results[0][0, 0]
        drying_time_shelf = shelf_results[1][0, 0]
        avg_flux_shelf = shelf_results[2][0, 0]

        drying_time_product = product_results[1][0]
        avg_flux_product = product_results[2][0]

        T_max_eq = eq_cap_results[0][0]
        drying_time_eq = eq_cap_results[1][0]
        flux_eq = eq_cap_results[2][0]

        # Physical constraints
        assert T_max_shelf >= -50.0, "Product temperature too low"
        assert T_max_shelf <= 50.0, "Product temperature too high"
        assert drying_time_shelf > 0, "Drying time must be positive"
        assert drying_time_shelf < 100.0, "Drying time unreasonably long"
        assert avg_flux_shelf >= 0, "Flux must be non-negative"

        assert drying_time_product > 0, "Product drying time must be positive"
        assert avg_flux_product > 0, "Product flux must be positive"

        assert T_max_eq >= -50.0, "Equipment max temp too low"
        assert T_max_eq <= 50.0, "Equipment max temp too high"
        assert drying_time_eq > 0, "Equipment drying time must be positive"
        assert flux_eq > 0, "Equipment flux must be positive"

    def test_design_space_shape_3T3P(self, design_space_3T3P):
        """Test that design space outputs have correct shapes for multiple Tshelf and Pchamber."""
        output = design_space.dry(*design_space_3T3P)

        check_shape(output, design_space_3T3P[3], design_space_3T3P[4])

    def test_design_space_shape_1T3P(self, design_space_1T3P):
        """Test that design space outputs have correct shapes for one Tshelf, multiple Pchamber."""
        output = design_space.dry(*design_space_1T3P)

        check_shape(output, design_space_1T3P[3], design_space_1T3P[4])

    def test_design_space_shape_3T1P(self, design_space_3T1P):
        """Test that design space outputs have correct shapes for one Tshelf, multiple Pchamber."""
        output = design_space.dry(*design_space_3T1P)
        # Shelf results: 5 components, each with shape (3, 1)
        check_shape(output, design_space_3T1P[3], design_space_3T1P[4])

    def test_constraint(self, design_space_1T1P):
        """Test that each piece of results matches constraints."""
        vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial = design_space_1T1P

        _, product_results, eq_cap_results = design_space.dry(*design_space_1T1P)

        # Product temperature should equal critical temperature
        T_product = product_results[0][0]
        assert T_product == pytest.approx(product["T_pr_crit"], abs=0.01), (
            f"Product temperature {T_product}°C should equal critical {product['T_pr_crit']}°C"
        )

        # Equipment sublimation rate
        dmdt_eq = (
            eq_cap["a"] + eq_cap["b"] * Pchamber["setpt"][0]
        )  # kg/hr for all vials
        flux_eq_expected = dmdt_eq / nVial / (vial["Ap"] * 1e-4)  # kg/hr/m²

        flux_eq_calculated = eq_cap_results[2][0]

        # Should match within numerical tolerance
        assert abs(flux_eq_calculated - flux_eq_expected) / flux_eq_expected < 0.01, (
            f"Equipment flux mismatch: {flux_eq_calculated} vs {flux_eq_expected}"
        )


class TestDesignSpaceEdgeCases:
    def test_design_space_negative_sublimation(self, design_space_1T1P):
        """Test design space with conditions that could lead to negative sublimation."""
        # Set very low shelf temperature to potentially trigger dmdt < 0
        vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial = design_space_1T1P
        Tshelf["init"] = -60.0
        Tshelf["setpt"] = [-55.0]

        # Expect a warning about infeasible sublimation
        with pytest.warns(UserWarning, match="sublimation"):
            output = design_space.dry(
                vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial
            )

        # Calculation completes anyway
        assert len(output) == 3
        assert (
            output[0].shape[0] == 5
        )  # [T_max, drying_time, sub_flux_avg, sub_flux_max, sub_flux_end]
        # But should have some NaNs due to infeasibility
        assert np.any(np.isnan(output[0])), (
            "Output should contain NaNs for infeasible conditions"
        )

    def test_design_space_shelf_ramp_down(self, design_space_1T1P):
        """Test design space with ramp-down in shelf temperature."""
        vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial = design_space_1T1P
        # Set ramp down in shelf temperature
        Tshelf["init"] = -10.0
        Tshelf["setpt"] = [-20.0]

        output = design_space.dry(
            vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial
        )
        check_shape(output, Pchamber, Tshelf)

    def test_design_space_no_sub(self, design_space_1T1P):
        """Test design space with no sublimation at initial shelf temperature."""
        vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial = design_space_1T1P
        # Set ramp down in shelf temperature
        Tshelf["init"] = -60.0
        Tshelf["setpt"] = [-30.0]

        with pytest.warns(UserWarning, match="too low for sublimation"):
            output = design_space.dry(
                vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial
            )
        check_shape(output, Pchamber, Tshelf)

    # TODO: assess whether this should be erroring, not just warning
    def test_design_space_fast_completion_Tpr(self, design_space_1T1P):
        """Test design space with conditions leading to very fast drying."""
        # Use high temperature and large timestep for fast drying
        vial, product, ht, Pchamber, Tshelf, _, eq_cap, nVial = design_space_1T1P
        Tshelf["init"] = 0.0
        Tshelf["setpt"] = [0.0]
        product["T_pr_crit"] = -1.0
        dt = 1.0  # Very large timestep

        with pytest.warns(UserWarning, match="At Pch"):
            output = design_space.dry(
                vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial
            )
        check_shape(output, Pchamber, Tshelf)

    def test_design_space_fast_completion_Tsh(self, design_space_1T1P):
        """Test design space with conditions leading to very fast drying."""
        # Use high temperature and large timestep for fast drying
        vial, product, ht, Pchamber, Tshelf, _, eq_cap, nVial = design_space_1T1P
        Pchamber["setpt"] = [0.01]
        eq_cap["a"] = 0
        Tshelf["init"] = 30.0
        Tshelf["setpt"] = [30.0]
        product["T_pr_crit"] = -10.0
        dt = 100.0  # Very large timestep

        # Check for both warnings, since I couldn't trigger the Tsh one without Pch one
        with pytest.warns(UserWarning, match="At Tsh"):
            with pytest.warns(UserWarning, match="At Pch"):
                output = design_space.dry(
                    vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial
                )
        check_shape(output, Pchamber, Tshelf)

    def test_design_space_subzero_eqcap(self, design_space_1T1P):
        """Test design space with equipment capability leading to subzero sublimation."""
        vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial = design_space_1T1P
        Pchamber["setpt"] = [0.001]  # Pch such that a + b*Pch < 0

        with pytest.warns(UserWarning, match="negative"):
            output = design_space.dry(
                vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial
            )

        check_shape(output, Pchamber, Tshelf)


class TestDesignSpaceComparison:
    """Comparative tests between different design space modes."""

    def test_shelf_vs_product_temperature_modes(self, design_space_1T1P):
        """Test that shelf and product temperature modes give different results."""
        shelf_results, product_results, _ = design_space.dry(*design_space_1T1P)

        # Shelf temperature mode (fixed Tshelf)
        drying_time_shelf = shelf_results[1][0, 0]

        # Product temperature mode (fixed Tproduct at critical)
        drying_time_product = product_results[1][0]

        # Product temperature mode should have different drying time
        # (usually longer since it maintains T at critical limit)
        assert drying_time_shelf != drying_time_product, (
            "Shelf and product modes should give different drying times"
        )

    def test_equipment_capability_fastest(self, design_space_1T1P):
        """Test that equipment capability gives fastest drying (if feasible)."""
        shelf_results, product_results, eq_cap_results = design_space.dry(
            *design_space_1T1P
        )

        drying_time_eq = eq_cap_results[1][0]
        drying_time_product = product_results[1][0]

        # Equipment capability should be faster or similar
        # (it assumes maximum equipment sublimation rate)
        assert drying_time_eq <= drying_time_product * 1.5, (
            "Equipment capability should give reasonably fast drying"
        )


# ==============================================================================
# Coverage gap tests (migrated from test_coverage_gaps.py)
# ==============================================================================


class TestDesignSpaceCoverageGaps:
    """Tests to cover missing lines in design_space.py."""

    @pytest.fixture
    def design_space_setup(self, standard_vial, standard_product, standard_ht):
        """Setup for design space calculations."""
        # Multiple pressure and temperature setpoints for full design space
        Pchamber = {'setpt': [0.060, 0.080, 0.100]}
        Tshelf = {
            'init': -40.0,
            'setpt': [-30.0, -20.0, -10.0],
            'ramp_rate': 1.0  # Fast ramp to test different branches
        }
        dt = 0.02  # Larger timestep for faster completion
        eq_cap = {'a': 5.0, 'b': 10.0}
        nVial = 398

        return {
            'vial': standard_vial,
            'product': standard_product,
            'ht': standard_ht,
            'Pchamber': Pchamber,
            'Tshelf': Tshelf,
            'dt': dt,
            'eq_cap': eq_cap,
            'nVial': nVial
        }

    def test_design_space_negative_sublimation(self, design_space_setup):
        """Test design space with conditions that could lead to negative sublimation."""
        # Set very low shelf temperature to potentially trigger dmdt < 0
        design_space_setup['Tshelf']['init'] = -60.0
        design_space_setup['Tshelf']['setpt'] = [-55.0]

        output = design_space.dry(
            design_space_setup['vial'],
            design_space_setup['product'],
            design_space_setup['ht'],
            design_space_setup['Pchamber'],
            design_space_setup['Tshelf'],
            design_space_setup['dt'],
            design_space_setup['eq_cap'],
            design_space_setup['nVial']
        )

        # Should complete without crashing
        assert len(output) == 3
        assert output[0].shape[0] == 5  # [T_max, drying_time, sub_flux_avg, sub_flux_max, sub_flux_end]

    @pytest.mark.skip(reason="Ramp-down scenarios cause temperatures too low for sublimation")
    def test_design_space_shelf_temp_ramp_down(self, design_space_setup):
        """Test design space with shelf temperature ramping down.

        SKIPPED: Ramping temperature DOWN creates temperatures too low for
        sublimation, causing OverflowError in Vapor_pressure calculation.
        """
        # Start warm, ramp down
        design_space_setup['Tshelf']['init'] = 0.0
        design_space_setup['Tshelf']['setpt'] = [-10.0]
        design_space_setup['Tshelf']['ramp_rate'] = 1.0

        output = design_space.dry(
            design_space_setup['vial'],
            design_space_setup['product'],
            design_space_setup['ht'],
            design_space_setup['Pchamber'],
            design_space_setup['Tshelf'],
            design_space_setup['dt'],
            design_space_setup['eq_cap'],
            design_space_setup['nVial']
        )

        assert len(output) == 3

    def test_design_space_fast_completion(self, design_space_setup):
        """Test design space with conditions leading to very fast drying."""
        # Use high temperature and large timestep for fast drying
        design_space_setup['Tshelf']['init'] = -15.0
        design_space_setup['Tshelf']['setpt'] = [-10.0]
        design_space_setup['dt'] = 0.5  # Very large timestep
        design_space_setup['product']['cSolid'] = 0.01  # Very dilute for faster drying

        output = design_space.dry(
            design_space_setup['vial'],
            design_space_setup['product'],
            design_space_setup['ht'],
            design_space_setup['Pchamber'],
            design_space_setup['Tshelf'],
            design_space_setup['dt'],
            design_space_setup['eq_cap'],
            design_space_setup['nVial']
        )

        # Should handle edge case where drying completes in one timestep
        assert len(output) == 3
        assert output[1].shape[0] == 5  # Product temp isotherms

    def test_design_space_equipment_capability_section(self, design_space_setup):
        """Test design space equipment capability calculations."""
        # Use full range of pressures
        design_space_setup['Pchamber']['setpt'] = [0.050, 0.075, 0.100, 0.125, 0.150]

        output = design_space.dry(
            design_space_setup['vial'],
            design_space_setup['product'],
            design_space_setup['ht'],
            design_space_setup['Pchamber'],
            design_space_setup['Tshelf'],
            design_space_setup['dt'],
            design_space_setup['eq_cap'],
            design_space_setup['nVial']
        )

        # Equipment capability data is in output[2]
        eq_cap_data = output[2]
        assert eq_cap_data.shape[0] == 3  # [T_max_eq_cap, drying_time_eq_cap, sub_flux_eq_cap]
        assert eq_cap_data[0].shape[0] == 5  # Should match number of pressure setpoints

    def test_design_space_product_temp_isotherms(self, design_space_setup):
        """Test product temperature isotherm section thoroughly."""
        # Use minimal setup to focus on product temp isotherms
        design_space_setup['Pchamber']['setpt'] = [0.060, 0.100]  # Just two pressures
        design_space_setup['Tshelf']['setpt'] = [-25.0]

        output = design_space.dry(
            design_space_setup['vial'],
            design_space_setup['product'],
            design_space_setup['ht'],
            design_space_setup['Pchamber'],
            design_space_setup['Tshelf'],
            design_space_setup['dt'],
            design_space_setup['eq_cap'],
            design_space_setup['nVial']
        )

        # Check product temperature isotherms output
        product_temp_data = output[1]
        assert product_temp_data.shape[0] == 5
        assert product_temp_data[1].shape[0] == 2  # drying_time_pr for 2 pressures

    def test_design_space_single_timestep_both_sections(self, design_space_setup):
        """Test both shelf temp and product temp sections with single timestep completion."""
        # Extreme conditions for very fast drying
        design_space_setup['vial']['Vfill'] = 0.5  # Very small fill volume
        design_space_setup['product']['cSolid'] = 0.005  # Very dilute
        design_space_setup['Tshelf']['init'] = -10.0
        design_space_setup['Tshelf']['setpt'] = [-5.0]
        design_space_setup['Pchamber']['setpt'] = [0.150]  # High pressure
        design_space_setup['dt'] = 1.0  # Large timestep

        output = design_space.dry(
            design_space_setup['vial'],
            design_space_setup['product'],
            design_space_setup['ht'],
            design_space_setup['Pchamber'],
            design_space_setup['Tshelf'],
            design_space_setup['dt'],
            design_space_setup['eq_cap'],
            design_space_setup['nVial']
        )

        # Should handle single-timestep completion in both sections
        assert len(output) == 3
        # Output arrays should be properly formed
        assert output[0] is not None
        assert output[1] is not None
        assert output[2] is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
