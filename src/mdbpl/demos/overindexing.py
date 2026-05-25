"""
Overindexing Demo — shows write performance degradation from maintaining too many indexes.

WORKFLOW PATTERN: write-performance / overindexing
  init → baseline (no secondary indexes) → one index → add many indexes → measure → compare

KEY INSIGHT: Every write must update ALL indexes on the collection. With 9 indexes,
each insert touches 9 B-tree structures instead of 1, multiplying I/O and lock
contention under concurrent load.

WORKLOAD: mdbpl run --workload insert --batch-size 1 --threads 8
- insert_one per operation (no batch pipelining) maximises per-op index lock cycles
- 8 concurrent threads surface B-tree write-lock contention
- 50k dataset pushes index B-trees beyond WiredTiger's warm cache

LLM ADAPTATION GUIDE:
  To adapt this demo to a user's write-heavy collection:

  1. Field mapping
     Replace --fields score,field0,...,field7 with the actual fields the user's
     application writes on insert. Include every field that has or will have an index.
     Example (orders collection):
       --fields status,region,customerId,amount,createdAt,updatedAt,productId,warehouseId

  2. Index selection
     In the "add-indexes" step, create indexes that mirror the user's real index set.
     Each createIndex call should reflect a query the application actually runs.
     The more indexes match real queries, the more convincing the comparison.

  3. Scale
     50k is the minimum to push index pages out of WiredTiger cache.
     For collections > 1M docs in production, use --scale 100k or --scale 1m.
     The relative degradation (%) is what matters, not absolute throughput.

  4. Workload choice for write scenarios
     insert      → new document creation (used here)
     update      → in-place field changes; use --filter-field and --update-fields
     mixed       → combined read + write; set --read-pct to match the user's ratio

  5. Thread count
     --threads 8 is a good default for write contention demos.
     Match to the user's expected application concurrency if known.
"""

from typing import List
from .base import Demo, DemoStep, ShellCommand, MongoshCommand

# Shared insert command used across all three benchmark steps.
# --fields lists every field the workload writes — must match the fields being indexed.
# Adapt: replace with the user's actual written fields, e.g.:
#   "status,region,customerId,amount,createdAt,updatedAt,productId,warehouseId"
# Rule: all three benchmark steps (no-index, one-index, over-indexed) MUST use
# identical flags; only --tag changes between runs.
_INSERT_CMD = (
    "mdbpl run --workload insert"
    " --fields score,field0,field1,field2,field3,field4,field5,field6,field7"
    " --batch-size 1 --threads 8 --duration 30s"
)


