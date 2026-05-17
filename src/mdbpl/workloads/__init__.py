"""Built-in benchmark workloads.

This package contains pre-defined workloads based on YCSB patterns.
Each workload is provided as a factory function that returns a configured Benchmark.
"""

from .read_heavy import create_read_heavy_benchmark
from .balanced import create_balanced_benchmark
from .write_heavy import create_write_heavy_benchmark
from .range_scan import create_range_scan_benchmark

__all__ = [
    'create_read_heavy_benchmark',
    'create_balanced_benchmark',
    'create_write_heavy_benchmark',
    'create_range_scan_benchmark',
]
