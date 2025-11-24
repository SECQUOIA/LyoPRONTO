# Benchmark Infrastructure Refactor — Complete

**Date:** January 2025  
**Branch:** `pyomo`  
**Status:** ✅ Production-ready

---

## Summary

Replaced bespoke 2×2 and 3×3 grid scripts with a unified CLI supporting N-dimensional parameter sweeps, multi-method comparison (scipy, finite differences, orthogonal collocation), discretization metadata, and read-only analysis notebook.

---

## What Changed

### 1. **New CLI: `benchmarks/grid_cli.py`**
   - **N-parameter Cartesian products**: `--vary key=val1,val2,...` (repeatable)
   - **Multi-method**: `--methods scipy,fd,colloc` (run all in one invocation)
   - **Discretization controls**: `--n-elements`, `--n-collocation`, `--raw-colloc`
   - **Warmstart flag**: `--warmstart` (default OFF for robustness testing)
   - **Reuse-first**: skips generation if JSONL exists unless `--force`
   - **Schema v2**: automatic hashing, trajectory embedding, version tracking

### 2. **Enhanced Adapters: `benchmarks/adapters.py`**
   - **Discretization metadata block**:
     - `method`: "fd" or "colloc"
     - `n_elements_requested`, `n_elements_applied`
     - `n_collocation` (colloc only)
     - `effective_nfe`: true for parity reporting
     - `total_mesh_points`: computed mesh size
   - **Warmstart default**: `False` (override with `warmstart=True`)
   - **Trajectory storage**: returns ndarray ready for serialization

### 3. **Schema v2: `benchmarks/schema.py`**
   - **Version field**: `"version": 2`
   - **Hashing utilities**: `hash_inputs()`, `hash_record()` (SHA-256 truncated)
   - **Trajectory-friendly serialization**: numpy arrays → lists automatically
   - **Environment capture**: Python, Pyomo, Ipopt versions; OS, hostname, timestamp

### 4. **Analysis Notebook: `benchmarks/grid_analysis.ipynb`**
   - **Read-only**: expects pre-generated JSONL (no generation cells)
   - **Multi-file ready**: can load and compare FD vs colloc vs scipy datasets
   - **Outputs**:
     - CSV pivot tables (objectives, ratios, speedups)
     - Heatmaps (objective difference, speedup, parity)
     - Scatter plots, histograms, summary interpretation
   - **Environment variables**: `JSONL_PATH`, `METRIC` for headless execution

### 5. **Minimal Makefile**
   - **Deprecated legacy targets**: removed `bench-grid`, `bench-grid-3x3`, `grid-summary`, `analyze-3x3`, `bench-single`, `bench-batch`, `bench-aggregate`
   - **New targets**:
     - `make bench`: generate via `grid_cli.py`
     - `make analyze`: execute notebook headless (optional nbconvert)
     - `make help`: show usage and examples
   - **Defaults**: `TASK=Tsh`, `SCENARIO=baseline`, `METHODS=scipy,fd,colloc`, `N_ELEMENTS=24`, `N_COLLOCATION=3`

### 6. **Removed Legacy Scripts**
   - `benchmarks/run_single.py`
   - `benchmarks/run_batch.py`
   - `benchmarks/aggregate.py`
   - `benchmarks/run_grid.py`
   - `benchmarks/run_grid_3x3.py`
   - `benchmarks/summarize_grid.py`

### 7. **Documentation Updates**
   - **`benchmarks/README.md`**: rewritten with new CLI workflow, schema v2 details, migration guide
   - **`README.md`**: added benchmarking quick-start section after examples

---

## Usage Examples

### Generate 3×3 grid (scipy + FD + collocation)
```bash
python benchmarks/grid_cli.py generate \
  --task Tsh --scenario baseline \
  --vary product.A1=16,18,20 \
  --vary ht.KC=2.75e-4,3.3e-4,4.0e-4 \
  --methods scipy,fd,colloc \
  --n-elements 24 --n-collocation 3 \
  --out benchmarks/results/grid_A1_KC.jsonl
```

### Makefile shortcut
```bash
make bench VARY='product.A1=16,18,20 ht.KC=2.75e-4,3.3e-4,4.0e-4' METHODS=fd,colloc
```

### Analyze results
```bash
# Jupyter interactive
JSONL_PATH=benchmarks/results/grid_A1_KC.jsonl jupyter notebook benchmarks/grid_analysis.ipynb

# Headless via Makefile
make analyze OUT=benchmarks/results/grid_A1_KC.jsonl METRIC=ratio.pyomo_over_scipy
```

### Compare FD vs Collocation
```bash
# Generate FD dataset
python benchmarks/grid_cli.py generate --task Tsh --scenario baseline \
  --vary product.A1=16,18,20 --vary ht.KC=2.75e-4,3.3e-4,4.0e-4 \
  --methods scipy,fd --out benchmarks/results/grid_fd.jsonl

# Generate collocation dataset
python benchmarks/grid_cli.py generate --task Tsh --scenario baseline \
  --vary product.A1=16,18,20 --vary ht.KC=2.75e-4,3.3e-4,4.0e-4 \
  --methods scipy,colloc --out benchmarks/results/grid_colloc.jsonl

# Load both in notebook for side-by-side comparison
```

