# Copyright (C) 2026, SECQUOIA
#
# This file is part of LyoPRONTO.
# LyoPRONTO is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

"""Pyomo-based optimization models for lyophilization processes.

This module provides Pyomo-based formulations for lyophilization optimization,
complementing the existing scipy-based optimizers. The Pyomo models offer:

- Mathematical programming formulations with explicit constraints
- Support for IPOPT and other NLP solvers
- Multi-period trajectory optimization
- Orthogonal collocation discretization

Usage:
    # Install optimization dependencies first:
    # pip install .[optimization]

    # If using conda environment, install via:
    # conda activate [env_name]
    # python -m pip install ".[optimization]"

    from lyopronto.pyomo_models import PYOMO_AVAILABLE

Actual optimizer implementations will be added in subsequent PRs.

Note: Requires IPOPT solver. Install via: idaes get-extensions --extra petsc
"""

from importlib.util import find_spec


def _is_pyomo_available() -> bool:
    """Return whether the optional Pyomo dependency is importable."""
    return find_spec("pyomo") is not None


PYOMO_AVAILABLE = _is_pyomo_available()

__all__ = ["PYOMO_AVAILABLE"]

# Version will be set when implementations are added
__version__ = "0.1.0-dev"
