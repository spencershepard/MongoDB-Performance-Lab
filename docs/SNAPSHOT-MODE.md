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
- Python workload file
- Query frequency distribution
- Parameter patterns

### 3. Run Benchmarks

```bash
# Run snapshot workload
mdbpl run --workload snapshots/production_replica.py --duration 5m

# Compare with optimizations
mdbpl run --workload snapshots/production_replica.py --tag "with-indexes"
mdbpl compare --tags baseline,with-indexes
```

## Python API for Snapshot Mode

### ✅ Current Support

**1. Arbitrary Schemas**
```python
benchmark = Benchmark(
    name="production-workload",
    database="production_db",
    collection="users"  # Any collection name
)
```

**2. Complex Filters**
```python
@benchmark.operation(weight=40, name="active_users_by_country")
def find_active_users(collection):
    return list(collection.find({
        "profile.country": country,
        "lastLogin": {"$gte": date_threshold}
    }).limit(20))
```

**3. Array Queries**
```python
@benchmark.operation(weight=20, name="tagged_items")
def find_by_tags(collection):
    return list(collection.find({
        "tags": {"$all": required_tags}
    }))
```

**4. Embedded Document Paths**
```python
@benchmark.operation(weight=30, name="by_zipcode")
def find_by_zip(collection):
    return list(collection.find({
        "address.zipCode": {"$in": ["10001", "10002"]}
    }))
```

**5. Aggregation Pipelines**
```python
@benchmark.operation(weight=10, name="user_order_totals")
def aggregate_orders(collection):
    return list(collection.aggregate([
        {"$match": {"status": "active"}},
        {"$lookup": {
            "from": "orders",
            "localField": "userId",
            "foreignField": "customerId",
            "as": "orders"
        }},
        {"$unwind": "$orders"},
        {"$group": {
            "_id": "$userId",
            "totalSpent": {"$sum": "$orders.total"}
        }}
    ]))
```

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
# Generates Python workload automatically
```

**3. LLM-Assisted Workload Creation** (Future)
```bash
mdbpl snapshot generate-workload --llm --description "User login flow"
# Uses LLM to generate realistic Python workload from description
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
See `examples/ecommerce_snapshot.py` for full example:

```python
from mdbpl import Benchmark, uniform

benchmark = Benchmark(
    name="ecommerce-snapshot",
    database="ecommerce",
    collection="orders"
)

user_dist = uniform(100000)

@benchmark.operation(weight=40, name="get_user_orders")
def get_user_orders(collection):
    user_id = user_dist.next()
    return list(collection.find(
        {"userId": user_id}
    ).sort("createdAt", -1).limit(10))

@benchmark.operation(weight=30, name="find_by_status")
def find_pending(collection):
    return list(collection.find(
        {"status": "pending"}
    ).limit(20))

@benchmark.operation(weight=30, name="find_by_product")
def find_by_product(collection):
    product_id = user_dist.next()
    return list(collection.find(
        {"items.productId": product_id}
    ).limit(10))
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

## Benefits of Python API for Snapshot Mode

1. **Reproducible**: Same workload runs identically across environments
2. **Shareable**: Check workload definitions into Git
3. **Versionable**: Track workload changes over time
4. **Flexible**: Full pymongo API, any MongoDB operation
5. **Type-safe**: IDE autocomplete and error checking
6. **CI/CD Ready**: Automated regression testing
7. **Familiar**: Standard Python, no new syntax to learn

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

The Python Benchmark API is **snapshot-ready**. Key capabilities:
- ✅ Flexible schema support
- ✅ Complex query patterns
- ✅ Array and embedded document queries
- ✅ Aggregation pipelines
- ✅ Reproducible workload definitions
- ✅ Full pymongo API access

Next implementation phases:
1. Snapshot import tooling
2. Schema inference
3. Workload auto-generation from profiler logs
4. LLM integration for workload generation