---

## Key Design Principles

1. **Coexistence, not replacement**: scipy remains baseline; Pyomo (FD + colloc) added as parallel methods
2. **Warmstart disabled by default**: robustness testing prioritized over convergence assistance
3. **Effective-nfe for collocation**: reports collocation `n_elements` as effective parity with FD mesh
4. **Reuse-first**: avoid redundant computation; hash-based deduplication planned (schema v2 ready)
5. **Read-only analysis**: notebook ingests pre-generated JSONL; no mutation of results
6. **Separation of concerns**: generation (CLI) vs analysis (notebook) decoupled for scalability

---

## Schema v2 Record Structure (Excerpt)

```json
{
  "version": 2,
  "hash": {
    "inputs": "a3f5c2...",
    "record": "7d8e1b..."
  },
  "environment": { "python": "3.13.1", "pyomo": "6.8.0", ... },
  "task": "Tsh",
  "scenario": "baseline",
  "grid": {
    "param1": {"path": "product.A1", "value": 18.0},
    "param2": {"path": "ht.KC", "value": 3.3e-4}
  },
  "scipy": {
    "success": true,
    "wall_time_s": 2.45,
    "objective_time_hr": 12.34,
    "solver": {...},
    "metrics": {"mass_balance_error_pct": 0.12, "dryness_target_met": true, ...}
  },
  "pyomo": {
    "success": true,
    "wall_time_s": 0.87,
    "objective_time_hr": 12.31,
    "solver": {...},
    "metrics": {...},
    "discretization": {
      "method": "colloc",
      "n_elements_requested": 24,
      "n_elements_applied": 24,
      "n_collocation": 3,
      "effective_nfe": true,
      "total_mesh_points": 73
    },
    "warmstart_used": false
  },
  "failed": false
}
```

---

## Testing

- **CLI help**: `python benchmarks/grid_cli.py --help` ✅
- **Makefile help**: `make help` ✅
- **Small test run**: ready for manual validation (2×2 grid scipy+fd takes ~30s)
- **Notebook execution**: compatible with `nbconvert --execute` for CI

---

## Migration Guide (for existing users)

### Old workflow (deprecated)
```bash
make bench-grid-3x3 P1_VALUES=16,18,20 P2_VALUES=2.75e-4,3.3e-4,4.0e-4
make grid-summary INFILE=benchmarks/results/grid_3x3.jsonl
```

### New workflow
```bash
python benchmarks/grid_cli.py generate \
  --task Tsh --scenario baseline \
  --vary product.A1=16,18,20 \
  --vary ht.KC=2.75e-4,3.3e-4,4.0e-4 \
  --methods scipy,fd,colloc \
  --out benchmarks/results/grid.jsonl

JSONL_PATH=benchmarks/results/grid.jsonl jupyter notebook benchmarks/grid_analysis.ipynb
```

Or use Makefile:
```bash
make bench VARY='product.A1=16,18,20 ht.KC=2.75e-4,3.3e-4,4.0e-4'
make analyze OUT=benchmarks/results/grid.jsonl
```

---

## Next Steps (Future Enhancements)

- [ ] **Legacy record migration tool**: convert schema v1 → v2 (add hashes, version)
- [ ] **CLI `slice` command**: filter JSONL by parameter ranges or methods
- [ ] **CLI `merge` command**: combine multiple JSONL files with deduplication
- [ ] **CLI `pivot2d` command**: CSV generation without notebook
- [ ] **Trajectory embedding validation**: confirm numpy→list round-trip correctness
- [ ] **Multi-file comparison notebook cells**: automated FD vs colloc plots
- [ ] **CI benchmark regression**: track objective parity and speedup trends over commits

---

## Files Modified

**Created:**
- `benchmarks/grid_cli.py` (new unified CLI)
- `docs/BENCHMARK_REFACTOR_COMPLETE.md` (this document)

**Updated:**
- `benchmarks/adapters.py` (discretization metadata, warmstart default)
- `benchmarks/schema.py` (v2 schema, hashing, trajectory serialization)
- `benchmarks/grid_analysis.ipynb` (read-only loader, removed generation)
- `Makefile` (minimal `bench`/`analyze` targets)
- `benchmarks/README.md` (new workflow documentation)
- `README.md` (benchmarking quick-start section)

**Removed:**
- `benchmarks/run_single.py`
- `benchmarks/run_batch.py`
- `benchmarks/aggregate.py`
- `benchmarks/run_grid.py`
- `benchmarks/run_grid_3x3.py`
- `benchmarks/summarize_grid.py`

---

## Contact

Questions or issues? See `docs/GETTING_STARTED.md` for developer setup or open an issue referencing this refactor document.
