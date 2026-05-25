"""
Index Performance Demo - Shows dramatic read improvement with proper indexing.

TEMPLATE PATTERNS FOR LLM-GENERATED WORKFLOWS:

This demo follows the standard performance testing workflow:
1. Initialize test data matching your query pattern
2. Run baseline benchmark (before optimization)
3. Apply optimization (create index, change schema, etc.)
4. Run optimized benchmark (same query after optimization)
5. Compare results side-by-side

COMMAND PATTERNS:
- ShellCommand: For mdbpl CLI commands (init, run, compare)
- MongoshCommand: For direct MongoDB operations (createIndex, queries, updates)
- Always tag benchmarks for easy comparison
- Use collapse_output=False to show detailed results

WORKFLOW STRUCTURE:
- Each DemoStep has: id, title, description, markdown, commands
- markdown explains WHY this step matters (context for LLM and users)
- commands list contains ShellCommand or MongoshCommand objects
- Steps execute sequentially in order
"""

from typing import List
from .base import Demo, DemoStep, ShellCommand, MongoshCommand


class IndexPerformanceDemo(Demo):
    """
    Demonstrates dramatic performance improvement when adding an index.
    
    Pattern: baseline → optimization → measurement → comparison
    This is the recommended structure for index optimization workflows.
    
    Use Case: Range queries with sorting (common for date/numeric fields)
    Without Index: Full collection scan + in-memory sort (slow)
    With Index: Index scan with pre-sorted data (10-100x faster)
    """
    
    # Unique identifier for this demo (lowercase, hyphenated)
    id = "index-performance"
    
    # Display name shown in UI
    title = "Index Performance Impact"
    
    # Short description for demo selection
    description = "Demonstrates dramatic read performance improvement with proper indexing"
    
    # Using inline markdown instead of separate file
    markdown_file = ""
    
    def steps(self) -> List[DemoStep]:
        """Define the demo steps."""
        return [
            # STEP 1: Initialize test data
            # Pattern: Load realistic data matching your query workload
            DemoStep(
                id="init",
                title="Initialize Test Dataset",
                description="Load 10,000 YCSB documents and add numeric score field for range queries",
                markdown="""
## Initialize Test Data

Load 10,000 test documents using YCSB (Yahoo Cloud Serving Benchmark) format. YCSB generates realistic documents with 10 random fields, simulating real-world data like user profiles or product catalogs.

Then add a **numeric `score` field** (0-9999) to enable range query testing. Range queries are common for filtering by dates, prices, ratings, or other numeric values.

**Why 10k documents?** With larger datasets, collection scans become significantly slower while index lookups stay fast, making the performance difference dramatic.
""",
                commands=[
                    # Pattern: Use mdbpl init to load YCSB test data
                    # --scale controls dataset size (10k = 10,000 documents)
                    ShellCommand("mdbpl init --scale 10k", collapse_output=False),
                    
                    # Pattern: Use MongoshCommand for MongoDB operations
                    # This adds a numeric field for range query testing
                    MongoshCommand("""
var count = 0;
var batch = [];
db.usertable.find().forEach(function(doc) {
    batch.push({updateOne: {filter: {_id: doc._id}, update: {$set: {score: count++}}}});
    if (batch.length >= 1000) {
        db.usertable.bulkWrite(batch);
        batch = [];
    }
});
if (batch.length > 0) db.usertable.bulkWrite(batch);

print("✓ Added score field to 10,000 documents");
print("Sample: " + JSON.stringify(db.usertable.findOne({}, {_id: 1, score: 1})));
""", collapse_output=False)
                ]
            ),
            
            # STEP 2: Baseline benchmark (before optimization)
            # Pattern: Always measure before optimization to establish baseline
            # Tag your benchmark for easy comparison later
            DemoStep(
                id="baseline",
                title="Baseline Performance (No Index)",
                description="Run range scans on numeric score field without an index",
                markdown="""
## Baseline Performance Test

Run benchmark workload **without any index** on the score field to establish baseline performance.

**Workload:** The `range-scan` workload performs:
- 80% range queries on score field (e.g., `{score: {$gte: 3000, $lt: 5000}}`)
- Each query sorts by score and returns 100 documents
- 20% point reads by `_id` (already indexed)

**Without Index:** MongoDB performs a COLLSCAN (collection scan):
1. Reads every document in the collection (10,000 documents)
2. Checks if each document's score matches the range
3. Collects all matching documents (~2,000 matches)
4. **Sorts results in memory** (expensive!)
5. Returns first 100

**Expected:** Low throughput (10-50 ops/sec), high latency (50-200ms), high collection_scans metric.
""",
                commands=[
                    # Pattern: Run benchmark with descriptive tag
                    # Tag is used later in compare step
                    ShellCommand("mdbpl run --workload range-scan --duration 15s --tag baseline")
                ]
            ),
            
            # STEP 3: Apply optimization (create index)
            # Pattern: Use MongoshCommand for MongoDB DDL operations
            DemoStep(
                id="create-index",
                title="Create Index on Score Field",
                description="Create a single-field ascending index on the score field",
                markdown="""
## Create Index

Create a **single-field index** on the score field:

```javascript
db.usertable.createIndex({score: 1})
```

**What this does:** MongoDB creates a B-tree index structure that stores score values in sorted order with pointers to documents. Enables O(log n) lookups instead of O(n) scans.

**How it helps:** After indexing, range queries use an IXSCAN (index scan) instead of COLLSCAN:
1. Jump directly to score=3000 in the index
2. Traverse sequentially (already sorted)
3. Stop at score=5000
4. No in-memory sorting needed

**Storage cost:** ~2-3MB for 10,000 documents (minimal compared to query speed gains).
""",
                commands=[
                    # Pattern: Create indexes using MongoshCommand
                    # Use ascending (1) or descending (-1) based on query sort order
                    MongoshCommand("""
db.usertable.createIndex({score: 1});
print("✓ Index created on score field");
print("");
print("Indexes:");
db.usertable.getIndexes().forEach(function(idx) {
    print("  " + idx.name + ": " + JSON.stringify(idx.key));
});
""")
                ]
            ),
            
            # STEP 4: Measure after optimization
            # Pattern: Run same benchmark with identical parameters + different tag
            DemoStep(
                id="with-index",
                title="Performance With Index",
                description="Re-run the same range-scan workload with the index in place",
                markdown="""
## Performance With Index

Run the **exact same workload** again, but now MongoDB uses the index.

**With Index:** MongoDB performs an IXSCAN (index scan):
1. Jump directly to score=3000 (O(log n) lookup)
2. Traverse index sequentially (already sorted)
3. Stop at score=5000
4. Return first 100 (no in-memory sort needed)

**Why it's fast:**
- Skips non-matching documents entirely
- Only examines ~100 documents instead of 10,000 (100x reduction)
- Results already in sorted order
- O(log n) vs O(n) makes huge difference at scale

**Expected improvements:**
- **50-100x higher throughput** - expect 1,000-5,000 ops/sec (vs 10-50)
- **95%+ lower latency** - expect 1-5ms per query (vs 50-200ms)
- **index_scans** high, **collection_scans** near zero
- **docs_examined** ~100 instead of 10,000
""",
                commands=[
                    # Pattern: Use same benchmark parameters, different tag
                    # This ensures apples-to-apples comparison
                    ShellCommand("mdbpl run --workload range-scan --duration 15s --tag with-index")
                ]
            ),
            
            # STEP 5: Compare results
            # Pattern: Use mdbpl compare with tags from previous benchmarks
            DemoStep(
                id="compare",
                title="Compare Results",
                description="Display side-by-side comparison of baseline vs indexed performance",
                markdown="""
## Compare Results

Side-by-side comparison showing the dramatic impact of proper indexing.

**Key Metrics:**

**Throughput (ops/sec)**
- Baseline: ~10-50 (full scans)
- With Index: ~1,000-5,000 (index lookups)
- **Expected: 50-100x improvement** 🚀

**Latency (ms)**
- Baseline: ~50-200ms (scan + sort)
- With Index: ~1-5ms (index traversal)
- **Expected: 95%+ reduction** ⚡

**Query Execution**
- Baseline: COLLSCAN (10,000 docs examined) + in-memory sort
- With Index: IXSCAN (~100 docs examined) + index-sorted
- **Expected: 100x reduction in docs_examined**

**Why such a big difference?**
1. Avoiding full collection scans (10k → ~100 docs)
2. No in-memory sorting (pre-sorted in index)
3. Efficient B-tree lookups (O(log n) vs O(n))
4. Scale matters - larger datasets = bigger wins

**Real-world impact:** Indexes are critical for range queries, sorting, and read-heavy workloads. This demo shows why indexing is one of the most important database optimization techniques.
""",
                commands=[
                    # Pattern: Compare by tags from previous benchmarks
                    # Tags must match exactly (comma-separated, no spaces)
                    ShellCommand("mdbpl compare --tags baseline,with-index")
                ]
            )
        ]
