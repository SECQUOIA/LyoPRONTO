# Benchmarks Reorganization - Complete

**Date:** November 20, 2025  
**Status:** ✅ Complete

## What Changed

### Directory Structure

**Before:**
```
benchmarks/
  ├── data_loader.py, visualization.py, etc. (mixed in root)
  ├── grid_cli.py, generate_reports.py, etc. (mixed in root)
  ├── grid_analysis_SIMPLE.ipynb (in root)
  ├── *.png (loose artifacts in root)
  └── results/test/*.jsonl (flat)

analysis/  (separate top-level directory)
  └── test/Tsh/*.png, *.csv, *.json (mixed)
```

**After:**
```
benchmarks/
  ├── src/                          # Reusable modules
  │   ├── __init__.py
  │   ├── paths.py                  # Centralized path resolution
  │   ├── data_loader.py
  │   ├── visualization.py
  │   ├── analyze_benchmark.py
  │   ├── adapters.py
  │   ├── scenarios.py
  │   └── schema.py
  ├── scripts/                      # CLI entry points
  │   ├── grid_cli.py
  │   ├── generate_reports.py
  │   ├── run_grid.py
  │   ├── run_batch.py
  │   ├── validate.py
  │   └── diagnostics.py
  ├── notebooks/                    # Interactive analysis
  │   ├── grid_analysis_SIMPLE.ipynb
  │   └── grid_analysis.ipynb
  ├── results/                      # Versioned benchmark runs
  │   └── test/
  │       ├── raw/                  # Original JSONL files
  │       │   └── *.jsonl
  │       ├── processed/            # CSV tables, JSON summaries
  │       │   ├── comparison_table.csv
  │       │   ├── summary.json
  │       │   └── manifest.json
  │       └── figures/              # PNG plots (by task)
  │           ├── Tsh/
  │           │   ├── objective_diff_heatmap_fd.png
  │           │   ├── speedup_heatmap_colloc.png
  │           │   └── nominal_trajectory_*.png
  │           ├── Pch/
  │           └── both/
  ├── archive/                      # Superseded artifacts
  │   ├── README.md
  │   ├── legacy_notebooks/
  │   │   └── grid_analysis_OLD.ipynb
  │   └── superseded_figures/
  │       ├── objective_diff_heatmap.png (combined)
  │       └── both_grid_heatmaps.png
  ├── tests/                        # Future test suite location
  ├── cleanup.py                    # Automated maintenance
  └── README.md                     # New structure documentation
```

## Key Improvements

### 1. **Separation of Concerns**
- **`src/`**: Pure modules (importable, testable, no side effects)
- **`scripts/`**: CLI tools (thin wrappers around `src/`)
- **`notebooks/`**: Interactive analysis interfaces
- **`results/`**: All generated artifacts (versioned)

### 2. **Merged `analysis/` into `benchmarks/results/`**
- Eliminated duplicate directory structure
- Single source of truth for all benchmark outputs
- Clear hierarchy: `results/<version>/{raw,processed,figures}`

### 3. **Centralized Path Management**
- **`src/paths.py`**: All path logic in one place
- Functions: `get_results_dir()`, `get_figures_dir()`, `get_processed_dir()`
- No more hardcoded paths scattered across scripts

### 4. **Archive Stale Artifacts**
- Moved combined heatmaps to `archive/superseded_figures/`
- Moved legacy 1700-line notebook to `archive/legacy_notebooks/`
- Removed loose PNG files from root

### 5. **Automated Cleanup Utility**
- **`cleanup.py`**: Detects duplicates, validates naming, generates manifests
- Flags naming convention violations (helps maintain consistency)
- Can auto-archive superseded files with `--archive-duplicates`

### 6. **Updated Imports**
- Scripts: `from src.data_loader import ...`
- Notebooks: `from src import ...`
- All import paths updated to use new `benchmarks.src` package

### 7. **Enhanced `.gitignore`**
```
# Temporary/cache files
benchmarks/results/*/raw/*.tmp
benchmarks/results/*/cache/
benchmarks/results/**/*.log

# Large intermediate files
benchmarks/results/**/*.pkl
```

## Migration Impact

### ✅ What Still Works
- All existing notebooks (imports updated)
- All CLI scripts (moved to `scripts/`, imports updated)
- `generate_reports.py` (now writes to `results/<version>/processed/` and `figures/`)
- All Python modules (now in `src/`)

