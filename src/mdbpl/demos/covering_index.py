"""
Covering Index Demo — shows how including all projected fields in an index
eliminates the FETCH stage entirely, dropping totalDocsExamined to zero.

WORKFLOW PATTERN: covering / ixscan-only
  init → {status: 1} baseline (IXSCAN + FETCH) → {status: 1, score: 1} covering → compare

LLM ADAPTATION GUIDE:
  This demo benchmarks a filtered projection query where the baseline index
  satisfies the $match but not the $project, forcing a FETCH per matched doc.

  1. Query shape
     The query must have a $project that returns fewer fields than the document.
     The covering index must include ALL projected fields plus the filter field.
     The projection must exclude _id (with {_id: 0}) — see rule 2.
     Use $limit large enough to make FETCH costs measurable (500–2000 per operation).

  2. _id exclusion is required
     MongoDB always returns _id unless explicitly excluded. Without {_id: 0},
     MongoDB must FETCH the document to return _id, even if all other projected
     fields are in the index. Always use _id: 0 when demonstrating covering indexes.

  3. Covering index vs compound index
     compound-index: adds key columns to improve $match selectivity (fewer docs examined)
     covering-index: adds projected columns so the index alone satisfies the query
                     (totalDocsExamined drops to 0 — document I/O eliminated entirely)
     Both effects can stack on the same index.

  4. Scale guidance
     50k ecommerce docs with $limit 1000 per operation gives ~30% throughput improvement
     in a RAM-cached Docker environment. At production scale (large docs, cold cache),
     covering index improvements of 2–10x are common.
"""

from typing import List
from .base import Demo, DemoStep, ShellCommand, MongoshCommand

_PIPELINE = (
    '[{"$match": {"status": "shipped"}}, '
    '{"$project": {"_id": 0, "status": 1, "score": 1}}, '
    '{"$limit": 1000}]'
)

_EXPLAIN_JS = """
var r = db.usertable.explain("executionStats").aggregate([
  {$match: {status: "shipped"}},
  {$project: {_id: 0, status: 1, score: 1}},
  {$limit: 1000}
]);
var es = r.executionStats;
print("totalDocsExamined : " + es.totalDocsExamined);
print("totalKeysExamined : " + es.totalKeysExamined);
print("nReturned         : " + es.nReturned);
"""


