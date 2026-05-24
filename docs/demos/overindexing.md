# ⚠️ Over-Indexing Performance Impact

This demo shows how **too many indexes** can significantly degrade **write performance**, even though indexes improve reads.

## What This Demo Does

1. **Loads 100,000 documents** with multiple fields and a numeric `score` field
2. **Baseline benchmark**: Runs write-heavy workload (90% updates) with NO extra indexes (10 seconds)
3. **Creates 1 index**: `db.usertable.createIndex({score: 1})`
4. **One index benchmark**: Re-runs the workload with one index (10 seconds)
5. **Creates 9 more indexes**: Total of 10 indexes on different fields
6. **Over-indexed benchmark**: Re-runs with 10 indexes (10 seconds)
7. **Compares results**: Shows progressive performance degradation

## Expected Results

You should see write performance **degrade** as you add more indexes:

- 📉 **10-30% throughput decrease** with 1 index
- 📉 **30-50% throughput decrease** with 10 indexes
- ⏱️ **Latency increases** proportionally
- ⚠️ **Each write must update ALL indexes**

### The Trade-off

Indexes are not free:
- **Reads benefit**: Queries become faster
- **Writes suffer**: Every insert/update must update all indexes
- **Storage cost**: Each index takes disk space

## MongoDB Commands

### View Current Indexes
```javascript
use perflab
db.usertable.getIndexes()
```

### Create Multiple Indexes (what the demo does)
```javascript
// First index (Step 3)
db.usertable.createIndex({score: 1})

// Additional indexes (Step 5)
db.usertable.createIndex({field0: 1})
db.usertable.createIndex({field1: 1})
db.usertable.createIndex({field2: 1})
// ... and so on
```

### Drop All Indexes (cleanup)
```javascript
db.usertable.dropIndexes()  // Drops all except _id
```

### See Index Sizes
```javascript
db.usertable.stats()
```

Look for `indexSizes` - shows disk space used by each index.

## Why This Happens

**Without extra indexes:**
- Update operation modifies document
- Updates the `_id` index (built-in)
- **Done!** Fast and simple.

**With 1 extra index:**
- Update operation modifies document
- Updates `_id` index
- Updates `score` index
- **2x index work**

**With 10 indexes:**
- Update operation modifies document
- Updates `_id` index
- Updates 10 additional indexes
- **11x index work!**

Each index must:
1. Find the old key in the B-tree
2. Remove it
3. Insert the new key
4. Rebalance the tree if needed

## Key Metrics to Watch

| Scenario | Indexes | Throughput | Latency p95 | Impact |
|----------|---------|------------|-------------|---------|
| **Baseline** | 1 (_id only) | ~3,000 ops/sec | ~5ms | 🟢 Baseline |
| **One Index** | 2 | ~2,500 ops/sec | ~6ms | 🟡 -17% |
| **Over-Indexed** | 11 | ~1,500 ops/sec | ~10ms | 🔴 -50% |

## The Right Balance

**Good indexing strategy:**
- ✅ Index fields used in frequent queries
- ✅ Index fields used in sorts
- ✅ Use compound indexes for multi-field queries
- ✅ Monitor query patterns and remove unused indexes

**Bad indexing strategy:**
- ❌ "Just index everything"
- ❌ Keep indexes "just in case"
- ❌ Multiple single-field indexes when a compound index would work
- ❌ Indexes on fields that are rarely queried

## Real-World Example

**E-commerce application:**

```javascript
// Users collection
// Bad: 15+ indexes on every field
{
  _id: 1,           // ← indexed
  email: "...",     // ← indexed
  name: "...",      // ← indexed
  address: "...",   // ← indexed
  phone: "...",     // ← indexed
  created_at: "..." // ← indexed
  // ... every field indexed!
}
```

**Impact:**
- Every new user registration updates 15+ indexes
- Order updates become slow
- Disk space bloats
- Backups take longer

**Better:**
```javascript
// Only index what you query
db.users.createIndex({email: 1})              // Login queries
db.users.createIndex({created_at: -1})        // Recent users
db.users.createIndex({email: 1, active: 1})   // Active user lookup
// That's it! 3 well-chosen indexes instead of 15.
```

## Try It Yourself

Follow this hands-on workflow to see how excess indexes degrade write performance:

(Use `docker compose exec perflab /bin/bash` to connect to MongoDB and run the commands below.)

### Step 1: Initialize the dataset

```bash
mdbpl init --scale 100k
```

This loads 100,000 generic documents into `perflab.usertable`.

### Step 2: Run baseline benchmark (minimal indexes)

```bash
mdbpl run --workload write-heavy --duration 10s --tag baseline
```

This runs update operations with only the default `_id` index.

### Step 3: Add indexes with mongosh
Use MongoDB Compass (GUI) or mongosh (CLI) to create multiple indexes:

```javascript
// Connect to MongoDB interactively with mongosh
mongosh mongodb://mongodb/perflab

// Add 5 indexes to different fields
for (var i = 0; i < 5; i++) {
  db.usertable.createIndex({["field" + i]: 1})
}

// Verify they were created
db.usertable.getIndexes()

// Check disk space used by indexes
db.usertable.stats().indexSizes

// Optional: Check which indexes are actually being used
db.usertable.aggregate([{ $indexStats: {} }])
// Look at 'accesses.ops' - likely 0 for most of these!
```

### Step 4: Run new benchmark (with 5 indexes)

```bash
mdbpl run --workload write-heavy --duration 10s --tag 5-indexes
```

Same workload, but now each update must maintain 6 indexes (5 new + _id).

### Step 5: Compare results

```bash
# Compare in the terminal
mdbpl compare --tags baseline,5-indexes

# Or view in the web UI at http://localhost:8050
```

You should see:
- **20-40% lower throughput** (fewer operations per second)
- **Higher latency** across all percentiles
- **Same query results** but slower writes
- **More disk space** used by index data


### Key Observations

**What to look for when running these examples:**

1. **Index Sizes**: Each index takes disk space (usually 1-10% of collection size per index)
2. **Write Latency**: Updates become progressively slower as you add more indexes
3. **Index Accesses**: `$indexStats` shows which indexes are actually being used
4. **The Sweet Spot**: Keep only indexes that improve query performance significantly

**Best Practices:**
- ✅ Create indexes for frequently queried fields
- ✅ Use compound indexes instead of multiple single-field indexes when possible
- ✅ Monitor index usage with `$indexStats` and remove unused ones
- ❌ Don't index every field "just in case"
- ❌ Don't keep indexes with 0 accesses

## Learn More

- [MongoDB Indexing Best Practices](https://www.mongodb.com/docs/manual/applications/indexes/)
- [Index Build Performance](https://www.mongodb.com/docs/manual/core/index-creation/)
- [Identify Unused Indexes](https://www.mongodb.com/docs/manual/reference/operator/aggregation/indexStats/)
- [pymongo Documentation](https://pymongo.readthedocs.io/)
- [mongodb/mongodb PHP Library](https://www.mongodb.com/docs/php-library/current/)
