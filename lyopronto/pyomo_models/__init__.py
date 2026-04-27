# Copyright 2019-2025, Gayathri Shivkumar, Petr S. Kazarin, Alina A. Alexeenko
# Maintained by Isaac S. Wheeler
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

"""
Pyomo-based optimization models for lyophilization process.

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

    from lyopronto.pyomo_models import optimize_Tsh_pyomo
    
    result = optimize_Tsh_pyomo(vial, product, ht, Pchamber, Tshelf, dt, eq_cap, nVial)

The optimizers maintain API compatibility with scipy-based versions:
- optimize_Tsh_pyomo: Optimize shelf temperature trajectory
- optimize_Pch_pyomo: Optimize chamber pressure trajectory  
- optimize_Pch_Tsh_pyomo: Optimize both pressure and temperature

Note: Requires IPOPT solver. Install via: idaes get-extensions --extra petsc
"""

# Placeholder - actual implementations will be added in subsequent PRs
__all__ = []

# Version will be set when implementations are added
__version__ = "0.1.0-dev"
