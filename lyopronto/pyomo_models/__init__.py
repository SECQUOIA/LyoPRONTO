"""Pyomo-based optimization models for lyophilization processes.

This module provides Pyomo NLP (Nonlinear Programming) implementations as an
alternative to the scipy-based optimizers. Both approaches coexist in LyoPRONTO,
allowing users to choose the method that fits their application.

Key modules:
    - model: Multi-period DAE model creation with collocation
    - optimizers: User-facing optimizer functions
    - single_step: Single time-step optimization
    - utils: Shared initialization, scaling, and result extraction utilities

Usage:
    # Install optimization dependencies first:
    # pip install .[optimization]

    from lyopronto.pyomo_models import PYOMO_AVAILABLE

    if PYOMO_AVAILABLE:
        from lyopronto.pyomo_models import optimize_Tsh_pyomo
"""

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

from importlib.util import find_spec


def _is_pyomo_available() -> bool:
    """Return whether the optional Pyomo dependency is importable."""
    return find_spec("pyomo") is not None


PYOMO_AVAILABLE = _is_pyomo_available()

__all__ = ["PYOMO_AVAILABLE"]

if PYOMO_AVAILABLE:
    from .model import (
        create_multi_period_model,
        optimize_multi_period,
        warmstart_from_scipy_trajectory,
    )
    from .optimizers import (
        optimize_Pch_pyomo,
        optimize_Pch_Tsh_pyomo,
        optimize_Tsh_pyomo,
    )
    from .paper_ocp import (
        PaperDiscretization,
        PaperPrimaryDryingConfig,
        classify_paper_policies,
        compare_paper_problem1_trajectories,
        create_paper_problem1_model,
        generate_problem1_policy_initialization,
        initialize_paper_problem1_from_trajectory,
        load_upstream_matlab_trajectory,
        solve_paper_problem1,
    )
    from .single_step import (
        create_single_step_model,
        optimize_single_step,
        solve_single_step,
    )

    __all__ += [
        "create_single_step_model",
        "solve_single_step",
        "optimize_single_step",
        "create_multi_period_model",
        "optimize_multi_period",
        "warmstart_from_scipy_trajectory",
        "optimize_Tsh_pyomo",
        "optimize_Pch_pyomo",
        "optimize_Pch_Tsh_pyomo",
        "PaperPrimaryDryingConfig",
        "PaperDiscretization",
        "create_paper_problem1_model",
        "generate_problem1_policy_initialization",
        "initialize_paper_problem1_from_trajectory",
        "load_upstream_matlab_trajectory",
        "compare_paper_problem1_trajectories",
        "solve_paper_problem1",
        "classify_paper_policies",
    ]

__version__ = "0.1.0-dev"
