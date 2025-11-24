"""Visualization utilities for benchmark analysis.

Generates publication-quality figures using matplotlib and seaborn.
All functions save figures to disk and return the figure object.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple
import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd
import numpy as np


# Set consistent style
plt.style.use('seaborn-v0_8-darkgrid')
sns.set_palette("husl")


def plot_objective_diff_heatmaps(
    df: pd.DataFrame,
    param1_name: str,
    param2_name: str,
    output_path: Path | str,
    title_prefix: str = "",
    vmax: Optional[float] = None,
) -> dict:
    """Generate separate objective difference heatmap files for each Pyomo method.
    
    Creates individual PNG files for each method for better scalability.
    Cell annotations show: scipy_obj / pyomo_obj
    Color represents percentage difference.
    
    Args:
        df: DataFrame with columns: param1, param2, method, pct_diff, obj_scipy, obj_pyomo
        param1_name: Name of first parameter
        param2_name: Name of second parameter
        output_path: Base path for saving figures (will add method suffix)
        title_prefix: Optional prefix for title
        vmax: Optional maximum value for color scale
        
    Returns:
        Dict mapping method name to saved file path
    """
    # Get all unique Pyomo methods dynamically
    unique_methods = df['method'].unique()
    
    # Create pivot tables for each method - both for coloring and annotation
    methods_data = []
    for method_key in unique_methods:
        df_method = df[df['method'] == method_key].copy()
        if len(df_method) == 0:
            continue
            
        # Create pivot for coloring (percentage difference)
        pivot = df_method.pivot(index='param2', columns='param1', values='pct_diff')
        
        # Create pivots for annotation values
        scipy_vals = df_method.pivot(index='param2', columns='param1', values='obj_scipy')
        pyomo_vals = df_method.pivot(index='param2', columns='param1', values='obj_pyomo')
        
        # Build annotation dataframe with labels
        annot = pd.DataFrame(index=scipy_vals.index, columns=scipy_vals.columns)
        for idx in scipy_vals.index:
            for col in scipy_vals.columns:
                s_val = scipy_vals.loc[idx, col]
                p_val = pyomo_vals.loc[idx, col]
                if pd.notna(s_val) and pd.notna(p_val):
                    annot.loc[idx, col] = f"Scipy: {s_val:.1f}\nPyomo: {p_val:.1f}"
                else:
                    annot.loc[idx, col] = ""
        
        # Format method name for display (capitalize first letter)
        method_name = method_key.upper() if len(method_key) <= 3 else method_key.capitalize()
        methods_data.append((method_key, method_name, pivot, annot))
    
    if not methods_data:
        return {}
    
    # Compute value range (ignore NaNs) - shared across all methods for consistent coloring
    all_vals = []
    for _, _, pivot, _ in methods_data:
        all_vals.append(pivot.values.flatten())
    all_vals = np.concatenate(all_vals)
    all_vals = all_vals[~np.isnan(all_vals)]
    
    if all_vals.size == 0:
        return {}
    
    data_min = float(np.min(all_vals))
    data_max = float(np.max(all_vals))
    
    # Decide colormap & centering: diverging only if both signs present
    mixed_signs = data_min < 0 < data_max
    if vmax is None:
        if mixed_signs:
            vmax = max(abs(data_min), abs(data_max))
            vmin = -vmax
            center = 0
            cmap = 'RdYlGn_r'
        else:
            # Single-sided (all negative or all positive)
            # Use Blues_r: smaller (better) = white, larger (worse) = dark blue
            vmin = data_min
            vmax = data_max
            center = None
            cmap = 'Blues_r'
    else:
        # User supplied vmax; derive vmin
        if mixed_signs:
            vmin = -vmax
            center = 0
            cmap = 'RdYlGn_r'
        else:
            vmin = data_min
            center = None
            cmap = 'Blues' if data_max <= 0 else 'YlOrRd'
    
    # Convert output_path to Path and get base directory and stem
    output_path = Path(output_path)
    output_dir = output_path.parent
    base_stem = output_path.stem
    
    saved_files = {}
    
    # Create separate figure for each method
    for method_key, method_name, pivot, annot in methods_data:
        fig, ax = plt.subplots(figsize=(10, 7))
        mask = pivot.isna()
        im = sns.heatmap(
            pivot,
            annot=annot,
            fmt='',
            cmap=cmap,
            center=center,
            vmin=vmin,
            vmax=vmax,
            cbar=True,
            ax=ax,
            linewidths=0.5,
            linecolor='gray',
            mask=mask,
            cbar_kws={'label': '% Difference vs Scipy', 'shrink': 0.8},
            annot_kws={'fontsize': 9}
        )
        title = f'{title_prefix}{method_name} Objective Difference\n(Cells show drying time in hr for Scipy and Pyomo)'
        ax.set_title(title, fontsize=13, fontweight='bold')
        ax.set_xlabel(param1_name, fontsize=11)
        ax.set_ylabel(param2_name, fontsize=11)
        
        plt.tight_layout()
        
        # Save with descriptive filename
        save_path = output_dir / f"{base_stem}_{method_key}.png"
        fig.savefig(save_path, dpi=300, bbox_inches='tight')
        plt.close(fig)
        
        saved_files[method_name] = save_path
    
    return saved_files


def plot_speedup_heatmaps(
    df: pd.DataFrame,
    param1_name: str,
    param2_name: str,
    output_path: Path | str,
    title_prefix: str = "",
) -> dict:
    """Generate separate speedup heatmap files for each Pyomo method.
    
    Creates individual PNG files for each method for better scalability.
    Cell annotations show: scipy_time / pyomo_time
    Color represents speedup factor.
    
    Args:
        df: DataFrame with columns: param1, param2, method, speedup, wall_time_scipy, wall_time_pyomo
        param1_name: Name of first parameter
        param2_name: Name of second parameter
        output_path: Base path for saving figures (will add method suffix)
        title_prefix: Optional prefix for title
        
    Returns:
        Dict mapping method name to saved file path
    """
    # Get all unique Pyomo methods dynamically
    unique_methods = df['method'].unique()
    
    # Create pivot tables for each method - both for coloring and annotation
    methods_data = []
    for method_key in unique_methods:
        df_method = df[df['method'] == method_key].copy()
        if len(df_method) == 0:
            continue
            
        # Create pivot for coloring (speedup factor)
        pivot = df_method.pivot(index='param2', columns='param1', values='speedup')
        
        # Create pivots for annotation values (wall times)
        scipy_time = df_method.pivot(index='param2', columns='param1', values='wall_time_scipy')
        pyomo_time = df_method.pivot(index='param2', columns='param1', values='wall_time_pyomo')
        
        # Build annotation dataframe with labels and units
        annot = pd.DataFrame(index=scipy_time.index, columns=scipy_time.columns)
        for idx in scipy_time.index:
            for col in scipy_time.columns:
                s_val = scipy_time.loc[idx, col]
                p_val = pyomo_time.loc[idx, col]
                if pd.notna(s_val) and pd.notna(p_val):
                    annot.loc[idx, col] = f"Scipy: {s_val:.2f} s\nPyomo: {p_val:.2f} s"
                else:
                    annot.loc[idx, col] = ""
        
        # Format method name for display (capitalize first letter)
        method_name = method_key.upper() if len(method_key) <= 3 else method_key.capitalize()
        methods_data.append((method_key, method_name, pivot, annot))
    
    if not methods_data:
        return {}
    
    # Compute global min/max ignoring NaNs - shared across all methods for consistent coloring
    all_vals = []
    for _, _, pivot, _ in methods_data:
        all_vals.append(pivot.values.flatten())
    all_vals = np.concatenate(all_vals)
    all_vals = all_vals[~np.isnan(all_vals)]
    
    if all_vals.size == 0:
        return {}
    
    vmin = float(np.min(all_vals))
    vmax = float(np.max(all_vals))
    
    # Convert output_path to Path and get base directory and stem
    output_path = Path(output_path)
    output_dir = output_path.parent
    base_stem = output_path.stem
    
    saved_files = {}
    
    # Create separate figure for each method
    for method_key, method_name, pivot, annot in methods_data:
        fig, ax = plt.subplots(figsize=(10, 7))
        mask = pivot.isna()
        im = sns.heatmap(
            pivot,
            annot=annot,
            fmt='',
            cmap='YlOrRd',
            vmin=vmin,
            vmax=vmax,
            cbar=True,
            ax=ax,
            linewidths=0.5,
            linecolor='gray',
            mask=mask,
            cbar_kws={'label': 'Speedup vs Scipy (×)', 'shrink': 0.8},
            annot_kws={'fontsize': 9}
        )
        title = f'{title_prefix}{method_name} Speedup\n(Cells show wall time for Scipy and Pyomo)'
        ax.set_title(title, fontsize=13, fontweight='bold')
        ax.set_xlabel(param1_name, fontsize=11)
        ax.set_ylabel(param2_name, fontsize=11)
        
        plt.tight_layout()
        
        # Save with descriptive filename
        save_path = output_dir / f"{base_stem}_{method_key}.png"
        fig.savefig(save_path, dpi=300, bbox_inches='tight')
        plt.close(fig)
        
        saved_files[method_name] = save_path
    
    return saved_files


def plot_trajectory_comparison(
    traj_scipy: Optional[np.ndarray],
    traj_pyomo: dict[str, np.ndarray],
    output_path: Path | str,
    task: str,
    param_str: str = "",
) -> dict:
    """Plot control trajectories comparing scipy baseline with Pyomo methods.
    
    Creates separate figures for each variable for better scalability.
    Trajectory columns: [time, Tsub, Tbot, Tsh, Pch, flux, frac_dried]
    
    Args:
        traj_scipy: Scipy trajectory (N x 7)
        traj_pyomo: Dict mapping method name to trajectory array (N x 7)
                    e.g., {'fd': traj_fd, 'colloc': traj_colloc}
        output_path: Base path for saving figures (will add suffixes)
        task: Task type ('Tsh', 'Pch', or 'both')
        param_str: String describing parameters for title
        
    Returns:
        Dict mapping variable name to saved file path
    """
    # Determine which variables to plot based on task
    if task.lower() == 'both':
        plot_vars = [
            (3, 'Tsh', '°C', 'shelf_temperature'),
            (4, 'Pch', 'mTorr', 'chamber_pressure'),
            (6, 'Fraction Dried', '', 'dried_fraction'),
        ]
    elif task.lower() == 'tsh':
        plot_vars = [
            (3, 'Tsh', '°C', 'shelf_temperature'),
            (6, 'Fraction Dried', '', 'dried_fraction'),
        ]
    elif task.lower() == 'pch':
        plot_vars = [
            (4, 'Pch', 'mTorr', 'chamber_pressure'),
            (6, 'Fraction Dried', '', 'dried_fraction'),
        ]
    else:
        raise ValueError(f"Unknown task: {task}")
    
    # Convert output_path to Path and get base directory and stem
    output_path = Path(output_path)
    output_dir = output_path.parent
    base_stem = output_path.stem
    
    # Line styles for different methods (cycle if more methods than styles)
    line_styles = ['--', '-.', ':', (0, (3, 1, 1, 1)), (0, (5, 2, 1, 2))]
    
    saved_files = {}
    
    # Create separate figure for each variable
    for col_idx, var_name, unit, file_suffix in plot_vars:
        fig, ax = plt.subplots(figsize=(10, 6))
        
        # Scipy baseline (always first, solid line)
        if traj_scipy is not None and len(traj_scipy) > 0:
            ax.plot(traj_scipy[:, 0], traj_scipy[:, col_idx], 
                   '-', label='Scipy', linewidth=2.5, alpha=0.7, color='black')
        
        # Pyomo methods (dynamic)
        for idx, (method_key, traj) in enumerate(traj_pyomo.items()):
            if traj is not None and len(traj) > 0:
                # Format method name for display
                method_name = method_key.upper() if len(method_key) <= 3 else method_key.capitalize()
                # Cycle through line styles
                linestyle = line_styles[idx % len(line_styles)]
                ax.plot(traj[:, 0], traj[:, col_idx],
                       linestyle, label=method_name, linewidth=2, alpha=0.8, color=f'C{idx}')
        
        ax.set_xlabel('Time (hr)', fontsize=12)
        ylabel = f'{var_name} ({unit})' if unit else var_name
        ax.set_ylabel(ylabel, fontsize=12)
        ax.set_title(f'{var_name} Comparison {param_str}', fontsize=13, fontweight='bold')
        ax.legend(loc='best', framealpha=0.9, fontsize=11)
        ax.grid(True, alpha=0.3, linestyle='--')
        
        plt.tight_layout()
        
        # Save with descriptive filename
        save_path = output_dir / f"{base_stem}_{file_suffix}.png"
        fig.savefig(save_path, dpi=300, bbox_inches='tight')
        plt.close(fig)
        
        saved_files[var_name] = save_path
    
    return saved_files


def plot_ramp_constraints(
    traj_scipy: Optional[np.ndarray],
    traj_pyomo: dict[str, np.ndarray],
    output_path: Path | str,
    task: str,
    param_str: str = "",
    max_ramp_rate_Tsh: Optional[float] = None,
    max_ramp_rate_Pch: Optional[float] = None,
) -> plt.Figure:
    """Plot control variable ramp rates to visualize constraint adherence.
    
    Shows the rate of change (derivative) of control variables to highlight
    whether ramp rate constraints are being respected.
    Trajectory columns: [time, Tsub, Tbot, Tsh, Pch, flux, frac_dried]
    
    Args:
        traj_scipy: Scipy trajectory (N x 7)
        traj_pyomo: Dict mapping method name to trajectory array (N x 7)
                    e.g., {'fd': traj_fd, 'colloc': traj_colloc}
        output_path: Where to save figure
        task: Task type ('Tsh', 'Pch', or 'both')
        param_str: String describing parameters for title
        max_ramp_rate_Tsh: Maximum allowed Tsh ramp rate (°C/hr), None if no constraint
        max_ramp_rate_Pch: Maximum allowed Pch ramp rate (Torr/hr), None if no constraint
        
    Returns:
        Figure object
    """
    # Determine which control variables to plot
    if task.lower() == 'both':
        control_vars = [
            (3, 'Tsh', '°C/hr', max_ramp_rate_Tsh),
            (4, 'Pch', 'Torr/hr', max_ramp_rate_Pch * 1000 if max_ramp_rate_Pch else None),  # Convert to mTorr/hr
        ]
        fig, axes = plt.subplots(2, 1, figsize=(10, 8))
        axes = [axes] if not isinstance(axes, np.ndarray) else axes
    elif task.lower() == 'tsh':
        control_vars = [(3, 'Tsh', '°C/hr', max_ramp_rate_Tsh)]
        fig, axes = plt.subplots(1, 1, figsize=(10, 5))
        axes = [axes]
    elif task.lower() == 'pch':
        control_vars = [(4, 'Pch', 'Torr/hr', max_ramp_rate_Pch * 1000 if max_ramp_rate_Pch else None)]  # Convert to mTorr/hr
        fig, axes = plt.subplots(1, 1, figsize=(10, 5))
        axes = [axes]
    else:
        raise ValueError(f"Unknown task: {task}")
    
    # Helper function to compute ramp rate (derivative)
    def compute_ramp_rate(traj: np.ndarray, col_idx: int) -> Tuple[np.ndarray, np.ndarray]:
        """Compute d(var)/dt using central differences."""
        time = traj[:, 0]
        var = traj[:, col_idx]
        # Use numpy gradient for smooth derivative estimation
        ramp = np.gradient(var, time)
        return time, ramp
    
    # Line styles for different methods (cycle if more methods than styles)
    line_styles = ['--', '-.', ':', (0, (3, 1, 1, 1)), (0, (5, 2, 1, 2))]
    
    # Plot ramp rates for each control variable
    for ax, (col_idx, var_name, unit, max_ramp) in zip(axes, control_vars):
        # Scipy baseline (always first, solid line)
        if traj_scipy is not None and len(traj_scipy) > 0:
            time, ramp = compute_ramp_rate(traj_scipy, col_idx)
            ax.plot(time, ramp, '-', label='Scipy', linewidth=2.5, alpha=0.7, color='black')
        
        # Pyomo methods (dynamic)
        for idx, (method_key, traj) in enumerate(traj_pyomo.items()):
            if traj is not None and len(traj) > 0:
                time, ramp = compute_ramp_rate(traj, col_idx)
                # Format method name for display
                method_name = method_key.upper() if len(method_key) <= 3 else method_key.capitalize()
                # Cycle through line styles
                linestyle = line_styles[idx % len(line_styles)]
                ax.plot(time, ramp, linestyle, label=method_name, linewidth=2, alpha=0.8, color=f'C{idx}')
        
        # Add constraint boundaries (only if constraint exists)
        if max_ramp is not None:
            ax.axhline(max_ramp, color='red', linestyle=':', linewidth=2, 
                      label=f'Constraint: ±{max_ramp} {unit}', alpha=0.7)
            ax.axhline(-max_ramp, color='red', linestyle=':', linewidth=2, alpha=0.7)
        else:
            # Add note that there's no constraint
            ax.text(0.02, 0.98, 'No ramp constraint', transform=ax.transAxes,
                   fontsize=9, verticalalignment='top', bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
        ax.axhline(0, color='gray', linestyle='-', linewidth=0.5, alpha=0.5)
        
        ax.set_xlabel('Time (hr)', fontsize=12)
        ax.set_ylabel(f'd({var_name})/dt ({unit})', fontsize=12)
        ax.set_title(f'{var_name} Ramp Rate {param_str}', fontsize=13, fontweight='bold')
        ax.legend(loc='best', framealpha=0.9, fontsize=10)
        ax.grid(True, alpha=0.3, linestyle='--')
    
    plt.tight_layout()
    fig.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close(fig)
    
    return fig


def create_comparison_table(
    comparison_df: pd.DataFrame,
    output_path: Path | str,
) -> pd.DataFrame:
    """Create and save detailed comparison table.
    
    Args:
        comparison_df: DataFrame from analyze_benchmark.compute_objective_differences
        output_path: Where to save CSV
        
    Returns:
        The comparison DataFrame (for display)
    """
    # Round numerical columns for readability
    display_df = comparison_df.copy()
    numeric_cols = ['obj_pyomo', 'obj_scipy', 'pct_diff', 
                   'wall_time_scipy', 'wall_time_pyomo', 'speedup']
    for col in numeric_cols:
        if col in display_df.columns:
            display_df[col] = display_df[col].round(3)
    
    # Save to CSV
    display_df.to_csv(output_path, index=False)
    
    return display_df


def plot_summary_barplot(
    summary_stats: dict,
    output_path: Path | str,
    metric: str = 'speedup',
) -> plt.Figure:
    """Create bar plot comparing methods on a metric.
    
    Dynamically adapts to the number of methods present.
    
    Args:
        summary_stats: Dict from analyze_benchmark.generate_summary_stats
        metric: Metric to plot ('speedup' or 'pct_diff')
        output_path: Where to save figure
        
    Returns:
        Figure object
    """
    methods = list(summary_stats.keys())
    means = [summary_stats[m][f'mean_{metric}'] for m in methods]
    stds = [summary_stats[m][f'std_{metric}'] for m in methods]
    
    # Dynamic sizing based on number of methods
    n_methods = len(methods)
    fig_width = max(6, 3 * n_methods)
    fig, ax = plt.subplots(figsize=(fig_width, 6))
    
    x_pos = np.arange(n_methods)
    bars = ax.bar(x_pos, means, yerr=stds, capsize=5, alpha=0.7)
    
    # Dynamic colors - use colormap to generate distinct colors
    colors = plt.cm.get_cmap('Set2')(np.linspace(0, 1, n_methods))
    for bar, color in zip(bars, colors):
        bar.set_color(color)
    
    ax.set_xticks(x_pos)
    ax.set_xticklabels([m.upper() for m in methods], fontsize=11)
    ax.set_ylabel(f'Mean {metric.capitalize()}', fontsize=12)
    ax.set_title(f'Method Comparison: {metric.capitalize()}', 
                fontsize=14, fontweight='bold')
    ax.grid(True, alpha=0.3, axis='y')
    
    plt.tight_layout()
    fig.savefig(output_path, dpi=300, bbox_inches='tight')
    
    return fig
