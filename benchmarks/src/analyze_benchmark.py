"""Core analysis functions for benchmark data.

Pure functions that compute metrics, comparisons, and summaries
from benchmark records. No I/O or plotting - just data transformation.
"""
from __future__ import annotations

from typing import Dict, List, Any, Optional, Tuple
import pandas as pd
import numpy as np


def compute_objective_differences(
    records_by_method: Dict[str, List[Dict[str, Any]]]
) -> pd.DataFrame:
    """Compute % objective difference for Pyomo methods vs scipy baseline.
    
    Args:
        records_by_method: Dict mapping method name to list of records
        
    Returns:
        DataFrame with columns: param1, param2, method, obj_pyomo, obj_scipy, 
                                pct_diff, speedup
    """
    scipy_records = records_by_method.get('scipy', [])
    
    results = []
    for method in ['fd', 'colloc']:
        pyomo_records = records_by_method.get(method, [])
        
        for py_rec in pyomo_records:
            if not py_rec.get('success', False):
                continue
                
            # Extract parameter values
            grid = py_rec.get('grid', {})
            p1 = grid.get('param1', {}).get('value')
            p2 = grid.get('param2', {}).get('value')
            p1_name = grid.get('param1', {}).get('path', 'param1')
            p2_name = grid.get('param2', {}).get('path', 'param2')
            
            # Find matching scipy record
            scipy_match = None
            for sc_rec in scipy_records:
                sc_grid = sc_rec.get('grid', {})
                if (sc_grid.get('param1', {}).get('value') == p1 and
                    sc_grid.get('param2', {}).get('value') == p2):
                    scipy_match = sc_rec
                    break
            
            if scipy_match is None or not scipy_match.get('success', False):
                continue
            
            # Extract objectives
            obj_pyomo = py_rec.get('objective_time_hr')
            obj_scipy = scipy_match.get('objective_time_hr')
            
            if obj_pyomo is None or obj_scipy is None:
                continue
            
            # Compute % difference: (pyomo - scipy) / scipy * 100
            pct_diff = (obj_pyomo - obj_scipy) / obj_scipy * 100
            
            # Compute speedup: scipy_time / pyomo_time
            time_scipy = scipy_match.get('wall_time_s', 0)
            time_pyomo = py_rec.get('wall_time_s', 0)
            speedup = time_scipy / time_pyomo if time_pyomo > 0 else np.nan
            
            results.append({
                'param1': p1,
                'param2': p2,
                'param1_name': p1_name,
                'param2_name': p2_name,
                'method': method,
                'obj_pyomo': obj_pyomo,
                'obj_scipy': obj_scipy,
                'pct_diff': pct_diff,
                'wall_time_scipy': time_scipy,
                'wall_time_pyomo': time_pyomo,
                'speedup': speedup,
            })
    
    return pd.DataFrame(results)


def compute_speedups(
    records_by_method: Dict[str, List[Dict[str, Any]]]
) -> pd.DataFrame:
    """Compute wall time speedup for Pyomo methods vs scipy.
    
    Args:
        records_by_method: Dict mapping method name to list of records
        
    Returns:
        DataFrame with speedup metrics
    """
    # Reuse objective_differences which already computes speedup
    df = compute_objective_differences(records_by_method)
    return df[['param1', 'param2', 'param1_name', 'param2_name', 
               'method', 'speedup', 'wall_time_scipy', 'wall_time_pyomo']]


