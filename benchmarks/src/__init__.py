"""
Benchmarks core modules package.

This package contains reusable Python modules for benchmark analysis:
- data_loader: Load and organize JSONL benchmark data
- visualization: Generate plots and heatmaps
- analyze_benchmark: Compute metrics and comparisons
- adapters: Interface adapters for different data sources
- scenarios: Benchmark scenario definitions
- schema: Data validation schemas
- paths: Centralized path resolution
"""

__version__ = "1.0.0"

# Expose key utilities at package level
from .data_loader import load_benchmark_jsonl, organize_by_method, extract_parameter_grid
from .paths import get_repo_root, get_results_dir, get_figures_dir

__all__ = [
    'load_benchmark_jsonl',
    'organize_by_method', 
    'extract_parameter_grid',
    'get_repo_root',
    'get_results_dir',
    'get_figures_dir',
]
