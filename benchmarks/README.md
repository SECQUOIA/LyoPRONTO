# LyoPRONTO Benchmarks

Tools to compare Pyomo (finite differences + orthogonal collocation) vs Scipy optimizers across parameter grids.

## Current Workflow (Jan 2025)

### 1. Generate Grid Data
Use `grid_cli.py` to run Cartesian product benchmarks across N parameters:

```bash
# Generate 3×3 grid: scipy baseline + FD + collocation
python benchmarks/grid_cli.py generate \
  --task Tsh --scenario baseline \
  --vary product.A1=16,18,20 \
  --vary ht.KC=2.75e-4,3.3e-4,4.0e-4 \
  --methods scipy,fd,colloc \
  --n-elements 24 --n-collocation 3 \
  --out benchmarks/results/grid_A1_KC.jsonl
```

**Options:**
- `--vary key=val1,val2,...` (repeatable) — parameter sweeps
- `--methods scipy,fd,colloc` — which solvers to run
- `--n-elements N` — finite elements (both FD and collocation base)
- `--n-collocation NCP` — collocation points per element
- `--warmstart` — enable staged solve with scipy trajectory (off by default for robustness)
- `--raw-colloc` — disable effective-nfe parity reporting
- `--force` — regenerate even if output exists (reuse-first by default)

### 2. Analyze Results
Open `benchmarks/grid_analysis.ipynb` (read-only; expects pre-generated JSONL):

```bash
JSONL_PATH=benchmarks/results/baseline_Tsh_3x3_summary.jsonl jupyter notebook benchmarks/grid_analysis.ipynb
```

Notebook cells produce:
- CSV pivot tables (objectives, ratios, speedups)
- Heatmaps (objective difference, speedup, parity)
- Scatter plots and histograms
- Summary interpretation

## Core Modules

- **`grid_cli.py`** — CLI for N-dimensional grid generation (replaces legacy `run_grid*.py`)
- **`adapters.py`** — Normalized scipy/Pyomo runners with discretization metadata
- **`scenarios.py`** — Scenario definitions (vial, product, ht, eq_cap, nVial)
- **`schema.py`** — Versioned record serialization (v2: trajectories + hashing)
- **`validate.py`** — Physics checks (mass balance, dryness, constraint violations)
- **`grid_analysis.ipynb`** — Analysis notebook (read-only data loader)
- **`results/`** — Default output directory

## Tasks

- `Tsh` — optimize shelf temperature only (pressure fixed)
- `Pch` — optimize chamber pressure only (shelf fixed)
- `both` — joint optimization (pressure + temperature)

## Output Schema (v2)

Each JSONL record includes:
- `version`: schema version (currently 2)
- `hash.inputs`, `hash.record`: SHA-256 hashes for deduplication
- `environment`: Python, NumPy, Pyomo, and platform versions
- `task`, `scenario`: optimization variant and scenario name
- `params`: varied parameter path/value mapping used for `hash.inputs`
- `grid.param1`, `grid.param2`, ... : swept parameters with paths and values
- `scipy`: `{success, wall_time_s, objective_time_hr, solver, metrics}`
- `pyomo`: same as scipy, plus:
  - `discretization`: `{method, n_elements_requested, n_elements_applied, n_collocation, effective_nfe, total_mesh_points}`
  - `warmstart_used`: bool
- `failed`: overall failure flag (any solver failed, dryness unmet, or product temperature exceeded)

## Notes

- **Warmstart disabled by default** for robustness testing; enable with `--warmstart`.
- **Effective-nfe true by default** for collocation parity with FD mesh density.
- **Reuse-first**: if JSONL exists, generation skipped unless `--force` supplied.
- **Trajectories optional**: use `--save-trajectories` to embed trajectories (numpy arrays → lists during serialization).
- **Hashing** prevents duplicate runs (schema v2 `hash.inputs` field).
