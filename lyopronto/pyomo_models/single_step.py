"""Single time-step Pyomo optimization for lyophilization primary drying.

This module provides a Pyomo-based NLP formulation that replicates one time step
of the scipy sequential optimization approach. It solves for optimal chamber
pressure (Pch) and shelf temperature (Tsh) at a given dried cake length (Lck).

The model includes:
    - 7 decision variables: Pch, Tsh, Tsub, Tbot, Psub, dmdt, Kv
    - 5 equality constraints: vapor pressure, sublimation rate, heat balance, 
      shelf temperature relation, vial heat transfer
    - 2 inequality constraints: equipment capability, product temperature limit
    - Objective: maximize sublimation driving force (minimize Pch - Psub)
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

import pyomo.environ as pyo
import numpy as np
from .. import constant


def create_single_step_model(
    vial, 
    product, 
    ht, 
    Lpr0, 
    Lck,
    Pch_bounds=(0.05, 0.5),
    Tsh_bounds=(-50, 50),
    eq_cap=None,
    nVial=None
):
    """Create Pyomo model for single time-step lyophilization optimization.
    
    This function constructs a ConcreteModel that represents the physics and
    constraints of lyophilization at a single time step. The model finds optimal
    chamber pressure and shelf temperature to maximize sublimation rate while
    respecting equipment and product temperature constraints.
    
    Args:
        vial (dict): Vial geometry with keys:
            - 'Av' (float): Vial area [cm²]
            - 'Ap' (float): Product area [cm²]
        product (dict): Product properties with keys:
            - 'R0' (float): Base product resistance [cm²·hr·Torr/g]
            - 'A1' (float): Resistance parameter [cm·hr·Torr/g]
            - 'A2' (float): Resistance parameter [1/cm]
            - 'T_pr_crit' (float): Critical product temperature [°C]
        ht (dict): Heat transfer parameters with keys:
            - 'KC' (float): Vial heat transfer parameter [cal/s/K/cm²]
            - 'KP' (float): Vial heat transfer parameter [cal/s/K/cm²/Torr]
            - 'KD' (float): Vial heat transfer parameter [1/Torr]
        Lpr0 (float): Initial product length [cm]
        Lck (float): Current dried cake length [cm]
        Pch_bounds (tuple, optional): (min, max) for chamber pressure [Torr]. 
            Default: (0.05, 0.5)
        Tsh_bounds (tuple, optional): (min, max) for shelf temperature [°C].
            Default: (-50, 50)
        eq_cap (dict, optional): Equipment capability parameters with keys:
            - 'a' (float): Equipment capability parameter [kg/hr]
            - 'b' (float): Equipment capability parameter [kg/hr/Torr]
            If None, equipment constraint is not enforced.
        nVial (int, optional): Number of vials in batch. Required if eq_cap provided.
    
    Returns:
        pyo.ConcreteModel: Pyomo model ready to solve with variables, constraints,
            and objective defined.
    
    Notes:
        The model uses the following physics equations:
        - Vapor pressure: Psub = 2.698e10 * exp(-6144.96/(Tsub + 273.15))
        - Product resistance: Rp = R0 + A1*Lck/(1 + A2*Lck)
        - Vial heat transfer: Kv = KC + KP*Pch/(1 + KD*Pch)
        - Sublimation rate: dmdt = Ap/Rp * (Psub - Pch) / kg_To_g
        - Energy balance: Q_shelf = Q_sublimation
        
    Examples:
        >>> from lyopronto import functions
        >>> vial = {'Av': 3.80, 'Ap': 3.14}
        >>> product = {'R0': 1.4, 'A1': 16.0, 'A2': 0.0, 'T_pr_crit': -5.0}
        >>> ht = {'KC': 2.75e-4, 'KP': 8.93e-4, 'KD': 0.46}
        >>> Lpr0 = functions.Lpr0_FUN(2.0, 3.14, 0.05)
        >>> Lck = 0.5  # Half dried
        >>> model = create_single_step_model(vial, product, ht, Lpr0, Lck)
        >>> # Now solve with solve_single_step(model)
    """
    model = pyo.ConcreteModel()
    
    # ==================== Parameters (Fixed for this step) ====================
    model.Lpr0 = pyo.Param(initialize=Lpr0)
    model.Lck = pyo.Param(initialize=Lck)
    model.Av = pyo.Param(initialize=vial['Av'])
    model.Ap = pyo.Param(initialize=vial['Ap'])
    model.R0 = pyo.Param(initialize=product['R0'])
    model.A1 = pyo.Param(initialize=product['A1'])
    model.A2 = pyo.Param(initialize=product['A2'])
    model.T_crit = pyo.Param(initialize=product['T_pr_crit'])
    model.KC = pyo.Param(initialize=ht['KC'])
    model.KP = pyo.Param(initialize=ht['KP'])
    model.KD = pyo.Param(initialize=ht['KD'])
    
    # Physical constants
    model.kg_To_g = pyo.Param(initialize=constant.kg_To_g)
    model.hr_To_s = pyo.Param(initialize=constant.hr_To_s)
    model.k_ice = pyo.Param(initialize=constant.k_ice)
    model.dHs = pyo.Param(initialize=constant.dHs)
    
    # ==================== Decision Variables ====================
    # Chamber pressure [Torr]
    model.Pch = pyo.Var(domain=pyo.NonNegativeReals, bounds=Pch_bounds)
    
    # Shelf temperature [°C]
    model.Tsh = pyo.Var(domain=pyo.Reals, bounds=Tsh_bounds)
    
    # Sublimation front temperature [°C] - always below freezing
    model.Tsub = pyo.Var(domain=pyo.Reals, bounds=(-60, 0))
    
    # Vial bottom temperature [°C]
    model.Tbot = pyo.Var(domain=pyo.Reals, bounds=(-60, 50))
    
    # Vapor pressure at sublimation front [Torr]
    model.Psub = pyo.Var(domain=pyo.NonNegativeReals, bounds=(1e-6, 10))
    
    # Sublimation rate [kg/hr] - must be non-negative
    model.dmdt = pyo.Var(domain=pyo.NonNegativeReals, bounds=(0, 10))
    
    # Vial heat transfer coefficient [cal/s/K/cm²]
    model.Kv = pyo.Var(domain=pyo.PositiveReals, bounds=(1e-6, 1e-2))
    
    # ==================== Derived Quantities (Expressions) ====================
    # Product resistance [cm²·hr·Torr/g]
    model.Rp = pyo.Expression(
        expr=model.R0 + model.A1 * model.Lck / (1 + model.A2 * model.Lck)
    )
    
    # ==================== Equality Constraints ====================
    # C1: Vapor pressure at sublimation front (Antoine equation)
    # Psub = 2.698e10 * exp(-6144.96/(Tsub + 273.15))
    model.vapor_pressure = pyo.Constraint(
        expr=model.Psub == 2.698e10 * pyo.exp(-6144.96 / (model.Tsub + 273.15))
    )
    
    # C2: Sublimation rate from mass transfer
    # dmdt = Ap/Rp * (Psub - Pch) / kg_To_g
    model.sublimation_rate = pyo.Constraint(
        expr=model.dmdt == model.Ap / model.Rp / model.kg_To_g * (model.Psub - model.Pch)
    )
    
    # C3: Heat transfer balance
    # (Tsh - Tbot) * Av * Kv * (Lpr0 - Lck) = Ap * (Tbot - Tsub) * k_ice
    model.heat_balance = pyo.Constraint(
        expr=(model.Tsh - model.Tbot) * model.Av * model.Kv * (model.Lpr0 - model.Lck)
             == model.Ap * (model.Tbot - model.Tsub) * model.k_ice
    )
    
    # C4: Shelf temperature relation
    # Tsh = dmdt * kg_To_g / hr_To_s * dHs / Av / Kv + Tbot
    model.shelf_temp = pyo.Constraint(
        expr=model.Tsh == model.dmdt * model.kg_To_g / model.hr_To_s * model.dHs / model.Av / model.Kv + model.Tbot
    )
    
    # C5: Vial heat transfer coefficient
    # Kv = KC + KP * Pch / (1 + KD * Pch)
    model.kv_calc = pyo.Constraint(
        expr=model.Kv == model.KC + model.KP * model.Pch / (1 + model.KD * model.Pch)
    )
    
    # ==================== Inequality Constraints ====================
    # Product temperature limit: Tbot ≤ T_crit
    model.temp_limit = pyo.Constraint(
        expr=model.Tbot <= model.T_crit
    )
    
    # Equipment capability limit (optional)
    if eq_cap is not None and nVial is not None:
        model.a_eq = pyo.Param(initialize=eq_cap['a'])
        model.b_eq = pyo.Param(initialize=eq_cap['b'])
        model.nVial = pyo.Param(initialize=nVial)
        
        # a + b*Pch - nVial*dmdt ≥ 0
        model.equipment_capability = pyo.Constraint(
            expr=model.a_eq + model.b_eq * model.Pch - model.nVial * model.dmdt >= 0
        )
    
    # ==================== Objective Function ====================
    # Minimize (Pch - Psub) to maximize sublimation driving force (Psub - Pch)
    model.obj = pyo.Objective(
        expr=model.Pch - model.Psub,
        sense=pyo.minimize
    )
    
    return model


def solve_single_step(model, solver='ipopt', tee=False, warmstart_data=None):
    """Solve Pyomo single-step model and extract results.
    
    Args:
        model (pyo.ConcreteModel): Pyomo model created by create_single_step_model()
        solver (str, optional): Solver name. Default: 'ipopt'
        tee (bool, optional): If True, print solver output. Default: False
        warmstart_data (dict, optional): Initial values for variables with keys:
            'Pch', 'Tsh', 'Tsub', 'Tbot', 'Psub', 'dmdt', 'Kv'.
            If provided, these values are used to initialize the model.
    
    Returns:
        dict: Solution dictionary with keys:
            - 'status' (str): Solver termination condition
            - 'Pch' (float): Chamber pressure [Torr]
            - 'Tsh' (float): Shelf temperature [°C]
            - 'Tsub' (float): Sublimation front temperature [°C]
            - 'Tbot' (float): Vial bottom temperature [°C]
            - 'Psub' (float): Vapor pressure [Torr]
            - 'dmdt' (float): Sublimation rate [kg/hr]
            - 'Kv' (float): Vial heat transfer coefficient [cal/s/K/cm²]
            - 'Rp' (float): Product resistance [cm²·hr·Torr/g]
            - 'obj' (float): Objective value
    
    Raises:
        RuntimeError: If solver is not available or fails to solve.
    
    Notes:
        For IPOPT solver, the following options are used:
        - max_iter: 3000
        - tol: 1e-6
        - mu_strategy: 'adaptive'
        - print_level: 5 (if tee=True), 0 (if tee=False)
        
        If IPOPT is not in PATH, will attempt to use IDAES-provided IPOPT.
    
    Examples:
        >>> model = create_single_step_model(vial, product, ht, Lpr0, Lck)
        >>> solution = solve_single_step(model, tee=True)
        >>> print(f"Optimal Pch: {solution['Pch']:.4f} Torr")
        >>> print(f"Optimal Tsh: {solution['Tsh']:.2f} °C")
    """
    # Initialize variables if warmstart data provided
    if warmstart_data is not None:
        if 'Pch' in warmstart_data:
            model.Pch.set_value(warmstart_data['Pch'])
        if 'Tsh' in warmstart_data:
            model.Tsh.set_value(warmstart_data['Tsh'])
        if 'Tsub' in warmstart_data:
            model.Tsub.set_value(warmstart_data['Tsub'])
        if 'Tbot' in warmstart_data:
            model.Tbot.set_value(warmstart_data['Tbot'])
        if 'Psub' in warmstart_data:
            model.Psub.set_value(warmstart_data['Psub'])
        if 'dmdt' in warmstart_data:
            model.dmdt.set_value(warmstart_data['dmdt'])
        if 'Kv' in warmstart_data:
            model.Kv.set_value(warmstart_data['Kv'])
    
    # Create solver - try IDAES first if available, then standard Pyomo
    if solver.lower() == 'ipopt':
        try:
            from idaes.core.solvers import get_solver
            opt = get_solver('ipopt')
        except (ImportError, Exception):
            # Fall back to standard Pyomo solver
            opt = pyo.SolverFactory(solver)
    else:
        opt = pyo.SolverFactory(solver)
    
    # Configure IPOPT options
    if solver.lower() == 'ipopt':
        opt.options['max_iter'] = 3000
        opt.options['tol'] = 1e-6
        opt.options['mu_strategy'] = 'adaptive'
        opt.options['print_level'] = 5 if tee else 0
    
    # Solve
    results = opt.solve(model, tee=tee)
    
    # Check convergence
    termination = results.solver.termination_condition
    status_str = str(termination)
    
    if termination not in [pyo.TerminationCondition.optimal, 
                           pyo.TerminationCondition.locallyOptimal]:
        print(f"WARNING: Solver status: {termination}")
    
    # Extract solution
    solution = {
        'status': status_str,
        'Pch': pyo.value(model.Pch),
        'Tsh': pyo.value(model.Tsh),
        'Tsub': pyo.value(model.Tsub),
        'Tbot': pyo.value(model.Tbot),
        'Psub': pyo.value(model.Psub),
        'dmdt': pyo.value(model.dmdt),
        'Kv': pyo.value(model.Kv),
        'Rp': pyo.value(model.Rp),
        'obj': pyo.value(model.obj),
    }
    
    return solution


def optimize_single_step(vial, product, ht, Lpr0, Lck, **kwargs):
    """Convenience function to create and solve single-step model in one call.
    
    This function combines create_single_step_model() and solve_single_step()
    for ease of use when you don't need to inspect the model structure.
    
    Args:
        vial (dict): Vial geometry (see create_single_step_model)
        product (dict): Product properties (see create_single_step_model)
        ht (dict): Heat transfer parameters (see create_single_step_model)
        Lpr0 (float): Initial product length [cm]
        Lck (float): Current dried cake length [cm]
        **kwargs: Additional arguments passed to create_single_step_model() and
            solve_single_step(). Common options:
            - Pch_bounds (tuple): Chamber pressure bounds [Torr]
            - Tsh_bounds (tuple): Shelf temperature bounds [°C]
            - eq_cap (dict): Equipment capability parameters
            - nVial (int): Number of vials
            - solver (str): Solver name (default: 'ipopt')
            - tee (bool): Print solver output (default: False)
            - warmstart_data (dict): Initial variable values
    
    Returns:
        dict: Solution dictionary (see solve_single_step)
    
    Examples:
        >>> solution = optimize_single_step(
        ...     vial={'Av': 3.8, 'Ap': 3.14},
        ...     product={'R0': 1.4, 'A1': 16.0, 'A2': 0.0, 'T_pr_crit': -5.0},
        ...     ht={'KC': 2.75e-4, 'KP': 8.93e-4, 'KD': 0.46},
        ...     Lpr0=1.5,
        ...     Lck=0.5,
        ...     tee=True
        ... )
    """
    # Separate kwargs for model creation vs solving
    model_kwargs = {k: v for k, v in kwargs.items() 
                   if k in ['Pch_bounds', 'Tsh_bounds', 'eq_cap', 'nVial']}
    solve_kwargs = {k: v for k, v in kwargs.items() 
                   if k in ['solver', 'tee', 'warmstart_data']}
    
    # Create and solve
    model = create_single_step_model(vial, product, ht, Lpr0, Lck, **model_kwargs)
    solution = solve_single_step(model, **solve_kwargs)
    
    return solution
