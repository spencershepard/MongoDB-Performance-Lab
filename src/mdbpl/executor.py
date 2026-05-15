"""Workload executor - runs DSL workloads and collects metrics."""

import time
import random
import math
import string
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from pymongo import MongoClient
from pymongo.collection import Collection

from .dsl.models import WorkloadSpec, OperationSpec
from .dsl.compiler import DSLCompiler


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
            
            # Store original values for logging
            original_examined = self.total_docs_examined
            original_returned = self.total_docs_returned
            
            # Extrapolate docs examined and returned
            self.total_docs_examined = int(self.total_docs_examined * sampling_ratio)
            self.total_docs_returned = int(self.total_docs_returned * sampling_ratio)
            
            # Extrapolate scan counts
            self.index_scans = int(self.index_scans * sampling_ratio)
            self.collection_scans = int(self.collection_scans * sampling_ratio)
            
            # Log extrapolation
            print(f"DEBUG Extrapolation: sampled={self.operations_with_explain}, "
                  f"total={self.successful_operations}, ratio={sampling_ratio:.1f}x")
            print(f"  Docs examined: {original_examined} → {self.total_docs_examined}")
            print(f"  Docs returned: {original_returned} → {self.total_docs_returned}")


class Distribution:
    """Base class for key distributions."""
    
    def __init__(self, record_count: int):
        self.record_count = record_count
    
    def next_key(self) -> str:
        """Generate the next key."""
        raise NotImplementedError


class UniformDistribution(Distribution):
    """Uniform random distribution - all keys equally likely."""
    
    def next_key(self) -> str:
        """Generate a uniformly random key."""
        key_num = random.randint(0, self.record_count - 1)
        # YCSB format with insertorder=ordered: user0, user1, user2, ...
        return f"user{key_num}"


class LatestDistribution(Distribution):
    """Latest distribution - bias toward recently inserted keys."""
    
    def __init__(self, record_count: int):
        super().__init__(record_count)
        self.zipfian = ZipfianDistribution(record_count)
    
    def next_key(self) -> str:
        """Generate a key biased toward recent inserts."""
        # Use Zipfian but start from the end
        zipf_key = self.zipfian.next_key()
        # Extract number from YCSB format "userN"
        key_num = int(zipf_key.replace("user", ""))
        # Invert to get recent keys
        inverted = self.record_count - key_num - 1
        # YCSB format with insertorder=ordered: user0, user1, user2, ...
        return f"user{inverted}"


class ZipfianDistribution(Distribution):
    """
    Zipfian distribution - power law where small number of items are hot.
    
    Based on YCSB implementation. Follows 80/20 rule where ~20% of keys
    account for ~80% of accesses.
    """
    
    def __init__(self, record_count: int, theta: float = 0.99):
        """
        Initialize Zipfian distribution.
        
        Args:
            record_count: Number of records in the dataset
            theta: Skewness parameter (0.99 is typical, higher = more skewed)
        """
        super().__init__(record_count)
        self.theta = theta
        self.alpha = 1.0 / (1.0 - theta)
        self.zeta_n = self._zeta(record_count, theta)
        self.zeta_2 = self._zeta(2, theta)
        self.eta = (1.0 - math.pow(2.0 / record_count, 1.0 - theta)) / (1.0 - self.zeta_2 / self.zeta_n)
    
    def _zeta(self, n: int, theta: float) -> float:
        """Calculate zeta constant for Zipfian distribution."""
        # For large n, use approximation to avoid slow computation
        if n > 10000:
            return self._zeta_approx(n, theta)
        
        sum_val = 0.0
        for i in range(1, n + 1):
            sum_val += 1.0 / math.pow(i, theta)
        return sum_val
    
    def _zeta_approx(self, n: int, theta: float) -> float:
        """Approximate zeta for large n."""
        # Use integral approximation
        return 1.0 + math.pow(0.5, theta) + (math.pow(n, 1.0 - theta) / (1.0 - theta))
    
    def next_key(self) -> str:
        """Generate a Zipfian-distributed key."""
        u = random.random()
        uz = u * self.zeta_n
        
        if uz < 1.0:
            key_num = 0
        elif uz < 1.0 + math.pow(0.5, self.theta):
            key_num = 1
        else:
            spread = self.record_count
            key_num = int(spread * math.pow(self.eta * (u - 1.0) + 1.0, self.alpha))
        
        # Ensure key is in valid range
        key_num = max(0, min(key_num, self.record_count - 1))
        # YCSB format with insertorder=ordered: user0, user1, user2, ...
        return f"user{key_num}"


