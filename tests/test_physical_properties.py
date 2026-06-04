import numpy as np
import pytest

from lyopronto import Q_, constant, physical_properties as pp


def test_physical_property_constants_match_julia_units_and_values():
    assert pp.delta_h_sub.to("kilojoule / kilogram").magnitude == pytest.approx(
        2838.0
    )
    assert pp.theta_sub.to("kelvin").magnitude == pytest.approx(6149.1130)
    assert pp.k_ice.to("watt / meter / kelvin").magnitude == pytest.approx(2.4)
    assert pp.cp_ice.to("joule / kilogram / kelvin").magnitude == pytest.approx(
        2.09e3
    )
    assert pp.rho_ice.to("gram / centimeter ** 3").magnitude == pytest.approx(
        0.918
    )
    assert pp.rho_glass.to("gram / centimeter ** 3").magnitude == pytest.approx(
        2.23
    )
    assert pp.epp_gl == pytest.approx(2.4e-2)
    assert pp.rho_sucrose.to("kilogram / meter ** 3").magnitude == pytest.approx(
        892.0
    )
    assert pp.mu_vap.to("micropascal * second").magnitude == pytest.approx(8.1)
    assert pp.e_0.to("farad / meter").magnitude == pytest.approx(8.854187e-12)
    assert pp.sigma.to("watt / meter ** 2 / kelvin ** 4").magnitude == (
        pytest.approx(5.670367e-8)
    )


def test_legacy_constants_are_not_changed_by_physical_property_module():
    assert constant.k_ice == pytest.approx(0.0059)
    assert constant.rho_ice == pytest.approx(0.918)


def test_sublimation_pressure_temperature_round_trip_plain_floats():
    temperatures = np.array([190.0, 200.0, 225.0, 254.0, 273.0])

    pressure = pp.calc_psub(temperatures)
    round_tripped = pp.calc_tsub(pressure)

    assert isinstance(pressure, np.ndarray)
    assert round_tripped == pytest.approx(temperatures)


def test_sublimation_pressure_temperature_round_trip_quantities():
    temperatures = Q_(np.array([190.0, 200.0, 225.0, 254.0, 273.0]), "kelvin")

    pressure = pp.calc_psub(temperatures)
    round_tripped = pp.calc_tsub(pressure)

    assert pressure.check("[pressure]")
    assert round_tripped.check("[temperature]")
    assert round_tripped.to("kelvin").magnitude == pytest.approx(
        temperatures.magnitude
    )
    assert pp.calc_Tsub(pressure).to("kelvin").magnitude == pytest.approx(
        temperatures.magnitude
    )


def test_sublimation_helpers_match_for_plain_and_quantity_scalars():
    pressure_plain = pp.calc_psub(254.0)
    pressure_quantity = pp.calc_psub(Q_(254.0, "kelvin"))

    assert pressure_quantity.to("pascal").magnitude == pytest.approx(
        pressure_plain
    )
    assert pp.calc_tsub(Q_(pressure_plain, "pascal")).to(
        "kelvin"
    ).magnitude == pytest.approx(254.0)


def test_eppf_is_finite_over_reference_frequency_range():
    frequencies = Q_(np.linspace(5.0, 39.0, 15), "gigahertz")

    for temperature in [Q_(200.0, "kelvin"), Q_(258.0, "kelvin")]:
        values = pp.eppf(temperature, frequencies)
        assert np.all(np.isfinite(values))
        assert np.all(values > 0)


def test_eppf_matches_plain_and_quantity_inputs():
    plain = pp.eppf(200.0, 10.0e9)
    quantity = pp.eppf(Q_(200.0, "kelvin"), Q_(10.0, "gigahertz"))

    assert quantity == pytest.approx(plain)
    assert pp.eppf(Q_(200.0, "kelvin"), Q_(0.0, "hertz")) == 0.0
