"""
$lookup Performance Demo — shows the dramatic impact of indexing the foreign field
in a $lookup join between two collections.

WORKFLOW PATTERN: lookup / join-index
  init customers → init orders → baseline (NestedLoopJoin) → index foreignField → measure → compare

LLM ADAPTATION GUIDE:
  This demo benchmarks a $lookup aggregation joining orders to customers.
  To adapt to a user's schema:

  1. Collection mapping
     customers   → any "small" reference collection (users, products, stores)
     orders      → any "large" fact collection that references the small one
     customerId  → the shared join field name (userId, productId, storeId, etc.)

  2. Index placement
     The index must be on the FOREIGN (from) collection's join field:
       db.<from_collection>.createIndex({<foreignField>: 1})
     Without this index, MongoDB does a full scan of the from collection
     for every document in the outer collection.

  3. Scale guidance
     10k customers + 100k orders is a realistic ratio (10:1 orders-per-customer).
     The impact scales with the from-collection size: at 10k customers, each
     NestedLoopJoin scan reads 10k docs; at 100k, it reads 100k per joined doc.

  4. Pipeline shape
     The $lookup must appear early in the pipeline — a preceding $match that
     filters the outer collection reduces the number of joins performed.
     Always add $limit after $lookup to bound result set size.
"""

from typing import List
from .base import Demo, DemoStep, ShellCommand, MongoshCommand


