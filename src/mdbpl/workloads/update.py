"""Update workload — targeted in-place document updates."""

import random
import string
from typing import List, Optional

from ..workload import Benchmark
from ..distributions import uniform, zipfian


def create_update_benchmark(
    database: str = "perflab",
    collection: str = "usertable",
    record_count: int = 10000,
    filter_field: str = "_id",
    update_fields: Optional[List[str]] = None,
    distribution: str = "uniform",
    id_pool: Optional[List] = None,
) -> Benchmark:
    """Create an update benchmark.

    Args:
        database:      MongoDB database name
        collection:    MongoDB collection name
        record_count:  Number of records (bounds distribution range)
        filter_field:  Field used to locate the document. Default: _id.
        update_fields: Fields to overwrite on each update. Default: ["field0"].
        distribution:  Key access pattern: uniform | zipfian.
        id_pool:       Pre-sampled list of real _id values (ObjectIds). When
                       provided and filter_field=="_id", lookups use this pool
                       instead of generating YCSB-format strings.

    Example:
        mdbpl run --workload update --filter-field _id --update-fields field0,field1
    """
    if update_fields is None:
        update_fields = ["field0"]

    dist_fn = zipfian if distribution == "zipfian" else uniform
    dist = dist_fn(record_count)

    benchmark = Benchmark(
        name="update",
        database=database,
        collection=collection,
        description=(
            f"Update — filter on {filter_field}, "
            f"set {','.join(update_fields)}, {distribution} distribution"
        ),
    )

    @benchmark.operation(weight=100, name="update")
    def update_doc(col):
        if id_pool and filter_field == "_id":
            filter_val = random.choice(id_pool)
        elif filter_field == "_id":
            raw = dist.next()
            filter_val = f"user{raw:010d}"  # backward compat: YCSB string _id
        else:
            filter_val = dist.next()
        new_vals = {
            f: "".join(random.choices(string.ascii_lowercase + string.digits, k=20))
            for f in update_fields
        }
        col.update_one({filter_field: filter_val}, {"$set": new_vals})

    return benchmark
