"""Workload executor - runs Python benchmark workloads and collects metrics."""

import time
import random
import math
import string
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.cursor import Cursor

from .workload import Benchmark


class ExplainCapturingCollection:
    """Wrapper around pymongo Collection that captures query info for explain sampling."""
    
    def __init__(self, collection: Collection):
        self.collection = collection
        self.last_query = None
        self.last_result_count = 0
    
    def find(self, filter=None, projection=None, **kwargs):
        """Wrap find() to capture query parameters."""
        # Capture query info for potential explain
        self.last_query = {
            'filter': filter or {},
            'projection': projection,
            'limit': kwargs.get('limit'),
            'sort': None  # Will be set by sort() call if chained
        }
        
        # Execute actual find
        cursor = self.collection.find(filter, projection, **kwargs)
        
        # Wrap cursor to capture result count
        return ExplainCapturingCursor(cursor, self)
    
    def find_one(self, filter=None, projection=None, **kwargs):
        """Wrap find_one() to capture query parameters."""
        self.last_query = {
            'filter': filter or {},
            'projection': projection,
            'limit': 1,
            'sort': None
        }
        
        result = self.collection.find_one(filter, projection, **kwargs)
        self.last_result_count = 1 if result else 0
        return result
    
    def update_one(self, filter, update, **kwargs):
        """Pass through update_one (no explain needed for writes)."""
        self.last_query = None  # No explain for writes
        return self.collection.update_one(filter, update, **kwargs)
    
    def update_many(self, filter, update, **kwargs):
        """Pass through update_many (no explain needed for writes)."""
        self.last_query = None
        return self.collection.update_many(filter, update, **kwargs)
    
    def insert_one(self, document, **kwargs):
        """Pass through insert_one (no explain needed for writes)."""
        self.last_query = None
        return self.collection.insert_one(document, **kwargs)
    
    def insert_many(self, documents, **kwargs):
        """Pass through insert_many (no explain needed for writes)."""
        self.last_query = None
        return self.collection.insert_many(documents, **kwargs)
    
    def aggregate(self, pipeline, **kwargs):
        """Pass through aggregate (complex explain, skip for now)."""
        self.last_query = None  # Could add aggregate explain support later
        return self.collection.aggregate(pipeline, **kwargs)
    
    def __getattr__(self, name):
        """Pass through any other methods to the underlying collection."""
        return getattr(self.collection, name)


class ExplainCapturingCursor:
    """Wrapper around pymongo Cursor that captures sort/limit and result count."""
    
    def __init__(self, cursor: Cursor, parent: ExplainCapturingCollection):
        self.cursor = cursor
        self.parent = parent
    
    def sort(self, key_or_list, direction=None):
        """Capture sort parameters."""
        if isinstance(key_or_list, str):
            # Single field sort: sort("field", 1)
            self.parent.last_query['sort'] = {key_or_list: direction}
        elif isinstance(key_or_list, list):
            # List of tuples: sort([("field1", 1), ("field2", -1)])
            self.parent.last_query['sort'] = dict(key_or_list)
        else:
            # Dict or other format
            self.parent.last_query['sort'] = key_or_list
        
        return ExplainCapturingCursor(self.cursor.sort(key_or_list, direction) if direction else self.cursor.sort(key_or_list), self.parent)
    
    def limit(self, n):
        """Capture limit parameter."""
        self.parent.last_query['limit'] = n
        return ExplainCapturingCursor(self.cursor.limit(n), self.parent)
    
    def skip(self, n):
        """Capture skip parameter."""
        if 'skip' not in self.parent.last_query:
            self.parent.last_query['skip'] = 0
        self.parent.last_query['skip'] = n
        return ExplainCapturingCursor(self.cursor.skip(n), self.parent)
    
    def __iter__(self):
        """Iterate through results and count them."""
        count = 0
        for doc in self.cursor:
            count += 1
            yield doc
        self.parent.last_result_count = count
    
    def __getattr__(self, name):
        """Pass through any other methods to the underlying cursor."""
        return getattr(self.cursor, name)


@dataclass
class OperationMetrics:
    """Metrics for a single operation execution."""
    operation_name: str
    operation_type: str
    latency_ms: float
    success: bool
    error: Optional[str] = None
    docs_examined: Optional[int] = None
    docs_returned: Optional[int] = None
    index_used: Optional[str] = None


