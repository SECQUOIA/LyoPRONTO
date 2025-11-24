# Repository Organization Guide

**Last Updated**: 2025-11-19  
**Purpose**: Explain the clean, organized structure of the LyoPRONTO repository after cleanup.

## 🎯 Overview

The repository follows a clean, professional structure with clear separation of concerns:
- **Source code**: `lyopronto/` - Core physics and optimization modules
- **Examples**: `examples/` - User-facing example scripts
- **Tests**: `tests/` - Comprehensive test suite
- **Benchmarks**: `benchmarks/` - Performance analysis infrastructure
- **Documentation**: `docs/` - Architecture, guides, and references

## 📁 Repository Structure

```
LyoPRONTO/
├── lyopronto/              # Core source code
│   ├── __init__.py
│   ├── constant.py         # Physical constants
│   ├── functions.py        # Physics equations
│   ├── calc_knownRp.py     # Primary drying (known resistance)
│   ├── calc_unknownRp.py   # Primary drying (unknown resistance)
│   ├── freezing.py         # Freezing phase
│   ├── design_space.py     # Design space generation
│   ├── opt_Tsh.py          # Temperature optimizer (scipy)
│   ├── opt_Pch.py          # Pressure optimizer (scipy)
│   ├── opt_Pch_Tsh.py      # Both optimizer (scipy)
│   └── pyomo_models/       # Pyomo optimization (coexists with scipy)
│       ├── __init__.py
│       ├── optimizers.py   # Main optimization functions
│       ├── constraints.py  # Constraint builders
│       └── mesh.py         # Discretization helpers
│
├── examples/               # User-facing examples
│   ├── README.md           # Example documentation
│   ├── example_web_interface.py      # Primary drying (4 modes)
│   ├── example_parameter_estimation.py
│   ├── example_optimizer.py
│   ├── example_freezing.py
│   ├── example_design_space.py
│   ├── legacy/             # Legacy scripts (maintained)
│   └── outputs/            # Example outputs (gitignored)
│
├── tests/                  # Test suite (85 tests, 100% passing)
│   ├── README.md           # Test documentation
│   ├── conftest.py         # Shared fixtures
│   ├── test_functions.py   # Unit tests for physics
│   ├── test_calculators.py # Integration tests
│   ├── test_freezing.py
│   ├── test_design_space.py
│   ├── test_optimizer.py
│   ├── test_opt_*.py       # Optimizer-specific tests
│   ├── test_calc_*.py      # Calculator-specific tests
│   ├── test_regression.py  # Regression tests
│   ├── test_example_scripts.py
│   └── test_web_interface.py
│
├── benchmarks/             # Performance analysis infrastructure
│   ├── README.md           # Legacy benchmark docs
│   ├── BENCHMARKS_README.md        # Infrastructure overview ⭐
│   ├── GRID_CLI_GUIDE.md           # Complete grid_cli.py reference ⭐
│   ├── QUICK_REFERENCE.md          # Workflow quick reference ⭐
│   ├── COMPLETED_WORK.md           # Implementation summary
│   ├── IMPLEMENTATION_SUMMARY.md   # What was built
│   ├── grid_cli.py         # Benchmark generation CLI
│   ├── generate_reports.py # Analysis generation CLI
│   ├── data_loader.py      # Data loading utilities
│   ├── analyze_benchmark.py # Analysis functions
│   ├── visualization.py    # Plotting utilities
│   ├── test_analysis_infrastructure.py
│   ├── grid_analysis_SIMPLE.ipynb  # Simplified viewer (150 lines)
│   ├── grid_analysis_OLD.ipynb     # Old notebook backup (1700 lines)
│   ├── scenarios.py        # Benchmark scenarios
│   ├── adapters.py         # Scipy/Pyomo adapters
│   ├── schema.py           # Data schema
│   ├── validate.py         # Validation utilities
│   ├── results/            # Benchmark data (versioned)
│   │   ├── README.md
│   │   ├── v1_baseline/    # Old benchmarks (wrong discretization)
│   │   ├── v2_*/           # New benchmarks (correct discretization)
│   │   └── archive/        # Scattered old files (36+ files cleaned)
│   └── analysis/           # Generated artifacts (heatmaps, tables, etc.)
│       └── <version>/
│           ├── Tsh/
│           ├── Pch/
│           └── both/
│
├── docs/                   # Documentation
│   ├── README.md           # Documentation index
│   ├── GETTING_STARTED.md  # Developer setup ⭐
│   ├── ARCHITECTURE.md     # System design ⭐
│   ├── PHYSICS_REFERENCE.md # Equations and models ⭐
│   ├── PYOMO_ROADMAP.md    # Pyomo integration plan ⭐
│   ├── COEXISTENCE_PHILOSOPHY.md # Scipy + Pyomo coexistence ⭐
│   ├── DEVELOPMENT_LOG.md  # Chronological changes
│   ├── CI_QUICK_REFERENCE.md
│   ├── CI_WORKFLOW_GUIDE.md
│   ├── PARALLEL_TESTING.md
│   ├── TESTING_STRATEGY.md
│   ├── index.md            # MkDocs index
│   ├── explanation.md
│   ├── how-to-guides.md
│   ├── tutorials.md
│   ├── reference.md
│   └── archive/            # Historical documents (26+ files archived)
│       ├── CODE_STRUCTURE.md
│       ├── *_COMPLETE.md   # Completion summaries
│       ├── *_SUMMARY.md    # Process summaries
│       ├── RAMP_*.md       # Ramp constraint experiments
│       └── ...
│
├── test_data/              # Test data files
│   └── README.md
│
├── .github/                # GitHub workflows and config
│   ├── copilot-instructions.md # Copilot context ⭐
│   └── workflows/
│       └── tests.yml       # CI/CD pipeline
│
├── README.md               # Main project README ⭐
├── CONTRIBUTING.md         # Contribution guidelines
├── LICENSE.txt             # GPL v3 license
├── requirements.txt        # Production dependencies
├── requirements-dev.txt    # Development dependencies
├── pyproject.toml          # Modern Python project config
├── setup.py               # Legacy setup (maintained)
├── pytest.ini             # Pytest configuration
├── mkdocs.yml             # Documentation site config
├── Makefile               # Build shortcuts
├── run_local_ci.sh        # Local CI script
└── main.py                # Legacy CLI entry point
```

