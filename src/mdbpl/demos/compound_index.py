"""
Compound Index Demo — two single-field indexes vs one compound index on a multi-predicate query.

WORKFLOW PATTERN: compound-index / multi-predicate
  init → two single-field indexes (baseline) → compound index → compare

LLM ADAPTATION GUIDE:
  This demo benchmarks a query with two equality predicates + a sort using the raw workload.
  To adapt to a user's schema:

  1. Field mapping
     rank / region → any two low-cardinality equality fields (status, category, tier, region)
     score         → any numeric/date field used for ordering results
     Replace in both --pipeline strings and createIndex calls.

  2. Collection / database
     Replace "usertable" / "perflab" with --collection <name> --database <name>
     on both `mdbpl init` and every `mdbpl run` command.

  3. Scale
     50k is the sweet spot: large enough to make AND_HASH visible, small enough to run fast.
     Use --scale 100k for more dramatic latency numbers.

  4. ESR rule
     For compound indexes: Equality fields first, Sort field last.
     {rank: 1, region: 1, score: -1} follows ESR — rank and region are equality predicates,
     score is the sort direction. This eliminates the in-memory sort stage entirely.

  5. Tagging rule
     Every `mdbpl run` must have --tag.
     Never re-use a tag across different configurations.
"""

from typing import List
from .base import Demo, DemoStep, ShellCommand, MongoshCommand