def extract_nominal_case(
    records: List[Dict[str, Any]],
    param1_val: float,
    param2_val: float,
    method: str,
    tol: float = 1e-9
) -> Optional[np.ndarray]:
    """Extract trajectory for specific parameter combination and method.
    
    Args:
        records: List of benchmark records
        param1_val: First parameter value
        param2_val: Second parameter value
        method: Method name ('scipy', 'fd', 'colloc')
        tol: Tolerance for float comparison
        
    Returns:
        Trajectory array (N x 7) or None if not found
    """
    for rec in records:
        # Parameter grid (same for v1 and v2)
        grid = rec.get('grid', {})
        p1 = grid.get('param1', {}).get('value')
        p2 = grid.get('param2', {}).get('value')
        if p1 is None or p2 is None:
            continue
        if not (abs(p1 - param1_val) < tol and abs(p2 - param2_val) < tol):
            continue

        # Version 2 format nests method-specific data under 'scipy' or 'pyomo'
        if method == 'scipy':
            data = rec.get('scipy', rec)  # fall back to v1 flat record
            success = data.get('success', False)
            traj = data.get('trajectory')
            if success and traj is not None:
                return np.array(traj)
        elif method in ['fd', 'colloc']:
            pyomo = rec.get('pyomo')
            if not isinstance(pyomo, dict):
                continue  # record does not contain pyomo results
            disc_method = pyomo.get('discretization', {}).get('method')
            if disc_method != method:
                continue
            success = pyomo.get('success', False)
            traj = pyomo.get('trajectory')
            if success and traj is not None:
                return np.array(traj)
        else:
            continue
    
    return None


def generate_summary_stats(
    comparison_df: pd.DataFrame
) -> Dict[str, Any]:
    """Generate summary statistics from comparison DataFrame.
    
    Args:
        comparison_df: DataFrame from compute_objective_differences
        
    Returns:
        Dict with summary metrics
    """
    summary = {}
    
    for method in comparison_df['method'].unique():
        method_df = comparison_df[comparison_df['method'] == method]
        
        summary[method] = {
            'mean_pct_diff': float(method_df['pct_diff'].mean()),
            'std_pct_diff': float(method_df['pct_diff'].std()),
            'max_pct_diff': float(method_df['pct_diff'].max()),
            'min_pct_diff': float(method_df['pct_diff'].min()),
            'mean_speedup': float(method_df['speedup'].mean()),
            'std_speedup': float(method_df['speedup'].std()),
            'max_speedup': float(method_df['speedup'].max()),
            'min_speedup': float(method_df['speedup'].min()),
            'n_cases': len(method_df),
        }
    
    return summary


def validate_solver_status(
    records: List[Dict[str, Any]]
) -> pd.DataFrame:
    """Generate report of solver status for all runs.
    
    Args:
        records: List of benchmark records
        
    Returns:
        DataFrame with success status and failure reasons
    """
    results = []
    
    for rec in records:
        grid = rec.get('grid', {})
        p1 = grid.get('param1', {}).get('value')
        p2 = grid.get('param2', {}).get('value')
        
        method = rec.get('method', 'unknown')
        if method != 'scipy':
            disc = rec.get('discretization', {})
            method = disc.get('method', 'unknown')
        
        results.append({
            'param1': p1,
            'param2': p2,
            'method': method,
            'success': rec.get('success', False),
            'message': rec.get('message', ''),
            'wall_time_s': rec.get('wall_time_s'),
            'objective_time_hr': rec.get('objective_time_hr'),
        })
    
    return pd.DataFrame(results)


def pivot_for_heatmap(
    comparison_df: pd.DataFrame,
    method: str,
    metric: str = 'pct_diff'
) -> pd.DataFrame:
    """Pivot comparison data for heatmap visualization.
    
    Args:
        comparison_df: DataFrame from compute_objective_differences
        method: Method to filter ('fd' or 'colloc')
        metric: Metric to pivot ('pct_diff' or 'speedup')
        
    Returns:
        Pivoted DataFrame suitable for seaborn heatmap
    """
    method_df = comparison_df[comparison_df['method'] == method]
    
    if len(method_df) == 0:
        return pd.DataFrame()
    
    # Get parameter names from first row
    param1_name = method_df.iloc[0]['param1_name']
    param2_name = method_df.iloc[0]['param2_name']
    
    # Pivot: rows=param2, cols=param1 (typical convention)
    pivoted = method_df.pivot(
        index='param2',
        columns='param1',
        values=metric
    )
    
    # Sort for consistent display
    pivoted = pivoted.sort_index(ascending=True).sort_index(axis=1, ascending=True)
    
    return pivoted
