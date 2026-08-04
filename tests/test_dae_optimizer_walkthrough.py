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


@pytest.mark.pyomo
def test_shelf_temperature_dae_reproduces_legacy_equality_residuals() -> None:
    """The DAE optimum satisfies the legacy SciPy equality constraints.

    This is the notebook's central identity claim in section 1.3: the Pyomo
    model encodes the same physics as ``functions.Eq_Constraints``, so those
    residuals must vanish at a solution the DAE found without ever calling
    them. Units follow the legacy seven-column convention: time [hr],
    temperatures [degC], pressure [mTorr], sublimation flux [kg/hr/m^2], and
    percent dried [0-100].
    """
    require_pyomo_solver("ipopt")

    from examples.current_main_optimizer_comparison import comparison_inputs
    from lyopronto import constant, functions
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

    lpr0_cm = functions.Lpr0_FUN(
        case["vial"]["Vfill"], case["vial"]["Ap"], case["product"]["cSolid"]
    )
    residuals = []
    for row in result.as_table():
        pch_torr = row[4] / constant.Torr_to_mTorr
        dmdt_kg_per_hr = row[5] * case["vial"]["Ap"] * constant.cm_To_m**2
        lck_cm = row[6] / 100.0 * lpr0_cm
        residuals.append(
            functions.Eq_Constraints(
                pch_torr,
                dmdt_kg_per_hr,
                row[2],
                row[3],
                functions.Vapor_pressure(row[1]),
                row[1],
                functions.Kv_FUN(
                    case["ht"]["KC"], case["ht"]["KP"], case["ht"]["KD"], pch_torr
                ),
                lpr0_cm,
                lck_cm,
                case["vial"]["Av"],
                case["vial"]["Ap"],
                functions.Rp_FUN(
                    lck_cm,
                    case["product"]["R0"],
                    case["product"]["A1"],
                    case["product"]["A2"],
                ),
            )
        )

    assert np.max(np.abs(residuals)) < 1.0e-4


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

    def drying_time_hr(kc: float, shelf_max_c: float | None) -> float:
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
        return float(result.objective_time_hr)

    kc_values = (2.75e-4, 4.00e-4)

    # Shipped ceiling binds, so a better vial heat transfer really does help.
    binding = [drying_time_hr(kc, None) for kc in kc_values]
    assert binding[0] - binding[1] > 1.0e-3

    # Lift the ceiling clear and the cancellation takes over.
    slack = [drying_time_hr(kc, 400.0) for kc in kc_values]
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