class CoveringIndexDemo(Demo):
    """
    Demonstrates how including projected fields in the index eliminates the FETCH
    stage, dropping totalDocsExamined to zero for filtered projection queries.

    Pattern: {status: 1} index (IXSCAN + FETCH) → {status: 1, score: 1} covering index (IXSCAN only)
    Schema:  ecommerce — status-filtered API query returning status + score for 1000 documents.

    With {status: 1} index:
      IXSCAN finds 1000 keys → FETCH reads each full document → project status and score.
      totalDocsExamined = 1000.

    With {status: 1, score: 1} covering index:
      IXSCAN reads 1000 keys that already contain status + score.
      No document read needed. totalDocsExamined = 0.
    """

    id = "covering-index"
    title = "Covering Index: Eliminate the FETCH Stage"
    description = "Shows how projecting only indexed fields drops document reads to zero"
    markdown_file = ""

    def steps(self) -> List[DemoStep]:
        return [
            DemoStep(
                id="init",
                title="Initialize Dataset",
                description="Load 50,000 e-commerce records",
                markdown="""
## Initialize the Dataset

Load 50,000 e-commerce records using the `ecommerce` schema.

| Field | Type | Example |
|-------|------|---------|
| `customerId` | string | `"a3f9k2m1"` |
| `amount` | float 1–5000 | `1,249.99` |
| `status` | choice | `"pending"`, `"processing"`, `"shipped"`, `"delivered"`, `"cancelled"` |
| `region` | choice | `"NA"`, `"EU"`, `"APAC"`, `"SA"` |
| `score` | sequential int | `0`–`49999` |

**The query we're benchmarking — a common API read pattern:**

```javascript
db.usertable.aggregate([
  { $match: { status: "shipped" } },
  { $project: { _id: 0, status: 1, score: 1 } },
  { $limit: 1000 }
])
```

This query filters on `status` and returns only `status` and `score` — discarding
`customerId`, `amount`, `region`, and `createdAt`. Each operation returns 1000 documents,
giving 1000 FETCH operations if the index doesn't cover the projection.

The gap between "fields the query needs" and "fields the document contains" is where
a covering index eliminates document I/O entirely.
""",
                commands=[
                    ShellCommand("mdbpl init --scale 50k --schema ecommerce", collapse_output=False),
                ]
            ),

            DemoStep(
                id="create-status-index",
                title="Create Single-Field Index on status",
                description="Add {status: 1} — satisfies $match but forces a document FETCH for every result",
                markdown="""
## Baseline Index: {status: 1}

```javascript
db.usertable.createIndex({status: 1})
```

**What this index can and cannot do:**

| Question | Answer |
|----------|--------|
| Locate `status = "shipped"` without scanning all docs? | ✓ Yes — IXSCAN |
| Contains `score`? | ✗ No |
| Contains `_id`? | ✗ No (not needed — excluded with `_id: 0`) |

**The FETCH stage appears:**

After the IXSCAN finds 1000 matching keys, MongoDB must follow each document pointer
to retrieve `score`. This is the FETCH stage — a random read per result.

The full document (all 6 fields) is loaded, `status` and `score` are kept,
and `customerId`, `amount`, `region`, `createdAt` are discarded.

**Cost per query:** 1000 IXSCAN key reads + 1000 full document FETCHes.

**totalDocsExamined = 1000** — one document read per result.
""",
                commands=[
                    MongoshCommand("""
db.usertable.createIndex({status: 1});
print("✓ Created {status: 1} index");
print("");
print("Indexes on usertable:");
db.usertable.getIndexes().forEach(function(idx) {
    print("  " + idx.name + ": " + JSON.stringify(idx.key));
});
""")
                ]
            ),

            DemoStep(
                id="baseline",
                title="Baseline: IXSCAN + FETCH",
                description="Measure with {status: 1} — 1000 document reads per operation",
                markdown="""
## Baseline: {status: 1} — IXSCAN + FETCH

Run the status-filtered projection query with the single-field index.

**Execution plan:**

```
IXSCAN {status: 1}  →  FETCH (×1000 docs)  →  PROJECT  →  LIMIT 1000
```

MongoDB jumps to `status = "shipped"` in the index, collects 1000 matching keys,
then reads each of the 1000 full documents from the collection to extract `score`.

**The explain output confirms:**

- `totalDocsExamined` = 1000 (one document read per result)
- `totalKeysExamined` = 1000

Every result triggers a document read — even though only 2 of 6 fields are needed.

**Expected:** moderate throughput; throughput improves once FETCH is eliminated.
""",
                commands=[
                    ShellCommand(
                        f"mdbpl run --workload raw --pipeline '{_PIPELINE}' "
                        "--duration 15s --tag ixscan-fetch"
                    ),
                    MongoshCommand(_EXPLAIN_JS),
                ]
            ),

            DemoStep(
                id="create-covering-index",
                title="Create Covering Index {status: 1, score: 1}",
                description="Add score to the index — the index alone now answers the query, FETCH eliminated",
                markdown="""
## The Covering Index: {status: 1, score: 1}

Replace the single-field index with a compound index that contains every
field the query needs:

```javascript
db.usertable.dropIndexes();
db.usertable.createIndex({status: 1, score: 1})
```

**Why this covers the query:**

| Field | In index? | Needed by query? |
|-------|-----------|-----------------|
| `status` | ✓ first key | ✓ `$match` + `$project` |
| `score` | ✓ second key | ✓ `$project` |
| `_id` | — | ✗ excluded with `_id: 0` |

A query is *covered* when the index contains every field the query needs and
the projection excludes `_id` (or includes it in the index).

**The FETCH stage disappears:**

MongoDB reads 1000 index leaf nodes. Each node already contains `status` and
`score` — the document pointer is never followed.

**New execution plan:**

```
IXSCAN {status: 1, score: 1}  →  PROJECT  →  LIMIT 1000
(no FETCH stage)
```

**totalDocsExamined drops to 0.** The collection is never opened.

**Why `_id: 0` is required:**

MongoDB returns `_id` by default. Without `_id: 0`, MongoDB must FETCH every
document just to return `_id` — even if all other projected fields are covered.
The projection exclusion is what makes the query coverable.
""",
                commands=[
                    MongoshCommand("""
db.usertable.dropIndexes();
db.usertable.createIndex({status: 1, score: 1});
print("✓ Replaced with covering index {status: 1, score: 1}");
print("");
print("Indexes on usertable:");
db.usertable.getIndexes().forEach(function(idx) {
    print("  " + idx.name + ": " + JSON.stringify(idx.key));
});
"""),
                ]
            ),

            DemoStep(
                id="with-covering",
                title="With Covering Index: IXSCAN Only",
                description="Re-run the identical query — the collection is never opened",
                markdown="""
## With Covering Index: Zero Document Reads

Run the **exact same query** again. MongoDB now uses `{status: 1, score: 1}`
and returns 1000 results without reading a single document.

**Execution plan:**

```
IXSCAN {status: 1, score: 1}  →  PROJECT  →  LIMIT 1000
```

**Expected explain output:**

```
totalDocsExamined : 0       ← collection never opened
totalKeysExamined : 1000    ← only index reads
nReturned         : 1000
```

`totalDocsExamined: 0` is the definitive signature of a covered query.

**Expected improvements:**

- ~30% higher throughput (in-memory, small docs)
- Larger improvements at production scale: 2–10x for large docs or cold cache

**When covering index improvements exceed 2x:**

| Scenario | FETCH cost | Covering gain |
|----------|-----------|---------------|
| Small docs (150 bytes), in-memory | minimal | ~30% |
| Large docs (2 KB+), in-memory | moderate | 2–4x |
| Any size, cold cache (production) | disk I/O per doc | 3–10x |
| Both large docs AND cold cache | multiple disk reads | 5–20x |
""",
                commands=[
                    ShellCommand(
                        f"mdbpl run --workload raw --pipeline '{_PIPELINE}' "
                        "--duration 15s --tag covering-ixscan"
                    ),
                    MongoshCommand(_EXPLAIN_JS),
                ]
            ),

            DemoStep(
                id="compare",
                title="Compare: IXSCAN+FETCH vs Covering IXSCAN",
                description="Side-by-side: 1000 document reads vs zero document reads",
                markdown="""
## Results: IXSCAN+FETCH vs Covering IXSCAN

**The core change — totalDocsExamined:**

| State | totalDocsExamined | totalKeysExamined |
|-------|-------------------|-------------------|
| {status: 1} IXSCAN+FETCH | **1,000** | 1,000 |
| {status: 1, score: 1} Covering | **0** | 1,000 |

The index-key work is identical. The document reads drop to zero.

**What this means in practice:**

Covering index doesn't improve index traversal — it eliminates the step after it.
Every result that used to require "read the document, extract the field, discard
the rest" now reads those values directly from the index B-tree node.

**Distinct from the compound-index demo:**

- `compound-index`: adds equality/range keys to reduce *which* documents are matched
  (e.g., `totalDocsExamined` drops from 50,000 to 100)
- `covering-index`: adds projected keys so the matched documents are never read
  (e.g., `totalDocsExamined` drops from 1,000 to **0**)

Both optimizations can be combined: a compound index on `{status: 1, region: 1, score: 1}`
would both narrow the match (status + region) AND cover the projection (score).

**When to apply this pattern:**

Run `explain_query` on any slow projected query. If `totalDocsExamined` equals
`docsReturned`, every matched document is being fetched. Add the projected fields
to the index and exclude `_id` from the projection to eliminate all document I/O.
""",
                commands=[
                    ShellCommand("mdbpl compare --tags ixscan-fetch,covering-ixscan")
                ]
            ),
        ]
