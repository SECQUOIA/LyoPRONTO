#!/usr/bin/env bash
# Local CI lane runner for LyoPRONTO.

set -euo pipefail

LANE="${1:-fast}"

FAST_EXPR="not slow and not notebook and not pyomo"
FULL_EXPR="not pyomo"
SLOW_EXPR="slow and not pyomo"
NOTEBOOK_EXPR="notebook"
PYOMO_EXPR="pyomo"
PYOMO_LIGHT_TARGETS="tests/test_pyomo_models tests/test_pyomo_solver.py"
NON_PYOMO_COV_CONFIG=".coveragerc.non-pyomo"

usage() {
    cat <<'USAGE'
Usage: ./run_local_ci.sh [fast|full|slow|notebook|pyomo-light|pyomo]

Lanes:
  fast      PR feedback lane: excludes slow, notebook, and Pyomo tests.
  full      Full non-Pyomo validation with coverage.
  slow      Manual slow optimizer-heavy validation with coverage.
  notebook  Explicit notebook validation with coverage.
  pyomo-light  Automatic Pyomo lane equivalent; installs .[dev,pyomo] without IPOPT.
  pyomo     Optional solver-backed Pyomo lane; installs .[dev,pyomo] and IPOPT.

Set SKIP_INSTALL=1 to skip dependency installation.
USAGE
}

install_idaes_extensions() {
    if ! command -v idaes >/dev/null 2>&1; then
        echo "Error: idaes command is unavailable after installing the Pyomo extra."
        echo 'Install the optional stack with: python -m pip install -e ".[dev,pyomo]"'
        return 1
    fi

    idaes get-extensions --extra petsc || {
        rc=$?
        echo "Failed to install IDAES solver extensions for the Pyomo lane."
        echo "Install IPOPT with: idaes get-extensions --extra petsc"
        echo "Alternative local install: conda install -c conda-forge ipopt"
        return "$rc"
    }
}

run_pytest_allow_empty() {
    "$@" || {
        rc=$?
        if [[ "$rc" -eq 5 ]]; then
            echo "No tests collected for selected lane; treating this as a no-op."
            return 0
        fi
        return "$rc"
    }
}

if [[ "$LANE" == "-h" || "$LANE" == "--help" ]]; then
    usage
    exit 0
fi

case "$LANE" in
    fast|full|slow|notebook|pyomo-light|pyomo)
        ;;
    *)
        echo "Unknown lane: $LANE"
        usage
        exit 2
        ;;
esac

echo "=========================================="
echo "LyoPRONTO Local CI: $LANE"
echo "=========================================="
echo ""

echo "1. Checking Python version..."
PYTHON_VERSION=$(python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "   Current Python: $(python --version)"
if [[ "$PYTHON_VERSION" != "3.13" ]]; then
    echo "   Warning: GitHub Actions uses Python 3.13; current Python is $PYTHON_VERSION"
fi
echo ""

echo "2. Checking repository structure..."
if [[ ! -f "pyproject.toml" || ! -d "tests" || ! -d "lyopronto" ]]; then
    echo "   Error: run this script from the repository root"
    exit 1
fi
echo "   Repository structure OK"
echo ""

if [[ "${SKIP_INSTALL:-0}" != "1" ]]; then
    echo "3. Installing dependencies..."
    python -m pip install --upgrade pip setuptools wheel -q
    if [[ "$LANE" == "pyomo" || "$LANE" == "pyomo-light" ]]; then
        pip install -e ".[dev,pyomo]" -q
        if [[ "$LANE" == "pyomo" ]]; then
            install_idaes_extensions
        fi
    else
        pip install -e ".[dev]" -q
    fi
    echo "   Dependencies installed"
else
    echo "3. Skipping dependency installation because SKIP_INSTALL=1"
    if [[ "$LANE" == "pyomo" || "$LANE" == "pyomo-light" ]]; then
        echo '   Pyomo lane expects: python -m pip install -e ".[dev,pyomo]"'
        if [[ "$LANE" == "pyomo" ]]; then
            echo "   IPOPT solver setup: idaes get-extensions --extra petsc"
        fi
    fi
fi
echo ""

echo "4. Running $LANE lane..."
case "$LANE" in
    fast)
        echo "   Command: pytest tests/ -n auto -v -m \"$FAST_EXPR\""
        pytest tests/ -n auto -v -m "$FAST_EXPR"
        ;;
    full)
        echo "   Command: pytest tests/ -n auto -v -m \"$FULL_EXPR\" --cov=lyopronto --cov-config=$NON_PYOMO_COV_CONFIG --cov-report=term-missing"
        pytest tests/ -n auto -v -m "$FULL_EXPR" --cov=lyopronto --cov-config="$NON_PYOMO_COV_CONFIG" --cov-report=term-missing
        ;;
    slow)
        echo "   Command: pytest tests/ -n auto -v -m \"$SLOW_EXPR\" --cov=lyopronto --cov-config=$NON_PYOMO_COV_CONFIG --cov-report=term-missing"
        pytest tests/ -n auto -v -m "$SLOW_EXPR" --cov=lyopronto --cov-config="$NON_PYOMO_COV_CONFIG" --cov-report=term-missing
        ;;
    notebook)
        echo "   Command: pytest tests/ -n auto -v -m \"$NOTEBOOK_EXPR\" --cov=lyopronto --cov-config=$NON_PYOMO_COV_CONFIG --cov-report=term-missing"
        pytest tests/ -n auto -v -m "$NOTEBOOK_EXPR" --cov=lyopronto --cov-config="$NON_PYOMO_COV_CONFIG" --cov-report=term-missing
        ;;
    pyomo-light)
        echo "   Command: pytest $PYOMO_LIGHT_TARGETS -n auto -v"
        pytest $PYOMO_LIGHT_TARGETS -n auto -v
        ;;
    pyomo)
        echo "   Command: pytest tests/ -n auto -v -m \"$PYOMO_EXPR\" --cov=lyopronto --cov-report=term-missing"
        run_pytest_allow_empty pytest tests/ -n auto -v -m "$PYOMO_EXPR" --cov=lyopronto --cov-report=term-missing
        ;;
esac

echo ""
echo "=========================================="
echo "Lane completed successfully: $LANE"
echo "=========================================="
