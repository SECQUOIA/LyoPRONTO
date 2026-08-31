# LyoPRONTO Examples

This directory contains maintained scripts that exercise the supported
dictionary-style workflows, the typed Pint API, and the optional Pyomo
optimization prototypes.

## Maintained Scripts

| Script | Purpose | Output |
| --- | --- | --- |
| `example_web_interface.py` | Primary drying with known product resistance, matching the web-interface style. | CSV and `primary_drying_results.png` under `examples/outputs/`. |
| `example_optimizer.py` | Shelf-temperature optimization at fixed chamber pressure. | CSV under `examples/outputs/`. |
| `example_freezing.py` | Freezing-phase simulation. | CSV under `examples/outputs/`. |
| `example_design_space.py` | Design-space sections for shelf temperature, product temperature, and equipment capability. | CSV under `examples/outputs/`. |
| `example_parameter_estimation.py` | Product-resistance estimation from temperature data. | CSV and `parameter_estimation_results.png` under `examples/outputs/`. |
| `original_workflow_parity.py` | Reusable original-case setup, SciPy calculations, fixed-horizon Pyomo replay, and hybrid Pyomo resistance fitting used by the known/unknown-Rp notebooks. | In-memory trajectories, fitted parameters, and solver metadata. |
| `typed_api_examples.py` | Typed Pint API examples for simulation, fitting, RF, vial utilities, ECCURT, and Pirani endpoint detection. | Console smoke output. |
| `example_pyomo_optimization.py` | Optional Pyomo construction example for pressure-only, shelf-temperature-only, and joint optimization modes. | Console model summaries. |
| `current_main_comparison.py` | Shared result, timing, matched-point-budget, and discretization-sensitivity orchestration for the three current-main comparisons. | In-memory normalized trajectories and metrics. |
| `current_main_optimizer_comparison.py` | Shelf-temperature SciPy/Pyomo.DAE comparison for the paper's mannitol case. | In-memory normalized trajectories and metrics. |
| `current_main_pressure_optimizer_comparison.py` | Chamber-pressure SciPy/Pyomo.DAE comparison for the paper's mannitol case. | In-memory normalized trajectories and metrics. |
| `current_main_joint_optimizer_comparison.py` | Joint-control SciPy/Pyomo.DAE comparison and optional rate-limited extension for the paper's mannitol case. | In-memory normalized trajectories and metrics. |
| `paper_optimal_control_replication.py` | Replication of the two optimal-control case studies in Srisuma and Braatz, arXiv:2509.10826v1, plus the same three-policy classification applied to the vial-scale model. | In-memory solutions, policy segments, and metrics. |
| `paper_gdp_validation.py` | Validation-only paper benchmark with free multiphase GDP policy selection, compared with the published and continuous-NLP results. | In-memory comparison rows, indicator-derived policies, trajectories, and solver metadata. |
| `pseudosteady_limit_study.py` | Continuation from the paper's transient frozen-region PDE toward the pseudosteady formulation, by scaling the frozen heat capacity. Doubles as a solver-comparison instance set through `--solver-executable`. | Per-rung endpoint, maximum product temperature, termination condition, solver status, and convergence quality; optional JSON. |

Run examples from the repository root:

```bash
python -m pip install -e ".[dev]"
python examples/example_web_interface.py
python examples/example_optimizer.py
python examples/example_freezing.py
python examples/example_design_space.py
python examples/example_parameter_estimation.py
python -m examples.typed_api_examples
```

The maintained examples use immutable inputs from `test_data/` where needed
and write local outputs to `examples/outputs/`. `test_data/temperature.txt` is
the canonical measured input for the unknown-Rp workflow; notebooks import the
loader rather than carrying copies. Generated outputs are ignored by git.

Run the optional Pyomo example only after installing the Pyomo extra:

```bash
python -m pip install -e ".[dev,pyomo]"
python examples/example_pyomo_optimization.py
```

The Pyomo example builds models without solving them, so it does not require
IPOPT. Solver-backed Pyomo comparisons are covered separately by the optional
Pyomo validation lane.

The GDP paper comparison requires IPOPT and GLPK:

```bash
idaes get-extensions --extra petsc
sudo apt-get install glpk-utils
python -m examples.paper_gdp_validation
```

The pseudosteady-limit study requires IPOPT and takes several minutes, because
the lower rungs are deliberately hard:

```bash
python -m examples.pseudosteady_limit_study
python -m examples.pseudosteady_limit_study --output benchmarks/results/<run>/ipopt.json
```

`--solver-executable` runs the same models under a different NLP binary without
changing model code. Any solver following the AMPL `<solver> <stub> -AMPL`
convention works:

```bash
python -m examples.pseudosteady_limit_study --solver-executable /path/to/pounce
```

Install the recorded comparison release with
`python -m pip install -e ".[dev,pyomo,pounce]"`; the `pounce` extra pins
POUNCE 0.10.0. The tracked `pounce.json` baseline records the remaining
Problem 1 `f=0.02` convergence boundary alongside the shared IPOPT results.

Recorded baselines live in `benchmarks/results/pseudosteady_limit/`; see
`benchmarks/README.md` for what they are and when to regenerate them.

The current-main
[paper optimizer comparison](../docs/examples/current_main_joint_optimizer_comparison.ipynb)
runs the pressure-only, shelf-only, and joint-control examples with both
backends and requires IPOPT. The retired shelf-only and pressure-only notebooks
remain as tested helper modules. Shared orchestration lives in
`current_main_comparison.py`; each module keeps its physical inputs, units,
optimizer calls, and diagnostics explicit.

## Legacy Scripts

`examples/legacy/` contains archival snapshots of the original standalone
scripts:

- `ex_knownRp_PD.py`
- `ex_unknownRp_PD.py`

They document provenance but are not maintained execution targets; their old
working-directory data copy was removed during fixture canonicalization. The
reader-facing replacements are `docs/examples/knownRp_PD.ipynb` and
`docs/examples/unknownRp_PD.ipynb`, which are fresh-kernel tested through
`tests/test_original_workflow_notebooks.py`. New examples should follow the
maintained scripts in this directory instead.

## Adding Examples

- Name new scripts `example_<topic>.py`.
- Keep input values explicit and physically meaningful.
- Add a module docstring with purpose, usage, and output summary.
- Write outputs under `examples/outputs/`.
- Add focused smoke or regression coverage under `tests/`.
- Update this README only with a concise row in the maintained scripts table.

## References

- `docs/how-to-guides.md`: setup, examples, notebooks, and local validation.
- `docs/reference.md`: API boundaries and unit conventions.
- `tests/README.md`: test lanes and marker policy.
- `examples/outputs/README.md`: generated-output policy.
- `AGENTS.md`: coding-agent guidance.
