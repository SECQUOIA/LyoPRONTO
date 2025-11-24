# Future Work Roadmap (Pyomo Integration Phase)

This document captures forward-looking enhancements identified during constraint validation, timeout integration, and benchmarking toolchain development.

## Near-Term Enhancements (High Impact)
- Wall-Time Enforcement: Implement external wall clock guard (subprocess wrapper) or upgrade IPOPT to >=3.14 to access `max_wall_time` option.
- Constraint Metrics in Analysis: Extend `generate_reports.py` to produce heatmaps for `max_Pch_ramp_violation`, `max_Tsh_ramp_violation`, and dryness shortfall.
- Logging Refactor: Replace bare `print` calls in Pyomo optimizers with a lightweight module logger supporting verbosity levels (`silent`, `info`, `debug`).
- Unit Tests Expansion: Add tests for `validate_constraints` ramp logic (synthetic trajectory) and adapter ramp override ordering.
- Manifest Schema Doc: Introduce `docs/BENCHMARK_SCHEMA.md` describing JSONL v2 fields including constraint metrics.
- CI Micro-Grid: Add a small (2×2) grid run in CI (marked slow, opt-in) to smoke test Pyomo path and schema integrity.

## Medium-Term Improvements
- Trust Region / Regularization: Optional toggles for adaptive trust radii (`--trust`) to stabilize challenging FD joint optimizations.
- Warmstart Strategies: Compare staged solve vs direct solve automatically; record fallback path in metadata.
- Discretization Advisor: Heuristic recommendation of `n_elements` + `n_collocation` based on dryness target and ramp constraints.
- Structured Fail Modes: Classify `maxIterations`, infeasibility, timeout, and ramp violation in a normalized `failure_reason` field.
- Incremental Dryness Target: Support progressive tightening (e.g., 95% → 99%) to improve convergence robustness.

## Longer-Term Directions
- Multi-Period Formulation: Implement Pyomo trajectory optimization over discrete phases (freezing + primary drying) with phase continuity constraints.
- Parameter Estimation via Pyomo: Integrate unknown Rp parameter fitting with solver-based sensitivity measures.
- Hybrid Solver Selection: Automatic switch between FD and collocation based on preliminary residual scan.
- Performance Benchmarking: Track and report CPU profile segments (model build vs solve vs extraction) for optimization.
- Visualization API: Python API returning figure objects instead of writing PNGs for downstream applications.

## Documentation Tasks
- Update `grid_cli.py` header: Add explicit note on `--solver-timeout` (CPU time semantics) and constraint failure marking.
- Add `run_single_case.py` section to developer guide (`GETTING_STARTED.md`).
- Notebook Annotation: Insert JSONL v2 schema explanation and constraint metric summary cell (DONE when merged).

## Open Questions / Research Topics
- Ramp Constraint Formulation: Evaluate alternative smoothing for ramp penalties vs hard constraints.
- Solver Scaling: Assess impact of tighter `bound_relax_factor` on feasibility recovery.
- Piecewise Control Parametrization: Evaluate reduced variable formulation for large element counts.

## Acceptance Criteria for Closure
A future milestone completes when:
1. Wall time guard reliably stops pathological >CPU loops.
2. Constraint metric heatmaps are generated and documented.
3. CI micro-grid test passes in standard workflow.
4. Schema doc (`BENCHMARK_SCHEMA.md`) merged and referenced by notebook.
5. Logging verbosity reduces noise in non-debug runs.

---
_Last updated: Initial creation during timeout/constraint validation integration._
