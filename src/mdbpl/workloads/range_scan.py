"""YCSB Range Scan Workload

80% range queries on numeric score field (tests index efficiency)
20% point reads by _id

Tests whether proper indexes exist for range queries on numeric fields.
Without an index on score, range scans with sorting require:
1. Full collection scan to find all matches
2. In-memory sort of results (very expensive)
With an index, MongoDB can use the index for both filtering and sorting (10-100x faster).
"""

from ..workload import Benchmark
from ..distributions import uniform
import random


def create_range_scan_benchmark(
    database: str = "perflab",
    collection: str = "usertable",
    record_count: int = 10000,
    field: str = "score",
    range_size: int = 2000,
    sort_field: str = "score",
) -> Benchmark:
    """Create a range scan workload benchmark.

    80% range queries on a numeric field + 20% point reads by _id.

    Args:
        database:    MongoDB database name
        collection:  MongoDB collection name
        record_count: Number of records (bounds the distribution range)
        field:       Numeric field to range-query on. Default: score.
        range_size:  Width of each range query window. Default: 2000.
        sort_field:  Field to sort results on. Default: score.

    Example:
        mdbpl run --workload range-scan
        mdbpl run --workload range-scan --field score --range-size 1000
    """
    benchmark = Benchmark(
        name="range-scan",
        database=database,
        collection=collection,
        description=(
            f"Range scan — 80% range queries on {field} "
            f"(window={range_size}), 20% point reads"
        ),
    )

    dist = uniform(record_count)

    @benchmark.operation(weight=80, name="range-scan")
    def range_scan(col):
        range_start = dist.next()
        return list(
            col.find(
                {field: {"$gte": range_start, "$lt": range_start + range_size}},
                projection={field: 1, "field0": 1, "field1": 1},
            )
            .sort(sort_field, 1)
            .limit(100)
        )

    @benchmark.operation(weight=20, name="point-read")
    def point_read(col):
        user_id = f"user{dist.next():010d}"
        return col.find_one({"_id": user_id})

    return benchmark


# Convenience: Allow direct execution for testing
if __name__ == "__main__":
    benchmark = create_range_scan_benchmark()
    print(f"Benchmark: {benchmark.name}")
    print(f"Description: {benchmark.description}")
    print(f"Operations: {benchmark.operations}")
    print(f"Total weight: {benchmark.get_total_weight()}")
