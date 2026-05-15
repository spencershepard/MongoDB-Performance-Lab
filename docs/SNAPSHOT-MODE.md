# Snapshot Mode Design

## ** Coming Soon **
## Overview

Snapshot mode allows you to **import production data** and **replay production workload patterns** in an isolated benchmarking environment.

## How It Works

### 1. Import Production Snapshot

```bash
# Option A: From MongoDB dump
mdbpl snapshot import --dump /path/to/dump --sample 10%

# Option B: From live database (with sampling)
mdbpl snapshot import --uri mongodb://prod:27017/mydb --sample 1000000
```

This creates:
- Sanitized data copy
- Schema analysis report
- Index definitions

### 2. Analyze Workload Patterns

```bash
# Option A: From MongoDB profiler logs
mdbpl snapshot analyze --profiler-logs /path/to/profiler.json

# Option B: From application logs
mdbpl snapshot analyze --app-logs /path/to/queries.log

# Option C: Manual workload definition
mdbpl snapshot analyze --interactive
```

This generates:
- Workload DSL YAML file
- Query frequency distribution
- Parameter patterns

### 3. Run Benchmarks

```bash
# Run snapshot workload
mdbpl run --workload snapshots/production-replica.yaml --duration 5m

# Compare with optimizations
mdbpl run --workload snapshots/production-replica.yaml --tag "with-indexes"
mdbpl compare --tags baseline,with-indexes
```

## DSL Support for Snapshot Mode

### ✅ Already Supported

**1. Arbitrary Schemas**
```yaml
database: "production_db"
collection: "users"  # Any collection name
```

**2. Complex Filters**
```yaml
filter:
  and:
    - field: "profile.country"
      operator: "eq"
      value: { type: "param", param: "country" }
    - field: "lastLogin"
      operator: "gte"
      value: { type: "param", param: "dateThreshold" }
```

**3. Array Queries**
```yaml
filter:
  field: "tags"
  operator: "all"
  value: { type: "param", param: "requiredTags" }
```

**4. Embedded Document Paths**
```yaml
filter:
  field: "address.zipCode"
  operator: "in"
  value: { type: "literal", value: ["10001", "10002"] }
```

**5. Aggregation Pipelines**
```yaml
operation: "aggregate"
pipeline:
  - $match: { status: "active" }
  - $lookup:
      from: "orders"
      localField: "userId"
      foreignField: "customerId"
      as: "orders"
  - $unwind: "$orders"
  - $group:
      _id: "$userId"
      totalSpent: { $sum: "$orders.total" }
```

### 🔧 Enhanced Features

We've added operators for production queries:
- `exists` - Check field existence
- `type` - Type checking
- `all` - Array contains all values
- `elemMatch` - Complex array element matching
- `size` - Array length
- `nin` - Not in array

### 📋 Future Enhancements

**1. Schema Inference** (Coming Soon)
```bash
mdbpl snapshot infer-schema --collection users
# Generates: field types, indexes, cardinality
```

**2. Workload Auto-Generation** (Coming Soon)
```bash
mdbpl snapshot generate-workload --from-profiler
# Analyzes slow query log
# Generates DSL workload automatically
```

**3. LLM-Assisted Workload Creation** (Future)
```bash
mdbpl snapshot generate-workload --llm --description "User login flow"
# Uses LLM to generate realistic workload from description
```

## Example: E-commerce Snapshot Workflow

### Step 1: Import Data
```bash
# Import 1M orders from production
mdbpl snapshot import \
  --uri mongodb://prod/ecommerce \
  --collection orders \
  --sample 1000000 \
  --sanitize userId,email
```

### Step 2: Create Workload
See `workloads/examples/ecommerce-snapshot.yaml` for full example:

```yaml
name: "ecommerce-snapshot"
database: "ecommerce"
collection: "orders"

operations:
  - name: "get-user-orders"
    weight: 40
    operation: "find"
    filter:
      field: "userId"
      operator: "eq"
      value: { type: "param", param: "userId" }
    sort:
      createdAt: -1
    limit: 10
```

### Step 3: Baseline Benchmark
```bash
mdbpl run --workload ecommerce-snapshot --tag baseline
```

### Step 4: Add Indexes
```javascript
// In MongoDB Compass or mongosh
db.orders.createIndex({ userId: 1, createdAt: -1 })
db.orders.createIndex({ "items.productId": 1 })
```

### Step 5: Re-benchmark
```bash
mdbpl run --workload ecommerce-snapshot --tag optimized
mdbpl compare --tags baseline,optimized
```

## Benefits of DSL for Snapshot Mode

1. **Reproducible**: Same workload runs identically across environments
2. **Shareable**: Check workload definitions into Git
3. **Versionable**: Track workload changes over time
4. **Analyzable**: Parse DSL to analyze query patterns
5. **Portable**: Could run against other databases (future)
6. **CI/CD Ready**: Automated regression testing

## Snapshot vs YCSB Mode

| Feature | YCSB Mode | Snapshot Mode |
|---------|-----------|---------------|
| Data Source | Generated | Production dump |
| Schema | Simple (field0-9) | Real production schema |
| Queries | Synthetic | Real query patterns |
| Use Case | Learning, generic benchmarks | Production optimization |
| Setup Time | < 1 minute | 10-30 minutes |

## Data Sanitization

For sensitive production data:

```bash
mdbpl snapshot import \
  --sanitize "email,ssn,creditCard" \
  --hash "userId,orderId" \
  --faker "name,address,phone"
```

- `--sanitize`: Remove fields entirely
- `--hash`: One-way hash (preserves distribution)
- `--faker`: Replace with realistic fake data

## Conclusion

The DSL is **snapshot-ready**. Key capabilities:
- ✅ Flexible schema support
- ✅ Complex query patterns
- ✅ Array and embedded document queries
- ✅ Aggregation pipelines
- ✅ Reproducible workload definitions

Next implementation phases:
1. Snapshot import tooling
2. Schema inference
3. Workload auto-generation
4. LLM integration
