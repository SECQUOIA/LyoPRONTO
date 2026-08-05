# LyoPRONTO external fixtures

`test_data/` owns immutable inputs and independent reference outputs. Python
test logic belongs in `tests/`; reusable example computation belongs in
`examples/`. These files stay separate because they exercise file-oriented
compatibility and provide reference evidence independent of the implementation.

Keeping this directory at the repository root is deliberate. The fixtures are
consumed by maintained examples, the file-oriented `main.py` compatibility
path, and tests; moving them under `tests/data/` would incorrectly imply
test-only ownership while forcing churn in YAML inputs, examples, workflows,
and documentation. Reconsider the path only if those non-test consumers are
retired. This decision concerns location, not ownership: every artifact below
still has one canonical tracked copy and named consumers.

## Measured input

| File | Format and units | Provenance | Consumers |
| --- | --- | --- | --- |
| `temperature.txt` | 452 measured rows: time [hr], vial-bottom temperature [degC] | Original web-interface unknown-Rp input | `examples/original_workflow_parity.py`, `examples/example_parameter_estimation.py`, unknown-Rp and scientific-reference tests |

This is the one canonical copy of the measured series. Documentation notebooks
load it through `examples.original_workflow_parity`; the former notebook and
legacy-script copies were byte- or normalization-equivalent duplicates.

## Independent reference outputs

All CSVs use semicolon delimiters and preserve the legacy web-interface output
units. Primary-drying and optimizer trajectories have seven columns: time [hr],
sublimation-front temperature [degC], vial-bottom temperature [degC], shelf
temperature [degC], chamber pressure [mTorr], sublimation flux [kg/hr/m^2], and
percent dried [0-100].

| File | Provenance and purpose | Consumers |
| --- | --- | --- |
| `reference_primary_drying.csv` | Web-interface known-Rp output, 2025-10-01 | `tests/test_calc_knownRp.py`, scientific-reference scenario |
| `reference_opt_Tsh.csv` | Web-interface shelf-temperature optimizer output, 2025-10-01 | `tests/test_opt_Tsh.py`, scientific-reference scenario |
| `reference_opt_Pch.csv` | Web-interface pressure optimizer output | `tests/test_opt_Pch.py` |
| `reference_freezing.csv` | Web-interface freezing output, 2025-10-01 | `tests/test_freezing.py`, scientific-reference scenario |

`reference_opt_Tsh.csv` is the sole shelf-optimizer reference. The retired
`reference_optimizer.csv` differed only in line endings and fed a redundant
historical test file. The retired `reference_design_space.csv` mixed a stale
shelf-temperature row with otherwise current sections and had no regression
consumer, so it and the example's silently skipped comparison were removed.

## Self-generated regression baselines

These share the schema above but are **not** independent references: they are
this repository's own output, recorded to detect unintended drift. They
demonstrate stability, not correctness, and can never confirm that a
trajectory is physically right — only that it has not changed. Keep the
`regression_` prefix so the distinction from `reference_` stays visible at the
call site.

| File | Provenance and purpose | Consumers |
| --- | --- | --- |
| `regression_opt_Pch_Tsh.csv` | Joint-optimizer trajectory generated from `dfdb53d` using the `standard_opt_pch_tsh_inputs` fixture; pins the trajectory against solver and formulation drift | `tests/test_opt_Pch_Tsh.py` |

The joint optimizer has no independent web-interface reference, and the two
that do exist are weak comparators for element-wise checks — `test_opt_Pch.py`
documents that comparing against `reference_opt_Pch.csv` directly is "brittle
and not meaningful" for that case. A recorded baseline is what actually guards
this module, so it is kept deliberately rather than as a stand-in for a
reference that does not exist.

When a change to the optimizer is intended, regenerate the baseline and update
the generating commit in the table above; do not widen the test's tolerance to
absorb a real behavioral change.

## File-interface YAML cases

The ten YAML files below are external input fixtures consumed by
`tests/test_main.py` through the `lyopronto.high_level`/`main.py` compatibility
path:

- `example_freezing.yaml`
- `example_knownrp.yaml`
- `example_unknownkv.yaml`
- `example_unknownrp.yaml`
- `example_design_space.yaml`
- `example_opt_tsh.yaml`
- `example_opt_pch.yaml`
- `example_opt_pch_tsh.yaml`
- `badexample_unknownkvrp.yaml`
- `badexample_optimizer_noopt.yaml`

## Adding data

For every new fixture, document its provenance, delimiter/schema, physical
units, and real consumer here. Use `reference_<mode>.csv` for independent
expected outputs and descriptive names for measured inputs. Do not commit local
run output, sensitive/proprietary data, or an artifact that can be generated
deterministically from repository inputs without a stated regression purpose.
