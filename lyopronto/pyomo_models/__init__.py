"""Pyomo-based optimization models for lyophilization process optimization.

This module provides Pyomo NLP (Nonlinear Programming) implementations as an
alternative to the scipy-based optimizers. Both approaches coexist in LyoPRONTO,
allowing users to choose the most appropriate method for their application.

Key modules:
    - model: Multi-period DAE model creation with collocation
    - optimizers: User-facing optimizer functions (optimize_Tsh_pyomo, optimize_Pch_pyomo, optimize_Pch_Tsh_pyomo)
    - single_step: Single time-step optimization (replicate scipy sequential approach)
    - utils: Shared utilities for initialization, scaling, and result extraction
"""

# LyoPRONTO, a vial-scale lyophilization process simulator
# Nonlinear optimization
# Copyright (C) 2025, David E. Bernal Neira

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

from .single_step import create_single_step_model, solve_single_step, optimize_single_step
from .model import create_multi_period_model, optimize_multi_period, warmstart_from_scipy_trajectory
from .optimizers import optimize_Tsh_pyomo, optimize_Pch_pyomo, optimize_Pch_Tsh_pyomo

__all__ = [
    # Single-step model functions
    'create_single_step_model',
    'solve_single_step',
    'optimize_single_step',
    # Multi-period model functions
    'create_multi_period_model',
    'optimize_multi_period',
    'warmstart_from_scipy_trajectory',
    # Main optimizer functions (recommended entry points)
    'optimize_Tsh_pyomo',
    'optimize_Pch_pyomo',
    'optimize_Pch_Tsh_pyomo',
]
