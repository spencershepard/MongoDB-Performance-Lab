"""
Aggregation Pipeline Performance Demo — shows how a compound index eliminates
a blocking sort stage and reduces docs examined in a $match → $sort → $group pipeline.

WORKFLOW PATTERN: aggregation-pipeline / index-impact
  init → baseline (no relevant index) → create compound index → measure → compare

LLM ADAPTATION GUIDE:
  This demo benchmarks a $match + $sort + $group aggregation pipeline.
  To adapt to a user's schema:

  1. Field mapping
     region  → any low-cardinality equality field used in $match
     score   → any numeric/date field used in $sort
     rank    → any grouping field used in $group _id

  2. Pipeline shape
     The key pattern is: $match (equality) → $sort → $group
     The compound index {match_field: 1, sort_field: -1} eliminates the blocking sort
     and makes the $group stage work on pre-sorted input (streaming group).

  3. Index direction
     Match sort_field direction in the index key to the $sort direction.
     If $sort: {score: -1}, use score: -1 in the index.
     MongoDB can traverse the index in either direction, but explicit match avoids
     the planner choosing a backward scan.

  4. Collection / database
     Replace "usertable" / "perflab" with --collection <name> --database <name>
     on both `mdbpl init` and every `mdbpl run` command.
"""

from typing import List
from .base import Demo, DemoStep, ShellCommand, MongoshCommand


