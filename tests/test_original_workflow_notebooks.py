"""Fresh-kernel smoke tests for the original-workflow documentation notebooks."""

from __future__ import annotations

from typing import Any

import papermill as pm
import pytest


# The notebooks run in the ordinary notebook lane without the optional stack,
# but the Pyomo marker also routes them into both solver-backed comparison
# lanes, where their optional IPOPT/POUNCE cells must execute rather than skip.
pytestmark = [pytest.mark.serial, pytest.mark.notebook, pytest.mark.pyomo]


def _stream_text(notebook: Any) -> str:
    """Collect text printed by an executed notebook."""
    return "".join(
        "".join(output.get("text", []))
        for cell in notebook.cells
        for output in cell.get("outputs", [])
        if output.get("output_type") == "stream"
    )


def _image_count(notebook: Any) -> int:
    """Count rendered Matplotlib figures in an executed notebook."""
    return sum(
        "image/png" in output.get("data", {})
        for cell in notebook.cells
        for output in cell.get("outputs", [])
    )


def _source(notebook: Any) -> str:
    """Join all notebook cell sources for diagnostic-coverage checks."""
    return "\n".join("".join(cell.get("source", [])) for cell in notebook.cells)


def test_known_rp_parity_notebook_execution(repo_root) -> None:
    """Execute the known-Rp SciPy/Pyomo tutorial without editing its source."""
    notebook = pm.execute_notebook(
        repo_root / "docs/examples/knownRp_PD.ipynb",
        repo_root / "docs/examples/knownRp_PD_output.ipynb",
    )

    output = _stream_text(notebook)
    source = _source(notebook)
    assert "SciPy integration wall time:" in output
    assert "Pyomo model construction wall time:" in source
    assert "Pyomo solver wall time:" in source
    assert _image_count(notebook) == 4
    assert "temperature_columns = ((1," in source
    assert "scipy_output[:, 4]" in source
    assert "scipy_output[:, 5]" in source
    assert "scipy_output[:, 6]" in source


def test_unknown_rp_hybrid_notebook_execution(repo_root) -> None:
    """Execute the shared-preprocessing SciPy/Pyomo fitting tutorial."""
    notebook = pm.execute_notebook(
        repo_root / "docs/examples/unknownRp_PD.ipynb",
        repo_root / "docs/examples/unknownRp_PD_output.ipynb",
    )

    output = _stream_text(notebook)
    source = _source(notebook)
    assert "Legacy inverse preprocessing wall time:" in output
    assert "SciPy curve_fit wall time:" in output
    assert "Pyomo model construction wall time:" in source
    assert "Pyomo solver wall time:" in source
    assert _image_count(notebook) == 5
    for column in range(1, 7):
        assert f"trajectory[:, {column}]" in source
