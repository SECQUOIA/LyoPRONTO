"""
Centralized path resolution for benchmarks infrastructure.

Eliminates hardcoded path strings and provides consistent access to:
- Repository root
- Results directories (versioned)
- Output subdirectories (raw, processed, figures)
"""

from pathlib import Path
from typing import Optional


def get_repo_root() -> Path:
    """
    Get the LyoPRONTO repository root directory.
    
    Returns:
        Path: Absolute path to repository root
    """
    # Start from this file's location (benchmarks/src/paths.py)
    # and navigate up two levels to repo root
    return Path(__file__).resolve().parent.parent.parent


def get_benchmarks_dir() -> Path:
    """
    Get the benchmarks directory.
    
    Returns:
        Path: Absolute path to benchmarks/
    """
    return get_repo_root() / "benchmarks"


def get_results_dir(version: Optional[str] = None) -> Path:
    """
    Get the results directory for a specific benchmark version.
    
    Args:
        version: Benchmark version (e.g., "test", "v1_baseline").
                If None, returns the base results/ directory.
    
    Returns:
        Path: Absolute path to benchmarks/results/ or benchmarks/results/<version>/
    """
    results_base = get_benchmarks_dir() / "results"
    if version is None:
        return results_base
    return results_base / version


def get_raw_dir(version: str) -> Path:
    """
    Get the raw data directory for a benchmark version.
    
    Args:
        version: Benchmark version (e.g., "test", "v1_baseline")
    
    Returns:
        Path: Absolute path to benchmarks/results/<version>/raw/
    """
    return get_results_dir(version) / "raw"


def get_processed_dir(version: str) -> Path:
    """
    Get the processed data directory for a benchmark version.
    
    Args:
        version: Benchmark version (e.g., "test", "v1_baseline")
    
    Returns:
        Path: Absolute path to benchmarks/results/<version>/processed/
    """
    return get_results_dir(version) / "processed"


def get_figures_dir(version: str, task: Optional[str] = None) -> Path:
    """
    Get the figures directory for a benchmark version and task.
    
    Args:
        version: Benchmark version (e.g., "test", "v1_baseline")
        task: Task type ("Tsh", "Pch", "both"). If None, returns base figures/ directory.
    
    Returns:
        Path: Absolute path to benchmarks/results/<version>/figures/ or
              benchmarks/results/<version>/figures/<task>/
    """
    figures_base = get_results_dir(version) / "figures"
    if task is None:
        return figures_base
    return figures_base / task


def ensure_dir(path: Path) -> Path:
    """
    Ensure a directory exists, creating it if necessary.
    
    Args:
        path: Directory path to ensure
    
    Returns:
        Path: The same path (for chaining)
    """
    path.mkdir(parents=True, exist_ok=True)
    return path