class OverindexingDemo(Demo):
    """
    Demonstrates write performance degradation caused by maintaining too many indexes.

    Pattern: drop-indexes → baseline → add-one-index → measure → add-eight-more → measure → compare
    Workload: mdbpl run --workload insert with 8 concurrent threads, insert_one, 50k dataset

    Without indexes: MongoDB only writes the document and updates _id B-tree (1 write path)
    With 9 indexes:  MongoDB writes the document + updates 9 B-trees (9x write amplification)
    """

    id = "overindexing"
    title = "Over-Indexing Performance Impact"
    description = "Demonstrates write performance degradation caused by maintaining too many indexes"
    markdown_file = ""

    def steps(self) -> List[DemoStep]:
        return [

            # STEP 1: Initialize test data
            DemoStep(
                id="init",
                title="Initialize Test Dataset",
                description="Load 50,000 YCSB documents as the write target",
                markdown="""
## Initialize Test Data

Load 50,000 YCSB documents. The write workload inserts additional documents
into this collection — we benchmark how quickly writes land when different
numbers of secondary indexes must be maintained.

**Why 50k?** Index B-tree overhead only becomes measurable once index pages
exceed WiredTiger's warm cache. With 10k documents, all 9 index B-trees fit
entirely in memory and updates are essentially free. At 50k, index pages
start spilling to disk under concurrent write pressure, making the overhead
visible. Scale further to 100k–1M for more dramatic numbers in production
comparisons.

**Workload shape:**
- `mdbpl run --workload insert` — one document per operation (`insert_one`)
- Fields written: `score`, `field0`–`field7` (9 fields, all YCSB-native)
- 8 concurrent threads — B-tree write-lock contention grows with thread count
- 30s duration — allows WiredTiger cache pressure to build and stabilise

> **Note on local vs production numbers:** This demo runs inside Docker on
> localhost. WiredTiger's cache is warm and disk I/O is fast SSD or tmpfs.
> In a production deployment — especially on spinning disk, a loaded Atlas
> cluster, or a replica set requiring `w:majority` journal flushes — the
> overindexing penalty is typically 2–5× larger than what you'll see here.
> The *relative* difference between runs is what matters.
""",
                commands=[
                    ShellCommand("mdbpl init --scale 50k", collapse_output=False),
                ]
            ),

            # STEP 2: Baseline — no secondary indexes
            DemoStep(
                id="baseline",
                title="Baseline Write Performance (No Secondary Indexes)",
                description="Drop all secondary indexes, then run the insert workload",
                markdown="""
## Baseline: No Secondary Indexes

Drop all secondary indexes so only the required `_id` index remains.
This measures the true cost of the write itself, with zero index maintenance overhead.

**What MongoDB does on each insert (no secondary indexes):**
1. Write document to collection
2. Update `_id` B-tree (mandatory, always present)

**Expected:** High throughput, low latency — writes go almost directly to WiredTiger.
The `_id` index update is unavoidable and represents the theoretical minimum write cost.
8 threads will be competing, but with only one B-tree to update they rarely block each other.
""",
                commands=[
                    MongoshCommand("""
db.usertable.dropIndexes();
print("✓ Dropped all secondary indexes");
print("");
print("Remaining indexes:");
db.usertable.getIndexes().forEach(function(idx) {
    print("  " + idx.name + ": " + JSON.stringify(idx.key));
});
""", collapse_output=False),
                    ShellCommand(
                        f"{_INSERT_CMD} --tag no-index",
                        collapse_output=False,
                    ),
                ]
            ),

            # STEP 3: Add one index, measure overhead
            DemoStep(
                id="one-index",
                title="Write Performance With One Index",
                description="Add a single index on score, re-run the same workload",
                markdown="""
## One Index: Minimal Overhead

Add a single index on the `score` field — a common optimization for range queries.

**What MongoDB does on each insert (1 secondary index):**
1. Write document to collection
2. Update `_id` B-tree
3. Update `score` B-tree ← new cost

The overhead of one index is usually modest (5–15%) because WiredTiger batches
index updates efficiently. This step establishes that **some** indexing is acceptable;
the problem emerges when indexes multiply.

**Expected:** Slight throughput reduction vs baseline — typically 5–15% at this scale.
One index means one additional B-tree to lock per insert, but WiredTiger handles
single-index contention well even under 8 threads.
""",
                commands=[
                    MongoshCommand("""
db.usertable.createIndex({score: 1});
print("✓ Created index on score");
print("");
print("Current indexes:");
db.usertable.getIndexes().forEach(function(idx) {
    print("  " + idx.name + ": " + JSON.stringify(idx.key));
});
""", collapse_output=False),
                    ShellCommand(
                        f"{_INSERT_CMD} --tag one-index",
                        collapse_output=False,
                    ),
                ]
            ),

            # STEP 4: Create 8 more indexes (9 total)
            DemoStep(
                id="add-indexes",
                title="Create 8 More Indexes (9 Total Secondary Indexes)",
                description="Index every field written by the workload — a common anti-pattern",
                markdown="""
## The Over-Indexing Anti-Pattern

Create indexes on every field the workload writes to. This mirrors a common mistake:
adding indexes reactively as query patterns emerge, without auditing the write cost.

**Indexes being added:**
| Index | Field | Why it's tempting |
|-------|-------|-------------------|
| `field0_1` | field0 | Filter by primary category |
| `field1_1` | field1 | Filter by secondary attribute |
| `field2_1` | field2 | Support legacy queries |
| `field3_1` | field3 | Support reporting queries |
| `field4_1` | field4 | Support analytics queries |
| `field5_1` | field5 | Support dashboard queries |
| `field6_1` | field6 | Support search queries |
| `field7_1` | field7 | Support export queries |

Each is justifiable in isolation. Together they create **9x write amplification**:
every insert must update 9 B-trees instead of 1.
""",
                commands=[
                    MongoshCommand("""
db.usertable.createIndex({field0: 1});
db.usertable.createIndex({field1: 1});
db.usertable.createIndex({field2: 1});
db.usertable.createIndex({field3: 1});
db.usertable.createIndex({field4: 1});
db.usertable.createIndex({field5: 1});
db.usertable.createIndex({field6: 1});
db.usertable.createIndex({field7: 1});

print("✓ Created 8 additional indexes");
print("");
print("All indexes (" + db.usertable.getIndexes().length + " total):");
db.usertable.getIndexes().forEach(function(idx) {
    print("  " + idx.name + ": " + JSON.stringify(idx.key));
});
""", collapse_output=False),
                ]
            ),

            # STEP 5: Measure write performance with 9 indexes
            DemoStep(
                id="over-indexed",
                title="Write Performance With 9 Indexes",
                description="Run the identical workload — now every write maintains 9 B-trees",
                markdown="""
## Over-Indexed: The Cost Revealed

Run the exact same workload against the collection with 9 secondary indexes.

**What MongoDB does on each insert (9 secondary indexes):**
1. Write document to collection
2. Update `_id` B-tree
3. Update `score` B-tree
4. Update `field0` B-tree
5. Update `field1` B-tree
6. Update `field2` B-tree
7. Update `field3` B-tree
8. Update `field4` B-tree
9. Update `field5` B-tree
10. Update `field6` B-tree
11. Update `field7` B-tree

Under 8 concurrent threads, each insert acquires write locks on 9 B-trees.
Threads frequently collide on the same index pages, serialising what would
otherwise be parallel writes. Lock wait time compounds beyond simple multiplication.

**Expected:** Significant throughput drop and latency increase vs baseline.
The p99 latency spike is often more dramatic than the throughput drop.
""",
                commands=[
                    ShellCommand(
                        f"{_INSERT_CMD} --tag over-indexed",
                        collapse_output=False,
                    ),
                ]
            ),

            # STEP 6: Compare baseline vs over-indexed
            DemoStep(
                id="compare",
                title="Compare Results: No Indexes vs Over-Indexed",
                description="Side-by-side comparison showing the full write performance cost",
                markdown="""
## Results Comparison

Side-by-side view of write throughput and latency across all three configurations.

**Key Metrics to Watch:**

**Throughput (ops/sec)**
- No index: maximum throughput (baseline)
- One index: minimal degradation (~5–15%)
- Over-indexed: measurable degradation (10–40% locally, 30–70% on Atlas/production)

**Latency (p99)**
- Over-indexed p99 is typically far worse than throughput suggests
- Lock contention under concurrent load creates latency spikes
- p99 degradation > throughput degradation is the overindexing signature

**Why it matters in production:**
- Write-heavy services (event streams, order processing, IoT) are hit hardest
- Index overhead compounds: 10k inserts/sec × 9 indexes = 90k B-tree writes/sec
- Unused indexes pay full write cost with zero read benefit
- Audit indexes regularly with `$indexStats` — drop indexes with zero accesses

**Remediation:** Use `db.usertable.aggregate([{$indexStats: {}}])` to identify
unused indexes, then drop them. One index removed = one full write path eliminated.
""",
                commands=[
                    ShellCommand("mdbpl compare --tags no-index,over-indexed"),
                ]
            ),
        ]
