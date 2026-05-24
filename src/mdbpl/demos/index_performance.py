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
                description="Load 10,000 YCSB documents and add numeric score field for range queries",
                markdown="""
## Step 1: Initialize Test Data

We'll start by loading 10,000 test documents using the YCSB (Yahoo Cloud Serving Benchmark) dataset. 

YCSB generates realistic documents with 10 random fields (`field0` through `field9`), each containing 100-character random strings. This simulates real-world data like user profiles or product catalogs.

After loading the data, we'll add a **numeric `score` field** to each document. This field will range from 0-9999 and allows us to test range queries - a common pattern where you query for values within a range (e.g., "find all products with price between $50-$100").

### Why a numeric field?

Range queries on numeric fields are a classic use case for indexes. Without an index, MongoDB must:
1. Scan **every document** in the collection
2. Check if each document's score falls within the range
3. Sort the results in memory (expensive!)

With an index, MongoDB can jump directly to the start of the range and efficiently traverse the sorted index.

### Commands executed:
- `mdbpl init --scale 10k` - Loads 10,000 YCSB documents
- `mongosh` script - Adds sequential score field (0-9999) to all documents
""",
                commands=[
                    ShellCommand("mdbpl init --scale 10k", collapse_output=True),
                    MongoshCommand("""
use perflab
// Add a numeric 'score' field to all documents for range query testing
// This simulates real-world scenarios like user ratings, product prices, timestamps, etc.
var count = 0;
db.usertable.find().forEach(function(doc) {
    db.usertable.updateOne(
        {_id: doc._id},
        {$set: {score: count++}}
    );
});
print("✓ Added score field to " + count + " documents");
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
1. **Reads every single document** in the collection (10,000 documents)
2. Checks if each document's score falls within the range
3. Collects all matching documents (~2,000 matches for a 2,000-value range)
4. **Sorts the results in memory** (expensive!)
5. Returns the first 100 after sorting

This is **very slow** because:
- Full collection scan touches every document
- In-memory sort of ~2,000 documents per query
- No way to skip non-matching documents

### Expected Results

Watch for:
- Low throughput (operations per second)
- High latency (milliseconds per operation)
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

The index will consume additional disk space (~200KB for 10,000 documents), but the performance gain is worth it for read-heavy workloads.

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
use perflab
db.usertable.createIndex({score: 1})
print("✓ Index created successfully on score field")
db.usertable.getIndexes().forEach(function(idx) {
    print("  - " + idx.name + ": " + JSON.stringify(idx.key));
});
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
- Only reads ~100 documents instead of 10,000
- Results are already in sorted order
- Uses efficient B-tree structure

### Expected Improvements

Watch for dramatic improvements:
- **10-100x higher throughput** (operations per second)
- **90%+ lower latency** (milliseconds per operation)
- **index_scans** metric will be high
- **collection_scans** will be near zero
- **docs_examined** will be much lower

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
- Baseline: ~50-100 ops/sec (slow!)
- With Index: ~5,000-10,000 ops/sec (fast!)
- **Expected: 50-100x improvement** 🚀

**Latency (milliseconds)**
- Baseline: ~20-50ms per operation
- With Index: ~0.2-1ms per operation
- **Expected: 95%+ reduction** ⚡

**Query Execution**
- Baseline: COLLSCAN + in-memory sort
- With Index: IXSCAN + index traversal
- **Expected: Massive reduction in docs_examined**

### Why Such a Big Difference?

The improvement comes from:
1. **Avoiding full collection scans** (10,000 docs → 100 docs)
2. **No in-memory sorting** (pre-sorted in index)
3. **Efficient B-tree lookups** (O(log n) instead of O(n))

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
