"""DSL compiler - translates workload DSL to MongoDB operations."""

import random
import string
from typing import Any, Dict, List, Optional
from pymongo import MongoClient
from pymongo.collection import Collection

from .models import (
    WorkloadSpec,
    OperationSpec,
    FilterCondition,
    CompoundFilter,
    ValueSpec
)


class DSLCompiler:
    """Compiles DSL workload specifications into executable MongoDB operations."""
    
    def __init__(self, workload: WorkloadSpec):
        self.workload = workload
        self._counter = 0
        
    def compile_filter(self, filter_spec: FilterCondition | CompoundFilter, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Compile a filter specification into a MongoDB filter document.
        
        Args:
            filter_spec: Filter specification from DSL
            params: Runtime parameters for the operation
            
        Returns:
            MongoDB filter document
        """
        if isinstance(filter_spec, FilterCondition):
            return self._compile_simple_filter(filter_spec, params)
        elif isinstance(filter_spec, CompoundFilter):
            return self._compile_compound_filter(filter_spec, params)
        else:
            raise ValueError(f"Unknown filter type: {type(filter_spec)}")
    
    def _compile_simple_filter(self, condition: FilterCondition, params: Dict[str, Any]) -> Dict[str, Any]:
        """Compile a simple filter condition."""
        field = condition.field
        operator = condition.operator
        
        # Map DSL operators to MongoDB operators
        operator_map = {
            "eq": lambda v: v,
            "ne": lambda v: {"$ne": v},
            "gt": lambda v: {"$gt": v},
            "gte": lambda v: {"$gte": v},
            "lt": lambda v: {"$lt": v},
            "lte": lambda v: {"$lte": v},
            "in": lambda v: {"$in": v if isinstance(v, list) else [v]},
            "nin": lambda v: {"$nin": v if isinstance(v, list) else [v]},
            "regex": lambda v: {"$regex": v},
            "exists": lambda v: {"$exists": bool(v) if v is not None else True},
            "type": lambda v: {"$type": v},
            "all": lambda v: {"$all": v if isinstance(v, list) else [v]},
            "elemMatch": lambda v: {"$elemMatch": v},
            "size": lambda v: {"$size": int(v)}
        }
        
        if operator not in operator_map:
            raise ValueError(f"Unknown operator: {operator}")
        
        # Some operators don't require a value
        if operator in ["exists"] and condition.value is None:
            return {field: {"$exists": True}}
        
        value = self._resolve_value(condition.value, params)
        return {field: operator_map[operator](value)}
    
    def _compile_compound_filter(self, compound: CompoundFilter, params: Dict[str, Any]) -> Dict[str, Any]:
        """Compile a compound filter (AND/OR)."""
        if compound.and_:
            conditions = [self._compile_simple_filter(cond, params) for cond in compound.and_]
            return {"$and": conditions}
        elif compound.or_:
            conditions = [self._compile_simple_filter(cond, params) for cond in compound.or_]
            return {"$or": conditions}
        else:
            return {}
    
    def _resolve_value(self, value_spec: ValueSpec, params: Dict[str, Any]) -> Any:
        """Resolve a value specification to an actual value."""
        if value_spec.type == "param":
            if value_spec.param not in params:
                raise ValueError(f"Missing required parameter: {value_spec.param}")
            return params[value_spec.param]
        elif value_spec.type == "literal":
            return value_spec.value
        elif value_spec.type == "random":
            length = value_spec.length or 100
            return ''.join(random.choices(string.ascii_letters + string.digits, k=length))
        elif value_spec.type == "counter":
            self._counter += 1
            return (value_spec.start or 0) + self._counter
        else:
            raise ValueError(f"Unknown value type: {value_spec.type}")
    
    def compile_operation(
        self,
        operation: OperationSpec,
        collection: Collection,
        params: Dict[str, Any]
    ) -> Any:
        """
        Execute a compiled operation against MongoDB.
        
        Args:
            operation: Operation specification
            collection: MongoDB collection
            params: Runtime parameters
            
        Returns:
            Result of the operation
        """
        if operation.operation == "find":
            return self._execute_find(operation, collection, params)
        elif operation.operation == "update":
            return self._execute_update(operation, collection, params)
        elif operation.operation == "insert":
            return self._execute_insert(operation, collection, params)
        elif operation.operation == "delete":
            return self._execute_delete(operation, collection, params)
        elif operation.operation == "aggregate":
            return self._execute_aggregate(operation, collection, params)
        else:
            raise ValueError(f"Unknown operation: {operation.operation}")
    
    def _execute_find(self, op: OperationSpec, collection: Collection, params: Dict[str, Any]) -> Any:
        """Execute a find operation."""
        query_filter = self.compile_filter(op.filter, params) if op.filter else {}
        
        cursor = collection.find(query_filter, projection=op.projection)
        
        if op.sort:
            cursor = cursor.sort(list(op.sort.items()))
        
        if op.limit:
            cursor = cursor.limit(op.limit)
        
        return list(cursor)
    
    def _execute_update(self, op: OperationSpec, collection: Collection, params: Dict[str, Any]) -> Any:
        """Execute an update operation."""
        query_filter = self.compile_filter(op.filter, params) if op.filter else {}
        
        # Resolve values in update document
        update_doc = self._resolve_update_document(op.update, params)
        
        return collection.update_one(query_filter, update_doc)
    
    def _execute_insert(self, op: OperationSpec, collection: Collection, params: Dict[str, Any]) -> Any:
        """Execute an insert operation."""
        document = self._resolve_document(op.document, params)
        return collection.insert_one(document)
    
    def _execute_delete(self, op: OperationSpec, collection: Collection, params: Dict[str, Any]) -> Any:
        """Execute a delete operation."""
        query_filter = self.compile_filter(op.filter, params) if op.filter else {}
        return collection.delete_one(query_filter)
    
    def _execute_aggregate(self, op: OperationSpec, collection: Collection, params: Dict[str, Any]) -> Any:
        """Execute an aggregation pipeline."""
        pipeline = op.pipeline or []
        return list(collection.aggregate(pipeline))
    
    def _resolve_update_document(self, update: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        """Resolve value specs in update document."""
        result = {}
        for operator, fields in update.items():
            result[operator] = {}
            for field, value_spec in fields.items():
                if isinstance(value_spec, dict) and "type" in value_spec:
                    result[operator][field] = self._resolve_value(ValueSpec(**value_spec), params)
                else:
                    result[operator][field] = value_spec
        return result
    
    def _resolve_document(self, document: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        """Resolve value specs in document."""
        result = {}
        for field, value_spec in document.items():
            if isinstance(value_spec, dict) and "type" in value_spec:
                result[field] = self._resolve_value(ValueSpec(**value_spec), params)
            else:
                result[field] = value_spec
        return result
