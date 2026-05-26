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
    Demonstrates dramatic read performance improvement from a single well-chosen index.

    Pattern: baseline → optimization → measurement → comparison
    Schema:  videogame player profiles — score field represents cumulative tournament score.

    Without Index: Full collection scan + in-memory sort for every leaderboard bracket query.
    With Index:    B-tree index scan — skips non-matching players entirely, pre-sorted.
    """

    id = "index-performance"
    title = "Index Performance Impact"
    description = "Demonstrates dramatic read performance improvement with proper indexing"
    markdown_file = ""

    def steps(self) -> List[DemoStep]:
        return [
            # STEP 1: Initialize test data
            # Pattern: mdbpl init --schema <preset> loads the dataset with the chosen schema.
            # score (0..record_count-1) is always sequential — safe to use as range target.
            DemoStep(
                id="init",
                title="Initialize Player Profile Dataset",
                description="Load 10,000 player profiles with the videogame schema",
                markdown="""
## Initialize Player Profile Data

Load 10,000 player profiles using the `videogame` schema. Each document represents
a player with realistic game stats:

| Field | Type | Example |
|-------|------|---------|
| `playerId` | string | `"a3f9k2m1p8q7"` |
| `username` | string | `"xr4k9b2m"` |
| `rank` | choice | `"Diamond"` |
| `region` | choice | `"NA"`, `"EU"`, `"APAC"` |
| `character` | choice | `"Mage"`, `"Warrior"`, … |
| `level` | int | 1–100 |
| `xp` | int | 0–1,000,000 |
| `wins` / `kills` / `kdr` | int/float | game performance stats |
| `score` | int (sequential) | 0–9,999 — cumulative tournament score |

**The query we're benchmarking:** The game backend serves a leaderboard feature that
shows players competing for prize tiers. Each tier covers a score bracket, e.g.
`{score: {$gte: 3000, $lt: 5000}}`. Without an index, every page load scans all
10,000 profiles to find the ~2,000 players in that tier, then sorts them in memory.

**Why 10k documents?** Collection scans become dramatically slower as datasets grow,
while index lookups stay O(log n). Even at 10k the difference is 10–100×; at 1M it's
larger still.
""",
                commands=[
                    # mdbpl init --schema videogame generates player profiles with ObjectId _id.
                    # To use a different preset: --schema ecommerce | iot | events
                    # To use a custom schema: --schema path/to/schema.json
                    ShellCommand("mdbpl init --scale 10k --schema videogame", collapse_output=False),
                ]
            ),

            # STEP 2: Baseline — always measure BEFORE the optimization.
            # The tag ("baseline") must be passed to mdbpl compare later.
            # To benchmark a different field: add --field <name> --range-size <N>
            DemoStep(
                id="baseline",
                title="Baseline Performance (No Index on Score)",
                description="Run leaderboard bracket queries against the unindexed score field",
                markdown="""
## Baseline: Leaderboard Queries Without an Index

Run the `range-scan` workload against the unindexed `score` field to establish baseline.

**What the workload does:**
- Queries a random 2,000-point score bracket: `{score: {$gte: N, $lt: N+2000}}`
- Sorts results by score (ascending) and returns the top 100 players
- This mirrors a real leaderboard page: "show me the top 100 players in prize tier 3"

**Without an index, MongoDB performs a COLLSCAN:**
1. Reads all 10,000 player documents from disk
2. Evaluates each document's `score` field against the range predicate
3. Collects ~2,000 matching players
4. **Sorts the 2,000 results in memory** (most expensive step)
5. Returns the top 100

Every leaderboard page load triggers this full-collection scan. At 100k+ players
in production, this becomes the primary bottleneck.

**Expected:** 10–50 ops/sec throughput, 50–200ms latency, high `collection_scans` metric.
""",
                commands=[
                    # Pattern: Run benchmark with descriptive tag — tag used in compare step.
                    # Default --field score --range-size 2000 --sort-field score matches init schema.
                    ShellCommand("mdbpl run --workload range-scan --duration 15s --tag baseline")
                ]
            ),

            # STEP 3: Apply the optimization.
            # Use MongoshCommand for DDL: createIndex, dropIndex, collMod, etc.
            DemoStep(
                id="create-index",
                title="Create Index on Score Field",
                description="Add a single ascending index on the tournament score field",
                markdown="""
