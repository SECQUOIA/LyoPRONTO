"""Optional Pyomo model prototypes for LyoPRONTO."""

from __future__ import annotations

from importlib import import_module
from importlib.util import find_spec
from typing import Any


def _is_pyomo_available() -> bool:
    return find_spec("pyomo") is not None


PYOMO_AVAILABLE = _is_pyomo_available()

_LAZY_EXPORTS = {
    "SingleStepResult": "single_step",
    "create_single_step_model": "single_step",
    "format_single_step_output": "utils",
    "solve_single_step": "single_step",
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
    "SingleStepResult",
    "create_single_step_model",
    "format_single_step_output",
    "solve_single_step",
]
