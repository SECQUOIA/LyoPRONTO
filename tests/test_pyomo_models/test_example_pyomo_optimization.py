from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

pytest.importorskip("pyomo.environ")


pytestmark = pytest.mark.pyomo

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MODULE_PATH = _REPO_ROOT / "examples" / "example_pyomo_optimization.py"


def _load_example():
    spec = importlib.util.spec_from_file_location("example_pyomo_optimization", _MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def pyomo_example():
    return _load_example()


def test_pyomo_optimization_example_builds_all_modes(pyomo_example, capsys):
    summaries = pyomo_example.run_pyomo_optimization_example()
    pyomo_example._print_summary(summaries)
    printed = capsys.readouterr().out

    assert set(summaries) == {"pressure", "shelf_temperature", "joint"}
    assert summaries["pressure"]["optimized_controls"] == ("Pch",)
    assert summaries["pressure"]["fixed_controls"] == ("Tsh",)
    assert summaries["shelf_temperature"]["optimized_controls"] == ("Tsh",)
    assert summaries["shelf_temperature"]["fixed_controls"] == ("Pch",)
    assert summaries["joint"]["optimized_controls"] == ("Pch", "Tsh")
    assert summaries["joint"]["fixed_controls"] == ()

    for mode, summary in summaries.items():
        assert summary["mode"] == mode
        assert summary["objective"] == "sum_Pch_minus_Psub"
        assert summary["time_nodes"] == 5
        assert summary["variables"] > 0
        assert summary["constraints"] > 0
        assert f"{mode}: optimized=" in printed
