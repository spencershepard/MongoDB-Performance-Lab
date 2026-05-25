"""Point-read workload — single document lookup by a configurable field."""

from ..workload import Benchmark
from ..distributions import uniform, zipfian


def create_point_read_benchmark(
    database: str = "perflab",
    collection: str = "usertable",
    record_count: int = 10000,
    filter_field: str = "_id",
    distribution: str = "uniform",
) -> Benchmark:
    """Create a point-read benchmark.

    Args:
        database:     MongoDB database name
        collection:   MongoDB collection name
        record_count: Number of records (bounds distribution range)
        filter_field: Field to look up. Default: _id (YCSB format user0000000000).
                      Other fields match on integer values 0..record_count-1.
        distribution: Key access pattern: uniform | zipfian.

    Example:
        mdbpl run --workload point-read --filter-field _id --distribution zipfian
    """
    dist_fn = zipfian if distribution == "zipfian" else uniform
    dist = dist_fn(record_count)

    benchmark = Benchmark(
        name="point-read",
        database=database,
        collection=collection,
        description=f"Point read — lookup by {filter_field}, {distribution} distribution",
    )

    @benchmark.operation(weight=100, name="point-read")
    def point_read(col):
        raw = dist.next()
        filter_val = f"user{raw:010d}" if filter_field == "_id" else raw
        return col.find_one({filter_field: filter_val})

    return benchmark
