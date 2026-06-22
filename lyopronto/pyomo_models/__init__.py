"""Optional Pyomo model prototypes for LyoPRONTO."""

from __future__ import annotations

from importlib import import_module
from importlib.util import find_spec
from typing import Any


def _is_pyomo_available() -> bool:
    return find_spec("pyomo") is not None


PYOMO_AVAILABLE = _is_pyomo_available()

_LAZY_EXPORTS = {
    "OptimizationMode": "optimization",
    "SingleStepResult": "single_step",
    "TrajectoryResult": "trajectory",
    "apply_trajectory_warmstart": "trajectory",
    "create_joint_optimization_model": "optimization",
    "create_pressure_optimization_model": "optimization",
    "create_primary_drying_optimization_model": "optimization",
    "create_shelf_temperature_optimization_model": "optimization",
    "create_single_step_model": "single_step",
    "create_trajectory_model": "trajectory",
    "format_single_step_output": "utils",
    "solve_primary_drying_optimization": "optimization",
    "solve_single_step": "single_step",
    "solve_trajectory": "trajectory",
    "sample_ramp_profile": "trajectory",
    "trajectory_initialization_from_scipy_output": "trajectory",
    "trajectory_values": "trajectory",
}


def __getattr__(name: str) -> Any:
    if name not in _LAZY_EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    module_name = _LAZY_EXPORTS[name]
    module = import_module(f"{__name__}.{module_name}")

    value = getattr(module, name)
    globals()[name] = value
    return value


__all__ = [
    "PYOMO_AVAILABLE",
    "OptimizationMode",
    "SingleStepResult",
    "TrajectoryResult",
    "apply_trajectory_warmstart",
    "create_joint_optimization_model",
    "create_pressure_optimization_model",
    "create_primary_drying_optimization_model",
    "create_shelf_temperature_optimization_model",
    "create_single_step_model",
    "create_trajectory_model",
    "format_single_step_output",
    "solve_primary_drying_optimization",
    "solve_single_step",
    "solve_trajectory",
    "sample_ramp_profile",
    "trajectory_initialization_from_scipy_output",
    "trajectory_values",
]
