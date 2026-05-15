# Performance Metrics Guide

## Overview

MongoDB Performance Lab collects detailed execution metrics during benchmark runs to help you understand query performance and identify optimization opportunities.

## Key Metrics

### Throughput & Latency
- **Operations Per Second**: Total operations completed per second
- **Latency P50/P95/P99**: Percentile latencies in milliseconds
  - P50: 50% of operations complete faster than this
  - P95: 95% of operations complete faster than this  
  - P99: 99% of operations complete faster than this

### Query Efficiency Metrics

#### Docs Examined
Total number of documents MongoDB scanned to answer queries. Lower is better.

- **With Index**: Typically scans only matching documents
- **Without Index**: Must scan entire collection (full table scan)

#### Docs Returned
Total number of documents actually returned to the application. This is the useful result set.

#### Efficiency Score
```
Efficiency = (Docs Returned / Docs Examined) × 100%
```

**Interpretation:**
- **🟢 >80%**: Excellent - index is very selective
- **🟡 50-80%**: Good - index helps but could be improved
- **🔴 <50%**: Poor - needs better indexing or query optimization

**Example:**
```
Query: Find users with score >= 5000, limit 20

Without Index (Collection Scan):
  - Docs Examined: 10,000 (entire collection)
  - Docs Returned: 20
  - Efficiency: 0.2% 🔴

With Index on 'score':
  - Docs Examined: 5,000 (matching range)
  - Docs Returned: 20
  - Efficiency: 0.4% 🔴

With Compound Index on 'score' + optimized query:
  - Docs Examined: 20
  - Docs Returned: 20
  - Efficiency: 100% 🟢
```

### Scan Types

#### Index Scans
Queries that used an index to locate documents. Efficient for selective queries.

```javascript
// Example: Uses index on 'score'
db.users.find({score: {$gte: 5000}}).sort({score: 1}).limit(20)
// Stage: IXSCAN (index scan)
```

#### Collection Scans
Queries that scanned the entire collection without an index. Inefficient for large datasets.

```javascript
// Example: No index on 'field0'
db.users.find({field0: {$gte: "abc"}})
// Stage: COLLSCAN (collection scan)
```

## How Metrics Are Collected

### During Benchmark Execution

1. **Query Execution**: Each query runs normally and latency is measured
2. **Result Counting**: Actual documents returned are counted
3. **Explain Sampling**: 10% of queries are analyzed with `explain()` to get:
   - Documents examined
   - Index usage
   - Execution plan

### Sampling Strategy

- **100% Sampling**: Latency, docs returned
- **10% Sampling**: Docs examined, index usage (to reduce overhead)
- **Extrapolation**: Sampled metrics are aggregated to represent the full workload

## Common Patterns

### Good Performance Indicators
```
✓ High efficiency score (>80%)
✓ Most operations use indexes
✓ Docs examined ≈ Docs returned
✓ Low P95/P99 latency
```

### Performance Problems
```
✗ Low efficiency score (<50%)
✗ Many collection scans
✗ Docs examined >> Docs returned
✗ High P95/P99 latency
```

## Troubleshooting

### "Docs Returned: 0"
**Cause**: Queries don't match any data
- Check filter criteria match actual data
- Verify field types (string vs numeric vs binary)
- Inspect sample documents: `db.collection.findOne()`

### "Docs Examined: 0"
**Cause**: Explain sampling hasn't captured data yet
- Wait for more operations to complete
- Increase benchmark duration
- Check logs for explain errors

### "Efficiency: N/A"
**Cause**: Missing either docs_examined or docs_returned
- Queries may not be returning results
- Explain sampling may not have run yet

## Best Practices

1. **Run benchmarks for at least 30 seconds** to get stable metrics
2. **Compare baseline vs optimized** runs side-by-side
3. **Focus on efficiency score** as a key indicator
4. **Monitor both throughput AND latency** - they tell different stories
5. **Check scan types** to verify indexes are being used

## Example Comparison

```
Baseline (No Index):
  Throughput: 100 ops/sec
  Latency P95: 250ms
  Docs Examined: 10,000,000
  Docs Returned: 100,000
  Efficiency: 1%
  Index Scans: 0 | Collection Scans: 100,000

Optimized (With Index):
  Throughput: 1,500 ops/sec  (15x faster!)
  Latency P95: 15ms         (17x faster!)
  Docs Examined: 100,000
  Docs Returned: 100,000
  Efficiency: 100%          (100x improvement!)
  Index Scans: 100,000 | Collection Scans: 0
```

This dramatic improvement is typical when adding the right index for your workload.