class ParameterGenerator:
    """Generates parameters for workload operations based on distribution."""
    
    def __init__(self, distribution: Distribution):
        self.distribution = distribution
    
    def generate(self, param_name: str) -> Any:
        """
        Generate a parameter value.
        
        Args:
            param_name: Name of the parameter to generate
            
        Returns:
            Generated parameter value
        """
        # For userId parameter, use distribution to get a key
        if param_name == "userId":
            return self.distribution.next_key()
        elif param_name == "rangeStart":
            # For range queries on numeric score field (0 to record_count)
            # Generate a random starting point that will match some data
            return random.randint(0, self.distribution.record_count)
        else:
            # For other parameters, generate random alphanumeric strings
            import string
            return ''.join(random.choices(string.ascii_letters + string.digits, k=20))


class WorkloadExecutor:
    """Executes DSL workloads and collects performance metrics."""
    
    def __init__(self, workload: WorkloadSpec, mongodb_uri: str, record_count: int):
        """
        Initialize workload executor.
        
        Args:
            workload: Workload specification from DSL
            mongodb_uri: MongoDB connection string
            record_count: Number of records in the dataset (for distribution)
        """
        self.workload = workload
        self.mongodb_uri = mongodb_uri
        self.record_count = record_count
        
        # Initialize compiler
        self.compiler = DSLCompiler(workload)
        
        # Initialize distribution
        dist_type = workload.distribution.type
        if dist_type == "zipfian":
            self.distribution = ZipfianDistribution(record_count)
        elif dist_type == "uniform":
            self.distribution = UniformDistribution(record_count)
        elif dist_type == "latest":
            self.distribution = LatestDistribution(record_count)
        else:
            raise ValueError(f"Unknown distribution type: {dist_type}")
        
        # Initialize parameter generator
        self.param_generator = ParameterGenerator(self.distribution)
        
        # Build operation selector based on weights
        self.operation_selector = self._build_operation_selector()
    
    def _build_operation_selector(self) -> List[OperationSpec]:
        """Build weighted operation selector."""
        operations = []
        for op in self.workload.operations:
            # Repeat operation 'weight' times for weighted random selection
            operations.extend([op] * op.weight)
        return operations
    
    def _select_operation(self) -> OperationSpec:
        """Select an operation based on weights."""
        return random.choice(self.operation_selector)
    
    def _generate_parameters(self, operation: OperationSpec) -> Dict[str, Any]:
        """Generate parameters required by an operation."""
        params = {}
        
        # Extract parameter names from the operation
        # This is simplified - in production, you'd walk the entire operation tree
        if operation.filter:
            params = self._extract_params_from_filter(operation.filter)
        
        # Generate values for each parameter
        generated_params = {}
        for param_name in params:
            generated_params[param_name] = self.param_generator.generate(param_name)
        
        return generated_params
    
    def _extract_params_from_filter(self, filter_spec) -> set:
        """Extract parameter names from a filter specification."""
        params = set()
        
        from .dsl.models import FilterCondition, CompoundFilter
        
        if isinstance(filter_spec, FilterCondition):
            if filter_spec.value and filter_spec.value.type == "param":
                params.add(filter_spec.value.param)
        elif isinstance(filter_spec, CompoundFilter):
            if filter_spec.and_:
                for cond in filter_spec.and_:
                    params.update(self._extract_params_from_filter(cond))
            if filter_spec.or_:
                for cond in filter_spec.or_:
                    params.update(self._extract_params_from_filter(cond))
        
        return params
    
    def _execute_operation(
        self,
        operation: OperationSpec,
        collection: Collection,
        params: Dict[str, Any]
    ) -> OperationMetrics:
        """Execute a single operation and collect metrics."""
        start_time = time.perf_counter()
        
        try:
            docs_examined = None
            docs_returned = None
            index_used = None
            
            # For find operations, execute the query and optionally get index info
            if operation.operation == "find":
                try:
                    query_filter = self.compiler.compile_filter(operation.filter, params) if operation.filter else {}
                    projection = operation.projection
                    
                    # Execute the actual query to measure latency
                    cursor = collection.find(query_filter, projection)
                    if operation.limit:
                        cursor = cursor.limit(operation.limit)
                    if operation.sort:
                        sort_spec = [(field, 1 if order == "asc" else -1) 
                                    for field, order in operation.sort.items()]
                        cursor = cursor.sort(sort_spec)
                    
                    # Consume the cursor to actually execute the query
                    results = list(cursor)
                    
                    end_time = time.perf_counter()
                    latency_ms = (end_time - start_time) * 1000
                    
                    # Will get both docs_returned and docs_examined from explain sampling
                    # This ensures both metrics are consistently sampled
                    result_count = len(results)
                    
                    # Debug: log read operation results
                    if operation.name == "read" and result_count == 0:
                        print(f"DEBUG: Read query returned 0 results. Filter: {query_filter}")
                    
                    docs_returned = None
                    docs_examined = None
                    index_used = None
                    
                    # Try to get execution stats from explain (sample to reduce overhead)
                    if random.random() < 0.1:  # Sample 10% of queries
                        try:
                            find_cmd = {
                                'find': collection.name,
                                'filter': query_filter
                            }
                            if projection:
                                find_cmd['projection'] = projection
                            if operation.limit:
                                find_cmd['limit'] = operation.limit
                            if operation.sort:
                                sort_spec_dict = dict([(field, 1 if order == "asc" else -1) 
                                                      for field, order in operation.sort.items()])
                                find_cmd['sort'] = sort_spec_dict
                            
                            explain_result = collection.database.command('explain', find_cmd, verbosity='allPlansExecution')
                            
                            if 'executionStats' in explain_result:
                                stats = explain_result['executionStats']
                                docs_examined = stats.get('totalDocsExamined', 0)
                                keys_examined = stats.get('totalKeysExamined', 0)
                                
                                # Set docs_returned from actual query result
                                # This ensures both metrics are sampled together
                                docs_returned = result_count
                                
                                # For index scans, use keys examined if docs examined is 0
                                if docs_examined == 0 and keys_examined > 0:
                                    docs_examined = keys_examined
                                
                                # Get index info from execution stages
                                def find_index_scan(stage):
                                    """Recursively find IXSCAN stage."""
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
                                
                                # Debug: log explain results
                                print(f"DEBUG: Explain for {operation.name}: examined={docs_examined}, "
                                      f"returned={docs_returned}, index={index_used}")
                        except Exception as e:
                            # Explain failed, continue with None values
                            print(f"DEBUG: Explain failed for {operation.name}: {e}")
                            pass
                    
                    success = True
                    
                except Exception as e:
                    # Query execution failed
                    end_time = time.perf_counter()
                    latency_ms = (end_time - start_time) * 1000
                    success = False
                    docs_examined = None
                    docs_returned = None
            else:
                # For non-find operations, just execute normally
                result = self.compiler.compile_operation(operation, collection, params)
                end_time = time.perf_counter()
                latency_ms = (end_time - start_time) * 1000
                success = True
            
            return OperationMetrics(
                operation_name=operation.name,
                operation_type=operation.operation,
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
                operation_type=operation.operation,
                latency_ms=latency_ms,
                success=False,
                error=str(e)
            )
    
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
        db = client[self.workload.database]
        collection = db[self.workload.collection]
        
        # Initialize results
        result = BenchmarkResult(
            workload_name=self.workload.name,
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
            
            # Generate parameters
            params = self._generate_parameters(operation)
            
            # Execute operation
            metrics = self._execute_operation(operation, collection, params)
            
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
        result.extrapolate_sampled_metrics()  # Scale up 10% sample to full workload
        
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
