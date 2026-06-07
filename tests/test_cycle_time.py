from dataclasses import dataclass

import numpy as np
import pytest

from lyopronto import Q_, identify_pd_end


def _synthetic_pirani():
    t = np.linspace(0.0, 100.0, 101)
    pch_pir = 20.0 - 20.0 * np.tanh((t - 60.0) / 5.0)
    return t, pch_pir


def test_identify_pd_end_matches_julia_tanh_bounds_with_quantities():
    t, pch_pir = _synthetic_pirani()

    t_end = identify_pd_end(Q_(t, "hour"), Q_(pch_pir, "pascal"), "der2")
    onset, offset = identify_pd_end(Q_(t, "hour"), Q_(pch_pir, "pascal"), "onoff")

    assert t_end.check("[time]")
    assert 50.0 < t_end.to("hour").magnitude < 100.0
    assert 40.0 < onset.to("hour").magnitude < 80.0
    assert 40.0 < offset.to("hour").magnitude < 80.0


def test_identify_pd_end_accepts_mapping_and_object_inputs():
    t, pch_pir = _synthetic_pirani()
    expected = identify_pd_end(t, pch_pir, "der2")

    @dataclass
    class PiraniData:
        t: np.ndarray
        pch_pir: np.ndarray

    mapping_result = identify_pd_end({"t": t, "pch_pir": pch_pir}, "der2")
    object_result = identify_pd_end(PiraniData(t=t, pch_pir=pch_pir), kind="der2")

    assert mapping_result == pytest.approx(expected)
    assert object_result == pytest.approx(expected)


def test_identify_pd_end_respects_absolute_indices_in_analysis_window():
    t, pch_pir = _synthetic_pirani()

    t_end = identify_pd_end(
        t,
        pch_pir,
        "der2",
        window_width=11,
        tmin=55.0,
        tmax=70.0,
    )

    assert t_end == pytest.approx(64.0)


def test_identify_pd_end_onoff_accepts_windowed_quantity_mapping():
    t, pch_pir = _synthetic_pirani()

    onset, offset = identify_pd_end(
        {"t": Q_(t, "hour"), "pch_pir": Q_(pch_pir, "pascal")},
        "onoff",
        window_width=11,
        tmin=Q_(55.0, "hour"),
        tmax=Q_(70.0, "hour"),
    )

    assert onset.check("[time]")
    assert offset.check("[time]")
    assert onset.to("hour").magnitude == pytest.approx(56.6428502501405)
    assert offset.to("hour").magnitude == pytest.approx(64.86646299947469)


def test_identify_pd_end_rejects_invalid_kind():
    t, pch_pir = _synthetic_pirani()

    with pytest.raises(ValueError, match='kind must be "der2" or "onoff"'):
        identify_pd_end(t, pch_pir, "midpoint")


def test_identify_pd_end_validates_window_width_and_input_lengths():
    t, pch_pir = _synthetic_pirani()

    with pytest.raises(ValueError, match="window_width must be odd"):
        identify_pd_end(t, pch_pir, "der2", window_width=90)

    with pytest.raises(ValueError, match="window_width cannot exceed input length"):
        identify_pd_end(t[:5], pch_pir[:5], "der2")

    with pytest.raises(ValueError, match="same length"):
        identify_pd_end(t, pch_pir[:-1], "der2")
