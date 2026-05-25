"""Point-read workload — single document lookup by a configurable field."""

import random
from typing import List, Optional

from ..workload import Benchmark
from ..distributions import uniform, zipfian


def create_point_read_benchmark(
    database: str = "perflab",
    collection: str = "usertable",
    record_count: int = 10000,
    filter_field: str = "_id",
    distribution: str = "uniform",
    id_pool: Optional[List] = None,
) -> Benchmark:
    """Create a point-read benchmark.

    Args:
        database:     MongoDB database name
        collection:   MongoDB collection name
        record_count: Number of records (bounds distribution range)
        filter_field: Field to look up. Default: _id.
        distribution: Key access pattern: uniform | zipfian.
        id_pool:      Pre-sampled list of real _id values (ObjectIds). When
                      provided and filter_field=="_id", lookups use this pool
                      instead of generating YCSB-format strings.

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
        if id_pool and filter_field == "_id":
            filter_val = random.choice(id_pool)
        elif filter_field == "_id":
            raw = dist.next()
            filter_val = f"user{raw:010d}"  # backward compat: YCSB string _id
        else:
            filter_val = dist.next()
        return col.find_one({filter_field: filter_val})

    return benchmark
