import pytest

from lyopronto import Q_, vials
from lyopronto.functions import Lpr0_FUN


def test_schott_table_contains_complete_supported_size_range():
    assert list(vials.VIAL_DIMS) == [
        "2R",
        "4R",
        "6R",
        "8R",
        "10R",
        "15R",
        "20R",
        "25R",
        "30R",
        "50R",
        "100R",
    ]


def test_get_vial_radii_matches_julia_table_for_6r():
    rad_i, rad_o = vials.get_vial_radii("6R")

    assert rad_i.check("[length]")
    assert rad_o.check("[length]")
    assert rad_i.to("millimeter").magnitude == pytest.approx(10.0)
    assert rad_o.to("millimeter").magnitude == pytest.approx(11.0)


def test_get_vial_mass_and_thickness_match_julia_table_for_6r():
    assert vials.get_vial_mass("6R").to("gram").magnitude == pytest.approx(7.9)
    assert vials.get_vial_thickness("6R").to("millimeter").magnitude == pytest.approx(
        1.0
    )


def test_invalid_vial_size_error_is_explicit():
    with pytest.raises(ValueError, match="invalid vial size '7R'"):
        vials.get_vial_mass("7R")


def test_get_vial_shape_and_areas_return_quantities():
    shape = vials.get_vial_shape("6R")
    ap, av = vials.get_vial_areas("6R")

    assert shape.barrel_height.to("millimeter").magnitude == pytest.approx(26.0)
    assert shape.curve_height.to("millimeter").magnitude == pytest.approx(31.5)
    assert ap.to("centimeter ** 2").magnitude == pytest.approx(3.14159265)
    assert av.to("centimeter ** 2").magnitude == pytest.approx(3.80132711)


def test_legacy_geometry_helper_returns_calculator_compatible_floats():
    geometry = vials.legacy_vial_geometry("6R", Q_(2.0, "milliliter"))

    assert geometry == pytest.approx({"Ap": 3.14159265, "Av": 3.80132711, "Vfill": 2.0})
    assert isinstance(geometry["Ap"], float)
    assert isinstance(geometry["Av"], float)
    assert isinstance(geometry["Vfill"], float)

    manual_height = Lpr0_FUN(2.0, 3.14159265, 0.05)
    helper_height = Lpr0_FUN(geometry["Vfill"], geometry["Ap"], 0.05)
    assert helper_height == pytest.approx(manual_height)


def test_shape_method_returns_legacy_geometry_for_plain_fill_volume():
    shape = vials.get_vial_shape("6R")
    geometry = shape.legacy_geometry(2.0)

    assert geometry["Ap"] == pytest.approx(3.14159265)
    assert geometry["Av"] == pytest.approx(3.80132711)
    assert geometry["Vfill"] == pytest.approx(2.0)


def test_make_outlines_returns_quantity_points_and_fill_height():
    shape = vials.get_vial_shape("6R")
    vial_points, fill_points = vials.make_outlines(shape, Q_(2.0, "milliliter"))

    assert len(vial_points) == 17
    assert len(fill_points) == 5
    assert fill_points[0][0].check("[length]")
    assert fill_points[0][1].check("[length]")

    expected_height = 2.0 * 1000.0 / (3.14159265 * 10.0**2)
    fill_top = fill_points[2][1].to("millimeter").magnitude
    assert fill_top == pytest.approx(0.7 + expected_height)
