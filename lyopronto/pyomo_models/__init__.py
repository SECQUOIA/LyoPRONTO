"""Pyomo-based optimization models for lyophilization process optimization.

This module provides Pyomo NLP (Nonlinear Programming) implementations as an
alternative to the scipy-based optimizers. Both approaches coexist in LyoPRONTO,
allowing users to choose the most appropriate method for their application.

Key modules:
    - single_step: Single time-step optimization (replicate scipy sequential approach)
    - utils: Shared utilities for initialization, scaling, and result extraction
"""

# LyoPRONTO, a vial-scale lyophilization process simulator
# Copyright (C) 2024, Gayathri Shivkumar, Petr S. Kazarin, Alina A. Alexeenko, Isaac S. Wheeler

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

__all__ = [
    'create_single_step_model',
    'solve_single_step',
    'optimize_single_step',
]
