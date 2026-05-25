"""Group-by aggregation workload — $match → $group → accumulate."""

from ..workload import Benchmark
from ..distributions import uniform
from typing import Optional


_VALID_ACCUMULATORS = ("count", "sum", "avg", "min", "max")


def create_group_by_benchmark(
    database: str = "perflab",
    collection: str = "usertable",
    record_count: int = 10000,
    match_field: str = "score",
    group_field: str = "field0",
    accumulator: str = "count",
    value_field: Optional[str] = None,
) -> Benchmark:
    """Create a group-by aggregation benchmark.

    Pipeline: $match (range on match_field) → $group → $sort

    Index optimization story:
      Without index on match_field: all documents reach $group (expensive).
      With index on match_field:    only the matched subset is aggregated.

    Args:
        database:     MongoDB database name
        collection:   MongoDB collection name
        record_count: Number of records (bounds the range match window)
        match_field:  Field to range-filter on before grouping. Default: score.
                      The match uses a sliding window of ~20% of record_count.
        group_field:  Field to group documents by. Default: field0.
        accumulator:  Aggregation function: count | sum | avg | min | max.
                      Default: count.
        value_field:  Field to accumulate for sum/avg/min/max.
                      Defaults to match_field when not specified.

    Example:
        mdbpl run --workload group-by --match-field score --group-field field0
        mdbpl run --workload group-by --match-field score --group-field field0 --accumulator sum --value-field score
    """
    if accumulator not in _VALID_ACCUMULATORS:
        raise ValueError(
            f"Invalid accumulator '{accumulator}'. "
            f"Choose from: {', '.join(_VALID_ACCUMULATORS)}"
        )

    dist = uniform(record_count)
    window = max(1, record_count // 5)  # match ~20% of the collection per query
    acc_target = value_field or match_field

    if accumulator == "count":
        acc_expr = {"$sum": 1}
    elif accumulator == "sum":
        acc_expr = {"$sum": f"${acc_target}"}
    elif accumulator == "avg":
        acc_expr = {"$avg": f"${acc_target}"}
    elif accumulator == "min":
        acc_expr = {"$min": f"${acc_target}"}
    else:  # max
        acc_expr = {"$max": f"${acc_target}"}

    benchmark = Benchmark(
        name="group-by",
        database=database,
        collection=collection,
        description=(
            f"Group-by — match on {match_field} (range), "
            f"group by {group_field}, {accumulator}"
            + (f"({acc_target})" if accumulator != "count" else "")
        ),
    )

    @benchmark.operation(weight=100, name="group-by")
    def group_by(col):
        start = dist.next()
        pipeline = [
            {"$match": {match_field: {"$gte": start, "$lt": start + window}}},
            {"$group": {"_id": f"${group_field}", "result": acc_expr}},
            {"$sort": {"result": -1}},
        ]
        return list(col.aggregate(pipeline))

    return benchmark
