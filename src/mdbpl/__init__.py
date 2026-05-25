"""MongoDB Performance Lab — benchmarking platform for MongoDB query and index optimization."""

__version__ = "0.1.0"

from .workload import Benchmark, Operation
from .distributions import zipfian, uniform, latest

__all__ = [
    "Benchmark",
    "Operation",
    "zipfian",
    "uniform",
    "latest",
]
