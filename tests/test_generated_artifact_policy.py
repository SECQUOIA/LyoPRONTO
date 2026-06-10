from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _is_ignored(path: str) -> bool:
    if not (ROOT / ".git").exists():
        pytest.skip("generated artifact policy checks require a git checkout")

    result = subprocess.run(
        ["git", "check-ignore", "--quiet", "--no-index", path],
        cwd=ROOT,
        check=False,
    )
    if result.returncode == 0:
        return True
    if result.returncode == 1:
        return False
    pytest.fail(f"git check-ignore failed for {path!r} with {result.returncode}")


@pytest.mark.parametrize(
    "path",
    [
        ".coverage",
        ".coverage.313",
        "coverage.xml",
        "htmlcov/index.html",
        ".pytest_cache/v/cache/nodeids",
        ".mypy_cache/3.13/foo.json",
        ".ruff_cache/0.12.0/foo",
        "docs/examples/knownRp_PD_output.ipynb",
        "docs/examples/new_notebook_output.ipynb",
        "examples/outputs/lyopronto_primary_drying_20260610.csv",
        "examples/outputs/primary_drying_results.png",
        "benchmarks/results/local_case.jsonl",
        "benchmarks/results/local_case/processed/summary.json",
        "benchmarks/results/archive/pre_physics_fix_20260204/grid.jsonl",
        "lyopronto_input_20260610.csv",
        "lyopronto_output_20260610.csv",
        "lyopronto_primary_drying_20260610.csv",
        "lyopronto_design_space_20260610.csv",
        "lyopronto_freezing_20260610.csv",
        "lyopronto_parameter_estimation_20260610.csv",
        "lyopronto_optimizer_20260610.csv",
        "lyo_Rp_data_20260610.csv",
        "lyo_Temperatures_20260610.pdf",
        "primary_drying_results.png",
        "design_space_results.png",
        "freezing_results.png",
        "parameter_estimation_results.png",
        "optimizer_results.png",
        "input_saved_251002_1816.csv",
        "output_saved_251002_1816.csv",
    ],
)
def test_generated_artifacts_are_ignored(path: str) -> None:
    assert _is_ignored(path), f"{path} should be ignored as generated output"


@pytest.mark.parametrize(
    "path",
    [
        "docs/examples/knownRp_PD.ipynb",
        "docs/examples/new_source_notebook.ipynb",
        "docs/examples/temperature.txt",
        "examples/outputs/README.md",
        "examples/outputs/.gitkeep",
        "test_data/reference_primary_drying.csv",
        "test_data/reference_new_case.csv",
        "test_data/example_new_case.yaml",
        "benchmarks/README.md",
        "benchmarks/results/archive/grid.jsonl",
        "benchmarks/results/archive/grid_ratio.png",
        "benchmarks/results/both_test/raw/both_2x2_test.jsonl",
        "benchmarks/results/test/processed/summary.json",
        "environment.yml",
        "requirements.txt",
    ],
)
def test_source_and_reference_files_remain_trackable(path: str) -> None:
    assert not _is_ignored(path), f"{path} should remain visible to git"
