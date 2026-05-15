"""Overindexing Demo - Shows write performance degradation with too many indexes."""

from datetime import datetime
from pymongo import MongoClient
import os

from .base import Demo, DemoStep, DemoResult
from ..ycsb import load_ycsb_data
from ..dsl.loader import WorkloadLoader
from ..executor import WorkloadExecutor
from ..storage import BenchmarkStorage


class OverindexingDemo(Demo):
    """
    Demonstrates write performance degradation with too many indexes.
    
    Runs a write-heavy workload with:
    1. No indexes (baseline)
    2. One index (slight overhead)
    3. Ten indexes (significant overhead)
    
    Shows that every write must update all indexes, causing slowdown.
    """
    
    name = "overindexing"
    title = "Over-Indexing Performance Impact"
    description = "Shows how too many indexes degrade write performance"
    
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
                description="Loading 100,000 test records",
                started_at=datetime.now()
            )
            load_ycsb_data(
                mongodb_uri=self.mongodb_uri,
                record_count=100000,
                drop_existing=True
            )
            
            # Add sortable numeric field
            count = self.collection.count_documents({})
            for i, doc in enumerate(self.collection.find({}, {"_id": 1})):
                self.collection.update_one(
                    {"_id": doc["_id"]},
                    {"$set": {"score": i}}
                )
            
            step1.completed_at = datetime.now()
            step1.result = {"records": count, "note": "Added 'score' field"}
            result.steps.append(step1)
            
            # Step 2: Baseline benchmark (no indexes)
            step2 = DemoStep(
                name="baseline_benchmark",
                description="Running write-heavy workload with NO indexes",
                started_at=datetime.now()
            )
            
            # Drop any existing indexes to ensure clean baseline
            self.collection.drop_indexes()
            
            workload_spec = WorkloadLoader.load_builtin("write-heavy")
            executor = WorkloadExecutor(
                workload=workload_spec,
                mongodb_uri=self.mongodb_uri,
                record_count=100000
            )
            
            baseline_result = executor.run(
                duration_seconds=10,
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
            
            # Step 3: Create one index
            step3 = DemoStep(
                name="create_one_index",
                description="Creating 1 index on score field",
                started_at=datetime.now()
            )
            
            self.collection.create_index("score")
            step3.completed_at = datetime.now()
            step3.result = {"indexes": ["score_1"]}
            result.steps.append(step3)
            
            # Step 4: Benchmark with one index
            step4 = DemoStep(
                name="one_index_benchmark",
                description="Running workload with 1 index",
                started_at=datetime.now()
            )
            
            one_index_result = executor.run(
                duration_seconds=10,
                tag="one-index"
            )
            
            self.storage.save_result(one_index_result, tag="one-index")
            step4.completed_at = datetime.now()
            step4.result = {
                "throughput": one_index_result.operations_per_second,
                "latency_p50": one_index_result.latency_p50,
                "latency_p95": one_index_result.latency_p95,
                "total_operations": one_index_result.total_operations,
            }
            result.steps.append(step4)
            
            # Step 5: Create many indexes
            step5 = DemoStep(
                name="create_many_indexes",
                description="Creating 9 additional indexes (10 total)",
                started_at=datetime.now()
            )
            
            # Create indexes on field0-field8 (binary fields) to show overhead
            for i in range(9):
                self.collection.create_index(f"field{i}")
            
            step5.completed_at = datetime.now()
            step5.result = {
                "indexes": ["score_1"] + [f"field{i}_1" for i in range(9)],
                "total": 10
            }
            result.steps.append(step5)
            
            # Step 6: Benchmark with many indexes
            step6 = DemoStep(
                name="many_indexes_benchmark",
                description="Running workload with 10 indexes",
                started_at=datetime.now()
            )
            
            many_indexes_result = executor.run(
                duration_seconds=10,
                tag="over-indexed"
            )
            
            self.storage.save_result(many_indexes_result, tag="over-indexed")
            step6.completed_at = datetime.now()
            step6.result = {
                "throughput": many_indexes_result.operations_per_second,
                "latency_p50": many_indexes_result.latency_p50,
                "latency_p95": many_indexes_result.latency_p95,
                "total_operations": many_indexes_result.total_operations,
            }
            result.steps.append(step6)
            
            # Step 7: Compare results
            step7 = DemoStep(
                name="compare",
                description="Comparing results",
                started_at=datetime.now()
            )
            
            throughput_degradation = (
                (baseline_result.operations_per_second - many_indexes_result.operations_per_second) 
                / baseline_result.operations_per_second * 100
            )
            latency_degradation = (
                (many_indexes_result.latency_p95 - baseline_result.latency_p95)
                / baseline_result.latency_p95 * 100
            )
            
            step7.completed_at = datetime.now()
            step7.result = {
                "baseline": step2.result,
                "one_index": step4.result,
                "over_indexed": step6.result,
                "degradation": {
                    "throughput_percent": round(throughput_degradation, 2),
                    "latency_p95_percent": round(latency_degradation, 2),
                }
            }
            result.steps.append(step7)
            
            result.completed_at = datetime.now()
            result.success = True
            
        except Exception as e:
            result.completed_at = datetime.now()
            result.success = False
            result.error = str(e)
        
        return result
