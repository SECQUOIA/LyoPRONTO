import math

import numpy as np
import pytest

from lyopronto import (
    ConstPhysProp,
    PrimaryDryFit,
    Q_,
    RampedVariable,
    RpFormFit,
    extract_ts,
)
from lyopronto.typed import to_magnitude_array


def test_rpformfit_matches_julia_formula_with_quantities():
    rp = RpFormFit(
        Q_(1.0, "centimeter ** 2 * hour * torr / gram"),
        Q_(14.0, "centimeter * hour * torr / gram"),
        Q_(1.0, "1 / centimeter"),
    )

    expected = rp.R0 + rp.A1 * Q_(5.0, "centimeter") / (
        1 + rp.A2 * Q_(5.0, "centimeter")
    )

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

    assert tsh(Q_(-5, "minute")) == Q_(228.15, "kelvin")
    assert tsh(Q_(-math.inf, "second")) == Q_(228.15, "kelvin")
    assert tsh(Q_(0, "second")) == Q_(228.15, "kelvin")
    assert tsh(Q_(math.inf, "second")) == Q_(248.15, "kelvin")
    assert tsh(10 / 60).to("kelvin").magnitude == pytest.approx(238.15)
    assert tsh(Q_(10, "minute")) == Q_(238.15, "kelvin")
    assert tsh(Q_(20, "minute")) == Q_(248.15, "kelvin")
    assert tsh(Q_(100, "minute")) == Q_(248.15, "kelvin")
    assert [t.to("minute").magnitude for t in tsh.timestops] == pytest.approx(
        [0.0, 20.0]
    )


def test_multi_ramped_variable_matches_julia_cases_and_warns_for_wrong_sign():
    with pytest.warns(UserWarning, match="wrong sign"):
        power = RampedVariable.multi(
            [Q_(40, "watt"), Q_(20, "watt"), Q_(10, "watt")],
            [Q_(1, "watt/minute"), Q_(math.inf, "watt/minute")],
            [Q_(1, "hour")],
        )

    assert power(Q_(-1, "minute")) == Q_(40, "watt")
    assert power(Q_(0, "second")) == Q_(40, "watt")
    assert power(Q_(10, "minute")) == Q_(30, "watt")
    assert power(Q_(20, "minute")) == Q_(20, "watt")
    assert power(Q_(50, "minute")) == Q_(20, "watt")
    assert power(Q_(79, "minute")) == Q_(20, "watt")
    assert power(Q_(81, "minute")) == Q_(10, "watt")
    assert power(Q_(math.inf, "minute")) == Q_(10, "watt")


def test_extract_ts_matches_julia_public_helper_cases():
    constant = RampedVariable.constant(Q_(150, "millitorr"))
    ramped = RampedVariable.linear(
        [Q_(228.15, "kelvin"), Q_(248.15, "kelvin")],
        Q_(1, "kelvin/minute"),
    )

    class InterpolationLike:
        times = np.array([0.0, 0.5, 1.0])

    class QuantityStops:
        timestops = [Q_(0.0, "minute"), Q_(30.0, "minute")]

    assert extract_ts(constant) == [0.0]
    assert extract_ts(ramped) == pytest.approx([0.0, 20.0 / 60.0])
    assert extract_ts(ramped, unit="minute") == pytest.approx([0.0, 20.0])
    assert extract_ts(InterpolationLike()) == pytest.approx([0.0, 0.5, 1.0])
    assert extract_ts(QuantityStops()) == pytest.approx([0.0, 0.5])
    assert extract_ts(object()) == [0.0]


def test_direct_ramped_variable_construction_requires_consistent_timestops():
    with pytest.raises(ValueError, match="timestops_hr"):
        RampedVariable(
            (Q_(228.15, "kelvin"), Q_(248.15, "kelvin")),
            (Q_(1, "kelvin/minute"),),
        )

    direct = RampedVariable(
        (Q_(228.15, "kelvin"), Q_(248.15, "kelvin")),
        (Q_(1, "kelvin/minute"),),
        (),
        (0.0, 20 / 60),
    )
    assert direct(Q_(10, "minute")) == Q_(238.15, "kelvin")


def test_quantity_array_helper_handles_pint_arrays_and_quantity_lists():
    arr = to_magnitude_array(Q_(np.array([1.0, 2.0]), "hour"), "minute")
    assert arr.tolist() == pytest.approx([60.0, 120.0])

    mixed = to_magnitude_array([Q_(1, "hour"), Q_(30, "minute")], "minute")
    assert mixed.tolist() == pytest.approx([60.0, 30.0])


def test_primary_dry_fit_constructor_normalizes_julia_cases():
    times = Q_(np.linspace(0.0, 10.0, 5), "hour")
    tf_a = Q_(np.linspace(220.0, 230.0, 5), "kelvin")
    tf_b = Q_(np.linspace(221.0, 229.0, 4), "kelvin")
    tvw = Q_(np.linspace(225.0, 232.0, 3), "kelvin")
    t_end = Q_(12.0, "hour")

    fit = PrimaryDryFit(times, (tf_a, tf_b), Tvws=tvw, t_end=t_end)

    assert len(fit.Tfs) == 2
    assert fit.Tf_iend == (5, 4)
    assert len(fit.Tvws) == 1
    assert fit.Tvw_iend == (3,)
    assert fit.t_end == t_end
    np.testing.assert_allclose(fit.t_hr, np.linspace(0.0, 10.0, 5))
    np.testing.assert_allclose(fit.Tfs_K[0], np.linspace(220.0, 230.0, 5))
    np.testing.assert_allclose(fit.Tvws_K[0], np.linspace(225.0, 232.0, 3))

    product_only = PrimaryDryFit(times, tf_a)
    assert len(product_only.Tfs) == 1
    assert product_only.Tf_iend == (5,)
    assert product_only.Tvws is None
    assert product_only.Tvw_iend is None

    endpoint = PrimaryDryFit(times, (tf_a, tf_b), Tvws=tvw[-1])
    assert endpoint.Tvw_iend is None
    assert endpoint.Tvws_K == pytest.approx(tvw[-1].to("kelvin").magnitude)

    window = PrimaryDryFit(
        times,
        tf_a,
        t_end=[Q_(9.0, "hour"), Q_(7.0, "hour")],
    )
    assert [value.to("hour").magnitude for value in window.t_end] == [7.0, 9.0]


def test_primary_dry_fit_constructor_rejects_incompatible_quantity_inputs():
    times = Q_(np.linspace(0.0, 10.0, 5), "hour")
    temps = Q_(np.linspace(220.0, 230.0, 5), "kelvin")

    with pytest.raises(ValueError, match="units of time"):
        PrimaryDryFit(temps, temps)

    with pytest.raises(ValueError, match="units of temperature"):
        PrimaryDryFit(times, times)

    with pytest.raises(ValueError, match="Tf_iend"):
        PrimaryDryFit(times, (temps, temps), Tf_iend=[5])

    with pytest.raises(ValueError, match="t_end"):
        PrimaryDryFit(
            times, temps, t_end=[Q_(1.0, "hour"), Q_(2.0, "hour"), Q_(3.0, "hour")]
        )
