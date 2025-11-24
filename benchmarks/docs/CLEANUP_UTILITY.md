# Cleanup Utility Guide

The `cleanup.py` utility automates benchmark workspace maintenance.

## Usage

```bash
# Check for issues (no changes)
python cleanup.py --version <version> --check-only

# Generate artifact manifest
python cleanup.py --version <version> --generate-manifest

# Archive duplicate files
python cleanup.py --version <version> --archive-duplicates
```

## What It Does

### Duplicate Detection
- Finds combined heatmaps when split versions exist (e.g., `objective_diff_heatmap.png` vs `*_fd.png` + `*_colloc.png`)
- Detects old combined trajectory plots vs new split versions

### Naming Validation
- Checks files follow conventions:
  - `traj_*.png` for trajectories
  - `heatmap_obj_*.png` for objective heatmaps
  - `heatmap_speed_*.png` for speedup heatmaps

### Manifest Generation
Creates `results/<version>/manifest.json` with:
- File inventory (raw, processed, figures)
- File sizes and modification times
- SHA256 hashes for JSONL files

## Recommended Workflow

Before commits:
```bash
python cleanup.py --version test --check-only
```

After generating new benchmarks:
```bash
python cleanup.py --version <version> --generate-manifest
```

Monthly maintenance:
```bash
python cleanup.py --version <version> --archive-duplicates
```

## Example Output

```
🔍 Checking benchmark version: test

============================================================
CLEANUP REPORT
============================================================

🔍 Found 2 duplicate(s):
  - objective_diff_heatmap.png ≈ objective_diff_heatmap_fd.png
    Reason: Combined heatmap superseded by split versions

⚠️  Found 4 naming violation(s):
  - speedup_heatmap_fd.png: Heatmap should use 'heatmap_speed_' prefix

📦 Archived 2 file(s):
  - objective_diff_heatmap.png → archive/superseded_figures/
  
✅ No errors
============================================================
```
