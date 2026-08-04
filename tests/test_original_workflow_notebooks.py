"""Fresh-kernel smoke tests for the original-workflow documentation notebooks."""

from __future__ import annotations

import papermill as pm
import pytest


pytestmark = [pytest.mark.serial, pytest.mark.notebook]


def test_known_rp_parity_notebook_execution(repo_root) -> None:
    """Execute the known-Rp SciPy/Pyomo tutorial without editing its source."""
    pm.execute_notebook(
        repo_root / "docs/examples/knownRp_PD.ipynb",
        repo_root / "docs/examples/knownRp_PD_output.ipynb",
    )


def test_unknown_rp_hybrid_notebook_execution(repo_root) -> None:
    """Execute the shared-preprocessing SciPy/Pyomo fitting tutorial."""
    pm.execute_notebook(
        repo_root / "docs/examples/unknownRp_PD.ipynb",
        repo_root / "docs/examples/unknownRp_PD_output.ipynb",
    )
