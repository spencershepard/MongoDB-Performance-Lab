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
    record_count: int = 10000
) -> Benchmark:
    """Create a range scan workload benchmark.
    
    Args:
        database: MongoDB database name
        collection: MongoDB collection name
        record_count: Number of records in the collection
        
    Returns:
        Configured Benchmark instance
        
    Example:
        >>> benchmark = create_range_scan_benchmark()
        >>> # benchmark has 80% range scans, 20% point reads
        >>> # Run it with: mdbpl run --workload range-scan
    """
    
    benchmark = Benchmark(
        name="range-scan",
        database=database,
        collection=collection,
        description="Range query workload - Tests index efficiency for range scans"
    )
    
    # Uniform distribution for generating query patterns
    dist = uniform(record_count)
    
    @benchmark.operation(weight=80, name="range-scan")
    def range_scan(collection):
        """Range query on numeric score field with sort and limit.
        
        Queries for documents where score is in a specific range, sorts by score,
        and returns 100 results. Without an index, this requires:
        1. Full COLLSCAN to find all matching documents  
        2. In-memory sort (expensive for large result sets)
        
        With an index on score, MongoDB can:
        1. Use IXSCAN to jump directly to the range start
        2. Traverse the sorted index (no in-memory sort needed)
        
        This is 10-100x faster with an index.
        """
        # Generate random range query on numeric score field
        # With 10k documents, score ranges from 0-9999
        range_start = dist.next()
        range_size = 2000  # Query for 2000 documents, return 100
        
        # Query with range filter, sort, and limit
        # This is the key pattern that benefits dramatically from indexing
        return list(collection.find(
            {
                "score": {
                    "$gte": range_start,
                    "$lt": range_start + range_size
                }
            },
            projection={
                "score": 1,
                "field0": 1,
                "field1": 1,
            }
        ).sort("score", 1).limit(100))  # Large limit to amplify sort cost
    
    @benchmark.operation(weight=20, name="point-read")
    def point_read(collection):
        """Point read query by _id."""
        user_id = f"user{dist.next()}"
        return collection.find_one(
            {"_id": user_id},
            projection={
                "field0": 1,
                "field1": 1,
                "field2": 1,
                "field3": 1,
                "field4": 1,
                "field5": 1,
                "field6": 1,
                "field7": 1,
                "field8": 1,
                "field9": 1
            }
        )
    
    return benchmark


# Convenience: Allow direct execution for testing
if __name__ == "__main__":
    benchmark = create_range_scan_benchmark()
    print(f"Benchmark: {benchmark.name}")
    print(f"Description: {benchmark.description}")
    print(f"Operations: {benchmark.operations}")
    print(f"Total weight: {benchmark.get_total_weight()}")
