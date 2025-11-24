# Pyomo Benchmark Diagnostics

Enhanced instrumentation for Pyomo optimization runs, capturing detailed solver, model, and environment metadata.

## Overview

The diagnostics module (`benchmarks/diagnostics.py`) automatically collects comprehensive metrics when Pyomo adapters run. This data enables:
- Deep failure forensics (distinguishing pre-solve, solver, post-solve failures)
- Performance analysis across environments
- Reproducibility tracking via option fingerprints and code versions
- Comparative analysis (scipy baseline vs Pyomo methods)

## Collected Fields

### Model Size
- `n_variables`: Total number of optimization variables
- `n_constraints`: Total number of constraints
- `n_objectives`: Number of objective functions (usually 1)

### IPOPT Solver Diagnostics
- `iterations`: Number of solver iterations (when available)
- `cpu_time_s`: CPU time spent in solver (seconds)
- `objective_final`: Final objective function value
- `primal_infeasibility`: Final constraint violation
- `dual_infeasibility`: Final dual feasibility metric
- `complementarity`: Complementarity measure
- `kkt_error`: Overall KKT error (NLP optimality measure)
- `barrier_parameter`: Final barrier parameter (mu)
- `barrier_objective`: Barrier objective value

*Note*: Some IPOPT metrics require log parsing and may not always be available through the Pyomo results object.

### Termination Detail
- `return_status_code`: Integer code mapping termination condition
  - `0`: optimal
  - `1`: iteration or time limit reached
  - `2`: infeasible
  - `3`: unbounded
  - `-1`: other/unknown

### Option Fingerprint
- `option_hash`: SHA-256 hash (16 chars) of all solver options
- `key_options`: Dictionary with key solver settings:
  - `linear_solver`
  - `tol`
  - `constr_viol_tol`
  - `mu_strategy`
  - `max_iter`

### Warmstart Metadata
- `warmstart_enabled`: Boolean flag
- `source_hash`: Hash of warmstart source (e.g., scipy baseline)
- `variable_match_ratio`: Fraction of variables successfully initialized

### Data Provenance
- `code_version`: Git commit SHA (12 chars)
- `environment`:
  - `python_version`: Python version string
  - `pyomo_version`: Pyomo version
  - `ipopt_version`: IPOPT version

### Solver Invocation Flags
- `solver_invoked`: True if solver.solve() was called
- `solver_returned`: True if solver returned a results object (even if failed)

## Usage

### In Benchmark Runs

Diagnostics are automatically collected when using the Pyomo adapter:

```python
from benchmarks.adapters import pyomo_adapter

result = pyomo_adapter(
    task='Tsh',
    vial=vial_params,
    product=product_params,
    ht=ht_params,
    eq_cap=eq_cap,
    nVial=1000,
    scenario={},
    dt=0.01,
    method='fd',
    n_elements=100,
)

# Access diagnostics
if result.get('diagnostics'):
    diag = result['diagnostics']
    print(f"Model: {diag['model_size']['n_variables']} vars")
    print(f"Status: {diag['return_status_code']}")
    print(f"Code: {diag['code_version']}")
    print(f"IPOPT: {diag['environment']['ipopt_version']}")
```

### In JSONL Benchmark Records

When benchmark results are serialized to JSONL, the `diagnostics` field is nested under the `pyomo` method block:

```json
{
  "timestamp": "2025-11-20T18:30:00Z",
  "pyomo": {
    "success": true,
    "wall_time_s": 1.23,
    "objective_time_hr": 13.2,
    "solver": {
      "status": "ok",
      "termination_condition": "optimal"
    },
    "diagnostics": {
      "solver_invoked": true,
      "solver_returned": true,
      "model_size": {
        "n_variables": 1001,
        "n_constraints": 1001,
        "n_objectives": 1
      },
      "return_status_code": 0,
      "code_version": "7da99a33a469",
      "environment": {
        "python_version": "3.13.9",
        "pyomo_version": "6.9.5",
        "ipopt_version": "3.13.2"
      },
      "option_fingerprint": {
        "option_hash": "30c79ba7109656ec",
        "key_options": {
          "tol": 1e-06,
          "constr_viol_tol": 1e-06,
          "mu_strategy": "adaptive",
          "max_iter": 5000
        }
      },
      "warmstart": {
        "warmstart_enabled": false,
        "source_hash": null,
        "variable_match_ratio": null
      },
      "ipopt": {
        "iterations": null,
        "cpu_time_s": 0.032,
        "objective_final": 13.2,
        "primal_infeasibility": null,
        "dual_infeasibility": null,
        "complementarity": null,
        "kkt_error": null
      }
    }
  }
}
```

## Standalone Usage

You can also collect diagnostics independently:

```python
from benchmarks import diagnostics as diag
import pyomo.environ as pyo

# After solving a model
model = ...  # your Pyomo model
results = solver.solve(model, tee=False)

# Collect diagnostics
solver_options = {
    'max_iter': 5000,
    'tol': 1e-6,
    'mu_strategy': 'adaptive',
}

full_diag = diag.collect_full_diagnostics(
    model=model,
    results=results,
    solver_options=solver_options,
    warmstart_source=None,
    warmstart_ratio=None
)

print(f"Model had {full_diag['model_size']['n_variables']} variables")
print(f"Solved in {full_diag['ipopt']['cpu_time_s']:.2f}s")
print(f"Environment: {full_diag['environment']}")
```

### Individual Utilities

```python
# Model size
model_size = diag.get_model_size(model)

# IPOPT metrics
ipopt_metrics = diag.parse_ipopt_diagnostics(results)

# Termination code
status_code = diag.get_termination_detail(results)

# Option fingerprint
opt_fp = diag.compute_option_fingerprint(solver_options)

# Environment
env = diag.get_environment_metadata()

# Git version
code_sha = diag.get_code_version()
```

## Integration Points

### Current Integration
- `benchmarks/adapters.py`: Pyomo adapter calls `diag.collect_full_diagnostics()` after successful solve
- `lyopronto/pyomo_models/optimizers.py`: Returns model and results in metadata when `return_metadata=True`

### Future Enhancements
- **Log parsing**: Extract full IPOPT iteration details from solver log
- **Failure classification**: Tag `failure_stage` (build_error, solve_fail, postcheck_fail)
- **Warmstart tracking**: Record scipy baseline hash and variable initialization success rate
- **Timing breakdown**: Separate model build, presolve, solve, postprocessing times

## Known Limitations

1. **IPOPT iterations**: Not always available via Pyomo results object; requires log file parsing
2. **IPOPT detailed metrics**: primal/dual infeasibility, complementarity, KKT error require parsing solver message or log
3. **Warmstart source hash**: Not yet implemented (placeholder exists)
4. **Linear solver detection**: Requires inspection of solver options or log output

## Version History

- **2025-11-20**: Initial implementation with core fields (model size, IPOPT diagnostics, provenance, option fingerprint)