class CompoundIndexDemo(Demo):
    """
    Demonstrates why a compound index outperforms two separate single-field indexes
    on a multi-predicate query.

    Pattern: two-index baseline → compound index → comparison
    Schema:  videogame player profiles — rank + region equality predicates, sort by score.

    Two Single Indexes: MongoDB may use AND_HASH or AND_SORTED to intersect the two index
    results in memory, or choose one index and filter on the other in-memory. Either path
    requires examining far more documents than the result set.

    Compound Index: B-tree encodes both predicates — MongoDB jumps directly to the exact
    (rank, region) combination, reads pre-sorted score values, and returns results with
    no in-memory work.
    """

    id = "compound-index"
    title = "Compound Index vs Two Single-Field Indexes"
    description = "Shows why a compound index outperforms two separate single-field indexes on multi-predicate queries"
    markdown_file = ""

    def steps(self) -> List[DemoStep]:
        return [
            # STEP 1: Load 50k videogame player profiles.
            # 50k is large enough to make AND_HASH overhead visible in throughput numbers.
            DemoStep(
                id="init",
                title="Initialize Player Profile Dataset",
                description="Load 50,000 player profiles with the videogame schema",
                markdown="""
## Initialize Player Profile Data

Load 50,000 player profiles using the `videogame` schema.

| Field | Type | Example |
|-------|------|---------|
| `rank` | choice | `"Iron"`, `"Bronze"`, `"Silver"`, `"Gold"`, `"Platinum"`, `"Diamond"`, `"Master"` |
| `region` | choice | `"NA"`, `"EU"`, `"APAC"`, `"SA"` |
| `score` | int (sequential) | 0–49,999 — cumulative tournament score |
| `playerId` / `username` | string | player identifiers |
| `level`, `wins`, `kills`, `kdr` | int/float | game performance stats |

**The query we're benchmarking:** A leaderboard endpoint returns the top 10 highest-scoring
players in a specific rank tier and region, e.g. "top Diamond players in NA":

```javascript
db.usertable.aggregate([
  {$match: {rank: "Diamond", region: "NA"}},
  {$sort: {score: -1}},
  {$limit: 10}
])
```

**Why this query matters:** Rank + region combinations are the most common leaderboard
filter pattern — players compare themselves against peers in their tier and geography.
Both predicates together select ~1–3% of the collection (7 ranks × 4 regions = 28 buckets),
but single-field indexes on each can't efficiently serve this access pattern.
""",
                commands=[
                    ShellCommand("mdbpl init --scale 50k --schema videogame", collapse_output=False),
                ]
            ),

            # STEP 2: Create two single-field indexes — the intuitive but suboptimal approach.
            # Most developers reach for this first: "I query on rank and region, so index both."
            DemoStep(
                id="two-indexes",
                title="Create Two Single-Field Indexes",
                description="Add individual indexes on rank and region — the intuitive first approach",
                markdown="""
## Two Single-Field Indexes: The Intuitive (But Suboptimal) Approach

Create one index per predicate field — a common first instinct:

```javascript
db.usertable.createIndex({rank: 1})
db.usertable.createIndex({region: 1})
```

**What MongoDB does with two single-field indexes:**

MongoDB's query planner has two options when two indexes are available for a multi-predicate query:

1. **Use one index, filter in-memory on the other:**
   - Use `rank_1` to find all Diamond players (~7,100 docs at 1/7 selectivity)
   - Evaluate `region: "NA"` against each one in memory (~1,800 pass)
   - Sort 1,800 docs by score in memory
   - Return top 10

2. **Index intersection (AND_HASH / AND_SORTED):**
   - Use `rank_1` → collect 7,100 `_id` values for Diamond players
   - Use `region_1` → collect 12,500 `_id` values for NA players
   - Hash-join the two sets → ~1,800 matching `_id` values
   - Fetch those 1,800 documents, sort by score, return top 10

Either path examines **700× more documents than it returns** and requires an expensive
in-memory sort. The query planner picks whichever plan wins the trial run — but neither
is efficient.
""",
                commands=[
                    MongoshCommand("""
db.usertable.createIndex({rank: 1});
db.usertable.createIndex({region: 1});
print("✓ Two single-field indexes created");
print("");
print("Indexes:");
db.usertable.getIndexes().forEach(function(idx) {
    print("  " + idx.name + ": " + JSON.stringify(idx.key));
});
""")
                ]
            ),

            # STEP 3: Baseline benchmark — raw workload with template variables.
            # Pipeline mirrors the real application query exactly.
            DemoStep(
                id="baseline",
                title="Baseline Performance (Two Single-Field Indexes)",
                description="Benchmark the leaderboard query with rank_1 + region_1 indexes",
                markdown="""
## Baseline: Multi-Predicate Query With Two Single-Field Indexes

Run the leaderboard aggregation against the two single-field indexes.

**What the workload does:**
- Each operation samples a random `rank` (uniform) and `region` (uniform) from real collection values
- Runs: `$match {rank, region}` → `$sort {score: -1}` → `$limit 10`
- This is the exact query the application would issue for a leaderboard page

**Expected behavior with two single-field indexes:**
- MongoDB picks `rank_1` (higher selectivity) and evaluates `region` in-memory, OR uses
  index intersection with AND_HASH — either way, thousands of docs examined per query
- In-memory sort on `score` for the filtered result set
- High `docs_examined / docs_returned` ratio (~700:1)

**Expected:** 200–500 ops/sec throughput, 5–15ms p50 latency.
""",
                commands=[
                    ShellCommand(
                        'mdbpl run --workload raw '
                        '--pipeline \'[{"$match": {"rank": "{{rank:uniform}}", "region": "{{region:uniform}}"}}, {"$sort": {"score": -1}}, {"$limit": 10}]\' '
                        '--duration 15s --tag two-indexes'
                    )
                ]
            ),

            # STEP 4: Drop the two indexes and create the compound index.
            # ESR rule: rank (equality) → region (equality) → score (sort, descending).
            DemoStep(
                id="create-compound-index",
                title="Replace With a Compound Index",
                description="Drop both single-field indexes and create one ESR compound index",
                markdown="""
## Compound Index: One Index, Three Fields, Zero In-Memory Work

Drop the two single-field indexes and replace them with a single compound index:

```javascript
db.usertable.createIndex({rank: 1, region: 1, score: -1})
```

**The ESR Rule** (Equality → Sort → Range):
- **E**quality fields first: `rank` and `region` — both are equality predicates (`$match` with exact values)
- **S**ort field last: `score: -1` — matches the `$sort` direction exactly

**What MongoDB does with the compound index:**
1. B-tree lookup: jump directly to the `(rank="Diamond", region="NA")` leaf node — O(log n)
2. Sequential scan: read forward through pre-sorted score values (descending because `score: -1`)
3. Stop at 10 — no further work needed

**Why docs_examined equals docs_returned:**
The compound index encodes all three query dimensions. MongoDB reads exactly the documents
it returns — no filtering, no sorting, no extra fetches.

**Storage cost:** ~3–5 MB for 50,000 documents. Worth it: a single compound index replaces
two indexes (net storage saving) while delivering far superior query performance.
""",
                commands=[
                    MongoshCommand("""
db.usertable.dropIndex({rank: 1});
db.usertable.dropIndex({region: 1});
db.usertable.createIndex({rank: 1, region: 1, score: -1});
print("✓ Compound index created: {rank: 1, region: 1, score: -1}");
print("");
print("Indexes:");
db.usertable.getIndexes().forEach(function(idx) {
    print("  " + idx.name + ": " + JSON.stringify(idx.key));
});
""")
                ]
            ),

            # STEP 5: Re-run the IDENTICAL workload — same pipeline, same duration, new tag.
            DemoStep(
                id="with-compound-index",
                title="Performance With Compound Index",
                description="Re-run the same leaderboard workload — MongoDB now uses the compound index",
                markdown="""
## With Compound Index: Leaderboard Queries in ~1ms

Run the **exact same workload** again. MongoDB now uses `rank_1_region_1_score_-1`.

**With the compound index, MongoDB performs a targeted IXSCAN:**
1. Seek to `(rank="Diamond", region="NA")` in the B-tree — ~15 comparisons for 50k docs
2. Read leaf nodes in descending score order — already sorted, no in-memory work
3. Return after 10 documents — traversal stops immediately at the limit

**Docs examined = docs returned:**
The query becomes a **covered index scan** for the sort portion — all fields the query
touches (`rank`, `region`, `score`) are encoded in the index. MongoDB reads 10 index
entries and fetches 10 documents. Nothing more.

**Expected improvements over two-index baseline:**
- **5–15x higher throughput** — compound index eliminates AND_HASH overhead and in-memory sort
- **80–95% lower latency** — single seek + 10 leaf reads vs thousands of doc evaluations
- `docs_examined / docs_returned` ratio drops to ~1:1
""",
                commands=[
                    ShellCommand(
                        'mdbpl run --workload raw '
                        '--pipeline \'[{"$match": {"rank": "{{rank:uniform}}", "region": "{{region:uniform}}"}}, {"$sort": {"score": -1}}, {"$limit": 10}]\' '
                        '--duration 15s --tag compound-index'
                    )
                ]
            ),

            # STEP 6: Compare the two runs.
            DemoStep(
                id="compare",
                title="Compare Results",
                description="Side-by-side: two single-field indexes vs one compound index",
                markdown="""
## Results: Two Single-Field Indexes vs One Compound Index

**Key Metrics:**

**Throughput (ops/sec)**
- Two indexes: ~200–500 (AND_HASH intersection + in-memory sort overhead)
- Compound index: ~2,000–5,000 (direct B-tree seek, no extra work)
- **Expected: 5–15x improvement**

**Latency (ms)**
- Two indexes: ~5–15ms (index intersection + sort)
- Compound index: ~0.5–2ms (seek + limit scan)
- **Expected: 80–95% reduction**

**Query Execution**
- Two indexes: COLLSCAN or AND_HASH — thousands of docs examined per query
- Compound index: IXSCAN — docs examined ≈ docs returned (near 1:1 ratio)

**Why this matters in production:**

A leaderboard endpoint on a live game may receive thousands of requests per second
with varied rank/region combinations. The two-index plan forces MongoDB to evaluate
thousands of documents per request — CPU, I/O, and memory all spike under load.

The compound index turns each query into a constant-time operation: seek + read 10
entries. Throughput scales linearly with hardware; latency stays flat regardless of
collection size.

**The ESR rule (Equality → Sort)** ensures that the compound index key ordering
matches both the filter selectivity and the sort direction simultaneously — this is
why a single well-designed compound index outperforms multiple single-field indexes
on multi-predicate queries with sorting.
""",
                commands=[
                    ShellCommand("mdbpl compare --tags two-indexes,compound-index")
                ]
            ),
        ]