## 🗂️ Key Directories Explained

### `lyopronto/` - Source Code
**Purpose**: Core physics simulation and optimization  
**Philosophy**: Coexistence - both scipy and Pyomo available  
**Key Files**:
- `functions.py` - All physics equations (vapor pressure, heat transfer, mass transfer)
- `constant.py` - Physical constants and unit conversions
- `calc_*.py` - Simulation calculators
- `opt_*.py` - Scipy optimizers (maintained alongside Pyomo)
- `pyomo_models/` - Pyomo optimizers (parallel implementation, not replacement)

### `examples/` - User-Facing Examples
**Purpose**: Easy-to-run examples for new users  
**Recommended Starting Point**: `example_web_interface.py`  
**Structure**:
- Modern examples (recommended): `example_*.py`
- Legacy examples (maintained): `legacy/`
- Generated outputs (gitignored): `outputs/`

### `tests/` - Test Suite
**Purpose**: Ensure code correctness and prevent regressions  
**Status**: 85 tests, 100% passing, 32% code coverage  
**Organization**:
- `test_functions.py` - Unit tests for physics functions
- `test_calculators.py` - Integration tests for simulators
- `test_opt_*.py` - Optimizer-specific tests
- `test_regression.py` - Regression tests
- `conftest.py` - Shared fixtures and utilities

### `benchmarks/` - Performance Analysis
**Purpose**: Compare Pyomo vs scipy performance across parameter grids  
**Recent Cleanup**: Reduced from 36+ scattered files to organized structure  
**Key Features**:
- Modular Python infrastructure (data → analysis → visualization)
- CLI-driven workflow (`grid_cli.py` + `generate_reports.py`)
- Version control for benchmarks (`v1_baseline/`, `v2_*/`)
- Simplified notebook (1700 → 150 lines)

**⭐ Start Here**: `QUICK_REFERENCE.md` for complete workflow

### `docs/` - Documentation
**Purpose**: Architecture, guides, physics references, development history  
**Recent Cleanup**: Moved 26+ completion/summary docs to `archive/`  
**Essential Docs** (⭐ marked in structure):
- `GETTING_STARTED.md` - Developer setup
- `ARCHITECTURE.md` - System design
- `PHYSICS_REFERENCE.md` - Equations and models
- `PYOMO_ROADMAP.md` - Pyomo integration plans
- `COEXISTENCE_PHILOSOPHY.md` - Scipy + Pyomo parallel approach