class AggregationPipelineDemo(Demo):
    """
    Demonstrates how a compound index transforms a blocking $match + $sort + $group
    pipeline into a streaming aggregation with zero in-memory sort work.

    Pattern: no-index baseline → compound index → comparison
    Schema:  videogame player profiles — regional leaderboard stats by rank tier.

    Without Index: Full collection scan → blocking in-memory sort on score → group.
    With Index:    IXSCAN on region → results already sorted by score → streaming group.

    The compound index {region: 1, score: -1} encodes both the $match selectivity
    and the $sort order, eliminating the most expensive stage in the pipeline.
    """

    id = "aggregation-pipeline"
    title = "Aggregation Pipeline Index Optimization"
    description = "Shows how a compound index eliminates blocking sort in $match → $sort → $group pipelines"
    markdown_file = ""

    def steps(self) -> List[DemoStep]:
        return [
            # STEP 1: Initialize 50k videogame player profiles.
            # 50k is large enough to make the blocking sort overhead clearly visible.
            DemoStep(
                id="init",
                title="Initialize Player Profile Dataset",
                description="Load 50,000 player profiles with the videogame schema",
                markdown="""
## Initialize Player Profile Data

Load 50,000 player profiles using the `videogame` schema.

**The query we're benchmarking:** A regional leaderboard stats endpoint returns
per-rank-tier statistics for a specific region:

```javascript
db.usertable.aggregate([
  {$match: {region: "NA"}},
  {$sort: {score: -1}},
  {$group: {
    _id: "$rank",
    topScore: {$first: "$score"},
    topPlayer: {$first: "$username"},
    playerCount: {$sum: 1}
  }}
])
```

**What this query answers:** "For each rank tier in region NA, who is the top-scoring
player and how many players are in that tier?"

This is a real-world reporting query: leaderboard dashboards, admin analytics, and
rank distribution charts all follow this $match → $sort → $group pattern. The
`$first` accumulator requires sorted input to be meaningful — without a sort,
"topPlayer" would be arbitrary.

**Why 50k documents?** The blocking in-memory sort is the expensive step. At 50k
docs, even a filtered $match result (~10k docs per region) requires sorting
thousands of documents in RAM before the $group can begin.
""",
                commands=[
                    ShellCommand("mdbpl init --scale 50k --schema videogame", collapse_output=False),
                ]
            ),

            # STEP 2: Baseline — no index on region or score.
            # The raw workload substitutes {{region:uniform}} per-operation from real values.
            DemoStep(
                id="baseline",
                title="Baseline Performance (No Relevant Index)",
                description="Benchmark the regional stats pipeline with no index on region or score",
                markdown="""
## Baseline: Regional Stats Pipeline Without a Supporting Index

Run the aggregation pipeline against the unindexed collection.

**What the workload does:**
- Each operation samples a random `region` from real collection values (uniform)
- Runs: `$match {region}` → `$sort {score: -1}` → `$group {_id: "$rank", ...}`
- Returns rank-tier stats for one region per operation

**Without a supporting index, MongoDB executes three expensive steps:**

1. **COLLSCAN:** Read all 50,000 player documents to find those in the target region
   (~10,000 per region at 5 regions × uniform distribution)

2. **Blocking SORT:** Sort all ~10,000 matching documents by score descending
   entirely in RAM before any `$group` work can begin.
   This is the most expensive step — O(n log n) in-memory work per query.

3. **$GROUP:** Iterate the sorted result, accumulate per-rank stats.
   Since input is sorted, `$first` is correct — but the sort cost was already paid.

**The "blocking" problem:** The `$sort` stage must consume and sort its entire
input before emitting a single document to `$group`. At ~10,000 docs per query,
this creates a memory spike and CPU burst on every request.

**Expected:** 50–200 ops/sec throughput, 10–50ms p50 latency.
""",
                commands=[
                    ShellCommand(
                        'mdbpl run --workload raw '
                        '--pipeline \'[{"$match": {"region": "{{region:uniform}}"}}, {"$sort": {"score": -1}}, {"$group": {"_id": "$rank", "topScore": {"$first": "$score"}, "topPlayer": {"$first": "$username"}, "playerCount": {"$sum": 1}}}]\' '
                        '--duration 15s --tag no-index'
                    )
                ]
            ),

            # STEP 3: Create the compound index following the ESR rule.
            # region (equality) first, score (sort) second — matches pipeline structure exactly.
            DemoStep(
                id="create-index",
                title="Create Compound Index for the Pipeline",
                description="Add {region: 1, score: -1} — matches the $match field and $sort direction",
                markdown="""
## Create a Pipeline-Supporting Compound Index

Create a compound index that matches the pipeline's `$match` field and `$sort` direction:

```javascript
db.usertable.createIndex({region: 1, score: -1})
```

**Why this index solves both stages simultaneously:**

The index key `{region: 1, score: -1}` stores entries ordered first by region, then
by score descending within each region. This layout directly mirrors what the pipeline needs:

| Pipeline Stage | What it needs | What the index provides |
|----------------|--------------|------------------------|
| `$match {region: "NA"}` | All docs with region=NA | Contiguous B-tree range — one seek |
| `$sort {score: -1}` | Docs sorted by score desc | Already stored in score desc order |
| `$group {_id: "$rank"}` | Sorted input for `$first` | Input arrives sorted — streaming group |

**The blocking sort disappears entirely.** MongoDB reads index entries for
`region="NA"` in score-descending order — there is nothing to sort. The `$group`
stage processes each document as it arrives, accumulating `$first` values as it
encounters each new rank value.

**Streaming vs blocking group:**
- Blocking group: consume all input, hold in memory, emit results after last doc
- Streaming group (with sorted input): emit a group result as soon as the sort key changes

At 50k documents with 5 regions, this transforms ~10,000-doc sort batches
into zero-sort streaming reads.
""",
                commands=[
                    MongoshCommand("""
db.usertable.createIndex({region: 1, "score": -1});
print("✓ Compound index created: {region: 1, score: -1}");
print("");
print("Indexes:");
db.usertable.getIndexes().forEach(function(idx) {
    print("  " + idx.name + ": " + JSON.stringify(idx.key));
});
""")
                ]
            ),

            # STEP 4: Re-run the IDENTICAL pipeline — same workload, new tag.
            DemoStep(
                id="with-index",
                title="Performance With Compound Index",
                description="Re-run the same aggregation pipeline — MongoDB now uses the compound index",
                markdown="""
## With Index: Regional Stats Pipeline in Milliseconds

Run the **exact same aggregation pipeline** again. MongoDB now uses `region_1_score_-1`.

**With the compound index, MongoDB executes a single streaming pass:**

1. **IXSCAN:** Seek to the first entry for `region="NA"` in the B-tree — O(log 50000) ≈ 16 comparisons
2. **Sequential scan:** Read index entries forward in score-descending order — no random I/O
3. **Streaming group:** Accumulate `topScore`, `topPlayer`, `playerCount` per rank on-the-fly
4. **Return:** Emit results as rank values change — no blocking, no in-memory buffer

**What changes in the execution plan:**
- `COLLSCAN` → `IXSCAN` — 50,000 docs examined becomes ~10,000 index entries
- `SORT` stage disappears from the plan entirely
- `$group` switches from blocking to streaming mode

**Expected improvements:**
- **10–30x higher throughput** — streaming eliminates the sort bottleneck
- **90%+ lower latency** — one B-tree seek + sequential read vs full scan + sort
- `docs_examined / docs_returned` drops significantly
- No in-memory sort stage in explain output
""",
                commands=[
                    ShellCommand(
                        'mdbpl run --workload raw '
                        '--pipeline \'[{"$match": {"region": "{{region:uniform}}"}}, {"$sort": {"score": -1}}, {"$group": {"_id": "$rank", "topScore": {"$first": "$score"}, "topPlayer": {"$first": "$username"}, "playerCount": {"$sum": 1}}}]\' '
                        '--duration 15s --tag with-agg-index'
                    )
                ]
            ),

            # STEP 5: Compare.
            DemoStep(
                id="compare",
                title="Compare Results",
                description="Side-by-side: blocking sort pipeline vs streaming indexed pipeline",
                markdown="""
## Results: Aggregation Pipeline Before and After Indexing

**Key Metrics:**

**Throughput (ops/sec)**
- No index: ~50–200 (COLLSCAN + blocking sort per query)
- With index: ~500–3,000 (IXSCAN + streaming group)
- **Expected: 10–30x improvement**

**Latency (ms)**
- No index: ~10–50ms (scan 50k docs, sort ~10k, group)
- With index: ~1–5ms (seek + stream ~10k sorted entries)
- **Expected: 90%+ reduction**

**Query Execution**
- No index: COLLSCAN → blocking SORT stage → GROUP
- With index: IXSCAN → streaming GROUP (no SORT stage)
- **Expected: SORT stage removed from explain plan**

**Why the improvement is larger than a simple index scan:**

A single-field index on `region` would eliminate the COLLSCAN but NOT the
blocking sort — MongoDB would still need to sort the ~10,000 matched documents
before grouping. The compound `{region: 1, score: -1}` index eliminates BOTH
the scan AND the sort in a single structure.

This is the key insight for aggregation pipeline optimization: the index must
cover the `$match` field AND match the `$sort` direction to achieve maximum benefit.
A partial index (only the `$match` field) gives a 2–5x improvement; the full
compound index gives 10–30x by eliminating the blocking sort.

**Production context:**
Analytics and reporting queries that aggregate large datasets are the most
CPU-intensive workloads on MongoDB. A blocking sort on 10,000 docs per query
at 100 QPS means sorting 1,000,000 documents per second. The compound index
reduces this to zero sort work, freeing CPU for other operations.
""",
                commands=[
                    ShellCommand("mdbpl compare --tags no-index,with-agg-index")
                ]
            ),
        ]
