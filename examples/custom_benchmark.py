"""Example: Custom MongoDB Benchmark

This demonstrates how to create a custom workload using the Python API.
"""

from mdbpl import Benchmark, zipfian

def create_custom_benchmark():
    """Create a custom benchmark for an e-commerce order collection.
    
    This example shows how to write workloads for your own schema,
    not just YCSB data.
    """
    
    # Define your benchmark
    benchmark = Benchmark(
        name="order-lookup",
        database="ecommerce",
        collection="orders",
        description="Realistic e-commerce order access patterns"
    )
    
    # Setup distribution (10000 orders, hot orders accessed frequently)
    dist = zipfian(10000)
    
    # Define operations with weights
    
    @benchmark.operation(weight=70, name="lookup_by_id")
    def lookup_order(collection):
        """Look up order by ID - most common operation"""
        order_id = f"ORD-{dist.next():06d}"
        return collection.find_one({"order_id": order_id})
    
    @benchmark.operation(weight=20, name="find_by_status")
    def find_pending(collection):
        """Find pending orders for a user"""
        user_id = dist.next()
        return collection.find(
            {"user_id": user_id, "status": "pending"}
        ).limit(10)
    
    @benchmark.operation(weight=10, name="aggregate_totals")
    def user_order_total(collection):
        """Calculate total order value for a user"""
        user_id = dist.next()
        return collection.aggregate([
            {"$match": {"user_id": user_id, "status": "completed"}},
            {"$group": {
                "_id": "$user_id",
                "total": {"$sum": "$amount"},
                "count": {"$sum": 1}
            }}
        ])
    
    return benchmark


if __name__ == "__main__":
    # You can test your benchmark definition
    benchmark = create_custom_benchmark()
    
    print(f"Benchmark: {benchmark.name}")
    print(f"Description: {benchmark.description}")
    print(f"Target: {benchmark.database}.{benchmark.collection}")
    print(f"\nOperations:")
    for op in benchmark.operations:
        pct = (op.weight / benchmark.get_total_weight()) * 100
        print(f"  - {op.name}: {op.weight} ({pct:.1f}%)")
    
    # To run this benchmark:
    # docker-compose exec perflab mdbpl run --workload examples/custom_benchmark.py