@dataclass
class BenchmarkResult:
    """Results from a benchmark run."""
    workload_name: str
    duration_seconds: float
    total_operations: int
    successful_operations: int
    failed_operations: int
    operations_per_second: float
    
    # Per-operation type metrics
    operation_metrics: Dict[str, List[float]] = field(default_factory=dict)
    
    # Aggregated metrics
    latency_p50: float = 0.0
    latency_p95: float = 0.0
    latency_p99: float = 0.0
    
    # Explain metrics (for operations that support it)
    total_docs_examined: int = 0
    total_docs_returned: int = 0
    operations_with_explain: int = 0
    index_scans: int = 0  # Operations that used an index
    collection_scans: int = 0  # Operations that did full collection scan
    
    def add_operation(self, metrics: OperationMetrics):
        """Add metrics from a single operation."""
        if metrics.operation_name not in self.operation_metrics:
            self.operation_metrics[metrics.operation_name] = []
        self.operation_metrics[metrics.operation_name].append(metrics.latency_ms)
        
        # Track explain metrics if available
        if metrics.docs_examined is not None:
            self.total_docs_examined += metrics.docs_examined
            self.operations_with_explain += 1
        
        if metrics.docs_returned is not None:
            self.total_docs_returned += metrics.docs_returned
        
        # Classify scan type based on index usage (only if we have explain data)
        if metrics.docs_examined is not None:
            if metrics.index_used:
                self.index_scans += 1
            else:
                self.collection_scans += 1
    
    def calculate_percentiles(self):
        """Calculate latency percentiles across all operations."""
        all_latencies = []
        for latencies in self.operation_metrics.values():
            all_latencies.extend(latencies)
        
        if not all_latencies:
            return
        
        all_latencies.sort()
        n = len(all_latencies)
        
        self.latency_p50 = all_latencies[int(n * 0.50)] if n > 0 else 0.0
        self.latency_p95 = all_latencies[int(n * 0.95)] if n > 0 else 0.0
        self.latency_p99 = all_latencies[int(n * 0.99)] if n > 0 else 0.0
    
    def extrapolate_sampled_metrics(self):
        """
        Extrapolate sampled explain metrics to represent the full workload.
        
        Explain is run on ~10% of operations for performance reasons.
        This method scales up the sampled metrics to estimate total values.
        """
        if self.operations_with_explain > 0 and self.successful_operations > 0:
            # Calculate sampling ratio (actual vs sampled)
            sampling_ratio = self.successful_operations / self.operations_with_explain
            
            # Extrapolate docs examined and returned
            self.total_docs_examined = int(self.total_docs_examined * sampling_ratio)
            self.total_docs_returned = int(self.total_docs_returned * sampling_ratio)
            
            # Extrapolate scan counts
            self.index_scans = int(self.index_scans * sampling_ratio)
            self.collection_scans = int(self.collection_scans * sampling_ratio)


