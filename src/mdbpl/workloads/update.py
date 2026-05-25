"""Update workload — targeted in-place document updates."""

from ..workload import Benchmark
from ..distributions import uniform, zipfian
import random
import string
from typing import List, Optional


def _filter_value(field: str, raw: int) -> object:
    """Convert distribution integer to the right filter value for a field."""
    if field == "_id":
        return f"user{raw:010d}"
    return raw


def create_update_benchmark(
    database: str = "perflab",
    collection: str = "usertable",
    record_count: int = 10000,
    filter_field: str = "_id",
    update_fields: Optional[List[str]] = None,
    distribution: str = "uniform",
) -> Benchmark:
    """Create an update benchmark.

    Args:
        database:      MongoDB database name
        collection:    MongoDB collection name
        record_count:  Number of records (bounds distribution range)
        filter_field:  Field used to locate the document. Default: _id.
                       _id uses YCSB format: user0000000000.
                       Other fields match on integer values 0..record_count-1.
        update_fields: Fields to overwrite on each update. Default: ["field0"].
        distribution:  Key access pattern: uniform | zipfian.

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
        filter_val = _filter_value(filter_field, dist.next())
        new_vals = {
            f: "".join(random.choices(string.ascii_lowercase + string.digits, k=20))
            for f in update_fields
        }
        col.update_one({filter_field: filter_val}, {"$set": new_vals})

    return benchmark
