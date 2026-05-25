"""
Index Performance Demo — shows dramatic read improvement from a single well-chosen index.

WORKFLOW PATTERN: read-performance / index-impact
  init → baseline (no index) → create index → measure → compare

LLM ADAPTATION GUIDE:
  This demo benchmarks range queries on a numeric field. To adapt to a user's schema:

  1. Field mapping
     score          → any numeric field: price, amount, createdAt (as epoch ms), rating
     range_size     → set to ~20% of the field's value domain
                      (e.g. 30-day window for a 150-day date range = range_size 30)

  2. Collection / database
     Replace "usertable" / "perflab" with --collection <name> --database <name>
     on both `mdbpl init` and every `mdbpl run` command.

  3. Scale
     10k is enough to show the COLLSCAN vs IXSCAN difference.
     Use --scale 100k if the user's collection is large and they want realistic numbers.

  4. Workload choice
     range-scan  → range queries + sorting (dates, prices, scores)  ← used here
     point-read  → equality lookups by a unique key
     top-n       → "show me the top 100 by X" queries
     mixed       → read/write mix (set --read-pct to match their workload ratio)

  5. Tagging rule
     Every `mdbpl run` must have --tag.
     Baseline tag and post-optimization tag must be passed together to `mdbpl compare`.
     Never re-use a tag across different workload configurations.
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
            # Pattern: mdbpl init loads the dataset AND injects the numeric score field.
            # No manual post-processing needed — score (0..record_count-1) is always present.
            DemoStep(
                id="init",
                title="Initialize Test Dataset",
                description="Load 10,000 documents with a numeric score field for range queries",
                markdown="""
## Initialize Test Data

Load 10,000 test documents. Each document contains ten string fields (`field0`–`field9`)
and a sequential numeric `score` field (0–9,999), which is used as the range-query target.

`score` represents any numeric field in a real application: a price, a rating, a timestamp
as epoch milliseconds, an age, a priority level. The range-scan workload will query
`{score: {$gte: N, $lt: N+2000}}` — replace `score` with `--field <your_field>` and
set `--range-size` to match your data's value domain.

**Why 10k documents?** Collection scans become dramatically slower as datasets grow,
while index lookups stay O(log n). Even at 10k the difference is 10–100×; at 1M it's
larger still.
""",
                commands=[
                    # mdbpl init loads documents and injects the score field in one step.
                    # To use a custom collection: mdbpl init --scale 10k --collection orders --database myapp
                    ShellCommand("mdbpl init --scale 10k", collapse_output=False),
                ]
            ),
            
            # STEP 2: Baseline — always measure BEFORE the optimization.
            # The tag ("baseline") must be passed to mdbpl compare later.
            # To benchmark a different field: add --field <name> --range-size <N>
            # To benchmark a different collection: add --collection <name> --database <name>
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
            
            # STEP 3: Apply the optimization.
            # Use MongoshCommand for any DDL: createIndex, dropIndex, collMod, etc.
            # For compound indexes: db.collection.createIndex({field1: 1, field2: 1})
            # For descending sort: db.collection.createIndex({field: -1})
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
            
            # STEP 4: Re-run the IDENTICAL workload, only the tag changes.
            # All other flags (--field, --range-size, --duration, --threads) must match step 2
            # exactly — otherwise mdbpl compare is not apples-to-apples.
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
            
            # STEP 5: Compare — pass the tags from steps 2 and 4 in order (baseline first).
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
