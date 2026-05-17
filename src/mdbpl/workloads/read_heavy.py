"""YCSB Workload B - Read Heavy

95% read operations, 5% update operations with Zipfian distribution.
This models scenarios where data is read much more frequently than updated:
- Content delivery systems
- Product catalogs
- User profile lookups
- Reference data access
"""

from ..workload import Benchmark
from ..distributions import zipfian
import random
import string


def create_read_heavy_benchmark(
    database: str = "perflab",
    collection: str = "usertable",
    record_count: int = 10000
) -> Benchmark:
    """Create a read-heavy benchmark (YCSB Workload B).
    
    Args:
        database: MongoDB database name
        collection: MongoDB collection name
        record_count: Number of records in the collection
        
    Returns:
        Configured Benchmark instance
        
    Example:
        >>> benchmark = create_read_heavy_benchmark()
        >>> # benchmark has 95% reads, 5% updates
        >>> # Run it with: mdbpl run --workload read-heavy
    """
    
    benchmark = Benchmark(
        name="read-heavy",
        database=database,
        collection=collection,
        description="YCSB Workload B - 95% reads, 5% updates with zipfian distribution"
    )
    
    # Setup Zipfian distribution for 80/20 access pattern
    dist = zipfian(record_count)
    
    @benchmark.operation(weight=95, name="read")
    def point_read(collection):
        """Point read query by _id with field projection."""
        user_id = f"user{dist.next():010d}"
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
    
    @benchmark.operation(weight=5, name="update")
    def update_field(collection):
        """Update a random field with new random data."""
        user_id = f"user{dist.next():010d}"
        
        # Generate random 100-character string (matching YCSB format)
        random_value = ''.join(random.choices(
            string.ascii_letters + string.digits,
            k=100
        ))
        
        return collection.update_one(
            {"_id": user_id},
            {"$set": {"field0": random_value}}
        )
    
    return benchmark


# Convenience: Allow direct execution for testing
if __name__ == "__main__":
    benchmark = create_read_heavy_benchmark()
    print(f"Benchmark: {benchmark.name}")
    print(f"Description: {benchmark.description}")
    print(f"Operations: {benchmark.operations}")
    print(f"Total weight: {benchmark.get_total_weight()}")
