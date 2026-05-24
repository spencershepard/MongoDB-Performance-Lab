"""Index Performance Demo - Shows dramatic read improvement with proper indexing."""

from typing import List
from .base import Demo, DemoStep, ShellCommand, MongoshCommand


class IndexPerformanceDemo(Demo):
    """
    Demonstrates the dramatic performance improvement when adding an index.
    
    Uses a range-scan workload that queries by numeric score field with sorting.
    Without an index, this requires a full collection scan and in-memory sort.
    With an index on score, MongoDB can use an index scan which is 10-100x faster.
    """
    
    id = "index-performance"
    title = "Index Performance Impact"
    description = "Demonstrates dramatic read performance improvement with proper indexing"
    markdown_file = ""  # Using inline markdown instead
    
    def steps(self) -> List[DemoStep]:
        """Define the demo steps."""
        return [
            DemoStep(
                id="init",
                title="Initialize Test Dataset",
                description="Load 100,000 YCSB documents and add numeric score field for range queries",
                markdown="""
## Step 1: Initialize Test Data

We'll start by loading 100,000 test documents using the YCSB (Yahoo Cloud Serving Benchmark) dataset. 

YCSB generates realistic documents with 10 random fields (`field0` through `field9`), each containing 100-character random strings. This simulates real-world data like user profiles or product catalogs.

After loading the data, we'll add a **numeric `score` field** to each document. This field will range from 0-99999 and allows us to test range queries - a common pattern where you query for values within a range (e.g., "find all products with price between $50-$100").

### Why a numeric field?

Range queries on numeric fields are a classic use case for indexes. Without an index, MongoDB must:
1. Scan **every document** in the collection
2. Check if each document's score falls within the range
3. Sort the results in memory (expensive!)

With an index, MongoDB can jump directly to the start of the range and efficiently traverse the sorted index.

### Why 100k documents?

With larger datasets:
- Collection scans become significantly slower (must read all 100k docs)
- In-memory sorts become expensive (sorting thousands of matches)
- Index benefits become dramatic (O(log n) vs O(n) matters more)

### Commands executed:
- `mdbpl init --scale 100k` - Loads 100,000 YCSB documents (~50MB of data)
- `mongosh` script - Adds sequential score field (0-99999) to all documents
""",
                commands=[
                    ShellCommand("mdbpl init --scale 100k", collapse_output=True),
                    MongoshCommand("""
print("Adding score field to documents...");
var count = 0;
var batch = [];
var cursor = db.usertable.find();
while (cursor.hasNext()) {
    var doc = cursor.next();
    batch.push({
        updateOne: {
            filter: {_id: doc._id},
            update: {$set: {score: count++}}
        }
    });
    if (batch.length >= 1000) {
        db.usertable.bulkWrite(batch);
        batch = [];
        if (count % 10000 === 0) {
            print("  Processed " + count + " documents...");
        }
    }
}
if (batch.length > 0) {
    db.usertable.bulkWrite(batch);
}
print("✓ Successfully added score field to " + count + " documents");
print("");
print("Sample document:");
printjson(db.usertable.findOne({}, {_id: 1, score: 1, field0: 1}));
""", collapse_output=True)
                ]
            ),
            
            DemoStep(
                id="baseline",
                title="Baseline Performance (No Index)",
                description="Run range scans on numeric score field without an index",
                markdown="""
## Step 2: Baseline Performance Test

Now we'll run a benchmark workload **without any index on the score field** to establish our baseline performance.

### The Workload

The `range-scan` workload performs:
- **80% range queries** on the score field (e.g., `{score: {$gte: 3000, $lt: 5000}}`)
- Each query sorts by score and returns 100 documents
- **20% point reads** by `_id` (already indexed)

### What MongoDB Must Do (Without Index)

For each range query, MongoDB performs a **COLLSCAN** (collection scan):
1. **Reads every single document** in the collection (100,000 documents!)
2. Checks if each document's score falls within the range
3. Collects all matching documents (~2,000 matches for a 2,000-value range)
4. **Sorts the results in memory** (expensive!)
5. Returns the first 100 after sorting

This is **very slow** because:
- Full collection scan touches every document (100k reads!)
- In-memory sort of ~2,000 documents per query
- No way to skip non-matching documents
- Must scan entire 50MB+ of data for every query

### Expected Results

Watch for:
- Low throughput (operations per second) - likely 10-50 ops/sec
- High latency (milliseconds per operation) - likely 50-200ms per query
- **collection_scans** metric will be high
- **index_scans** will be 0 (except for _id lookups)

Let's see how slow it is...
""",
                commands=[
                    ShellCommand("mdbpl run --workload range-scan --duration 15s --tag baseline")
                ]
            ),
            
            DemoStep(
                id="create-index",
                title="Create Index on Score Field",
                description="Create a single-field ascending index on the score field",
                markdown="""
## Step 3: Create an Index

Now we'll create a simple **single-field index** on the score field:

```javascript
db.usertable.createIndex({score: 1})
```

### What This Does

MongoDB creates a **B-tree index** structure that:
1. **Stores score values in sorted order**
2. Includes pointers to the actual documents
3. Allows **O(log n)** lookups instead of **O(n)** scans
4. Enables efficient range traversal

### How Indexes Work

Think of it like a phone book:
- **Without index**: Like searching for all people with birthdays in January by reading every single page
- **With index**: Like having a separate "Birthday Index" where you can jump directly to January entries

### Storage Cost

The index will consume additional disk space (~2-3MB for 100,000 documents), but the performance gain is worth it for read-heavy workloads. This is a tiny fraction of the total data size (~50MB).

### What Changes for Queries

After creating this index, queries like `{score: {$gte: 3000, $lt: 5000}}` will:
1. **Use an index scan (IXSCAN)** instead of collection scan
2. Jump directly to score=3000 in the index
3. Traverse the index sequentially (already sorted!)
4. Stop at score=5000
5. No in-memory sorting needed

Let's create it...
""",
                commands=[
                    MongoshCommand("""
try {
    var result = db.usertable.createIndex({score: 1});
    print("✓ Index created successfully on score field");
    print("  Result: " + JSON.stringify(result));
} catch (e) {
    print("Note: Index may already exist - " + e.message);
}

print("");
print("Current indexes:");
var indexes = db.usertable.getIndexes();
indexes.forEach(function(idx) {
    print("  - " + idx.name + ": " + JSON.stringify(idx.key));
});

print("");
print("Verifying index usage with explain():");
try {
    var explainResult = db.usertable.find({score: {$gte: 5000, $lt: 7000}}).sort({score: 1}).limit(100).explain("executionStats");
    var stage = explainResult.executionStats.executionStages.stage;
    var docsExamined = explainResult.executionStats.totalDocsExamined;
    var docsReturned = explainResult.executionStats.nReturned;
    
    print("  Query plan: " + stage);
    print("  Documents examined: " + docsExamined);
    print("  Documents returned: " + docsReturned);
    
    if (stage === "IXSCAN" || stage === "FETCH") {
        print("  ✓ Index is being used!");
    } else {
        print("  ⚠ WARNING: Not using index scan (got " + stage + ")");
    }
} catch (e) {
    print("  Error running explain: " + e.message);
}
""")
                ]
            ),
            
            DemoStep(
                id="with-index",
                title="Performance With Index",
                description="Re-run the same range-scan workload with the index in place",
                markdown="""
## Step 4: Performance Test With Index

Now we'll run the **exact same workload** again, but this time MongoDB will use our new index on the score field.

### What MongoDB Does Now (With Index)

For each range query, MongoDB performs an **IXSCAN** (index scan):
1. **Jumps directly** to score=3000 in the sorted index (O(log n) lookup)
2. **Traverses the index** sequentially reading entries in score order
3. Stops at score=5000
4. Returns first 100 documents (already sorted!)
5. **No in-memory sort needed!**

### Why This is Fast

- **Skips non-matching documents** entirely
- Only reads ~100 documents instead of 100,000 (1000x fewer reads!)
- Results are already in sorted order
- Uses efficient B-tree structure
- O(log n) lookup vs O(n) scan makes huge difference at this scale

### Expected Improvements

Watch for dramatic improvements:
- **50-100x higher throughput** (operations per second) - expect 1,000-5,000 ops/sec
- **95%+ lower latency** (milliseconds per operation) - expect 1-5ms per query
- **index_scans** metric will be high
- **collection_scans** will be near zero
- **docs_examined** will be ~100 instead of 100,000 (1000x reduction!)

Let's see the improvement...
""",
                commands=[
                    ShellCommand("mdbpl run --workload range-scan --duration 15s --tag with-index")
                ]
            ),
            
            DemoStep(
                id="compare",
                title="Compare Results",
                description="Display side-by-side comparison of baseline vs indexed performance",
                markdown="""
## Step 5: Compare the Results

Now let's see the before and after comparison! The `mdbpl compare` command will show us:

### Key Metrics to Watch

**Throughput (ops/sec)**
- Baseline: ~10-50 ops/sec (slow - full scans on 100k docs)
- With Index: ~1,000-5,000 ops/sec (fast - index lookups)
- **Expected: 50-100x improvement** 🚀

**Latency (milliseconds)**
- Baseline: ~50-200ms per operation (full collection scan + sort)
- With Index: ~1-5ms per operation (index traversal)
- **Expected: 95%+ reduction** ⚡

**Query Execution**
- Baseline: COLLSCAN (100,000 docs examined) + in-memory sort
- With Index: IXSCAN (~100 docs examined) + index traversal
- **Expected: 1000x reduction in docs_examined**

### Why Such a Big Difference?

The improvement comes from:
1. **Avoiding full collection scans** (100,000 docs → ~100 docs = 1000x reduction!)
2. **No in-memory sorting** (pre-sorted in index)
3. **Efficient B-tree lookups** (O(log n) instead of O(n))
4. **Scale matters** - With 100k docs, the difference between scanning everything vs using an index is dramatic

### Real-World Impact

This demonstrates why **indexes are critical** for:
- Range queries on numeric/date fields
- Sorting operations
- Queries with high selectivity
- Read-heavy workloads

The performance difference you're about to see is why database indexing is one of the most important optimization techniques!
""",
                commands=[
                    ShellCommand("mdbpl compare --tags baseline,with-index")
                ]
            )
        ]
