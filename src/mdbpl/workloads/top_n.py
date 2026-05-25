"""Top-N aggregation workload — $sort → $limit with optional $match pre-filter."""

import pymongo
from ..workload import Benchmark
from typing import Optional


def create_top_n_benchmark(
    database: str = "perflab",
    collection: str = "usertable",
    record_count: int = 10000,
    sort_field: str = "score",
    sort_direction: str = "desc",
    limit: int = 100,
    match_field: Optional[str] = None,
    match_value: Optional[str] = None,
) -> Benchmark:
    """Create a top-N aggregation benchmark.

    Pipeline: [$match (optional)] → $sort → $limit

    Index optimization story:
      Without index on sort_field: MongoDB sorts the entire collection in memory.
      With index on sort_field:    MongoDB reads the top N directly from the index.

    Args:
        database:       MongoDB database name
        collection:     MongoDB collection name
        record_count:   Number of records (unused directly, kept for API consistency)
        sort_field:     Field to sort on. Default: score.
        sort_direction: Sort order: desc | asc. Default: desc.
        limit:          Number of documents to return. Default: 100.
        match_field:    Optional field to pre-filter on before sorting.
        match_value:    Value to match on match_field. Parsed as int if possible.

    Example:
        mdbpl run --workload top-n --sort-field score --limit 100
        mdbpl run --workload top-n --sort-field score --match-field status --match-value active
    """
    direction = pymongo.DESCENDING if sort_direction == "desc" else pymongo.ASCENDING

    desc = f"Top-{limit} by {sort_field} ({sort_direction})"
    if match_field:
        desc += f", filtered by {match_field}={match_value}"

    benchmark = Benchmark(
        name="top-n",
        database=database,
        collection=collection,
        description=desc,
    )

    # Pre-parse match_value once
    parsed_match_value: object = match_value
    if match_value is not None:
        try:
            parsed_match_value = int(match_value)
        except (ValueError, TypeError):
            pass

    @benchmark.operation(weight=100, name="top-n")
    def top_n(col):
        pipeline = []
        if match_field is not None:
            pipeline.append({"$match": {match_field: parsed_match_value}})
        pipeline.append({"$sort": {sort_field: direction}})
        pipeline.append({"$limit": limit})
        return list(col.aggregate(pipeline))

    return benchmark
