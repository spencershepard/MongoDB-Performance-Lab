"""Built-in benchmark workloads.

Each workload is a factory function returning a configured Benchmark.
The REGISTRY maps CLI workload names to their factory functions.
"""

from .range_scan import create_range_scan_benchmark
from .insert import create_insert_benchmark
from .update import create_update_benchmark
from .point_read import create_point_read_benchmark
from .mixed import create_mixed_benchmark
from .top_n import create_top_n_benchmark
from .group_by import create_group_by_benchmark

__all__ = [
    "create_range_scan_benchmark",
    "create_insert_benchmark",
    "create_update_benchmark",
    "create_point_read_benchmark",
    "create_mixed_benchmark",
    "create_top_n_benchmark",
    "create_group_by_benchmark",
    "REGISTRY",
]

# Maps CLI workload name → factory function.
# All factories accept (database, collection, record_count) as a base,
# plus workload-specific keyword arguments.
REGISTRY = {
    "insert":      create_insert_benchmark,
    "update":      create_update_benchmark,
    "point-read":  create_point_read_benchmark,
    "range-scan":  create_range_scan_benchmark,
    "mixed":       create_mixed_benchmark,
    "top-n":       create_top_n_benchmark,
    "group-by":    create_group_by_benchmark,
}
