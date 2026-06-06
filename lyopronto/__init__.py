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

# ----------------------
# Import submodules

from . import constant
from . import freezing
from . import calc_knownRp
from . import calc_unknownRp
from . import design_space
from . import opt_Pch_Tsh
from . import opt_Pch
from . import opt_Tsh
from . import functions
from . import plot_styling
from . import typed
from . import physical_properties
from . import vials
from . import pikal
from . import fitting
from . import cycle_time

from .typed import Q_, ureg, RpFormFit, ConstPhysProp, RampedVariable, PrimaryDryFit
from .cycle_time import identify_pd_end
from .pikal import (
    PikalDiagnostics,
    PikalParams,
    PikalSolution,
    RpEstimator,
    calc_hRp_T,
    calc_md_q,
    calc_pikal_u0,
    get_pikal_t0,
    get_pikal_tstops,
    legacy_unknown_rp_to_hRp,
    pikal_solution_to_legacy_table,
    solve_pikal,
)
from .fitting import (
    KRpTransform,
    KTransform,
    RpTransform,
    SharedSeparateTransform,
    SharedSeparateUpdates,
    err_expT,
    err_pd,
    errn_pd,
    fit_primary_drying,
    gen_nsol_pd,
    gen_sol_pd,
    num_errs,
    obj_expT,
    obj_pd,
    objn_pd,
)

from .high_level import (
    execute_simulation,
    save_inputs_legacy,
    save_inputs,
    read_inputs,
    save_csv,
    generate_visualizations,
)

__all__ = [
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
    "fitting",
    "cycle_time",
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
    "fit_primary_drying",
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
