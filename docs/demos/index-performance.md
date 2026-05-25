# 🎯 Index Performance Impact

This demo demonstrates the **dramatic performance improvement** when adding a simple index to a MongoDB collection.

## What This Demo Does

1. **Loads 10,000 documents** with a numeric `score` field (0-9999)
2. **Baseline benchmark**: Runs range queries WITHOUT an index (15 seconds)
3. **Creates an index**: `db.usertable.createIndex({score: 1})`
4. **Indexed benchmark**: Re-runs the same queries WITH the index (15 seconds)
5. **Compares results**: Shows side-by-side performance metrics

## Expected Results

You should see dramatic improvements:

- 📈 **10-100x throughput increase** (operations per second)
- ⚡ **90%+ latency reduction** (p95 latency drops from ~50ms to <5ms)
- 🎯 **Efficiency jumps from <1% to ~100%**
- 🔍 **Collection scans → Index scans** (0 index scans → thousands of index scans)

### Why Efficiency Matters

The **Efficiency** metric shows how selective your queries are:
- **<1% efficiency**: MongoDB scans 10,000 docs to return 20 → wasteful
- **100% efficiency**: MongoDB scans 20 docs to return 20 → optimal

## MongoDB Commands

### View the Collection
```javascript
use perflab
db.usertable.countDocuments()
db.usertable.findOne()
```

### Create Index (what the demo does in Step 3)
```javascript
db.usertable.createIndex({score: 1})
```

### View All Indexes
```javascript
db.usertable.getIndexes()
```

### Explain a Query (see execution plan)
```javascript
db.usertable.find({score: {$gte: 5000}})
  .sort({score: 1})
  .limit(20)
  .explain("executionStats")
```

Look for:
- `executionStats.totalDocsExamined` - should be ~20 with index
- `executionStages.stage` - should be "IXSCAN" (index scan) not "COLLSCAN"

## Why This Works

**Without an index**, MongoDB must:
- Scan **every document** in the collection (10,000 docs)
- Check if `score >= threshold` for each one
- Sort all matching documents in memory
- Return the top 20

**With an index**, MongoDB can:
- Use the B-tree index to jump directly to the starting point
- Read documents in sorted order (no memory sort needed)
- Stop after finding 20 matches
- Scan only **~20-50 documents** instead of 10,000

This is why the **"Docs Examined"** metric is so important - it shows how much work MongoDB is doing behind the scenes.

## Key Metrics to Watch

| Metric | Without Index | With Index | Why It Matters |
|--------|---------------|------------|----------------|
| **Efficiency** | <1% | ~100% | Shows query selectivity |
| **Index Scans** | 0 | ~10,000+ | Confirms index is used |
| **Docs Examined** | 100,000+ | ~20,000 | Lower is better |
| **Throughput** | ~200 ops/sec | 2,000+ ops/sec | 10x faster |
| **Latency p95** | ~50ms | ~5ms | 90% improvement |

## Try It Yourself

Follow this hands-on workflow to see the impact of indexes firsthand:

(Use `docker compose exec perflab /bin/bash` to connect to MongoDB and run the commands below.)

### Step 1: Initialize the dataset

```bash
mdbpl init --scale 10k
```

This loads 10,000 generic documents into `perflab.usertable`.

### Step 2: Run baseline benchmark (no index)

```bash
mdbpl run --workload read-heavy --duration 15s --tag baseline
```

This runs range queries against the collection **without** any index on the `score` field.

### Step 3: Add an index
Use MongoDB Compass (GUI) or mongosh (CLI) to create an index on the `score` field:

```javascript
// Connect to MongoDB interactively with mongosh
mongosh mongodb://mongodb/perflab

// Create index on the score field
db.usertable.createIndex({score: 1})

// Verify it was created
db.usertable.getIndexes()

// Optional: See what explain shows now
db.usertable.find({score: {$gte: 5000}}).sort({score: 1}).limit(20)
  .explain("executionStats")
// Look for: executionStages.stage: "IXSCAN" (index scan)
//           totalDocsExamined: ~20-50 instead of 10,000!
```

### Step 4: Run new benchmark (with index)

```bash
mdbpl run --workload read-heavy --duration 15s --tag with-index
```

Same workload, but now queries use the index you just created.

### Step 5: Compare results

```bash
# Compare in the terminal
mdbpl compare --tags baseline,with-index

# Or view in the web UI at http://localhost:8050
```

You should see:
- **10-100x higher throughput** (operations per second)
- **90%+ lower latency** (p95 latency)
- **Dramatic increase in efficiency** (docs examined vs docs returned)
- **Index scans in the thousands** (vs zero before)

## Learn More

- [MongoDB Indexing Strategies](https://www.mongodb.com/docs/manual/indexes/)
- [Explain Plans Documentation](https://www.mongodb.com/docs/manual/reference/explain-results/)
- [pymongo Documentation](https://pymongo.readthedocs.io/)
- [mongodb/mongodb PHP Library](https://www.mongodb.com/docs/php-library/current/)
