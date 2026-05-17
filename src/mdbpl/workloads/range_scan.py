"""YCSB Range Scan Workload

80% range queries on score field (tests index efficiency)
20% point reads by _id

Tests whether proper indexes exist for range queries.
Without an index, range scans require full collection scans.
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
    
    # Uniform distribution (not zipfian) for range starts
    dist = uniform(record_count)
    
    @benchmark.operation(weight=80, name="range-scan")
    def range_scan(collection):
        """Range query on score field with sort and limit."""
        # Generate random range start point
        range_start = dist.next()
        
        # Find documents with score >= range_start, sorted, limited to 20
        return list(collection.find(
            {"score": {"$gte": range_start}},
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
        ).sort("score", 1).limit(20))
    
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
