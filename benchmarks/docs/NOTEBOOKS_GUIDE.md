# Jupyter Notebooks Guide

## Current Notebooks (2 Active)

### 1. `grid_analysis_SIMPLE.ipynb` ⭐ **RECOMMENDED**

**Purpose**: Modern simplified viewer for pre-generated analysis  
**Size**: ~150 lines (95% smaller than original!)  
**Status**: ✅ **Use this for all new work**

**Features**:
- Just displays pre-generated analysis artifacts
- Clean, focused, maintainable
- Works with modular Python infrastructure
- Easy to customize

**Workflow**:
1. Generate benchmarks: `python grid_cli.py generate ...`
2. Generate analysis: `python generate_reports.py results/<version>`
3. Open this notebook and set `benchmark_version` and `task`
4. Run cells to view results

**Default Configuration**: Points to `test` benchmark for quick validation

---

### 2. `grid_analysis.ipynb` (Original)

**Purpose**: Original comprehensive analysis notebook  
**Size**: ~1700 lines  
**Status**: ✅ Kept for historical reference  

**Contains**:
- All analysis logic embedded in cells
- Inline data processing and visualization
- Self-contained (doesn't use Python modules)

**When to Use**:
- Historical reference
- Need to see original analysis approach
- One-off custom analysis that doesn't fit the standard workflow

---

## Archived Notebooks

### `archive/grid_analysis_OLD.ipynb`

**Purpose**: Backup copy created during infrastructure refactoring  
**Status**: Archived (can be deleted after validation period)  
**Why**: Safety measure during transition to modular infrastructure

---

## Recommendation

**For all new benchmark analysis work**: Use `grid_analysis_SIMPLE.ipynb`

The simplified notebook works with the modular Python infrastructure:
- `data_loader.py` - Load and organize JSONL data
- `analyze_benchmark.py` - Compute metrics and comparisons
- `visualization.py` - Generate plots
- `generate_reports.py` - Orchestrate analysis generation

This separation makes the code:
- More maintainable
- Easier to test
- Reusable in scripts and automation
- Cleaner and more focused
- Data loading (uses `data_loader.py`)
- Display pre-generated figures
- Load pre-generated tables
- Minimal computation (just viewing)

**When to Use**:
- ✅ **Normal benchmarking workflow** (recommended)
- ✅ Viewing results after running `generate_reports.py`
- ✅ Quick comparisons between versions
- ✅ Clean, professional presentations

**Workflow**:
```bash
# 1. Generate benchmarks
python grid_cli.py generate ... --out results/v2/Tsh.jsonl

# 2. Generate ALL analysis (one command!)
python generate_reports.py results/v2

# 3. View in simplified notebook
jupyter notebook grid_analysis_SIMPLE.ipynb
```

## Recommended Usage

### For Daily Work: Use `grid_analysis_SIMPLE.ipynb` ⭐

**Why**:
- Fast (no recomputation)
- Clean (just viewing)
- Professional (separation of concerns)
- Easy to understand
- Works with modular infrastructure

**Steps**:
1. Set `benchmark_version = "v2"` and `task = "Tsh"`
2. Run cells
3. View heatmaps, tables, trajectories

### For Historical Reference: Keep `grid_analysis.ipynb`

**Why**:
- Shows evolution of analysis approach
- Contains inline computation examples
- Useful for understanding decisions

**Don't modify** - preserved for reference

### For Safety: Keep `grid_analysis_OLD.ipynb`

**Why**:
- Backup in case something goes wrong
- Can compare implementations
- Safety net during transition

**Can be deleted** after new infrastructure is proven

## Comparison

| Feature | Original (1700 lines) | SIMPLE (150 lines) |
|---------|----------------------|-------------------|
| **Lines of code** | 1700 | 150 |
| **Complexity** | High (mixed concerns) | Low (just viewing) |
| **Recomputation** | Every time | Never (pre-generated) |
| **Testability** | Difficult | Easy (modules tested) |
| **Maintenance** | Hard (monolithic) | Easy (modular) |
| **Speed** | Slow (recomputes) | Fast (just loads) |
| **Use case** | Reference | **Daily work** ⭐ |

## Migration Path

### Current State
- ✅ All 3 notebooks coexist
- ✅ Old approach still works (grid_analysis.ipynb)
- ✅ New approach ready (grid_analysis_SIMPLE.ipynb)

### Recommended
1. **Use** `grid_analysis_SIMPLE.ipynb` for new work
2. **Keep** `grid_analysis.ipynb` for reference
3. **Keep** `grid_analysis_OLD.ipynb` for safety (can delete later)

### Future (After Validation)
1. Once new infrastructure proven reliable:
   - Delete `grid_analysis_OLD.ipynb` (no longer needed)
   - Keep `grid_analysis.ipynb` (historical reference)
   - Use `grid_analysis_SIMPLE.ipynb` (daily work)

2. Eventually (optional):
   - Archive `grid_analysis.ipynb` to `legacy/` or `docs/archive/`
   - Rename `grid_analysis_SIMPLE.ipynb` → `grid_analysis.ipynb`

## Benefits of SIMPLE Notebook

### Separation of Concerns
- **Data**: JSONL files in `results/<version>/`
- **Analysis**: Python modules (`analyze_benchmark.py`, etc.)
- **Visualization**: Generated artifacts in `analysis/<version>/`
- **Presentation**: Notebook just displays results

### Advantages
1. ✅ **Faster**: No recomputation (just load images)
2. ✅ **Cleaner**: 95% fewer lines
3. ✅ **Testable**: Analysis logic in modules
4. ✅ **Reusable**: Functions importable
5. ✅ **Reproducible**: CLI-driven workflow
6. ✅ **Professional**: Industry best practices

### Workflow
```
Generate Data → Generate Analysis → View Results
(grid_cli.py)   (generate_reports)  (SIMPLE notebook)
```

## Which One Should I Use?

### Quick Decision Tree

**Are you viewing existing benchmark results?**
→ Use `grid_analysis_SIMPLE.ipynb` ⭐

**Do you need to modify analysis logic?**
→ Modify Python modules (`analyze_benchmark.py`, etc.), then use SIMPLE notebook

**Do you want to see how the old approach worked?**
→ Open `grid_analysis.ipynb` (read-only)

**Do you need to recover from a mistake?**
→ Use `grid_analysis_OLD.ipynb` (backup)

## Summary

**3 Notebooks, 3 Purposes**:

1. **Original** (`grid_analysis.ipynb`) - Reference, keep
2. **Backup** (`grid_analysis_OLD.ipynb`) - Safety, can delete after validation
3. **Simple** (`grid_analysis_SIMPLE.ipynb`) - **Daily use, recommended** ⭐

**Recommendation**: Use the SIMPLE notebook for all new work!

---

**Created**: 2025-11-19  
**Purpose**: Clarify notebook situation after infrastructure refactoring  
**Status**: Final organization
