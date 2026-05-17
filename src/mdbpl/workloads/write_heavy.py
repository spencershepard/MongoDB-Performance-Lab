"""YCSB Workload E - Write Heavy

10% read operations, 90% update operations with Zipfian distribution.
Updates multiple fields per operation.
This models write-intensive scenarios:
- Logging systems
- Data ingestion pipelines
- Real-time updates
- Session management
"""

from ..workload import Benchmark
from ..distributions import zipfian
import random
import string


def create_write_heavy_benchmark(
    database: str = "perflab",
    collection: str = "usertable",
    record_count: int = 10000
) -> Benchmark:
    """Create a write-heavy benchmark (10% read, 90% update).
    
    Args:
        database: MongoDB database name
        collection: MongoDB collection name
        record_count: Number of records in the collection
        
    Returns:
        Configured Benchmark instance
        
    Example:
        >>> benchmark = create_write_heavy_benchmark()
        >>> # benchmark has 10% reads, 90% updates (multi-field)
        >>> # Run it with: mdbpl run --workload write-heavy
    """
    
    benchmark = Benchmark(
        name="write-heavy",
        database=database,
        collection=collection,
        description="YCSB Workload E - 10% reads, 90% updates with zipfian distribution"
    )
    
    # Setup Zipfian distribution for 80/20 access pattern
    dist = zipfian(record_count)
    
    @benchmark.operation(weight=10, name="read")
    def point_read(collection):
        """Point read query by _id with field projection."""
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
    
    @benchmark.operation(weight=90, name="update-many-fields")
    def update_many_fields(collection):
        """Update multiple fields with new random data."""
        user_id = f"user{dist.next()}"
        
        # Generate random 100-character strings for each field (matching YCSB format)
        update_doc = {}
        for i in range(7):  # Update fields 0-6
            update_doc[f"field{i}"] = ''.join(random.choices(
                string.ascii_letters + string.digits,
                k=100
            ))
        
        return collection.update_one(
            {"_id": user_id},
            {"$set": update_doc}
        )
    
    return benchmark


# Convenience: Allow direct execution for testing
if __name__ == "__main__":
    benchmark = create_write_heavy_benchmark()
    print(f"Benchmark: {benchmark.name}")
    print(f"Description: {benchmark.description}")
    print(f"Operations: {benchmark.operations}")
    print(f"Total weight: {benchmark.get_total_weight()}")
