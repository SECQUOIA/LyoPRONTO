"""Guards for the pseudosteady frozen-layer tutorial notebook.

The notebook teaches the measured cost of LyoPRONTO's pseudosteady
frozen-layer assumption from the committed continuation baseline in
``benchmarks/results/pseudosteady_limit/ipopt.json``. Its narrative quotes
specific numbers from that artifact, so the agreement between the two is
pinned here in the fast lane: regenerating the baseline without updating the
notebook text must fail loudly rather than ship stale teaching numbers.
"""

from __future__ import annotations

import json

import pytest

from tests.pyomo_solver import require_pyomo_solver

NOTEBOOK = "docs/examples/pseudosteady_frozen_layer.ipynb"
BASELINE = "benchmarks/results/pseudosteady_limit/ipopt.json"

#: Headline endpoint shifts the notebook narrative quotes, in percent, held to
#: half a unit in the last quoted decimal place. This is a rounding contract
#: on arithmetic over a committed file; no solver runs in this test, so no
#: solver-build tolerance is involved.
DOCUMENTED_SHIFT_PERCENT = {"problem1": -0.622, "problem2": -0.080}
SHIFT_ROUNDING_TOLERANCE = 0.0005


def _notebook(repo_root):
    return json.loads((repo_root / NOTEBOOK).read_text())


def _baseline_shift_percent(rungs) -> float:
    converged = [r for r in rungs if r["converged"]]
    first, last = converged[0], converged[-1]
    return (last["endpoint_hr"] - first["endpoint_hr"]) / first["endpoint_hr"] * 100.0


def test_notebook_declares_papermill_parameters(repo_root) -> None:
    """CI executes the coarse settings, so the parameters cell must stay tagged."""
    cells = _notebook(repo_root)["cells"]
    tagged = [
        cell
        for cell in cells
        if "parameters" in (cell.get("metadata", {}).get("tags") or [])
    ]

    assert len(tagged) == 1, "exactly one papermill parameters cell is expected"
    source = "".join(tagged[0]["source"])
    for name in ("n_z", "nfe", "ncp", "live_ladder", "baseline_path"):
        assert f"{name} =" in source, f"parameter {name!r} is missing"


def test_notebook_ships_executed_outputs(repo_root) -> None:
    """The tracked notebook carries rendered results, matching the other examples."""
    cells = _notebook(repo_root)["cells"]
    code_cells = [cell for cell in cells if cell["cell_type"] == "code"]
    with_outputs = [cell for cell in code_cells if cell.get("outputs")]

    assert code_cells, "notebook has no code cells"
    # Every code cell except the papermill parameters cell should have run.
    assert len(with_outputs) >= len(code_cells) - 1
    assert not [
        output
        for cell in code_cells
        for output in cell.get("outputs", [])
        if output.get("output_type") == "error"
    ], "committed notebook contains an execution error"


def test_baseline_still_supports_the_documented_headline(repo_root) -> None:
    """The committed baseline reproduces the shifts the notebook narrative quotes.

    Also pins the caveat the notebook is built around: the conduction-time
    ratio ``tau / t_dry`` under-predicts the measured shift for problem 1 and
    over-predicts it for problem 2, so it screens the order of magnitude
    without being a quantitative predictor.
    """
    baseline = json.loads((repo_root / BASELINE).read_text())["results"]

    for name, expected in DOCUMENTED_SHIFT_PERCENT.items():
        shift = _baseline_shift_percent(baseline[name])
        assert shift == pytest.approx(expected, abs=SHIFT_ROUNDING_TOLERANCE), (
            f"{name}: baseline shift {shift:+.4f}% no longer matches the "
            f"documented {expected:+.3f}%; update the notebook narrative"
        )

        first = next(r for r in baseline[name] if r["converged"])
        tau_over_t_dry = first["conduction_time_s"] / (first["endpoint_hr"] * 3600.0)
        ratio = abs(shift / 100.0) / tau_over_t_dry
        if name == "problem1":
            assert ratio > 1.0, "problem1 no longer over-shoots the timescale ratio"
        else:
            assert ratio < 1.0, "problem2 no longer under-shoots the timescale ratio"


@pytest.mark.serial
@pytest.mark.notebook
@pytest.mark.pyomo
def test_pseudosteady_frozen_layer_notebook_execution(repo_root) -> None:
    require_pyomo_solver("ipopt")
    papermill = pytest.importorskip("papermill")

    papermill.execute_notebook(
        repo_root / NOTEBOOK,
        repo_root / "docs/examples/pseudosteady_frozen_layer_output.ipynb",
        parameters={
            # The notebook's own defaults are already the coarse CI settings;
            # they are passed explicitly so a default change cannot silently
            # grow this lane's runtime.
            "n_z": 5,
            "nfe": 12,
            "ncp": 3,
            "live_ladder": [1.0, 0.2, 0.05],
        },
    )
