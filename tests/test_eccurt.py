"""Tests for ECCURT equipment-capability interpolation."""

import numpy as np
import pytest

import lyopronto.design_space as design_space
from lyopronto.eccurt import (
    DA_SAMPLE,
    D_SAMPLE,
    L_SAMPLE,
    M_DOT,
    PCH,
    VOLUME_SAMPLE,
    eq_cap_line,
    eq_cap_line_new,
    eq_cap_pressure,
    eq_cap_pressures_new,
)
from lyopronto.typed import Q_


def test_eq_cap_pressure_matches_julia_acceptance_values():
    pressures = eq_cap_pressure(
        np.array([0.1, 0.3, 0.5, 0.8]),
        120.0,
        50.0,
        300.0,
        0.092,
    )

    assert np.allclose(pressures, [45.6, 93.1, 140.5, 211.7], atol=1.0)


def test_eq_cap_pressure_accepts_quantities():
    pressure = eq_cap_pressure(
        Q_(0.1, "kilogram / hour"),
        Q_(120.0, "millimeter"),
        Q_(50.0, "millimeter"),
        Q_(300.0, "millimeter"),
        Q_(0.092, "meter ** 3"),
    )

    assert pressure.to("millitorr").magnitude == pytest.approx(45.6, abs=1.0)


def test_eq_cap_extrapolation_warns():
    with pytest.warns(UserWarning, match="extrapolation"):
        eq_cap_pressure(0.1, 120.0, 50.0, 30.0, 0.492)


def test_eq_cap_pressures_new_reproduce_grid_points():
    for d_index, diameter in enumerate(D_SAMPLE):
        for da_index, diameter_to_valve in enumerate(DA_SAMPLE):
            for volume_index, chamber_volume in enumerate(VOLUME_SAMPLE):
                for length_index, duct_length in enumerate(reversed(L_SAMPLE)):
                    valve_thickness = diameter / diameter_to_valve

                    pressures = eq_cap_pressures_new(
                        diameter,
                        valve_thickness,
                        duct_length,
                        chamber_volume,
                    )

                    assert np.allclose(
                        pressures,
                        PCH[:, volume_index, d_index, da_index, length_index],
                        atol=0.1,
                    )


def test_eq_cap_line_new_has_lower_total_table_error_than_original_line():
    old_errors = 0.0
    new_errors = 0.0

    for d_index, diameter in enumerate(D_SAMPLE):
        for da_index, diameter_to_valve in enumerate(DA_SAMPLE):
            for volume_index, chamber_volume in enumerate(VOLUME_SAMPLE):
                for length_index, duct_length in enumerate(reversed(L_SAMPLE)):
                    valve_thickness = diameter / diameter_to_valve
                    old_line = eq_cap_line(
                        diameter,
                        valve_thickness,
                        duct_length,
                        chamber_volume,
                    )
                    new_line = eq_cap_line_new(
                        diameter,
                        valve_thickness,
                        duct_length,
                        chamber_volume,
                    )

                    for mass_flow, pressure in zip(
                        M_DOT,
                        PCH[:, volume_index, d_index, da_index, length_index],
                    ):
                        new_error = abs(new_line(pressure) - mass_flow)
                        old_error = abs(old_line(pressure) - mass_flow)
                        old_errors += old_error**2
                        new_errors += new_error**2

    assert new_errors < old_errors


def test_design_space_accepts_eccurt_geometry_input(
    standard_vial,
    standard_product,
    standard_ht,
):
    pchamber = {"setpt": np.array([0.15])}
    tshelf = {"init": -35.0, "setpt": np.array([0.0]), "ramp_rate": 1.0}
    eq_cap = {
        "duct_diameter": 120.0,
        "valve_thickness": 50.0,
        "duct_length": 300.0,
        "chamber_volume": 0.092,
    }

    _, _, eq_cap_results = design_space.dry(
        standard_vial,
        standard_product,
        standard_ht,
        pchamber,
        tshelf,
        0.01,
        eq_cap,
        398,
    )

    line = eq_cap_line_new(120.0, 50.0, 300.0, 0.092)
    expected_mass_flow = line(pchamber["setpt"][0] * 1000.0)
    expected_flux = expected_mass_flow / 398 / (standard_vial["Ap"] * 1e-4)
    assert eq_cap_results[2, 0] == pytest.approx(expected_flux)
