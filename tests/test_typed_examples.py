"""Smoke tests for the typed Julia-parity examples.

These run the runnable examples in ``examples/typed_api_examples.py`` as plain
Python (no Jupyter/papermill needed) and assert basic sanity, covering the
typed conventional, fitting, direct-Rp, RF, vial, ECCURT, and Pirani
end-detection workflows added across the Julia-parity series.
"""

import importlib.util
import math
import re
from pathlib import Path

import numpy as np
import pytest

_REPO_ROOT = Path(__file__).parent.parent
_MODULE_PATH = _REPO_ROOT / "examples" / "typed_api_examples.py"
_PARITY_MATRIX = _REPO_ROOT / "docs" / "technical" / "julia-parity.md"
_VALID_STATUSES = {
    "ported",
    "partially ported",
    "planned",
    "intentionally unsupported",
}


def _load_examples():
    spec = importlib.util.spec_from_file_location("typed_api_examples", _MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def examples():
    return _load_examples()


def test_typed_conventional_simulation(examples):
    result = examples.run_typed_conventional_simulation()
    assert result["n_points"] > 1
    assert 0.0 < result["drying_time_hr"] < 40.0
    assert 200.0 < result["final_tf_K"] < 320.0


@pytest.mark.slow
def test_conventional_kv_rp_fitting(examples):
    result = examples.run_conventional_kv_rp_fitting()
    assert result["success"]
    assert result["objective"] == pytest.approx(0.0, abs=1e-8)
    assert result["kv_ratio"] == pytest.approx(1.0, rel=0.1)
    assert result["r0_ratio"] == pytest.approx(1.0, rel=0.1)


def test_direct_rp_estimation(examples):
    result = examples.run_direct_rp_estimation()
    assert result["n_points"] > 1
    assert result["max_h_dried_cm"] > 0.0
    assert result["rp_units_ok"]


def test_rf_simulation(examples):
    result = examples.run_rf_simulation()
    assert result["terminated_by_drying"]
    assert 0.0 < result["drying_time_hr"] < 400.0
    assert 150.0 < result["final_tf_K"] < 400.0


def test_rf_energy_accounting(examples):
    result = examples.run_rf_energy_accounting()
    assert set(result) == {"Qsub", "Qshf", "Qvwf", "QRFf", "QRFvw"}
    assert all(math.isfinite(value) for value in result.values())
    assert result["QRFf"] > 0.0


@pytest.mark.slow
def test_rf_fitting(examples):
    result = examples.run_rf_fitting()
    assert result["success"]
    assert result["objective"] == pytest.approx(0.0, abs=1e-8)
    assert result["kvwf_ratio"] == pytest.approx(1.0, rel=0.3)


def test_bounded_rf_transform(examples):
    result = examples.run_bounded_rf_transform()
    assert result["kvwf_ratio"] == pytest.approx(1.0)


def test_vial_utilities(examples):
    result = examples.run_vial_utilities()
    assert result["outer_radius_cm"] > result["inner_radius_cm"] > 0.0
    assert result["mass_g"] > 0.0
    assert result["shape_type"]


def test_eccurt_equipment_capability(examples):
    result = examples.run_eccurt_equipment_capability()
    assert np.allclose(result["pressures_mtorr"], [45.6, 93.1, 140.5, 211.7], atol=1.0)
    assert result["line_slope"] > 0.0


def test_primary_drying_end_detection(examples):
    result = examples.run_primary_drying_end_detection()
    assert 50.0 < result["der2_end_hr"] < 100.0
    assert 40.0 < result["onset_hr"] < 80.0
    assert 40.0 < result["offset_hr"] < 80.0


def test_parity_matrix_has_no_unclassified_exports():
    """Every Julia export row in the parity matrix carries a known status."""

    text = _PARITY_MATRIX.read_text(encoding="utf-8")
    row = re.compile(r"^\|\s*`(?P<name>[^`]+)`\s*\|\s*(?P<status>[^|]+?)\s*\|")
    statuses = [
        match.group("status")
        for line in text.splitlines()
        if (match := row.match(line))
    ]
    assert statuses, "no Julia export rows found in the parity matrix"
    unclassified = sorted(set(statuses) - _VALID_STATUSES)
    assert not unclassified, f"unclassified parity-matrix statuses: {unclassified}"