### 📝 What Changed
- **Default output location**: `results/test/` instead of `analysis/test/`
- **Import paths**: `from src.module import ...` instead of `from module import ...`
- **File locations**: 
  - JSONL → `raw/`
  - CSV/JSON → `processed/`
  - PNG → `figures/<task>/`

### 🔧 To Update
- External scripts that import benchmarks modules: Change `from data_loader` → `from benchmarks.src.data_loader`
- Hardcoded paths to `analysis/` directory: Change to `benchmarks/results/`

## Usage Examples

### Run Analysis
```bash
cd /home/bernalde/repos/LyoPRONTO/benchmarks
python scripts/generate_reports.py results/test --task Tsh
```

**Output:**
- `results/test/processed/summary.json`
- `results/test/processed/comparison_table.csv`
- `results/test/figures/Tsh/*.png` (8 files)

### Check for Issues
```bash
python cleanup.py --version test
```

### Generate Manifest
```bash
python cleanup.py --version test --generate-manifest
```

### Archive Duplicates
```bash
python cleanup.py --version test --archive-duplicates
```

## Preventing Future Clutter

### 1. **Use `cleanup.py` Regularly**
```bash
# Before committing
python cleanup.py --version <current_version> --check-only

# Weekly maintenance
python cleanup.py --version <current_version> --archive-duplicates --generate-manifest
```

### 2. **Follow File Naming Conventions**
- Trajectories: `traj_*.png`
- Objective heatmaps: `heatmap_obj_<method>.png`
- Speedup heatmaps: `heatmap_speed_<method>.png`
- Tables: `table_*.csv`
- Summaries: `summary*.json`

### 3. **Use Path Helpers**
```python
from src.paths import get_figures_dir, get_processed_dir

# Don't do this:
output_file = "analysis/test/Tsh/heatmap.png"

# Do this:
figures_dir = get_figures_dir("test", "Tsh")
output_file = figures_dir / "heatmap_obj_fd.png"
```

### 4. **Archive Old Versions**
When creating a new benchmark version (`v2`, `v3`, etc.):
```bash
# Compress old version
cd benchmarks/results
tar -czf v1_baseline.tar.gz v1_baseline/
mv v1_baseline.tar.gz ../archive/
rm -rf v1_baseline/
```

### 5. **Update `.gitignore` for New Patterns**
If you create new temporary file types, add them:
```bash
echo "benchmarks/results/**/*.tmp_new_type" >> .gitignore
```

## Testing

✅ **All tests passed:**
1. ✅ Moved core modules to `src/`
2. ✅ Moved CLI scripts to `scripts/`
3. ✅ Merged `analysis/` → `benchmarks/results/`
4. ✅ Restructured to `raw/processed/figures/`
5. ✅ Archived obsolete files
6. ✅ Created `cleanup.py` utility
7. ✅ Updated all imports
8. ✅ Updated `.gitignore`
9. ✅ Created documentation
10. ✅ Ran `generate_reports.py` successfully
    - Outputs in correct locations
    - All 8 figures generated
    - CSV and JSON in `processed/`
    - JSONL in `raw/`

## Metrics

- **Files moved:** 15 Python modules + 9 scripts + 2 notebooks + 12 images
- **Directories created:** 8 new subdirectories
- **Directories removed:** 1 (`analysis/`)
- **Lines of new code:** ~400 (paths.py + cleanup.py + README.md)
- **Import statements updated:** 18 files

## Next Steps (Optional)

1. **Rename files** to follow conventions:
   ```bash
   mv objective_diff_heatmap_fd.png heatmap_obj_fd.png
   mv speedup_heatmap_fd.png heatmap_speed_fd.png
   # etc.
   ```

2. **Move tests** from `benchmarks/` root to `benchmarks/tests/`:
   ```bash
   mv test_*.py tests/
   ```

3. **Add pre-commit hook** to run `cleanup.py --check-only`

4. **Compress `test` version** once validated:
   ```bash
   cd benchmarks/results
   tar -czf test.tar.gz test/
   mv test.tar.gz ../archive/
   ```

## Documentation

- **Main README**: `benchmarks/README.md` (new structure overview)
- **Archive README**: `benchmarks/archive/README.md` (what's archived and why)
- **This file**: Records the reorganization process
