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
     Replace --fields rank,region,... with the actual fields the user's application
     writes on insert. Include every field that has or will have an index.
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
    " --fields rank,region,character,weaponPrimary,level,xp,wins,kills,headshots"
    " --batch-size 1 --threads 8 --duration 30s"
)


class OverindexingDemo(Demo):
    """
    Demonstrates write performance degradation caused by maintaining too many indexes.

    Pattern: drop-indexes → baseline → add-one-index → measure → add-eight-more → measure → compare
    Schema:  videogame player profiles — indexes accumulate as game features launch over seasons.

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
                title="Initialize Player Profile Dataset",
                description="Load 50,000 player profiles as the write target",
                markdown="""
## Initialize Player Profile Data

Load 50,000 player profiles using the `videogame` schema. The insert workload will
write new player documents into this collection — we benchmark how quickly those
writes land when different numbers of secondary indexes must be maintained.

**Schema fields written on each insert:**
`rank`, `region`, `character`, `weaponPrimary`, `level`, `xp`, `wins`, `kills`, `headshots`

**The realistic scenario:** A game backend registers new players as they sign up.
Over several seasons, the team added indexes to support features as they launched:
- **Season 1:** `rank` index — matchmaking bracket queries
- **Season 2:** `region`, `character`, `weaponPrimary` — regional analytics, hero stats
- **Season 3:** `level`, `xp`, `wins`, `kills`, `headshots` — leaderboards and stat pages

Each index made sense for the feature it supported. Together, they force every new
player registration to update 9 B-trees instead of 1.

**Why 50k?** Index B-tree overhead only becomes measurable once index pages exceed
WiredTiger's warm cache. At 10k, all 9 index B-trees fit entirely in memory and
updates are essentially free. At 50k, pages start spilling under concurrent write
pressure, making the overhead visible. Scale to 100k–1M for more dramatic numbers
in production comparisons.

> **Note on local vs production numbers:** This demo runs inside Docker on localhost.
> In a production deployment — especially on a replica set requiring `w:majority`
> journal flushes, or a loaded Atlas cluster — the overindexing penalty is typically
> 2–5× larger than what you'll see here. The *relative* difference between runs is
> what matters.
""",
                commands=[
                    ShellCommand("mdbpl init --scale 50k --schema videogame", collapse_output=False),
                ]
            ),

            # STEP 2: Baseline — no secondary indexes
            DemoStep(
                id="baseline",
                title="Baseline Write Performance (No Secondary Indexes)",
                description="Drop all secondary indexes, then benchmark new player registrations",
                markdown="""
## Baseline: No Secondary Indexes

Drop all secondary indexes so only the required `_id` index remains.
This measures the true cost of the write itself, with zero index maintenance overhead.

**What MongoDB does on each player registration (no secondary indexes):**
1. Write player document to collection
2. Update `_id` B-tree (mandatory, always present)

