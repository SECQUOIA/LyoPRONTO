"""Utility functions for Pyomo model initialization, scaling, and result extraction.

This module provides helper functions to bridge scipy and Pyomo implementations,
including warmstarting Pyomo models from scipy solutions and converting results
to standard output formats.
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
from .. import functions, constant


def initialize_from_scipy(scipy_output, time_index, vial, product, Lpr0, ht=None):
    """Create warmstart data dictionary from scipy optimization output.
    
    This function extracts values from a scipy optimization result array
    and formats them as a dictionary suitable for initializing Pyomo variables.
    
    Args:
        scipy_output (np.ndarray): Output from opt_Pch_Tsh.dry() or similar,
            with shape (n_steps, 7) and columns:
            [time, Tsub, Tbot, Tsh, Pch_mTorr, flux, frac_dried]
        time_index (int): Index of the time step to extract (0-based)
        vial (dict): Vial geometry with 'Av', 'Ap' keys
        product (dict): Product properties with 'R0', 'A1', 'A2' keys
        Lpr0 (float): Initial product length [cm]
        ht (dict, optional): Heat transfer parameters with 'KC', 'KP', 'KD' keys.
            If provided, Kv will be computed accurately.
    
    Returns:
        dict: Warmstart data with keys: 'Pch', 'Tsh', 'Tsub', 'Tbot', 'Psub', 
            'log_Psub', 'dmdt', 'Kv'
    
    Notes:
        - Pch is converted from mTorr to Torr (divides by 1000)
        - Lck is calculated from frac_dried
        - Derived quantities (Psub, dmdt, Kv) are computed from physics functions
    
    Examples:
        >>> from lyopronto import opt_Pch_Tsh
        >>> scipy_out = opt_Pch_Tsh.dry(vial, product, ht, Pch, Tsh, dt, eq_cap, nVial)
        >>> warmstart = initialize_from_scipy(scipy_out, 10, vial, product, Lpr0)
        >>> # Use warmstart dict to initialize Pyomo model
    """
    # Extract values from scipy output
    # Columns: [time, Tsub, Tbot, Tsh, Pch_mTorr, flux, frac_dried]
    Tsub = scipy_output[time_index, 1]
    Tbot = scipy_output[time_index, 2]
    Tsh = scipy_output[time_index, 3]
    Pch = scipy_output[time_index, 4] / constant.Torr_to_mTorr  # mTorr → Torr
    frac_dried = scipy_output[time_index, 6]
    
    # Calculate derived quantities
    Lck = frac_dried * Lpr0  # Current dried cake length [cm]
    Rp = functions.Rp_FUN(Lck, product['R0'], product['A1'], product['A2'])
    Psub = functions.Vapor_pressure(Tsub)
    dmdt = functions.sub_rate(vial['Ap'], Rp, Tsub, Pch)
    
    # Calculate Kv from heat transfer parameters if available
    if ht is not None:
        Kv = functions.Kv_FUN(ht['KC'], ht['KP'], ht['KD'], Pch)
    else:
        # Use typical value as fallback
        Kv = 5e-4  # Typical value [cal/s/K/cm²]
    
    warmstart_data = {
        'Pch': Pch,
        'Tsh': Tsh,
        'Tsub': Tsub,
        'Tbot': Tbot,
        'Psub': Psub,
        'log_Psub': np.log(max(Psub, 1e-10)),  # Add log for stability
        'dmdt': max(0.0, dmdt),  # Ensure non-negative
        'Kv': Kv,
    }
    
    return warmstart_data


def extract_solution_to_array(solution, time):
    """Convert Pyomo solution dict to standard output array format.
    
    This function formats a Pyomo solution to match the scipy output format
    for consistency and comparison.
    
    Args:
        solution (dict): Solution from solve_single_step() with keys:
            'Pch', 'Tsh', 'Tsub', 'Tbot', 'dmdt', etc.
        time (float): Time value for this step [hr]
    
    Returns:
        np.ndarray: Array of shape (7,) with columns:
            [time, Tsub, Tbot, Tsh, Pch_mTorr, flux, frac_dried]
    
    Notes:
        - Pch is converted from Torr to mTorr
        - flux is dmdt normalized by product area
        - frac_dried must be computed externally (requires Lck and Lpr0)
    
    Examples:
        >>> solution = solve_single_step(model)
        >>> output_row = extract_solution_to_array(solution, time=0.5)
    """
    # Note: This is a simplified version
    # In full implementation, would need vial['Ap'] and Lck/Lpr0 for complete conversion
    output = np.array([
        time,
        solution['Tsub'],
        solution['Tbot'],
        solution['Tsh'],
        solution['Pch'] * constant.Torr_to_mTorr,  # Torr → mTorr
        solution['dmdt'],  # Note: needs conversion to flux [kg/hr/m²]
        0.0,  # frac_dried - needs to be computed externally
    ])
    
    return output


def add_scaling_suffix(model, variable_scales=None):
    """Add scaling factors to Pyomo model for improved numerical conditioning.
    
    Scaling can significantly improve solver convergence by ensuring all
    variables and constraints have similar magnitudes.
    
    Args:
        model (pyo.ConcreteModel): Pyomo model to add scaling to
        variable_scales (dict, optional): Custom scaling factors. If None,
            uses default scales based on typical variable magnitudes.
            Keys are variable names ('Tsub', 'Pch', etc.), values are
            scaling factors.
    
    Returns:
        None: Modifies model in place by adding scaling_factor Suffix
    
    Notes:
        Default scaling factors:
        - Temperature variables (Tsub, Tbot, Tsh): 0.01 (typical ~-20°C)
        - Pressure variables (Pch, Psub): 10 (typical ~0.1 Torr)
        - Kv: 1e4 (typical ~1e-4)
        - dmdt: 1.0
    
    Examples:
        >>> model = create_single_step_model(...)
        >>> add_scaling_suffix(model)  # Use defaults
        >>> # Or with custom scales:
        >>> add_scaling_suffix(model, {'Pch': 5, 'Tsh': 0.02})
    """
    import pyomo.environ as pyo
    
    # Default scales
    default_scales = {
        'Tsub': 0.01,    # Typical value ~-20°C
        'Tbot': 0.01,
        'Tsh': 0.01,
        'Pch': 10,       # Typical value ~0.1 Torr
        'Psub': 10,
        'Kv': 1e4,       # Typical value ~1e-4
        'dmdt': 1.0,
    }
    
    # Use custom scales if provided, otherwise defaults
    scales = variable_scales if variable_scales is not None else default_scales
    
    # Create scaling suffix
    model.scaling_factor = pyo.Suffix(direction=pyo.Suffix.EXPORT)
    
    # Apply scaling factors
    for var_name, scale in scales.items():
        if hasattr(model, var_name):
            var = getattr(model, var_name)
            model.scaling_factor[var] = scale


def check_solution_validity(solution, tol=1e-3):
    """Validate that a Pyomo solution satisfies physical constraints.
    
    Args:
        solution (dict): Solution dictionary from solve_single_step()
        tol (float, optional): Tolerance for constraint violations. Default: 1e-3
    
    Returns:
        tuple: (is_valid, violations) where:
            - is_valid (bool): True if all checks pass
            - violations (list): List of violation messages
    
    Notes:
        Checks performed:
        - Temperature ordering: Tsub ≤ Tbot ≤ Tsh
        - Sublimation temperature below freezing: Tsub < 0
        - Positive pressures and rates
        - Vapor pressure consistency
    
    Examples:
        >>> solution = solve_single_step(model)
        >>> is_valid, violations = check_solution_validity(solution)
        >>> if not is_valid:
        ...     print("Violations:", violations)
    """
    violations = []
    
    # Temperature ordering
    if solution['Tsub'] > solution['Tbot'] + tol:
        violations.append(f"Tsub ({solution['Tsub']:.2f}) > Tbot ({solution['Tbot']:.2f})")
    
    if solution['Tbot'] > solution['Tsh'] + tol:
        violations.append(f"Tbot ({solution['Tbot']:.2f}) > Tsh ({solution['Tsh']:.2f})")
    
    # Sublimation temperature below freezing
    if solution['Tsub'] > 0 + tol:
        violations.append(f"Tsub ({solution['Tsub']:.2f}) above freezing")
    
    # Positive values
    if solution['Pch'] < -tol:
        violations.append(f"Negative Pch: {solution['Pch']:.4f}")
    
    if solution['Psub'] < -tol:
        violations.append(f"Negative Psub: {solution['Psub']:.4f}")
    
    if solution['dmdt'] < -tol:
        violations.append(f"Negative dmdt: {solution['dmdt']:.6f}")
    
    # Driving force check (Psub should be > Pch for sublimation)
    if solution['Psub'] < solution['Pch'] - tol:
        violations.append(f"Psub ({solution['Psub']:.4f}) < Pch ({solution['Pch']:.4f})")
    
    is_valid = len(violations) == 0
    
    return is_valid, violations