class LookupDemo(Demo):
    """
    Demonstrates how indexing the foreign field in a $lookup join transforms
    NestedLoopJoin (full from-collection scan per doc) into IndexedLoopJoin
    (single B-tree seek per doc).

    Pattern: two-collection init → no-index baseline → index foreignField → comparison
    Schema:  customers (10k) joined to orders (100k) on customerId.

    Without Index: For each of the 100 orders in the batch, scan all 10k customers
    to find the matching customer → 100 × 10,000 = 1,000,000 reads per operation.

    With Index:    For each order, B-tree seek on customers.customerId → 100 seeks,
    ~100 reads total per operation — 10,000x fewer document reads.
    """

    id = "lookup"
    title = "$lookup Join Index Optimization"
    description = "Shows how indexing the foreign field eliminates NestedLoopJoin in $lookup pipelines"
    markdown_file = ""

    def steps(self) -> List[DemoStep]:
        return [
            # STEP 1a: Load the customers (reference) collection first.
            # orders.customerId references customers.customerId — must exist before orders are loaded.
            DemoStep(
                id="init-customers",
                title="Initialize Customers Collection",
                description="Load 10,000 customer records — the reference side of the join",
                markdown="""
## Initialize the Customers Collection

Load 10,000 customer records using the `customers` schema.

| Field | Type | Example |
|-------|------|---------|
| `customerId` | string (sequential) | `"cust_000042"` |
| `name` | string | `"xr4k9b2m"` |
| `email` | string | `"a3f9k2m1p8q7"` |
| `region` | choice | `"NA"`, `"EU"`, `"APAC"`, `"SA"` |
| `tier` | choice | `"Bronze"`, `"Silver"`, `"Gold"`, `"Platinum"` |

`customerId` is a **formatted sequential string** — `"cust_000000"` through
`"cust_009999"`. This deterministic format allows the `orders` generator to
sample real customer IDs and guarantee every order joins to an existing customer.

**Load customers first** — the orders generator samples `customerId` values from
this collection at load time.
""",
                commands=[
                    ShellCommand(
                        "mdbpl init --scale 10k --schema customers --collection customers",
                        collapse_output=False,
                    ),
                ]
            ),

            # STEP 1b: Load orders, which references customers.customerId.
            DemoStep(
                id="init-orders",
                title="Initialize Orders Collection",
                description="Load 100,000 orders — each references a real customer ID",
                markdown="""
## Initialize the Orders Collection

Load 100,000 orders using the `orders` schema. The generator samples real
`customerId` values from the `customers` collection loaded in the previous step.

| Field | Type | Example |
|-------|------|---------|
| `customerId` | ref → customers.customerId | `"cust_004291"` |
| `amount` | float 1–5000 | `1,249.99` |
| `status` | choice | `"pending"`, `"shipped"`, `"delivered"`, … |
| `productId` | string | `"a3f9k2m1p8q7"` |
| `createdAt` | date | recent UTC datetime |

Every `customerId` in the orders collection is guaranteed to match an existing
customer — the generator uses uniform random sampling from the customer ID pool,
giving each customer approximately 10 orders on average.

**The query we're benchmarking:**

```javascript
db.orders.aggregate([
  {$match: {status: <value>}},
  {$lookup: {
    from: "customers",
    localField: "customerId",
    foreignField: "customerId",
    as: "customer"
  }},
  {$limit: 100}
])
```

This is the classic "enrich order with customer data" query — one of the most
common MongoDB aggregation patterns in e-commerce and SaaS applications.
""",
                commands=[
                    ShellCommand(
                        "mdbpl init --scale 100k --schema orders --collection orders",
                        collapse_output=False,
                    ),
                ]
            ),

            # STEP 2: Baseline — no index on customers.customerId.
            DemoStep(
                id="baseline",
                title="Baseline Performance (No Index on customers.customerId)",
                description="Benchmark the $lookup pipeline with NestedLoopJoin — full customer scan per order",
                markdown="""
## Baseline: $lookup With NestedLoopJoin

Run the order-enrichment aggregation with no index on `customers.customerId`.

**What the workload does:**
- Each operation filters orders by a random `status` value (uniform sampling)
- Joins each matching order to its customer via `$lookup`
- Returns the first 100 enriched orders

**Without an index on customers.customerId, MongoDB uses NestedLoopJoin:**

For each of the ~100 orders processed:
1. Scan all 10,000 customer documents sequentially
2. Compare each customer's `customerId` to the order's `customerId`
3. Return the one matching customer

**Cost per operation: ~100 orders × 10,000 customer reads = 1,000,000 document reads**

This is the "N+1 query problem" at the database level — each join requires a
full collection scan. Unlike application-level N+1 (N separate queries), this
happens inside a single aggregation pipeline but the cost is identical.

At 10k customers the penalty is significant. At 100k customers (realistic for a
real application), each order join would read 100,000 documents — making the
pipeline effectively unusable at scale.

**Expected:** 5–30 ops/sec, 50–500ms p50 latency.
""",
                commands=[
                    ShellCommand(
                        'mdbpl run --workload raw --collection orders '
                        '--pipeline \'[{"$match": {"status": "{{status:uniform}}"}}, {"$lookup": {"from": "customers", "localField": "customerId", "foreignField": "customerId", "as": "customer"}}, {"$limit": 100}]\' '
                        '--duration 15s --tag no-lookup-index'
                    )
                ]
            ),

            # STEP 3: Add the index on the foreign field.
            DemoStep(
                id="create-index",
                title="Index the Foreign Field on customers",
                description="Add {customerId: 1} to customers — the join target for every $lookup",
                markdown="""
## Index the $lookup Foreign Field

Create an index on the field that $lookup uses to find matching customer documents:

```javascript
db.customers.createIndex({customerId: 1})
```

**Why this index transforms the join strategy:**

Without the index, MongoDB has no way to find a specific `customerId` in the
customers collection without reading every document. With the index, MongoDB
can jump directly to the matching customer in O(log 10000) ≈ 13 comparisons.

**The join strategy changes from NestedLoopJoin to IndexedLoopJoin:**

| Strategy | Per-order work | 100 orders cost |
|----------|---------------|-----------------|
| NestedLoopJoin (no index) | Scan 10,000 customers | 1,000,000 reads |
| IndexedLoopJoin (with index) | 1 B-tree seek | ~100 reads |

**The index placement matters:** The index must be on the **from** collection
(customers), not on the orders collection. It's the customer lookup that needs
to be fast — orders are the outer loop; customers are the inner loop.

This is a common mistake: developers add an index on `orders.customerId`
(improving `$match` filtering) but forget to index `customers.customerId`
(which actually fixes the join performance).
""",
                commands=[
                    MongoshCommand("""
db.customers.createIndex({customerId: 1});
print("✓ Index created on customers.customerId");
print("");
print("Customer collection indexes:");
db.customers.getIndexes().forEach(function(idx) {
    print("  " + idx.name + ": " + JSON.stringify(idx.key));
});
""")
                ]
            ),

            # STEP 4: Re-run the identical workload.
            DemoStep(
                id="with-index",
                title="Performance With Indexed $lookup",
                description="Re-run the same pipeline — MongoDB now uses IndexedLoopJoin",
                markdown="""
## With Index: $lookup Using IndexedLoopJoin

Run the **exact same aggregation pipeline** again. MongoDB now uses `IndexedLoopJoin`
on the `customers.customerId_1` index.

**With the index, MongoDB executes a seek per order instead of a scan:**

For each of the ~100 orders processed:
1. B-tree seek on `customers.customerId` index — O(log 10000) comparisons
2. Read the one matching customer document
3. Attach to order as `customer` array

**Cost per operation: ~100 seeks + ~100 document reads ≈ 200 total reads**

This is a **10,000x reduction** in document reads per operation — from 1,000,000
down to ~200.

**Why the improvement is multiplicative:**

The join cost scales with (outer_docs × inner_collection_size) without an index,
but with an index it scales with (outer_docs × log(inner_collection_size)).
At the 10k customer scale:
- Without index: 100 × 10,000 = 1,000,000
- With index:    100 × log₂(10,000) ≈ 100 × 13 = 1,300

At 1M customers the gap widens to ~75,000x. The index doesn't just help — it's
required for any $lookup at production scale.

**Expected improvements:**
- **100–1,000x higher throughput**
- **99%+ lower latency**
""",
                commands=[
                    ShellCommand(
                        'mdbpl run --workload raw --collection orders '
                        '--pipeline \'[{"$match": {"status": "{{status:uniform}}"}}, {"$lookup": {"from": "customers", "localField": "customerId", "foreignField": "customerId", "as": "customer"}}, {"$limit": 100}]\' '
                        '--duration 15s --tag with-lookup-index'
                    )
                ]
            ),

            # STEP 5: Compare.
            DemoStep(
                id="compare",
                title="Compare Results",
                description="Side-by-side: NestedLoopJoin vs IndexedLoopJoin",
                markdown="""
## Results: $lookup Before and After Indexing the Foreign Field

**Key Metrics:**

**Throughput (ops/sec)**
- No index: ~5–30 (1M doc reads per operation)
- With index: ~500–5,000 (200 doc reads per operation)
- **Expected: 100–1,000x improvement**

**Latency (ms)**
- No index: ~50–500ms (full customer scan × 100 orders)
- With index: ~1–10ms (indexed seek × 100 orders)
- **Expected: 99%+ reduction**

**Join Strategy (from explain_query)**
- No index: `NestedLoopJoin` — no index on customers.customerId
- With index: `IndexedLoopJoin` — uses `customerId_1` index
- **The strategy change is the root cause of the entire improvement**

**Why this is the most impactful single-index addition in a join workload:**

A $lookup with NestedLoopJoin reads the entire from-collection once per outer
document. This means the cost grows as O(outer × inner), which quickly becomes
the dominant cost in any pipeline that joins data.

Adding the index on the foreign field reduces this to O(outer × log(inner)) —
the join becomes essentially free relative to the cost of processing the outer
documents themselves.

**The rule:** Any `$lookup` `foreignField` that doesn't have an index is a
performance crisis waiting to happen. Always index it. The from-collection
index is often forgotten because developers focus on the outer collection's
query patterns and miss the inner collection's access pattern.
""",
                commands=[
                    ShellCommand("mdbpl compare --tags no-lookup-index,with-lookup-index")
                ]
            ),
        ]
