"""Guards for the DAE optimizer walkthrough notebook.

The notebook explains how the free-final-time Pyomo.DAE model is assembled and
re-derives the evidence behind its documented behavior. Two of its claims are
load-bearing enough to pin here as well, so a regression is caught by the fast
suite rather than only by executing the notebook.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from tests.pyomo_solver import require_pyomo_solver

NOTEBOOK = "docs/examples/dae_optimizer_walkthrough.ipynb"


def _notebook(repo_root):
    return json.loads((repo_root / NOTEBOOK).read_text())


def test_walkthrough_notebook_declares_papermill_parameters(repo_root) -> None:
    """CI overrides the sweep sizes, so the parameters cell must stay tagged."""
    cells = _notebook(repo_root)["cells"]
    tagged = [
        cell
        for cell in cells
        if "parameters" in (cell.get("metadata", {}).get("tags") or [])
    ]

    assert len(tagged) == 1, "exactly one papermill parameters cell is expected"
    source = "".join(tagged[0]["source"])
    for name in (
        "a1",
        "kc",
        "kc_sweep_values",
        "point_budget",
        "ncp",
        "scipy_dt_sweep",
        "slack_shelf_ceiling_c",
    ):
        assert f"{name} =" in source, f"parameter {name!r} is missing"


def test_walkthrough_notebook_ships_executed_outputs(repo_root) -> None:
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


#: Dimensionless bound on each legacy equality residual, normalized by that
#: equation's own scale. A converged solve lands near 1e-9, so this leaves
#: roughly three orders of headroom for solver tolerance while still catching
#: a sub-0.1% error in any single equation. A shared *absolute* bound cannot
#: do this job: the four residuals carry Torr, kg/hr, cal cm/s, and degC, and
#: the kg/hr terms are O(1e-3), so one threshold loose enough for degC hides a
#: 10% mass-transfer error.
MAX_RELATIVE_EQUALITY_RESIDUAL = 1.0e-6


@pytest.mark.pyomo
def test_shelf_temperature_dae_reproduces_legacy_equality_residuals() -> None:
    """The DAE optimum satisfies the legacy SciPy equality constraints.

    This is the notebook's central identity claim in section 1.3: the Pyomo
    model encodes the same physics as ``functions.Eq_Constraints``, so those
    residuals must vanish at a solution the DAE found without ever calling
    them.

    Each equation is checked against its own normalized tolerance. Scaling a
    10% error into the mass-transfer equation moves that equation's relative
    residual to 9.1e-2, and a 0.1% error to 1.0e-3, both far above the bound;
    the remaining equations stay near 1e-9.
    """
    require_pyomo_solver("ipopt")

    from examples.current_main_comparison import (
        LEGACY_EQUALITY_CONSTRAINTS,
        legacy_equality_residuals,
    )
    from examples.current_main_optimizer_comparison import comparison_inputs
    from lyopronto.pyomo_models import solve_dae_shelf_temperature_optimization

    case = comparison_inputs(16.0, 2.75e-4)
    result = solve_dae_shelf_temperature_optimization(
        case["vial"],
        case["product"],
        case["ht"],
        case["pchamber"],
        case["tshelf"],
        eq_cap=case["eq_cap"],
        nvial=case["nvial"],
        nfe=8,
        discretization="collocation",
        ncp=3,
    )
    assert result.success, result.message

    diagnostics = legacy_equality_residuals(result.as_table(), case)

    assert set(diagnostics) == {name for name, _, _ in LEGACY_EQUALITY_CONSTRAINTS}
    for name, entry in diagnostics.items():
        assert entry["max_relative"] < MAX_RELATIVE_EQUALITY_RESIDUAL, (
            f"{name} residual {entry['max_relative']:.3e} (absolute "
            f"{entry['max_absolute']:.3e} {entry['unit']}, scale "
            f"{entry['scale']:.3e} {entry['unit']}) exceeds the normalized bound"
        )


@pytest.mark.pyomo
def test_drying_time_loses_kc_dependence_once_the_shelf_ceiling_is_slack() -> None:
    """Section 2.2: the ``Kv`` cancellation holds only while the shelf is free.

    With ``Tbot`` pinned at ``T_pr_crit``, substituting the energy balance into
    the frozen-layer heat balance cancels ``Kv``, so drying time [hr] cannot
    depend on ``KC`` [cal/s/K/cm^2]. That argument assumes the shelf can supply
    whatever temperature [degC] the balance demands, which the shipped paper
    case does not allow. Both regimes are asserted so the precondition cannot
    quietly stop being reported.
    """
    require_pyomo_solver("ipopt")

    from examples.current_main_optimizer_comparison import comparison_inputs
    from lyopronto.pyomo_models import solve_dae_shelf_temperature_optimization

    def solve(kc: float, shelf_max_c: float | None):
        case = comparison_inputs(16.0, kc)
        if shelf_max_c is not None:
            case["tshelf"] = {**case["tshelf"], "max": shelf_max_c}
        result = solve_dae_shelf_temperature_optimization(
            case["vial"],
            case["product"],
            case["ht"],
            case["pchamber"],
            case["tshelf"],
            eq_cap=case["eq_cap"],
            nvial=case["nvial"],
            nfe=8,
            discretization="collocation",
            ncp=3,
        )
        assert result.success, result.message
        return result, case

    kc_values = (2.75e-4, 4.00e-4)
    shipped_ceiling_c = comparison_inputs(16.0, kc_values[0])["tshelf"]["max"]
    relaxed_ceiling_c = 400.0

    # The derivation only applies where the product-temperature limit pins
    # Tbot, so every endpoint must reach that bound for the claim to be about
    # the mechanism rather than about some other regime.
    def assert_product_limit_active(result, case) -> None:
        reached_c = float(np.max(result.values["Tbot"]))
        assert reached_c == pytest.approx(case["product"]["T_pr_crit"], abs=1.0e-4)

    # Shipped ceiling binds: shelf pinned at its bound with a priced multiplier,
    # so a better vial heat-transfer coefficient really does shorten the cycle.
    binding = []
    for kc in kc_values:
        result, case = solve(kc, None)
        assert_product_limit_active(result, case)
        assert float(np.max(result.values["Tsh"])) == pytest.approx(
            shipped_ceiling_c, abs=1.0e-4
        )
        assert abs(result.shadow_prices["shelf_temperature_upper_bound"]) > 1.0e-6
        binding.append(float(result.objective_time_hr))
    assert binding[0] - binding[1] > 1.0e-3

    # Ceiling lifted clear: the shelf stays well inside its bound and prices at
    # zero, so the Kv cancellation governs and KC drops out of the drying time.
    slack = []
    for kc in kc_values:
        result, case = solve(kc, relaxed_ceiling_c)
        assert_product_limit_active(result, case)
        reached_c = float(np.max(result.values["Tsh"]))
        assert reached_c < relaxed_ceiling_c - 1.0
        assert abs(result.shadow_prices["shelf_temperature_upper_bound"]) < 1.0e-9
        slack.append(float(result.objective_time_hr))
    assert abs(slack[0] - slack[1]) < 1.0e-4


@pytest.mark.serial
@pytest.mark.notebook
@pytest.mark.pyomo
def test_dae_optimizer_walkthrough_notebook_execution(repo_root) -> None:
    require_pyomo_solver("ipopt")
    papermill = pytest.importorskip("papermill")

    papermill.execute_notebook(
        repo_root / NOTEBOOK,
        repo_root / "docs/examples/dae_optimizer_walkthrough_output.ipynb",
        parameters={
            "a1": 16.0,
            "kc": 2.75e-4,
            # Two values still show the sweep flipping between regimes.
            "kc_sweep_values": [2.75e-4, 4.00e-4],
            "point_budget": 25,
            "ncp": 3,
            "final_dried_fraction": 1.0,
            "scipy_dt": 0.05,
            # Two steps are enough to show the 1/scipy_dt trend.
            "scipy_dt_sweep": [0.04, 0.02],
            "slack_shelf_ceiling_c": 400.0,
        },
    )
