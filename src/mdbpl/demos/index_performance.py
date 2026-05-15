"""Index Performance Demo - Shows dramatic read improvement with proper indexing."""

from datetime import datetime
from pymongo import MongoClient
import os

from .base import Demo, DemoStep, DemoResult
from ..ycsb import load_ycsb_data
from ..dsl.loader import WorkloadLoader
from ..executor import WorkloadExecutor
from ..storage import BenchmarkStorage


class IndexPerformanceDemo(Demo):
    """
    Demonstrates the dramatic performance improvement when adding an index.
    
    Shows a range query workload that performs poorly without an index,
    then adds a single index and re-runs to show 10x+ improvement.
    """
    
    name = "index-performance"
    title = "Index Performance Impact"
    description = "Demonstrates dramatic read performance improvement with proper indexing"
    markdown_file = "index-performance.md"
    
    def __init__(self):
        self.mongodb_uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
        self.client = MongoClient(self.mongodb_uri)
        self.db = self.client["perflab"]
        self.collection = self.db["usertable"]
        self.storage = BenchmarkStorage()
    
    def run(self) -> DemoResult:
        """Execute the demo."""
        result = DemoResult(
            demo_name=self.name,
            title=self.title,
            started_at=datetime.now()
        )
        
        try:
            # Step 1: Load data
            step1 = DemoStep(
                name="load_data",
                description="Loading 10,000 test records",
                started_at=datetime.now()
            )
            load_ycsb_data(
                mongodb_uri=self.mongodb_uri,
                record_count=10000,
                drop_existing=True
            )
            
            # Add sortable numeric field for range queries
            # YCSB creates binary fields which don't work with range scans
            count = self.collection.count_documents({})
            for i, doc in enumerate(self.collection.find({}, {"_id": 1})):
                self.collection.update_one(
                    {"_id": doc["_id"]},
                    {"$set": {"score": i}}
                )
            
            step1.completed_at = datetime.now()
            step1.result = {"records": count, "note": "Added 'score' field for range queries"}
            result.steps.append(step1)
            
            # Step 2: Baseline benchmark (no index)
            step2 = DemoStep(
                name="baseline_benchmark",
                description="Running range scan workload WITHOUT index",
                started_at=datetime.now()
            )
            
            # Drop any existing indexes (except _id) to ensure clean baseline
            self.collection.drop_indexes()
            
            workload_spec = WorkloadLoader.load_builtin("range-scan")
            executor = WorkloadExecutor(
                workload=workload_spec,
                mongodb_uri=self.mongodb_uri,
                record_count=10000
            )
            
            baseline_result = executor.run(
                duration_seconds=15,
                tag="no-index"
            )
            
            self.storage.save_result(baseline_result, tag="no-index")
            step2.completed_at = datetime.now()
            step2.result = {
                "throughput": baseline_result.operations_per_second,
                "latency_p50": baseline_result.latency_p50,
                "latency_p95": baseline_result.latency_p95,
                "total_operations": baseline_result.total_operations,
            }
            result.steps.append(step2)
            
            # Step 3: Create index
            step3 = DemoStep(
                name="create_index",
                description="Creating index on score field",
                started_at=datetime.now()
            )
            
            self.collection.create_index("score")
            step3.completed_at = datetime.now()
            step3.result = {"index": "score_1"}
            result.steps.append(step3)
            
            # Step 4: Benchmark with index
            step4 = DemoStep(
                name="indexed_benchmark",
                description="Running same workload WITH index",
                started_at=datetime.now()
            )
            
            indexed_result = executor.run(
                duration_seconds=15,
                tag="with-index"
            )
            
            self.storage.save_result(indexed_result, tag="with-index")
            step4.completed_at = datetime.now()
            step4.result = {
                "throughput": indexed_result.operations_per_second,
                "latency_p50": indexed_result.latency_p50,
                "latency_p95": indexed_result.latency_p95,
                "total_operations": indexed_result.total_operations,
            }
            result.steps.append(step4)
            
            # Step 5: Compare results
            step5 = DemoStep(
                name="compare",
                description="Comparing results",
                started_at=datetime.now()
            )
            
            throughput_improvement = (
                (indexed_result.operations_per_second - baseline_result.operations_per_second) 
                / baseline_result.operations_per_second * 100
            )
            latency_improvement = (
                (baseline_result.latency_p95 - indexed_result.latency_p95)
                / baseline_result.latency_p95 * 100
            )
            
            step5.completed_at = datetime.now()
            step5.result = {
                "baseline": step2.result,
                "indexed": step4.result,
                "improvements": {
                    "throughput_percent": round(throughput_improvement, 2),
                    "latency_p95_percent": round(latency_improvement, 2),
                }
            }
            result.steps.append(step5)
            
            result.completed_at = datetime.now()
            result.success = True
            
        except Exception as e:
            result.completed_at = datetime.now()
            result.success = False
            result.error = str(e)
        
        return result
