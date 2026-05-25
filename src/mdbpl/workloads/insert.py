"""Insert workload — pure document inserts with configurable fields and batch size."""

from ..workload import Benchmark
from ..distributions import uniform, zipfian
import random
import string
from typing import List, Optional


def _random_value(field: str, record_count: int) -> object:
    """Generate a random value appropriate to the field name."""
    name = field.lower()
    if name == "score" or name in ("rating", "rank", "count", "quantity", "age"):
        return random.randint(0, record_count - 1)
    if any(k in name for k in ("amount", "price", "value", "total", "cost")):
        return round(random.uniform(1.0, 1000.0), 2)
    # Default: short random string (readable, low storage overhead)
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=20))


def create_insert_benchmark(
    database: str = "perflab",
    collection: str = "usertable",
    record_count: int = 10000,
    fields: Optional[List[str]] = None,
    batch_size: int = 1,
) -> Benchmark:
    """Create a pure-insert benchmark.

    Args:
        database:     MongoDB database name
        collection:   MongoDB collection name
        record_count: Used to bound numeric field values
        fields:       Fields to include in each inserted document.
                      Defaults to ["field0", "field1", "field2"].
        batch_size:   Documents per operation. 1 = insert_one, >1 = insert_many.

    Example:
        mdbpl run --workload insert --fields field0,field1,score --batch-size 5 --threads 4
    """
    if fields is None:
        fields = ["field0", "field1", "field2"]

    benchmark = Benchmark(
        name="insert",
        database=database,
        collection=collection,
        description=(
            f"Pure insert — {batch_size} doc(s)/op, "
            f"fields: {','.join(fields)}"
        ),
    )

    @benchmark.operation(weight=100, name="insert")
    def insert_docs(col):
        docs = [
            {f: _random_value(f, record_count) for f in fields}
            for _ in range(batch_size)
        ]
        if batch_size == 1:
            col.insert_one(docs[0])
        else:
            col.insert_many(docs)

    return benchmark
