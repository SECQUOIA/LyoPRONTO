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

"""Public package interface for LyoPRONTO.

The package-level API is kept compatible with earlier releases while avoiding
heavy side effects during ``import lyopronto``. Submodules and compatibility
helpers are imported on first access.
"""

from __future__ import annotations

from importlib import import_module, metadata
from pathlib import Path
import re
from typing import Any


def _version_from_pyproject() -> str:
    """Return the source-tree project version when package metadata is absent."""
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    try:
        try:
            tomllib: Any = import_module("tomllib")
        except ModuleNotFoundError:  # pragma: no cover - Python < 3.11 fallback
            tomllib = None

        if tomllib is not None:
            with pyproject.open("rb") as handle:
                return tomllib.load(handle)["project"]["version"]

        text = pyproject.read_text(encoding="utf-8")
    except (OSError, KeyError):
        return "0+unknown"

    in_project = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line == "[project]":
            in_project = True
            continue
        if in_project and line.startswith("["):
            break
        if in_project:
            match = re.match(r"""version\s*=\s*["']([^"']+)["']""", line)
            if match:
                return match.group(1)
    return "0+unknown"


def _load_version() -> str:
    try:
        return metadata.version("lyopronto")
    except metadata.PackageNotFoundError:
        return _version_from_pyproject()


__version__ = _load_version()

_SUBMODULES = {
    "constant",
    "freezing",
    "calc_knownRp",
    "calc_unknownRp",
    "design_space",
    "opt_Pch_Tsh",
    "opt_Pch",
    "opt_Tsh",
    "functions",
    "plot_styling",
    "typed",
    "physical_properties",
    "vials",
    "pikal",
    "rf",
    "fitting",
    "cycle_time",
    "eccurt",
    "high_level",
}

_SYMBOL_TO_MODULE = {
    "Q_": "typed",
    "ureg": "typed",
    "RpFormFit": "typed",
    "ConstPhysProp": "typed",
    "RampedVariable": "typed",
    "PrimaryDryFit": "typed",
    "identify_pd_end": "cycle_time",
    "PikalDiagnostics": "pikal",
    "PikalParams": "pikal",
    "PikalSolution": "pikal",
    "RpEstimator": "pikal",
    "calc_hRp_T": "pikal",
    "calc_md_q": "pikal",
    "calc_pikal_u0": "pikal",
    "get_pikal_t0": "pikal",
    "get_pikal_tstops": "pikal",
    "legacy_unknown_rp_to_hRp": "pikal",
    "pikal_solution_to_legacy_table": "pikal",
    "solve_pikal": "pikal",
    "RFDiagnostics": "rf",
    "RFParams": "rf",
    "RFSolution": "rf",
    "calc_rf_diagnostics": "rf",
    "calc_rf_heat_terms": "rf",
    "calc_rf_u0": "rf",
    "get_rf_tstops": "rf",
    "qrf_integrate": "rf",
    "rf_rhs": "rf",
    "shape_factor": "rf",
    "solve_rf": "rf",
    "BoundedKBBTransform": "fitting",
    "KBBTransform": "fitting",
    "RpTransform": "fitting",
    "KTransform": "fitting",
    "KRpTransform": "fitting",
    "SharedSeparateTransform": "fitting",
    "SharedSeparateUpdates": "fitting",
    "gen_sol_pd": "fitting",
    "gen_nsol_pd": "fitting",
    "err_pd": "fitting",
    "errn_pd": "fitting",
    "obj_pd": "fitting",
    "objn_pd": "fitting",
    "gen_sol_rf": "fitting",
    "err_rf": "fitting",
    "obj_rf": "fitting",
    "fit_primary_drying": "fitting",
    "fit_rf_primary_drying": "fitting",
    "ECLine": "eccurt",
    "eq_cap_line": "eccurt",
    "eq_cap_line_new": "eccurt",
    "eq_cap_pressure": "eccurt",
    "eq_cap_pressures_new": "eccurt",
    "err_expT": "fitting",
    "num_errs": "fitting",
    "obj_expT": "fitting",
    "execute_simulation": "high_level",
    "save_inputs_legacy": "high_level",
    "save_inputs": "high_level",
    "read_inputs": "high_level",
    "save_csv": "high_level",
    "generate_visualizations": "high_level",
}

__all__ = [
    "__version__",
    "constant",
    "freezing",
    "calc_knownRp",
    "calc_unknownRp",
    "design_space",
    "opt_Pch_Tsh",
    "opt_Pch",
    "opt_Tsh",
    "functions",
    "plot_styling",
    "typed",
    "physical_properties",
    "vials",
    "pikal",
    "rf",
    "fitting",
    "cycle_time",
    "eccurt",
    "Q_",
    "ureg",
    "RpFormFit",
    "ConstPhysProp",
    "RampedVariable",
    "PrimaryDryFit",
    "identify_pd_end",
    "PikalDiagnostics",
    "PikalParams",
    "PikalSolution",
    "RpEstimator",
    "calc_hRp_T",
    "calc_md_q",
    "calc_pikal_u0",
    "get_pikal_t0",
    "get_pikal_tstops",
    "legacy_unknown_rp_to_hRp",
    "pikal_solution_to_legacy_table",
    "solve_pikal",
    "RFDiagnostics",
    "RFParams",
    "RFSolution",
    "calc_rf_diagnostics",
    "calc_rf_heat_terms",
    "calc_rf_u0",
    "get_rf_tstops",
    "qrf_integrate",
    "rf_rhs",
    "shape_factor",
    "solve_rf",
    "BoundedKBBTransform",
    "KBBTransform",
    "RpTransform",
    "KTransform",
    "KRpTransform",
    "SharedSeparateTransform",
    "SharedSeparateUpdates",
    "gen_sol_pd",
    "gen_nsol_pd",
    "err_pd",
    "errn_pd",
    "obj_pd",
    "objn_pd",
    "gen_sol_rf",
    "err_rf",
    "obj_rf",
    "fit_primary_drying",
    "fit_rf_primary_drying",
    "ECLine",
    "eq_cap_line",
    "eq_cap_line_new",
    "eq_cap_pressure",
    "eq_cap_pressures_new",
    "err_expT",
    "num_errs",
    "obj_expT",
    "execute_simulation",
    "save_inputs_legacy",
    "save_inputs",
    "read_inputs",
    "save_csv",
    "generate_visualizations",
]


def __getattr__(name: str) -> Any:
    if name in _SUBMODULES:
        value = import_module(f".{name}", __name__)
    elif name in _SYMBOL_TO_MODULE:
        module = import_module(f".{_SYMBOL_TO_MODULE[name]}", __name__)
        value = getattr(module, name)
    else:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__) | _SUBMODULES)
