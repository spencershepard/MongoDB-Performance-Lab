"""Mixed workload — configurable read/write ratio over the same key space."""

from ..workload import Benchmark
from ..distributions import uniform, zipfian
import random
import string
from typing import List, Optional


def create_mixed_benchmark(
    database: str = "perflab",
    collection: str = "usertable",
    record_count: int = 10000,
    read_pct: int = 70,
    filter_field: str = "_id",
    update_fields: Optional[List[str]] = None,
    distribution: str = "uniform",
) -> Benchmark:
    """Create a mixed read/write benchmark.

    Args:
        database:      MongoDB database name
        collection:    MongoDB collection name
        record_count:  Number of records (bounds distribution range)
        read_pct:      Percentage of operations that are reads (0-100). Default: 70.
                       Remaining percentage are updates.
        filter_field:  Field used to locate documents for both reads and updates.
                       Default: _id (YCSB format). Others match on integer values.
        update_fields: Fields overwritten by update operations. Default: ["field0"].
        distribution:  Key access pattern: uniform | zipfian.

    Example:
        mdbpl run --workload mixed --read-pct 80 --filter-field _id --update-fields field0,field1
    """
    if update_fields is None:
        update_fields = ["field0"]

    write_pct = 100 - read_pct
    if write_pct <= 0:
        raise ValueError("read-pct must be < 100 to include write operations")
    if read_pct <= 0:
        raise ValueError("read-pct must be > 0 to include read operations")

    dist_fn = zipfian if distribution == "zipfian" else uniform
    dist = dist_fn(record_count)

    benchmark = Benchmark(
        name="mixed",
        database=database,
        collection=collection,
        description=(
            f"Mixed — {read_pct}% reads / {write_pct}% updates, "
            f"filter on {filter_field}, {distribution} distribution"
        ),
    )

    @benchmark.operation(weight=read_pct, name="read")
    def read_op(col):
        raw = dist.next()
        filter_val = f"user{raw:010d}" if filter_field == "_id" else raw
        return col.find_one({filter_field: filter_val})

    @benchmark.operation(weight=write_pct, name="update")
    def update_op(col):
        raw = dist.next()
        filter_val = f"user{raw:010d}" if filter_field == "_id" else raw
        new_vals = {
            f: "".join(random.choices(string.ascii_lowercase + string.digits, k=20))
            for f in update_fields
        }
        col.update_one({filter_field: filter_val}, {"$set": new_vals})

    return benchmark
