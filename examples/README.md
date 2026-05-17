# Python Workload Examples

This directory contains example benchmarks using the Python workload API.

## Quick Start

### 1. Use a Built-in Workload

```python
from mdbpl import create_read_heavy_benchmark

# Create a read-heavy workload
benchmark = create_read_heavy_benchmark(
    database="perflab",
    collection="usertable",
    record_count=10000
)
```

### 2. Create a Custom Workload

```python
from mdbpl import Benchmark, zipfian

# Define your benchmark
benchmark = Benchmark(
    name="my-workload",
    database="mydb",
    collection="mycollection",
    description="My custom workload"
)

# Setup distribution
dist = zipfian(10000)

# Add operations
@benchmark.operation(weight=80, name="read")
def read_operation(collection):
    doc_id = dist.next()
    return collection.find_one({"_id": doc_id})

@benchmark.operation(weight=20, name="update")
def update_operation(collection):
    doc_id = dist.next()
    return collection.update_one(
        {"_id": doc_id},
        {"$set": {"updated": True}}
    )
```

### 3. Run Your Benchmark

```bash
# Run a custom workload file
docker-compose exec perflab mdbpl run --workload examples/custom_benchmark.py

# Or use built-in workloads
docker-compose exec perflab mdbpl run --workload read-heavy
docker-compose exec perflab mdbpl run --workload balanced
```

## Available Examples

- **custom_benchmark.py** - E-commerce order collection example
- More examples coming soon...

## Distribution Types

Choose a distribution based on your access pattern:

```python
from mdbpl import zipfian, uniform, latest

# Zipfian: 80/20 rule (hot keys)
dist = zipfian(10000)

# Uniform: Equal probability
dist = uniform(10000)

# Latest: Recent keys accessed more
dist = latest(10000)
```

## Tips

1. **Test your benchmark locally:**
   ```bash
   python examples/custom_benchmark.py
   ```

2. **Operations are weighted:**
   - `weight=80` means 80% of operations
   - Total doesn't need to equal 100

3. **Use realistic queries:**
   - Copy your production queries
   - Test actual indexes and projections
   - Measure what matters to your app

## Next Steps

See [Custom Workload Guide](../docs/CUSTOM-WORKLOADS.md) for advanced usage.