## Create a Leaderboard Index

Create a **single-field ascending index** on `score` — the field driving every leaderboard query:

```javascript
db.usertable.createIndex({score: 1})
```

**What MongoDB builds:** A B-tree structure where each node stores a score value alongside
a pointer to the matching document. Values are stored in sorted order, so traversal is
already ordered — no in-memory sort needed.

**How it transforms the query plan:**

| Step | Without Index | With Index |
|------|--------------|------------|
| Find score=3000 | Scan all 10,000 docs | B-tree lookup — O(log n) |
| Traverse range | Evaluate every doc | Sequential leaf scan |
| Sort results | Sort 2,000 docs in RAM | Already sorted in index |
| Return 100 | Slice after sort | Stop traversal at 100 |

**Storage cost:** ~1–2 MB for 10,000 documents. The read latency reduction far
outweighs the small storage and write overhead at this scale.
""",
                commands=[
                    # Pattern: Create indexes using MongoshCommand.
                    # Use ascending (1) for range queries with ascending sort order.
                    # Use descending (-1) for "top N" queries (e.g., highest scores first).
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

            # STEP 4: Re-run the IDENTICAL workload — only the tag changes.
            # All other flags must match step 2 exactly for apples-to-apples comparison.
            DemoStep(
                id="with-index",
                title="Performance With Index",
                description="Re-run the same leaderboard workload — now MongoDB uses the B-tree",
                markdown="""
## With Index: Leaderboard Queries in Milliseconds

Run the **exact same workload** again. MongoDB now uses the `score_1` index.

**With the index, MongoDB performs an IXSCAN:**
1. B-tree lookup — jump directly to `score=3000` in O(log 10000) ≈ 13 comparisons
2. Sequential leaf traversal — scan forward until `score=5000`
3. Return first 100 — stop as soon as the limit is reached
4. **No in-memory sort** — index leaves are already in ascending score order

**Why the improvement is so large:**

- **Docs examined:** ~100 instead of 10,000 — 100x reduction
- **Sort eliminated:** results arrive pre-ordered from the B-tree
- **I/O reduced:** only index pages touched for most queries; document pages only for the 100 returned

**Expected improvements:**
- **50–100x higher throughput** — expect 1,000–5,000 ops/sec (vs 10–50)
- **95%+ lower latency** — expect 1–5ms per query (vs 50–200ms)
- `collection_scans` drops to near zero; `index_scans` dominates
""",
                commands=[
                    # Pattern: Same benchmark parameters, different tag.
                    ShellCommand("mdbpl run --workload range-scan --duration 15s --tag with-index")
                ]
            ),

            # STEP 5: Compare — pass the tags from steps 2 and 4 in order (baseline first).
            DemoStep(
                id="compare",
                title="Compare Results",
                description="Side-by-side comparison: unindexed vs indexed leaderboard queries",
                markdown="""
## Results: Leaderboard Queries Before and After Indexing

**Key Metrics:**

**Throughput (ops/sec)**
- Baseline: ~10–50 (full collection scan per query)
- With Index: ~1,000–5,000 (B-tree lookup per query)
- **Expected: 50–100x improvement**

**Latency (ms)**
- Baseline: ~50–200ms (scan + in-memory sort)
- With Index: ~1–5ms (index traversal)
- **Expected: 95%+ reduction**

**Query Execution**
- Baseline: COLLSCAN — 10,000 docs examined, 2,000 sorted in memory
- With Index: IXSCAN — ~100 docs examined, zero in-memory sort
- **Expected: 100x reduction in docs_examined**

**Production context:**
At 1M players (realistic for a live game), a COLLSCAN leaderboard query examines
1,000,000 documents per page load. The `score_1` index keeps query time at ~5ms
regardless of collection size — the B-tree depth grows by one level per 10x increase
in document count. Indexing `score` is the single highest-leverage optimization
for this access pattern.
""",
                commands=[
                    ShellCommand("mdbpl compare --tags baseline,with-index")
                ]
            )
        ]
