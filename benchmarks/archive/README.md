# Archive Directory

This directory contains deprecated or superseded artifacts kept for historical reference.

## Contents

### `legacy_notebooks/`
- `grid_analysis_OLD.ipynb` - Original 1700-line monolithic notebook (superseded by modular `notebooks/grid_analysis_SIMPLE.ipynb`)

### `superseded_figures/`
- **Combined heatmaps** (replaced by per-method split versions):
  - `objective_diff_heatmap.png` - Combined FD+Collocation objective difference
  - `speedup_heatmap.png` - Combined FD+Collocation speedup
- **Old trajectory plots** (replaced by per-variable split versions):
  - `nominal_trajectory.png` - Combined trajectory plot
  - `both_grid_heatmaps.png` - Legacy combined grid visualization
  - `example_both_trajectory.png` - Example trajectory from early development

### `old_docs/`
**Status/completion docs from implementation phases:**
- `BENCHMARKS_README.md` - Old main README (superseded by `../README.md`)
- `COMPLETED_WORK.md` - Implementation status snapshots
- `IMPLEMENTATION_SUMMARY.md` - What was built and why
- `QUICK_REFERENCE.md` - Old quick reference (info now in `../docs/`)
- `DIAGNOSTICS.md` - Diagnostic report from development
- `VISUALIZATION_UPDATE.md` - Notes on visualization changes
- `REORGANIZATION_COMPLETE.md` - This directory restructure summary

**Why archived:** These docs were useful during development but are now superseded by:
- `../README.md` - Current structure & getting started
- `../docs/CLI_GUIDE.md` - CLI usage
- `../docs/CLEANUP_UTILITY.md` - Maintenance guide
- `../docs/NOTEBOOKS_GUIDE.md` - Notebook usage

## Rationale

These files are retained for:
1. **Historical reference** - Understanding evolution of analysis approach
2. **Comparison** - Validating that new visualizations match legacy outputs
3. **Documentation archaeology** - Context for past design decisions

## Cleanup Policy

- Archives older than 6 months may be compressed to `.tar.gz`
- Large result sets (>100MB) should be compressed immediately
- When adding to archive, update this README with:
  - Filename
  - Date archived
  - Reason for deprecation
  - Replacement (if applicable)
