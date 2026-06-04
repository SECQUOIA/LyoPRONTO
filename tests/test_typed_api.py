import math

import numpy as np
import pytest

from lyopronto import ConstPhysProp, Q_, RampedVariable, RpFormFit
from lyopronto.typed import to_magnitude_array


def test_rpformfit_matches_julia_formula_with_quantities():
    rp = RpFormFit(
        Q_(1.0, "centimeter ** 2 * hour * torr / gram"),
        Q_(14.0, "centimeter * hour * torr / gram"),
        Q_(1.0, "1 / centimeter"),
    )

    expected = rp.R0 + rp.A1 * Q_(5.0, "centimeter") / (1 + rp.A2 * Q_(5.0, "centimeter"))

    assert rp(Q_(5.0, "centimeter")) == expected
    assert rp(Q_(0.0, "centimeter")) == rp.R0


def test_const_phys_prop_returns_stored_value():
    prop = ConstPhysProp(Q_(7.5, "joule / gram"))

    assert prop() == Q_(7.5, "joule / gram")
    assert prop(Q_(200.0, "kelvin")) == Q_(7.5, "joule / gram")


def test_constant_ramped_variable_matches_julia_cases():
    pch = RampedVariable.constant(Q_(150, "millitorr"))

    assert pch(-math.inf) == Q_(150, "millitorr")
    assert pch(0) == Q_(150, "millitorr")
    assert pch(Q_(15, "hour")) == Q_(150, "millitorr")


def test_linear_ramped_variable_matches_julia_cases():
    tsh = RampedVariable.linear(
        [Q_(228.15, "kelvin"), Q_(248.15, "kelvin")],
        Q_(1, "kelvin/minute"),
    )

    assert tsh(Q_(0, "second")) == Q_(228.15, "kelvin")
    assert tsh(Q_(math.inf, "second")) == Q_(248.15, "kelvin")
    assert tsh(Q_(10, "minute")) == Q_(238.15, "kelvin")
    assert tsh(Q_(20, "minute")) == Q_(248.15, "kelvin")
    assert tsh(Q_(100, "minute")) == Q_(248.15, "kelvin")
    assert [t.to("minute").magnitude for t in tsh.timestops] == pytest.approx([0.0, 20.0])


def test_multi_ramped_variable_matches_julia_cases_and_warns_for_wrong_sign():
    with pytest.warns(UserWarning, match="wrong sign"):
        power = RampedVariable.multi(
            [Q_(40, "watt"), Q_(20, "watt"), Q_(10, "watt")],
            [Q_(1, "watt/minute"), Q_(math.inf, "watt/minute")],
            [Q_(1, "hour")],
        )

    assert power(Q_(0, "second")) == Q_(40, "watt")
    assert power(Q_(10, "minute")) == Q_(30, "watt")
    assert power(Q_(20, "minute")) == Q_(20, "watt")
    assert power(Q_(50, "minute")) == Q_(20, "watt")
    assert power(Q_(79, "minute")) == Q_(20, "watt")
    assert power(Q_(81, "minute")) == Q_(10, "watt")
    assert power(Q_(math.inf, "minute")) == Q_(10, "watt")


def test_quantity_array_helper_handles_pint_arrays_and_quantity_lists():
    arr = to_magnitude_array(Q_(np.array([1.0, 2.0]), "hour"), "minute")
    assert arr.tolist() == pytest.approx([60.0, 120.0])

    mixed = to_magnitude_array([Q_(1, "hour"), Q_(30, "minute")], "minute")
    assert mixed.tolist() == pytest.approx([60.0, 30.0])
