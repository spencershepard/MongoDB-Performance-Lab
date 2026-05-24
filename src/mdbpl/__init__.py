"""MongoDB Performance Lab - YCSB-inspired benchmarking platform."""

__version__ = "0.1.0"

# Python Workload API (new simplified approach)
from .workload import Benchmark, Operation
from .distributions import zipfian, uniform, latest

# Built-in workload factories
from .workloads import (
    create_read_heavy_benchmark,
    create_balanced_benchmark,
    create_write_heavy_benchmark,
    create_range_scan_benchmark
)

__all__ = [
    # Core API
    "Benchmark",
    "Operation",
    # Distributions
    "zipfian",
    "uniform",
    "latest",
    # Built-in workloads
    "create_read_heavy_benchmark",
    "create_balanced_benchmark",
    "create_write_heavy_benchmark",
    "create_range_scan_benchmark",
]
