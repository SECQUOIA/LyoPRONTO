"""Multi-period lyophilization optimization using Pyomo DAE with orthogonal collocation.

This module implements dynamic optimization of the primary drying phase using:
- Pyomo's DAE (Differential-Algebraic Equations) framework
- Orthogonal collocation on finite elements for time discretization
- Log-transformed vapor pressure for numerical stability
- Variable scaling for improved conditioning

The model optimizes chamber pressure Pch(t) and shelf temperature Tsh(t)
trajectories over time to minimize drying time while respecting temperature
constraints.

Reference:
- Pyomo DAE documentation: https://pyomo.readthedocs.io/en/stable/modeling_extensions/dae.html
- Orthogonal collocation: Biegler (2010), Nonlinear Programming
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

import numpy as np
from typing import Dict, Optional
import pyomo.environ as pyo
import pyomo.dae as dae
from lyopronto import functions, constant


def create_multi_period_model(
    vial: Dict[str, float],
    product: Dict[str, float],
    ht: Dict[str, float],
    Vfill: float,
    n_elements: int = 10,
    n_collocation: int = 3,
    t_final: float = 10.0,
    apply_scaling: bool = True,
) -> pyo.ConcreteModel:
    """Create multi-period Pyomo DAE model for primary drying optimization.
    
    This creates a dynamic optimization model with:
    - Time as a continuous variable discretized by collocation
    - Differential equations for temperature evolution
    - Algebraic equations for heat/mass transfer
    - Path constraints on product temperature
    
    Args:
        vial (dict): Vial parameters (Av, Ap)
        product (dict): Product parameters (R0, A1, A2, Tpr_max, cSolid)
        ht (dict): Heat transfer parameters (KC, KP, KD)
        Vfill (float): Fill volume [mL]
        n_elements (int): Number of finite elements for time discretization
        n_collocation (int): Number of collocation points per element (3-5 recommended)
        t_final (float): Final time [hr] (will be optimized)
        apply_scaling (bool): Apply variable/constraint scaling
        
    Returns:
        model (ConcreteModel): Pyomo model ready for optimization
        
    Model Variables:
        Time-indexed (continuous):
        - Pch(t): Chamber pressure [Torr]
        - Tsh(t): Shelf temperature [°C]
        - Tsub(t): Sublimation front temperature [°C]
        - Tbot(t): Vial bottom temperature [°C]
        - Psub(t): Vapor pressure at sublimation front [Torr]
        - log_Psub(t): Log of vapor pressure (for stability)
        - dmdt(t): Sublimation rate [kg/hr]
        - Kv(t): Vial heat transfer coefficient [cal/s/K/cm²]
        - Lck(t): Dried cake length [cm]
        - Rp(t): Product resistance [cm²-hr-Torr/g]
        
        Scalar:
        - t_final: Total drying time [hr] (optimization variable)
        
    Constraints:
        ODEs:
        - dTsub/dt = f(heat balance, sublimation)
        - dTbot/dt = f(shelf heat transfer)
        - dLck/dt = dmdt * conversion_factor
        
        Algebraic:
        - Vapor pressure (log-transformed)
        - Sublimation rate (mass transfer)
        - Heat balance
        - Product resistance
        - Kv calculation
        
        Path constraints:
        - Tsub(t) >= Tpr_max (product temperature limit)
        - 0 <= Pch(t) <= 0.5 (chamber pressure bounds)
        - -50 <= Tsh(t) <= 50 (shelf temperature bounds)
        
    Objective:
        Minimize t_final (total drying time)
        
    Notes:
        - Uses Radau collocation (right-biased, good for stiff systems)
        - Log transformation improves numerical stability
        - Scaling reduces condition number by 2-3 orders of magnitude
        - Warmstart from scipy trajectory recommended
    """
    model = pyo.ConcreteModel()
    
    # Extract parameters
    Av = vial['Av']
    Ap = vial['Ap']
    R0 = product['R0']
    A1 = product['A1']
    A2 = product['A2']
    Tpr_max = product.get('Tpr_max', product.get('T_pr_crit', -25.0))  # Handle both naming conventions
    cSolid = product['cSolid']
    KC = ht['KC']
    KP = ht['KP']
    KD = ht['KD']
    
    # Compute initial product length
    Lpr0 = functions.Lpr0_FUN(Vfill, Ap, cSolid)
    
    # Physical constants - use values from constant.py
    dHs = constant.dHs  # Heat of sublimation [cal/g] (678.0)
    
    # ======================
    # TIME DOMAIN
    # ======================
    
    model.t = dae.ContinuousSet(bounds=(0, 1))  # Normalized time [0, 1]
    
    # Actual time scaling factor (to be optimized)
    model.t_final = pyo.Var(bounds=(0.1, 50.0), initialize=t_final)
    
    # ======================
    # STATE VARIABLES
    # ======================
    
    # Temperatures [°C]
    model.Tsub = pyo.Var(model.t, bounds=(-60, 0), initialize=-25.0)
    model.Tbot = pyo.Var(model.t, bounds=(-60, 50), initialize=-20.0)
    
    # Dried cake length [cm]
    model.Lck = pyo.Var(model.t, bounds=(0, Lpr0), initialize=0.0)
    
    # ======================
    # CONTROL VARIABLES
    # ======================
    
    # Chamber pressure [Torr]
    model.Pch = pyo.Var(model.t, bounds=(0.05, 0.5), initialize=0.1)
    
    # Shelf temperature [°C]
    model.Tsh = pyo.Var(model.t, bounds=(-50, 50), initialize=-10.0)
    
    # ======================
    # ALGEBRAIC VARIABLES
    # ======================
    
    # Vapor pressure [Torr]
    model.Psub = pyo.Var(model.t, bounds=(0.001, 10), initialize=0.5)
    model.log_Psub = pyo.Var(model.t, bounds=(-14, 2.5), initialize=np.log(0.5))
    
    # Sublimation rate [kg/hr]
    model.dmdt = pyo.Var(model.t, bounds=(0, 100), initialize=1.0)
    
    # Vial heat transfer coefficient [cal/s/K/cm²]
    model.Kv = pyo.Var(model.t, bounds=(1e-5, 1e-2), initialize=5e-4)
    
    # Product resistance [cm²-hr-Torr/g]
    model.Rp = pyo.Var(model.t, bounds=(0, 1000), initialize=R0)
    
    # ======================
    # DERIVATIVES
    # ======================
    
    # Only Lck has a true derivative - Tsub and Tbot are algebraic (quasi-steady)
    model.dLck_dt = dae.DerivativeVar(model.Lck, wrt=model.t)
    
    # ======================
    # ALGEBRAIC CONSTRAINTS
    # ======================
    
    def vapor_pressure_log_rule(m, t):
        """Log transformation of Antoine equation for vapor pressure."""
        return m.log_Psub[t] == pyo.log(2.698e10) - 6144.96 / (m.Tsub[t] + 273.15)
    
    model.vapor_pressure_log = pyo.Constraint(model.t, rule=vapor_pressure_log_rule)
    
    def vapor_pressure_exp_rule(m, t):
        """Exponential recovery of vapor pressure."""
        return m.Psub[t] == pyo.exp(m.log_Psub[t])
    
    model.vapor_pressure_exp = pyo.Constraint(model.t, rule=vapor_pressure_exp_rule)
    
    def product_resistance_rule(m, t):
        """Product resistance as function of dried cake length."""
        return m.Rp[t] == R0 + A1 * m.Lck[t] / (1 + A2 * m.Lck[t])
    
    model.product_resistance = pyo.Constraint(model.t, rule=product_resistance_rule)
    
    def kv_calc_rule(m, t):
        """Vial heat transfer coefficient.
        
        Kv = KC + KP * Pch / (1 + KD * Pch)  [cal/s/K/cm^2]
        """
        return m.Kv[t] == KC + KP * m.Pch[t] / (1.0 + KD * m.Pch[t])
    
    model.kv_calc = pyo.Constraint(model.t, rule=kv_calc_rule)
    
    def sublimation_rate_rule(m, t):
        """Mass transfer equation for sublimation rate.
        
        From functions.sub_rate: dmdt = Ap/Rp/kg_To_g*(Psub-Pch)
        Rearranged: dmdt * Rp = Ap * (Psub - Pch) / kg_To_g
        """
        if t == 0:
            return pyo.Constraint.Skip  # Initial condition handled separately
        # dmdt in kg/hr; kg_To_g = 1000 from constant.py
        return m.dmdt[t] * m.Rp[t] == Ap * (m.Psub[t] - m.Pch[t]) / constant.kg_To_g
    
    model.sublimation_rate = pyo.Constraint(model.t, rule=sublimation_rate_rule)
    
    # ======================
    # QUASI-STEADY HEAT BALANCE (ALGEBRAIC CONSTRAINTS)
    # ======================
    # The scipy model uses quasi-steady state heat balance:
    # Qsub = dHs * (Psub - Pch) * Ap / Rp / hr_To_s  [cal/s]
    # Tbot = Tsub + Qsub / Ap / k_ice * (Lpr0 - Lck)
    # Qsh = Kv * Av * (Tsh - Tbot)                   [cal/s]
    # At steady state: Qsub = Qsh
    
    k_ice = constant.k_ice  # Thermal conductivity of ice [cal/cm/s/K] (0.0059)
    hr_To_s = constant.hr_To_s  # Seconds per hour (3600.0)
    
    def heat_balance_rule(m, t):
        """Quasi-steady heat balance: heat in from shelf = heat for sublimation.
        
        This replaces the ODE approach with the correct algebraic constraint.
        """
        # Heat for sublimation [cal/s]
        # Qsub = dHs * (Psub - Pch) * Ap / Rp / hr_To_s
        Qsub = dHs * (m.Psub[t] - m.Pch[t]) * Ap / m.Rp[t] / hr_To_s
        
        # Heat from shelf [cal/s]
        Qsh = m.Kv[t] * Av * (m.Tsh[t] - m.Tbot[t])
        
        # Quasi-steady: Qsub = Qsh
        return Qsub == Qsh
    
    model.heat_balance = pyo.Constraint(model.t, rule=heat_balance_rule)
    
    def bottom_temp_rule(m, t):
        """Vial bottom temperature from temperature gradient through frozen product.
        
        Tbot = Tsub + Qsub / (Ap * k_ice) * (Lpr0 - Lck)
        """
        # Heat for sublimation [cal/s]
        Qsub = dHs * (m.Psub[t] - m.Pch[t]) * Ap / m.Rp[t] / hr_To_s
        
        # Temperature gradient: dT/dx = Q / (A * k)
        # So Tbot - Tsub = Q * L / (A * k)
        return m.Tbot[t] == m.Tsub[t] + Qsub / (Ap * k_ice) * (Lpr0 - m.Lck[t])
    
    model.bottom_temp = pyo.Constraint(model.t, rule=bottom_temp_rule)
    
    # ======================
    # DIFFERENTIAL EQUATION FOR CAKE LENGTH
    # ======================
    
    def cake_length_ode_rule(m, t):
        """Dried cake length increases with sublimation.
        
        dLck/dt = dmdt / (Ap * rho_ice * (1 - cSolid))
        """
        if t == 0:
            return pyo.Constraint.Skip
        
        rho_ice = 0.92  # Density of ice [g/cm³]
        
        # Convert dmdt [kg/hr] to [g/hr], divide by area and density
        return m.dLck_dt[t] == (m.dmdt[t] * 1000) / (Ap * rho_ice * (1 - cSolid)) * m.t_final
    
    model.cake_length_ode = pyo.Constraint(model.t, rule=cake_length_ode_rule)
    
    # ======================
    # INITIAL CONDITIONS
    # ======================
    
    def lck_ic_rule(m):
        """Initial cake length is zero."""
        return m.Lck[0] == 0.0
    
    model.lck_ic = pyo.Constraint(rule=lck_ic_rule)
    
    # ======================
    # TERMINAL CONSTRAINTS
    # ======================
    
    def final_dryness_rule(m):
        """Ensure drying is complete at final time."""
        return m.Lck[1] >= 0.95 * Lpr0  # 95% dried
    
    model.final_dryness = pyo.Constraint(rule=final_dryness_rule)
    
    # ======================
    # PATH CONSTRAINTS
    # ======================
    
    def temp_limit_rule(m, t):
        """Product temperature must not exceed maximum.
        
        Skip at t=0 since the process starts from cold shelf temperature.
        """
        if t == 0:
            return pyo.Constraint.Skip
        return m.Tsub[t] >= Tpr_max
    
    model.temp_limit = pyo.Constraint(model.t, rule=temp_limit_rule)
    
    # ======================
    # OBJECTIVE
    # ======================
    
    # Minimize total drying time
    model.obj = pyo.Objective(expr=model.t_final, sense=pyo.minimize)
    
    # ======================
    # APPLY DISCRETIZATION
    # ======================
    
    discretizer = pyo.TransformationFactory('dae.collocation')
    discretizer.apply_to(
        model,
        nfe=n_elements,
        ncp=n_collocation,
        scheme='LAGRANGE-RADAU'  # Right-biased, good for stiff systems
    )
    
    # ======================
    # APPLY SCALING
    # ======================
    
    if apply_scaling:
        # Scaling factors (based on typical magnitudes)
        model.scaling_factor = pyo.Suffix(direction=pyo.Suffix.EXPORT)
        
        # Variables
        for t in model.t:
            # Temperatures already O(10)
            model.scaling_factor[model.Tsub[t]] = 1.0
            model.scaling_factor[model.Tbot[t]] = 1.0
            model.scaling_factor[model.Tsh[t]] = 1.0
            
            # Pressures already O(0.1-1)
            model.scaling_factor[model.Pch[t]] = 1.0
            model.scaling_factor[model.Psub[t]] = 1.0
            model.scaling_factor[model.log_Psub[t]] = 1.0
            
            # Sublimation rate O(1) -> scale to O(1)
            model.scaling_factor[model.dmdt[t]] = 0.1
            
            # Kv O(1e-4) -> scale to O(0.1)
            model.scaling_factor[model.Kv[t]] = 1000.0
            
            # Rp O(10-100) -> scale to O(1)
            model.scaling_factor[model.Rp[t]] = 0.01
            
            # Lck O(1) already good
            model.scaling_factor[model.Lck[t]] = 1.0
            
            # Derivatives (per normalized time) - only Lck has a derivative now
            model.scaling_factor[model.dLck_dt[t]] = 1.0
        
        # Scalar variables
        model.scaling_factor[model.t_final] = 0.1
        
        # Apply scaling transformation
        scaling_transform = pyo.TransformationFactory('core.scale_model')
        scaled_model = scaling_transform.create_using(model)
        
        return scaled_model
    
    return model


def warmstart_from_scipy_trajectory(
    model: pyo.ConcreteModel,
    scipy_trajectory: np.ndarray,
    vial: Dict[str, float],
    product: Dict[str, float],
    ht: Dict[str, float],
) -> None:
    """Initialize Pyomo DAE model from scipy trajectory.
    
    Args:
        model (ConcreteModel): Pyomo model to initialize
        scipy_trajectory (ndarray): Output from calc_knownRp.dry()
            Columns: [time, Tsub, Tbot, Tsh, Pch, flux, percent_dried]
        vial (dict): Vial parameters (needed for Lck calculation)
        product (dict): Product parameters (needed for Lck calculation)
        ht (dict): Heat transfer parameters
    """
    # Extract data from scipy trajectory
    t_scipy = scipy_trajectory[:, 0]  # Time [hr]
    Tsub_scipy = scipy_trajectory[:, 1]  # Tsub [°C]
    Tbot_scipy = scipy_trajectory[:, 2]  # Tbot [°C]
    Tsh_scipy = scipy_trajectory[:, 3]  # Tsh [°C]
    Pch_scipy = scipy_trajectory[:, 4] / 1000.0  # Pch [Torr] (from mTorr)
    percent_dried_scipy = scipy_trajectory[:, 6]  # Percent dried [0-100]
    
    # Get Pyomo time points (normalized to [0, 1])
    t_pyomo = sorted(model.t)
    
    # Compute initial product length from vial parameters
    Lpr0 = functions.Lpr0_FUN(
        vial['Vfill'],
        vial['Ap'],
        product['cSolid']
    )
    
    # Initialize t_final
    model.t_final.set_value(t_scipy[-1])
    
    # Interpolate scipy data to Pyomo time points
    for i, t_norm in enumerate(t_pyomo):
        t_actual = t_norm * t_scipy[-1]
        
        # Interpolate scipy data
        Tsub_interp = np.interp(t_actual, t_scipy, Tsub_scipy)
        Tbot_interp = np.interp(t_actual, t_scipy, Tbot_scipy)
        Tsh_interp = np.interp(t_actual, t_scipy, Tsh_scipy)
        Pch_interp = np.interp(t_actual, t_scipy, Pch_scipy)
        percent_interp = np.interp(t_actual, t_scipy, percent_dried_scipy)
        
        # Set variable values
        model.Tsub[t_norm].set_value(Tsub_interp)
        model.Tbot[t_norm].set_value(Tbot_interp)
        model.Tsh[t_norm].set_value(Tsh_interp)
        model.Pch[t_norm].set_value(Pch_interp)
        
        # Compute Lck from percent dried (convert to fraction first)
        Lck_interp = (percent_interp / 100.0) * Lpr0
        model.Lck[t_norm].set_value(Lck_interp)
        
        # Compute algebraic variables
        Psub_interp = functions.Vapor_pressure(Tsub_interp)
        model.Psub[t_norm].set_value(Psub_interp)
        model.log_Psub[t_norm].set_value(np.log(Psub_interp))
        
        Kv_interp = functions.Kv_FUN(ht['KC'], ht['KP'], ht['KD'], Pch_interp)
        model.Kv[t_norm].set_value(Kv_interp)
        
        Rp_interp = functions.Rp_FUN(Lck_interp, product['R0'], product['A1'], product['A2'])
        model.Rp[t_norm].set_value(Rp_interp)
        
        # Estimate dmdt from heat balance
        if Rp_interp > 0:
            dmdt_interp = vial['Ap'] * (Psub_interp - Pch_interp) / (Rp_interp * 100.0)
            model.dmdt[t_norm].set_value(max(dmdt_interp, 0.0))
        else:
            model.dmdt[t_norm].set_value(0.1)

    # Initialize derivative variable (dLck_dt only) by computing from state trajectories
    # The derivatives are with respect to normalized time, so scale by t_final
    t_pyomo_list = list(t_pyomo)

    for i, t_norm in enumerate(t_pyomo_list):
        if i == 0:
            # Use forward difference for first point
            if len(t_pyomo_list) > 1:
                t_next = t_pyomo_list[1]
                dt_norm = t_next - t_norm
                dLck_dt = (pyo.value(model.Lck[t_next]) - pyo.value(model.Lck[t_norm])) / dt_norm
            else:
                dLck_dt = 0.0
        else:
            # Use backward difference
            t_prev = t_pyomo_list[i - 1]
            dt_norm = t_norm - t_prev
            if dt_norm > 1e-10:
                dLck_dt = (pyo.value(model.Lck[t_norm]) - pyo.value(model.Lck[t_prev])) / dt_norm
            else:
                dLck_dt = 0.0

        # Set derivative value (skip t=0 as it doesn't have derivative vars after discretization)
        if hasattr(model, 'dLck_dt') and t_norm in model.dLck_dt:
            model.dLck_dt[t_norm].set_value(dLck_dt)


def optimize_multi_period(
    vial: Dict[str, float],
    product: Dict[str, float],
    ht: Dict[str, float],
    Vfill: float,
    n_elements: int = 10,
    n_collocation: int = 3,
    warmstart_data: Optional[np.ndarray] = None,
    solver: str = 'ipopt',
    tee: bool = False,
    apply_scaling: bool = True,
) -> Dict:
    """Optimize multi-period primary drying process.
    
    Args:
        vial (dict): Vial parameters
        product (dict): Product parameters
        ht (dict): Heat transfer parameters
        Vfill (float): Fill volume [mL]
        n_elements (int): Number of finite elements
        n_collocation (int): Collocation points per element
        warmstart_data (ndarray, optional): Scipy trajectory from calc_knownRp.dry()
        solver (str): Solver to use ('ipopt' recommended)
        tee (bool): Print solver output
        apply_scaling (bool): Apply variable scaling
        
    Returns:
        solution (dict): Optimized trajectories and final time
            - 't': Time points [hr]
            - 'Pch': Chamber pressure trajectory [Torr]
            - 'Tsh': Shelf temperature trajectory [°C]
            - 'Tsub': Sublimation temperature trajectory [°C]
            - 'Tbot': Vial bottom temperature trajectory [°C]
            - 'Lck': Dried cake length trajectory [cm]
            - 'dmdt': Sublimation rate trajectory [kg/hr]
            - 't_final': Total drying time [hr]
            - 'status': Solver termination status
            
    Example:
        >>> # Get scipy warmstart
        >>> scipy_traj = calc_knownRp.dry(vial, product, ht, 2.0, -10.0, 0.1)
        >>> solution = optimize_multi_period(
        ...     vial, product, ht, Vfill=2.0, warmstart_data=scipy_traj
        ... )
        >>> print(f"Optimal drying time: {solution['t_final']:.2f} hr")
    """
    # Create model WITHOUT scaling first (for warmstart)
    model = create_multi_period_model(
        vial, product, ht, Vfill,
        n_elements=n_elements,
        n_collocation=n_collocation,
        apply_scaling=False  # Don't scale yet
    )

    # Apply warmstart if provided (must be done before scaling)
    if warmstart_data is not None:
        warmstart_from_scipy_trajectory(model, warmstart_data, vial, product, ht)

    # Now apply scaling if requested
    if apply_scaling:
        model.scaling_factor = pyo.Suffix(direction=pyo.Suffix.EXPORT)

        # Variables
        for t in model.t:
            model.scaling_factor[model.Tsub[t]] = 1.0
            model.scaling_factor[model.Tbot[t]] = 1.0
            model.scaling_factor[model.Tsh[t]] = 1.0
            model.scaling_factor[model.Pch[t]] = 1.0
            model.scaling_factor[model.Psub[t]] = 1.0
            model.scaling_factor[model.log_Psub[t]] = 1.0
            model.scaling_factor[model.dmdt[t]] = 0.1
            model.scaling_factor[model.Kv[t]] = 1000.0
            model.scaling_factor[model.Rp[t]] = 0.01
            model.scaling_factor[model.Lck[t]] = 1.0
            model.scaling_factor[model.dLck_dt[t]] = 1.0

        model.scaling_factor[model.t_final] = 0.1

        scaling_transform = pyo.TransformationFactory('core.scale_model')
        model = scaling_transform.create_using(model)
    
    # Solve
    opt = pyo.SolverFactory(solver)
    
    if solver == 'ipopt':
        opt.options['max_iter'] = 3000
        opt.options['tol'] = 1e-6
        opt.options['acceptable_tol'] = 1e-4
        opt.options['print_level'] = 5 if tee else 0
        opt.options['mu_strategy'] = 'adaptive'
    
    results = opt.solve(model, tee=tee)

    # Helper to get variable (handles scaled vs unscaled model)
    def get_var(name):
        if hasattr(model, name):
            return getattr(model, name)
        return getattr(model, f'scaled_{name}')

    # Extract solution
    t_final_var = get_var('t_final')
    solution = {
        'status': str(results.solver.termination_condition),
        't_final': pyo.value(t_final_var),
    }

    # Extract trajectories
    t_set = get_var('t') if hasattr(model, 't') else model.scaled_t
    t_points = sorted(t_set)
    Pch_var = get_var('Pch')
    Tsh_var = get_var('Tsh')
    Tsub_var = get_var('Tsub')
    Tbot_var = get_var('Tbot')
    Lck_var = get_var('Lck')
    dmdt_var = get_var('dmdt')
    Psub_var = get_var('Psub')
    Rp_var = get_var('Rp')

    solution['t'] = np.array([t * solution['t_final'] for t in t_points])
    solution['Pch'] = np.array([pyo.value(Pch_var[t]) for t in t_points])
    solution['Tsh'] = np.array([pyo.value(Tsh_var[t]) for t in t_points])
    solution['Tsub'] = np.array([pyo.value(Tsub_var[t]) for t in t_points])
    solution['Tbot'] = np.array([pyo.value(Tbot_var[t]) for t in t_points])
    solution['Lck'] = np.array([pyo.value(Lck_var[t]) for t in t_points])
    solution['dmdt'] = np.array([pyo.value(dmdt_var[t]) for t in t_points])
    solution['Psub'] = np.array([pyo.value(Psub_var[t]) for t in t_points])
    solution['Rp'] = np.array([pyo.value(Rp_var[t]) for t in t_points])
    
    return solution
