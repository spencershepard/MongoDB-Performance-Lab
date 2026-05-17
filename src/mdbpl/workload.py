"""Python-based workload API for MongoDB Performance Lab.

This module provides a simple, Pythonic way to define benchmarks without DSL complexity.
Workloads are defined as Python functions with decorators, making them flexible and LLM-friendly.
"""

from dataclasses import dataclass
from typing import Callable, List, Optional, Any
from pymongo.collection import Collection


@dataclass
class Operation:
    """A single benchmark operation with its weight and execution function.
    
    Attributes:
        name: Human-readable operation name (e.g., "read", "update")
        weight: Relative frequency (e.g., 80 means 80% of operations)
        func: Function that takes a Collection and executes the operation
    """
    name: str
    weight: int
    func: Callable[[Collection], Any]


class Benchmark:
    """Main benchmark builder for defining workloads.
    
    Example:
        >>> from mdbpl import Benchmark, zipfian
        >>> 
        >>> benchmark = Benchmark(
        ...     name="read-heavy",
        ...     database="perflab",
        ...     collection="usertable",
        ...     description="95% reads, 5% updates"
        ... )
        >>> 
        >>> dist = zipfian(10000)
        >>> 
        >>> @benchmark.operation(weight=95, name="read")
        >>> def point_read(collection):
        ...     user_id = f"user{dist.next():010d}"
        ...     return collection.find_one({"_id": user_id})
        >>> 
        >>> @benchmark.operation(weight=5, name="update")
        >>> def update_field(collection):
        ...     user_id = f"user{dist.next():010d}"
        ...     return collection.update_one(
        ...         {"_id": user_id},
        ...         {"$set": {"field0": "new_value"}}
        ...     )
    """
    
    def __init__(
        self, 
        name: str, 
        database: str, 
        collection: str,
        description: str = ""
    ):
        """Initialize a new benchmark.
        
        Args:
            name: Unique benchmark identifier (e.g., "read-heavy")
            database: MongoDB database name
            collection: MongoDB collection name
            description: Human-readable description of what this benchmark tests
        """
        self.name = name
        self.database = database
        self.collection = collection
        self.description = description
        self.operations: List[Operation] = []
    
    def operation(self, weight: int = 1, name: Optional[str] = None):
        """Decorator to register an operation with this benchmark.
        
        Args:
            weight: Relative frequency of this operation (default: 1)
            name: Operation name (defaults to function name)
            
        Returns:
            Decorator function
            
        Example:
            >>> @benchmark.operation(weight=80, name="read")
            >>> def my_read_operation(collection):
            ...     return collection.find_one({"_id": "user123"})
        """
        def decorator(func: Callable[[Collection], Any]) -> Callable[[Collection], Any]:
            op_name = name or func.__name__
            self.operations.append(Operation(op_name, weight, func))
            return func
        return decorator
    
    def get_total_weight(self) -> int:
        """Calculate total weight of all operations."""
        return sum(op.weight for op in self.operations)
    
    def validate(self) -> bool:
        """Validate that the benchmark is properly configured.
        
        Returns:
            True if valid
            
        Raises:
            ValueError: If configuration is invalid
        """
        if not self.operations:
            raise ValueError(f"Benchmark '{self.name}' has no operations defined")
        
        if self.get_total_weight() == 0:
            raise ValueError(f"Benchmark '{self.name}' has zero total weight")
        
        return True
    
    def __repr__(self) -> str:
        ops_summary = ", ".join(f"{op.name}:{op.weight}" for op in self.operations)
        return f"Benchmark(name='{self.name}', operations=[{ops_summary}])"