class WorkloadExecutor:
    """Executes Python Benchmark workloads, collecting performance metrics."""
    
    def __init__(self, workload: Benchmark, mongodb_uri: str, record_count: int):
        """
        Initialize workload executor.
        
        Args:
            workload: Python Benchmark workload
            mongodb_uri: MongoDB connection string
            record_count: Number of records in the dataset (for distribution)
        """
        self.mongodb_uri = mongodb_uri
        self.record_count = record_count
        self.benchmark = workload
        
        # Build operation selector for weighted random selection
        self.operation_selector = self._build_operation_selector()
    
    def _build_operation_selector(self) -> List:
        """Build weighted operation selector for Python Benchmark."""
        operations = []
        for op in self.benchmark.operations:
            # Repeat operation 'weight' times for weighted random selection
            operations.extend([op] * op.weight)
        return operations
    
    def _select_operation(self):
        """Select an operation based on weights."""
        return random.choice(self.operation_selector)
    
    def _execute_python_operation(
        self,
        operation,  # mdbpl.workload.Operation
        collection: Collection
    ) -> OperationMetrics:
        """Execute a Python Benchmark operation and collect metrics."""
        start_time = time.perf_counter()
        
        try:
            # Wrap collection to capture query info for explain sampling
            wrapped_collection = ExplainCapturingCollection(collection)
            
            # Execute the operation function with wrapped collection
            result = operation.func(wrapped_collection)
            
            end_time = time.perf_counter()
            latency_ms = (end_time - start_time) * 1000
            
            # Get captured query info and optionally run explain (sample 10%)
            docs_examined = None
            docs_returned = None
            index_used = None
            
            if wrapped_collection.last_query and random.random() < 0.1:
                # Sample 10% of queries for explain
                try:
                    query_info = wrapped_collection.last_query
                    
                    # Build find command
                    find_cmd = {
                        'find': collection.name,
                        'filter': query_info.get('filter', {})
                    }
                    if query_info.get('projection'):
                        find_cmd['projection'] = query_info['projection']
                    if query_info.get('limit'):
                        find_cmd['limit'] = query_info['limit']
                    if query_info.get('sort'):
                        find_cmd['sort'] = query_info['sort']
                    
                    # Run explain
                    explain_result = collection.database.command('explain', find_cmd, verbosity='allPlansExecution')
                    
                    if 'executionStats' in explain_result:
                        stats = explain_result['executionStats']
                        docs_examined = stats.get('totalDocsExamined', 0)
                        keys_examined = stats.get('totalKeysExamined', 0)
                        
                        # Get actual result count from the wrapper
                        docs_returned = wrapped_collection.last_result_count
                        
                        # For index scans, use keys examined if docs examined is 0
                        if docs_examined == 0 and keys_examined > 0:
                            docs_examined = keys_examined
                        
                        # Get index info from execution stages
                        def find_index_scan(stage):
                            if not stage:
                                return None
                            if stage.get('stage') == 'IXSCAN':
                                return stage.get('indexName', 'unknown')
                            for key in ['inputStage', 'inputStages']:
                                if key in stage:
                                    if isinstance(stage[key], list):
                                        for substage in stage[key]:
                                            idx = find_index_scan(substage)
                                            if idx:
                                                return idx
                                    else:
                                        idx = find_index_scan(stage[key])
                                        if idx:
                                            return idx
                            return None
                        
                        index_used = find_index_scan(stats.get('executionStages', {}))
                
                except Exception:
                    # Explain failed, continue with None values
                    pass
            
            return OperationMetrics(
                operation_name=operation.name,
                operation_type="python",
                latency_ms=latency_ms,
                success=True,
                docs_examined=docs_examined,
                docs_returned=docs_returned,
                index_used=index_used
            )
            
        except Exception as e:
            end_time = time.perf_counter()
            latency_ms = (end_time - start_time) * 1000
            
            return OperationMetrics(
                operation_name=operation.name,
                operation_type="python",
                latency_ms=latency_ms,
                success=False,
                error=str(e)
            )
    
    def run_threaded(self, duration_seconds: float, threads: int = 4) -> BenchmarkResult:
        """Run the workload with multiple concurrent threads.

        Each thread gets its own Collection reference against the shared MongoClient
        connection pool. Metrics are merged after all threads complete.

        Args:
            duration_seconds: How long to run the workload
            threads: Number of concurrent worker threads

        Returns:
            Aggregated BenchmarkResult across all threads
        """
        import threading

        # socketTimeoutMS caps individual operation time so threads can re-check
        # end_time even when MongoDB is under heavy write load.
        client = MongoClient(self.mongodb_uri, socketTimeoutMS=10000)
        db = client[self.benchmark.database]

        # Pre-allocate per-thread lists — no lock needed during the hot loop
        thread_metrics: List[List[OperationMetrics]] = [[] for _ in range(threads)]

        start_time = time.time()
        end_time = start_time + duration_seconds

        def worker(idx: int):
            collection = db[self.benchmark.collection]
            local = thread_metrics[idx]
            while time.time() < end_time:
                operation = self._select_operation()
                local.append(self._execute_python_operation(operation, collection))

        thread_list = [threading.Thread(target=worker, args=(i,), daemon=True) for i in range(threads)]
        for t in thread_list:
            t.start()
        for t in thread_list:
            t.join()

        client.close()

        actual_duration = time.time() - start_time

        result = BenchmarkResult(
            workload_name=self.benchmark.name,
            duration_seconds=actual_duration,
            total_operations=0,
            successful_operations=0,
            failed_operations=0,
            operations_per_second=0.0,
        )

        for metrics_list in thread_metrics:
            for m in metrics_list:
                result.total_operations += 1
                if m.success:
                    result.successful_operations += 1
                else:
                    result.failed_operations += 1
                result.add_operation(m)

        if actual_duration > 0:
            result.operations_per_second = result.total_operations / actual_duration
        result.calculate_percentiles()
        result.extrapolate_sampled_metrics()

        return result

    def run(self, duration_seconds: float, tag: str = "baseline") -> BenchmarkResult:
        """
        Run the workload for specified duration.
        
        Args:
            duration_seconds: How long to run the workload
            tag: Tag for this benchmark run
            
        Returns:
            Benchmark results with metrics
        """
        # Connect to MongoDB
        client = MongoClient(self.mongodb_uri)
        db = client[self.benchmark.database]
        collection = db[self.benchmark.collection]
        
        # Initialize results
        result = BenchmarkResult(
            workload_name=self.benchmark.name,
            duration_seconds=duration_seconds,
            total_operations=0,
            successful_operations=0,
            failed_operations=0,
            operations_per_second=0.0
        )
        
        # Run workload
        start_time = time.time()
        end_time = start_time + duration_seconds
        
        while time.time() < end_time:
            # Select operation
            operation = self._select_operation()
            
            # Execute Python operation
            metrics = self._execute_python_operation(operation, collection)
            
            # Record metrics
            result.total_operations += 1
            if metrics.success:
                result.successful_operations += 1
            else:
                result.failed_operations += 1
            
            result.add_operation(metrics)
        
        # Calculate final metrics
        actual_duration = time.time() - start_time
        result.duration_seconds = actual_duration
        result.operations_per_second = result.total_operations / actual_duration
        result.calculate_percentiles()
        
        # Extrapolate sampled explain metrics (both DSL and Python workloads sample ~10%)
        result.extrapolate_sampled_metrics()
        
        # Close connection
        client.close()
        
        return result


def parse_duration(duration_str: str) -> float:
    """
    Parse duration string to seconds.
    
    Args:
        duration_str: Duration string (e.g., "30s", "2m", "1h")
        
    Returns:
        Duration in seconds
    """
    duration_str = duration_str.strip().lower()
    
    if duration_str.endswith('s'):
        return float(duration_str[:-1])
    elif duration_str.endswith('m'):
        return float(duration_str[:-1]) * 60
    elif duration_str.endswith('h'):
        return float(duration_str[:-1]) * 3600
    else:
        # Assume seconds if no unit
        return float(duration_str)