**Expected:** High throughput, low latency — writes go almost directly to WiredTiger.
The `_id` index update is unavoidable and represents the theoretical minimum write cost.
8 threads will be competing for write locks, but with only one B-tree to update they
rarely block each other.
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

            # STEP 3: Add the first realistic index (rank — matchmaking)
            DemoStep(
                id="one-index",
                title="Write Performance With One Index (Rank)",
                description="Add the matchmaking index on rank, re-run the same workload",
                markdown="""
## Season 1: One Index for Matchmaking

The matchmaking system needs to find players at the same rank tier. The team creates
an index on `rank` — a completely reasonable decision.

**What MongoDB does on each insert (1 secondary index):**
1. Write player document to collection
2. Update `_id` B-tree
3. Update `rank` B-tree ← new cost

The overhead of one index is modest (5–15%) because WiredTiger batches index updates
efficiently. This step establishes that **some** indexing is acceptable and necessary;
the problem emerges when indexes multiply across every queryable field.

**Expected:** Slight throughput reduction vs baseline — typically 5–15% at this scale.
WiredTiger handles single-index contention well under 8 threads.
""",
                commands=[
                    MongoshCommand("""
db.usertable.createIndex({rank: 1});
print("✓ Created index on rank (matchmaking)");
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

            # STEP 4: Add 8 more indexes as features accumulated over seasons
            DemoStep(
                id="add-indexes",
                title="Seasons 2 & 3: Add 8 More Indexes (9 Total)",
                description="Index every queryable field as features launched — a common accumulation pattern",
                markdown="""
## Seasons 2 & 3: Indexes Accumulate

As new game features shipped over two seasons, each team added the indexes their
feature needed. No single decision was wrong in isolation.

**Indexes added across Season 2 and Season 3:**
| Index | Field | Feature that justified it |
|-------|-------|--------------------------|
| `region_1` | region | Regional server routing and analytics |
| `character_1` | character | Hero usage stats and balance dashboard |
| `weaponPrimary_1` | weaponPrimary | Weapon popularity and drop-rate tuning |
| `level_1` | level | Level-bracket matchmaking (PvE content) |
| `xp_1` | xp | Progression leaderboard |
| `wins_1` | wins | Win-rate leaderboard and ranked rewards |
| `kills_1` | kills | Eliminations leaderboard |
| `headshots_1` | headshots | Precision stat page and achievement tracking |

Each index supported a feature players actively use. Together they create
**9x write amplification**: every new player registration now updates 9 B-trees.

At 8 concurrent registration threads, each insert competes for write locks on
9 separate B-tree structures. Threads that would write in parallel instead
serialise on index page locks, compounding the latency beyond simple multiplication.
""",
                commands=[
                    MongoshCommand("""
db.usertable.createIndex({region: 1});
db.usertable.createIndex({character: 1});
db.usertable.createIndex({weaponPrimary: 1});
db.usertable.createIndex({level: 1});
db.usertable.createIndex({xp: 1});
db.usertable.createIndex({wins: 1});
db.usertable.createIndex({kills: 1});
db.usertable.createIndex({headshots: 1});

print("✓ Created 8 additional indexes");
print("");
print("All indexes (" + db.usertable.getIndexes().length + " total):");
db.usertable.getIndexes().forEach(function(idx) {
    print("  " + idx.name + ": " + JSON.stringify(idx.key));
});
""", collapse_output=False),
                ]
            ),

            # STEP 5: Measure write performance with all 9 indexes
            DemoStep(
                id="over-indexed",
                title="Write Performance With 9 Indexes",
                description="Run the identical workload — every registration now maintains 9 B-trees",
                markdown="""
## Over-Indexed: The Registration Cost Revealed

Run the exact same insert workload against the fully-indexed collection.

**What MongoDB does on each player registration (9 secondary indexes):**
1. Write player document to collection
2. Update `_id` B-tree
3. Update `rank` B-tree
4. Update `region` B-tree
5. Update `character` B-tree
6. Update `weaponPrimary` B-tree
7. Update `level` B-tree
8. Update `xp` B-tree
9. Update `wins` B-tree
10. Update `kills` B-tree
11. Update `headshots` B-tree

Under 8 concurrent threads, each insert acquires write locks on 9 B-trees.
Threads frequently collide on the same index pages, serialising what would
otherwise be parallel writes. Lock wait time compounds beyond simple multiplication.

**Expected:** Significant throughput drop and latency increase vs baseline.
The p99 latency spike is often more dramatic than the throughput drop — this is
the overindexing signature: tail latency degrades faster than mean throughput.
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
## Results: The True Cost of Feature-Driven Index Accumulation

**Key Metrics to Watch:**

**Throughput (ops/sec)**
- No index: maximum registration throughput (baseline)
- One index (rank): minimal degradation (~5–15%)
- Over-indexed (9 indexes): measurable degradation (10–40% locally, 30–70% on Atlas/production)

**Latency (p99)**
- Over-indexed p99 is typically far worse than throughput suggests
- Lock contention under concurrent load creates latency spikes
- **p99 degradation > throughput degradation is the overindexing signature**

**Why it matters in production:**
- A game launch with 50k registrations/hour × 9 indexes = 450k B-tree writes/hour
- Spike events (new season launch, free weekend) amplify contention dramatically
- Indexes on `character`, `weaponPrimary`, `headshots` are never used for writes — but
  every new registration still pays their full update cost
- Unused indexes pay full write cost with zero read benefit

**Remediation:**
```javascript
db.usertable.aggregate([{$indexStats: {}}])
```
Identify indexes with `accesses.ops: 0` — these are candidates for removal.
One index dropped = one full B-tree update eliminated from every write path.
Consider a **compound index** `{rank: 1, region: 1}` to serve both matchmaking
queries with a single B-tree, replacing two single-field indexes.
""",
                commands=[
                    ShellCommand("mdbpl compare --tags no-index,over-indexed"),
                ]
            ),
        ]
