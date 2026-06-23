#!/usr/bin/env python
"""Example: optional Pyomo primary-drying optimization model construction.

Usage:
    python examples/example_pyomo_optimization.py

This example requires the optional Pyomo extra:
    python -m pip install -e ".[pyomo]"

It constructs the pressure-only, shelf-temperature-only, and joint Pyomo
optimization models without solving them. Solving requires an external NLP
solver such as IPOPT.
"""

from __future__ import annotations

from typing import Any, Mapping

import pyomo.environ as pyo  # type: ignore[import-untyped]

from lyopronto.pyomo_models import (
    OptimizationMode,
    create_primary_drying_optimization_model,
)


def pyomo_optimization_inputs() -> dict[str, Any]:
    """Return a small physically meaningful input set for Pyomo examples."""
    return {
        "vial": {"Av": 3.8, "Ap": 3.14, "Vfill": 2.0},
        "product": {
            "cSolid": 0.05,
            "R0": 1.4,
            "A1": 16.0,
            "A2": 0.0,
            "T_pr_crit": -15.0,
        },
        "ht": {"KC": 2.75e-4, "KP": 8.93e-4, "KD": 0.46},
        "pchamber": {
            "min": 0.05,
            "max": 0.5,
            "setpt": [0.15],
            "dt_setpt": [1800.0],
            "ramp_rate": 0.5,
        },
        "tshelf": {
            "min": -45.0,
            "max": 50.0,
            "init": -35.0,
            "setpt": [20.0],
            "dt_setpt": [1800.0],
            "ramp_rate": 1.0,
        },
        "eq_cap": {"a": -0.182, "b": 11.7},
        "nvial": 398,
    }


def _component_count(model: pyo.ConcreteModel, component_type: type) -> int:
    return sum(1 for _ in model.component_data_objects(component_type, active=True))


def summarize_pyomo_model(model: pyo.ConcreteModel) -> dict[str, Any]:
    """Summarize the public tags and model size for one Pyomo optimization model."""
    return {
        "mode": model.optimization_mode,
        "optimized_controls": tuple(model.optimized_controls),
        "fixed_controls": tuple(model.fixed_controls),
        "objective": model.optimization_objective,
        "time_nodes": len(list(model.TIME)),
        "variables": _component_count(model, pyo.Var),
        "constraints": _component_count(model, pyo.Constraint),
    }


def build_pyomo_optimization_models() -> dict[str, pyo.ConcreteModel]:
    """Build all supported experimental Pyomo optimization modes."""
    data = pyomo_optimization_inputs()
    models = {}
    for mode in OptimizationMode:
        model = create_primary_drying_optimization_model(
            data["vial"],
            data["product"],
            data["ht"],
            data["pchamber"],
            data["tshelf"],
            n_steps=4,
            dt=0.5,
            mode=mode,
            final_dried_fraction=0.20,
            eq_cap=data["eq_cap"],
            nvial=data["nvial"],
            enforce_ramp_rates=True,
        )
        models[mode.value] = model
    return models


def run_pyomo_optimization_example() -> dict[str, Mapping[str, Any]]:
    """Build all Pyomo optimization models and return summary diagnostics."""
    return {
        mode: summarize_pyomo_model(model)
        for mode, model in build_pyomo_optimization_models().items()
    }


def _print_summary(summary: Mapping[str, Mapping[str, Any]]) -> None:
    for mode, values in summary.items():
        optimized = ", ".join(values["optimized_controls"]) or "none"
        fixed = ", ".join(values["fixed_controls"]) or "none"
        print(
            f"{mode}: optimized={optimized}; fixed={fixed}; "
            f"time_nodes={values['time_nodes']}; variables={values['variables']}; "
            f"constraints={values['constraints']}"
        )


if __name__ == "__main__":
    _print_summary(run_pyomo_optimization_example())