## 🧹 Recent Cleanup (2025-11-19)

### Benchmarks Directory
**Before**: 36+ scattered PNG, CSV, JSONL files  
**After**: Clean structure with version control

**Actions**:
- ✅ Moved all PNG/CSV to `results/archive/`
- ✅ Organized `*_free.jsonl` into `results/v1_baseline/`
- ✅ Moved test/debug JSONL to `results/archive/`
- ✅ Created `analysis/` for generated artifacts

**Result**: `results/` now contains only:
- `README.md` - Documentation
- `v1_baseline/` - Old benchmarks (wrong discretization)
- `archive/` - All scattered files (safe, reversible)

### Root Directory
**Before**: Scattered experiment files  
**After**: Clean root with only essential files

**Actions**:
- ✅ Moved `RAMP_*.md` to `docs/archive/`
- ✅ Moved `ramp_constraint_*.png` to `docs/archive/`
- ✅ Moved `test_ramp_constraints.py` to `docs/archive/`

### Docs Directory
**Before**: 40+ markdown files (many completion summaries)  
**After**: 15 essential docs, rest in `archive/`

**Actions**:
- ✅ Moved 14 `*_COMPLETE.md` files to `archive/`
- ✅ Moved 4 `*_SUMMARY.md` files to `archive/`
- ✅ Moved 8 detailed process docs to `archive/`

**Kept** (Essential Documentation):
- Architecture and design docs
- User guides and references
- Active development documentation
- MkDocs content files

## 📚 Documentation Strategy

### Active Documentation (docs/)
Files that are **actively used** or **reference material**:
- **Getting Started** - Developer onboarding
- **Architecture** - System design (updated as code evolves)
- **Physics Reference** - Equation documentation
- **Pyomo Roadmap** - Future plans
- **CI/Workflow Guides** - CI/CD processes
- **Testing Strategy** - Testing approach

### Archived Documentation (docs/archive/)
Files that are **historical** or **superseded**:
- Completion summaries (`*_COMPLETE.md`)
- Process summaries (`*_SUMMARY.md`)
- Specific investigations (ramp constraints, debugging)
- Reorganization documentation
- Assessment documents

**Philosophy**: Archive, don't delete - preserve history for context

## 🎯 File Naming Conventions

### Python Modules
- `calc_*.py` - Simulation calculators
- `opt_*.py` - Optimizers
- `test_*.py` - Test files
- `example_*.py` - Example scripts

### Documentation
- `README.md` - Directory-specific documentation
- `*_REFERENCE.md` - Reference documentation
- `*_GUIDE.md` - How-to guides
- `*_ROADMAP.md` - Future plans
- `*_COMPLETE.md` - Completion summaries (archived)
- `*_SUMMARY.md` - Process summaries (archived)

### Benchmarks
- `grid_cli.py` - CLI tools
- `*_adapter.py` - Adapters for different tools
- `*.jsonl` - Benchmark data (JSONL format)
- `v1_*/`, `v2_*/` - Versioned benchmark directories

## 🔍 Finding Things

### "Where is...?"

| What | Where | Notes |
|------|-------|-------|
| Physics equations | `lyopronto/functions.py` | All heat/mass transfer |
| Scipy optimizers | `lyopronto/opt_*.py` | Original optimizers (maintained) |
| Pyomo optimizers | `lyopronto/pyomo_models/` | New optimizers (coexist with scipy) |
| Example scripts | `examples/` | Start with `example_web_interface.py` |
| Tests | `tests/` | 85 tests, organized by module |
| Benchmark tools | `benchmarks/*.py` | CLI tools and analysis modules |
| Benchmark data | `benchmarks/results/` | Versioned directories |
| Benchmark docs | `benchmarks/*.md` | Start with `QUICK_REFERENCE.md` |
| Architecture docs | `docs/ARCHITECTURE.md` | System design |
| Physics docs | `docs/PHYSICS_REFERENCE.md` | Equations |
| Developer setup | `docs/GETTING_STARTED.md` | Getting started |
| Historical docs | `docs/archive/` | Preserved for context |

### "How do I...?"

| Task | Documentation |
|------|---------------|
| Run simulations | `examples/README.md` |
| Run benchmarks | `benchmarks/QUICK_REFERENCE.md` |
| Understand grid_cli.py | `benchmarks/GRID_CLI_GUIDE.md` |
| Set up dev environment | `docs/GETTING_STARTED.md` |
| Understand physics | `docs/PHYSICS_REFERENCE.md` |
| Understand architecture | `docs/ARCHITECTURE.md` |
| Run tests | `tests/README.md` |
| Contribute | `CONTRIBUTING.md` |

