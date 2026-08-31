"""Guards for the pseudosteady frozen-layer tutorial notebook.

The notebook teaches the measured cost of LyoPRONTO's pseudosteady
frozen-layer assumption from the committed continuation baseline in
``benchmarks/results/pseudosteady_limit/ipopt.json``. Its narrative quotes
specific numbers from that artifact, so the agreement between the two is
pinned here in the fast lane: regenerating the baseline without updating the
notebook text must fail loudly rather than ship stale teaching numbers.

The same contract covers the convergence level the baseline records, which
several documents outside this notebook also state; see
:data:`DOCUMENTS_STATING_THE_CONVERGENCE_LEVEL`.
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

#: Every document that states the convergence level of the committed baseline
#: in prose. They are true only as long as the artifact keeps that level, and
#: `benchmarks/README.md` instructs regenerating it whenever the models or the
#: solver version change, so the claim needs a guard rather than a proofread.
DOCUMENTS_STATING_THE_CONVERGENCE_LEVEL = (
    "examples/pseudosteady_limit_study.py (module and RungResult docstrings)",
    "benchmarks/README.md",
    "docs/how-to-guides.md",
    f"{NOTEBOOK} (section 2)",
)

#: What every converged rung of the committed baseline records. Named here
#: rather than imported from ``paper_ocp`` so the guard states the expected
#: string independently of the classifier that produces it.
EXPECTED_CONVERGED_QUALITY = "accepted_at_acceptable_tol"

#: What a rung that never produced a solution records: it met no tolerance, so
#: it must not claim one.
EXPECTED_UNSOLVED_QUALITY = "unknown"


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


def test_committed_outputs_render_the_convergence_level(repo_root) -> None:
    """A source edit that is not re-executed must not ship the old rendering.

    This notebook commits its rendered outputs and `mkdocs` publishes them, so
    the outputs are a separate artifact from the sources that produced them.
    Changing a cell to report the convergence level therefore does nothing for
    a reader until the notebook is re-executed and the result committed: the
    #147 review caught exactly that, with sources reporting the level while the
    published outputs still showed a `termination` column of `optimal` and
    `(converged)` per rung -- the conflation of issue #146, still on the page.

    Regenerate with a no-parameter papermill run (which is what the committed
    `metadata.papermill` records) and copy the result over the tracked file::

        python -c "import papermill; papermill.execute_notebook(
            'docs/examples/pseudosteady_frozen_layer.ipynb',
            'docs/examples/pseudosteady_frozen_layer_output.ipynb')"
        cp docs/examples/pseudosteady_frozen_layer_output.ipynb \\
           docs/examples/pseudosteady_frozen_layer.ipynb
    """
    rendered_text = {}
    for index, cell in enumerate(_notebook(repo_root)["cells"]):
        if cell["cell_type"] != "code":
            continue
        rendered_text[index] = "".join(
            "".join(output.get("text", [])) for output in cell.get("outputs", [])
        )

    #: The baseline table and the live-rerun listing. Both print one rung per
    #: line, and both are what a reader of the published page sees.
    reporting = {
        index
        for index, text in rendered_text.items()
        if EXPECTED_CONVERGED_QUALITY in text
    }
    assert len(reporting) == 2, (
        "expected the baseline table and the live rerun to render "
        f"{EXPECTED_CONVERGED_QUALITY!r} in their committed output; found it in "
        f"{sorted(reporting)}. Re-execute the notebook and commit the result."
    )

    stale = {
        index: marker
        for index, text in rendered_text.items()
        for marker in ("(converged)", "termination")
        if marker in text
    }
    assert not stale, (
        f"committed output still renders the pre-#146 form {stale}. The cell "
        "sources were changed without re-executing, so the published page "
        "shows a convergence level the sources no longer report."
    )


def test_baseline_still_records_the_documented_convergence_level(repo_root) -> None:
    """The baseline keeps the convergence level several documents state in prose.

    Issue #146 is a report that described this artifact as something it was
    not. The fix states the level everywhere, which is only true while the
    artifact keeps it -- and `benchmarks/README.md` instructs regenerating it
    whenever the models or the solver version change. Without this guard a
    regeneration that converged to `tol` would leave every document in
    `DOCUMENTS_STATING_THE_CONVERGENCE_LEVEL` quietly wrong.

    No solver runs here; this is a read of a committed file.
    """
    baseline = json.loads((repo_root / BASELINE).read_text())["results"]
    stale = "\n  ".join(DOCUMENTS_STATING_THE_CONVERGENCE_LEVEL)

    checked = 0
    for name, rungs in baseline.items():
        for rung in rungs:
            expected = (
                EXPECTED_CONVERGED_QUALITY
                if rung["converged"]
                else EXPECTED_UNSOLVED_QUALITY
            )
            assert rung["convergence_quality"] == expected, (
                f"{name} f={rung['factor']:g}: baseline records "
                f"{rung['convergence_quality']!r}, not {expected!r}. If the "
                f"regeneration is intended, update the prose in:\n  {stale}"
            )
            checked += 1

    # Guards against a truncated or empty artifact satisfying the loop.
    assert checked == 13, f"expected 13 recorded rungs, read {checked}"


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
