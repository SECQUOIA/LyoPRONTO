"""Data loading and validation for benchmark results.

Provides utilities to load JSONL benchmark files, validate schema,
and organize data by method (scipy/FD/collocation).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Any, Optional
import pandas as pd
import numpy as np


def load_benchmark_jsonl(filepath: Path | str) -> List[Dict[str, Any]]:
    """Load benchmark data from JSONL file.
    
    Args:
        filepath: Path to JSONL file
        
    Returns:
        List of benchmark records (dicts)
        
    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If file is empty or malformed
    """
    filepath = Path(filepath)
    if not filepath.exists():
        raise FileNotFoundError(f"Benchmark file not found: {filepath}")
    
    records = []
    with open(filepath, 'r') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                records.append(record)
            except json.JSONDecodeError as e:
                raise ValueError(f"Malformed JSON at line {line_num}: {e}")
    
    if not records:
        raise ValueError(f"No valid records found in {filepath}")
    
    return records


def validate_benchmark_record(record: Dict[str, Any]) -> bool:
    """Check if benchmark record has required fields.
    
    Args:
        record: Benchmark record dict
        
    Returns:
        True if valid, False otherwise
    """
    required_fields = ['task', 'success', 'wall_time_s']
    return all(field in record for field in required_fields)


def organize_by_method(records: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Organize benchmark records by method (scipy/fd/colloc).
    
    Handles two formats:
    - Version 2: Single record with scipy/fd/collocation as nested keys
    - Version 1: Separate records with 'method' field
    
    Args:
        records: List of benchmark records
        
    Returns:
        Dict mapping method name to list of records (one per method per grid point)
    """
    organized = {'scipy': [], 'fd': [], 'colloc': []}
    
    for rec in records:
        # Check for version 2 format (nested method keys)
        version = rec.get('version', 1)
        
        if version == 2:
            # Handle scipy method
            if 'scipy' in rec and rec['scipy'] is not None:
                method_rec = {
                    'task': rec['task'],
                    'scenario': rec.get('scenario', ''),
                    'grid': rec.get('grid', {}),
                    'method': 'scipy',
                    'success': rec['scipy'].get('success', False),
                    'wall_time_s': rec['scipy'].get('wall_time_s', 0),
                    'objective_time_hr': rec['scipy'].get('objective_time_hr', 0),
                    'solver': rec['scipy'].get('solver', {}),
                    'metrics': rec['scipy'].get('metrics', {}),
                    'trajectory': rec['scipy'].get('trajectory', []),
                }
                organized['scipy'].append(method_rec)
            
            # Handle pyomo method (check discretization.method for fd/colloc)
            if 'pyomo' in rec and rec['pyomo'] is not None:
                disc_method = rec['pyomo'].get('discretization', {}).get('method', '')
                if disc_method in ['fd', 'colloc', 'collocation']:
                    method_rec = {
                        'task': rec['task'],
                        'scenario': rec.get('scenario', ''),
                        'grid': rec.get('grid', {}),
                        'method': disc_method,
                        'success': rec['pyomo'].get('success', False),
                        'wall_time_s': rec['pyomo'].get('wall_time_s', 0),
                        'objective_time_hr': rec['pyomo'].get('objective_time_hr', 0),
                        'solver': rec['pyomo'].get('solver', {}),
                        'metrics': rec['pyomo'].get('metrics', {}),
                        'trajectory': rec['pyomo'].get('trajectory', []),
                        'discretization': rec['pyomo'].get('discretization', {}),
                    }
                    # Map collocation -> colloc for consistency
                    key = 'colloc' if disc_method in ['collocation', 'colloc'] else 'fd'
                    organized[key].append(method_rec)
        else:
            # Version 1 format (legacy)
            if rec.get('method') == 'scipy':
                organized['scipy'].append(rec)
            else:
                # Pyomo methods - check discretization
                disc = rec.get('discretization', {})
                method = disc.get('method', '')
                if method == 'fd':
                    organized['fd'].append(rec)
                elif method == 'colloc':
                    organized['colloc'].append(rec)
    
    return organized


def extract_parameter_grid(records: List[Dict[str, Any]]) -> Dict[str, np.ndarray]:
    """Extract unique parameter values from grid.
    
    Args:
        records: List of benchmark records
        
    Returns:
        Dict with 'param1_name', 'param1_values', 'param2_name', 'param2_values'
    """
    if not records:
        return {}
    
    # Extract from first record's grid structure
    first_grid = records[0].get('grid', {})
    
    param_info = {}
    for i in [1, 2]:
        param_key = f'param{i}'
        if param_key in first_grid:
            param_info[f'{param_key}_name'] = first_grid[param_key]['path']
            # Collect all unique values across records
            values = set()
            for rec in records:
                grid = rec.get('grid', {})
                if param_key in grid:
                    values.add(grid[param_key]['value'])
            param_info[f'{param_key}_values'] = np.array(sorted(values))
    
    return param_info


def get_matching_records(records: List[Dict[str, Any]], 
                        param1_val: float, 
                        param2_val: float,
                        tol: float = 1e-9) -> List[Dict[str, Any]]:
    """Find all records matching specific parameter values.
    
    Args:
        records: List of benchmark records
        param1_val: First parameter value to match
        param2_val: Second parameter value to match
        tol: Tolerance for float comparison
        
    Returns:
        List of matching records
    """
    matches = []
    for rec in records:
        grid = rec.get('grid', {})
        p1 = grid.get('param1', {}).get('value')
        p2 = grid.get('param2', {}).get('value')
        
        if (p1 is not None and p2 is not None and
            abs(p1 - param1_val) < tol and abs(p2 - param2_val) < tol):
            matches.append(rec)
    
    return matches


def filter_successful(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Filter to only successful runs.
    
    Args:
        records: List of benchmark records
        
    Returns:
        List of records where success=True
    """
    return [r for r in records if r.get('success', False)]


def extract_metadata(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Extract common metadata from benchmark records.
    
    Args:
        records: List of benchmark records
        
    Returns:
        Dict with task, scenario, parameter info, etc.
    """
    if not records:
        return {}
    
    first = records[0]
    metadata = {
        'task': first.get('task'),
        'scenario': first.get('scenario'),
        'total_records': len(records),
        'successful_records': len(filter_successful(records)),
        'methods': list(organize_by_method(records).keys()),
    }
    
    # Add parameter grid info
    param_info = extract_parameter_grid(records)
    metadata.update(param_info)
    
    # Add ramp constraint info if present
    if 'ramp_rates' in first:
        metadata['ramp_rates'] = first['ramp_rates']
    
    return metadata