## 🚀 Quick Start Paths

### New User (Want to Run Simulations)
1. Read `README.md` (project overview)
2. Read `docs/GETTING_STARTED.md` (setup)
3. Run `examples/example_web_interface.py`
4. Explore other examples in `examples/`

### Developer (Want to Contribute)
1. Read `README.md` (project overview)
2. Read `docs/GETTING_STARTED.md` (environment setup)
3. Read `docs/ARCHITECTURE.md` (system design)
4. Read `CONTRIBUTING.md` (contribution guidelines)
5. Run tests: `pytest tests/ -v`

### Benchmarking (Want to Compare Methods)
1. Read `benchmarks/QUICK_REFERENCE.md` (workflow)
2. Read `benchmarks/GRID_CLI_GUIDE.md` (CLI details)
3. Run benchmark generation
4. Run analysis generation
5. View results in notebook

### Understanding Physics (Want to Learn)
1. Read `docs/PHYSICS_REFERENCE.md` (equations)
2. Read `lyopronto/functions.py` (implementation)
3. Run `examples/example_web_interface.py` (see it work)
4. Read `tests/test_functions.py` (validation)

## ✅ Cleanup Verification

### Benchmarks Directory
```bash
$ ls benchmarks/results/
README.md  archive/  v1_baseline/
```
✅ Clean - only versioned data and archive

### Root Directory
```bash
$ ls -1 *.md *.py 2>/dev/null | grep -v README.md
CONTRIBUTING.md
main.py
setup.py
```
✅ Clean - only essential files

### Docs Directory
```bash
$ ls docs/*.md | wc -l
15
```
✅ Clean - reduced from 40+ to 15 essential docs

## 📝 Maintenance Guidelines

### Adding New Files

**Source Code** (`lyopronto/`):
- Follow existing naming conventions (`calc_*.py`, `opt_*.py`)
- Add corresponding tests in `tests/test_*.py`
- Update `docs/ARCHITECTURE.md` if adding major features

**Examples** (`examples/`):
- Add to `examples/` directory
- Document in `examples/README.md`
- Test in `tests/test_example_scripts.py`

**Tests** (`tests/`):
- Name: `test_<module>.py`
- Use fixtures from `conftest.py`
- Document in `tests/README.md`

**Documentation** (`docs/`):
- Essential docs in `docs/`
- Historical/completed work in `docs/archive/`
- Update `docs/README.md` index

**Benchmarks** (`benchmarks/`):
- Data: `results/<version>/`
- Analysis: Generated in `analysis/<version>/`
- Tools: Root of `benchmarks/`
- Docs: `benchmarks/*.md`

### Archive vs Delete

**Archive** (preserve in `archive/` or `docs/archive/`):
- ✅ Completion summaries (historical record)
- ✅ Investigation reports (debugging context)
- ✅ Experiment results (data preservation)
- ✅ Superseded documentation (evolution history)

**Delete** (if really unnecessary):
- ❌ Duplicate files
- ❌ Build artifacts (covered by .gitignore)
- ❌ Temporary test files

**Philosophy**: When in doubt, archive. Disk space is cheap, context is valuable.

## 🎉 Benefits of Clean Organization

### Before Cleanup
- ❌ 36+ scattered benchmark files in `results/`
- ❌ 40+ markdown files in `docs/` (unclear which are current)
- ❌ Experiment files in root directory
- ❌ 1700-line notebook mixing analysis and visualization
- ❌ Unclear where to find documentation

### After Cleanup
- ✅ Version-controlled benchmark results
- ✅ 15 essential docs (clear purpose)
- ✅ Clean root directory
- ✅ Modular benchmark infrastructure (150-line viewer)
- ✅ Clear documentation structure

### Metrics
- **Benchmark files organized**: 36+ → 3 (README, v1_baseline/, archive/)
- **Docs archived**: 26+ historical docs moved to archive/
- **Notebook simplified**: 1700 → 150 lines (95% reduction)
- **Root directory cleaned**: 6 scattered files → 0

---

**Status**: ✅ Repository is clean and well-organized  
**Last Cleanup**: 2025-11-19  
**Maintained By**: Follow patterns in this guide
