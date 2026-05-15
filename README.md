
![MongoDB Performance Lab](logo.gif)

# MongoDB Performance Lab

An interactive MongoDB performance experimentation platform designed for learning, optimization, and CI/CD integration.

---

## Overview

**MongoDB Performance Lab** bridges the gap between MongoDB tutorials and production optimization. Unlike traditional benchmarking tools (YCSB, NoSQLBench), this platform is designed for iterative experimentation with a focus on **learning** and **reproducibility**.

### What Makes This Different?

**For Developers Learning MongoDB:**
- 🎓 Out-of-the-box datasets and workloads (no complex setup)
- 📊 Visual before/after comparisons to understand optimization impact
- 🔍 Integrated explain plan analysis and metrics
- 🎯 Guided workflows for common performance scenarios

**For DBAs Optimizing Production:**
- 📸 Snapshot mode: Import production data and replay workloads
- 🔄 Reproducible benchmarks via declarative DSL
- 🚀 CI/CD integration for performance regression testing
- 📈 Historical trend analysis across schema iterations

**vs. Traditional Tools:**
- **vs. YCSB**: Easier to use, MongoDB-focused, visual comparison, DSL abstraction
- **vs. MongoDB Atlas Performance Advisor**: Works locally, synthetic workloads, proactive testing
- **vs. Custom Scripts**: Standardized metrics, reproducible, shareable benchmarks

### Core Features

- ⚡ **YCSB-powered data generation** with realistic distributions
- 📝 **Workload DSL** for defining queries independent of MongoDB syntax
- 🎯 **Benchmark runner** with detailed performance metrics (p50/p95/p99, docs scanned, index usage)
- 🔄 **Compare mode** to visualize optimization impact
- 🌐 **Web UI** with interactive charts and one-click demos (Plotly Dash)
- 🛠️ **CLI & REST API** for both interactive experimentation and automation
- 🐳 **Docker-based** for consistent, reproducible environments

---

## Getting Started

### Prerequisites

- Docker and Docker Compose
- Git

### Quick Start

1. **Clone and start services**

```bash
git clone https://github.com/your-org/mongodb-performance-lab.git
cd mongodb-performance-lab
docker-compose up -d
```

This starts:
- MongoDB (port 27017)
- Performance Lab API & Web UI (port 8888)

### Web UI (Interactive Dashboard)

Open your browser to explore performance demos visually:

**http://localhost:8888/ui/**

Or use the convenient redirect:

**http://localhost:8888/dashboard**

The Web UI provides:
- 🎯 **Demo selector** - Choose from available performance demonstrations
- ▶️ **One-click execution** - Run demos with a button click
- 📊 **Live charts** - Interactive Plotly visualizations of throughput and latency
- 📈 **Detailed metrics** - Before/after comparison tables with improvement percentages
- ⏱️ **Execution timeline** - Step-by-step progress with timing information

The Web UI is built with Plotly Dash for rapid development, but the REST API (`/api/*`) is designed to support any frontend framework. The same API powers both the CLI and web interface, making it easy to switch to React/Next.js in the future.


**Run your first benchmark**

```bash
# Initialize with sample dataset
docker-compose exec perflab mdbpl init --scale 10k --drop

# Run a read-heavy workload
docker-compose exec perflab mdbpl run --workload read-heavy --duration 30s --tag baseline

# View results
docker-compose exec perflab mdbpl report --last

# List all benchmark runs
docker-compose exec perflab mdbpl report --list
```

**Init options:**
- `--scale`: Dataset size (10, 1k, 100k, 1M, 10M, etc.)
- `--distribution`: Key distribution (zipfian, uniform, latest)
- `--fields`: Number of fields per document (default: 10)
- `--field-length`: Length of each field value (default: 100)
- `--drop`: Drop existing collection before loading (recommended)

3. **Experiment and optimize**

Use MongoDB tools to experiment with performance optimizations:

**MongoDB Compass** (Recommended - Visual GUI)
- Download: [MongoDB Compass](https://www.mongodb.com/products/compass)
- Connect to: `mongodb://localhost:27017`
- Navigate to: `perflab` database

**mongosh** (MongoDB Shell - Advanced users)
```bash
docker-compose exec mongodb mongosh
use perflab
```

**Optimization Techniques to Try:**

**Indexes** - Most common optimization
```bash
# Using the built-in index commands (recommended for beginners)
docker-compose exec perflab mdbpl index create field0
docker-compose exec perflab mdbpl index create "field0,field1"  # compound
docker-compose exec perflab mdbpl index list
docker-compose exec perflab mdbpl index drop field0_1

# Or use mongosh directly (advanced)
docker-compose exec mongodb mongosh perflab --eval "db.usertable.createIndex({field0: 1})"
docker-compose exec mongodb mongosh perflab --eval "db.usertable.getIndexes()"
docker-compose exec mongodb mongosh perflab --eval "db.usertable.dropIndex('field0_1')"
```

**Schema Design** - Restructure your data
```javascript
// Add embedded documents
db.usertable.updateMany({}, { 
  $set: { metadata: { field0: "$field0" } } 
})

// Denormalize data
db.usertable.updateMany({}, {
  $set: { computed_field: "value" }
})
```

**Query Optimization** - Modify your workload DSL
```yaml
# Use projection to limit fields returned
# Use covered queries (query + projection only use indexed fields)
# Adjust sort orders
# Add filters to reduce result sets
```

**Data Modeling** - Change collection structure
```javascript
// Try bucketing patterns
// Experiment with array fields
// Test different data types
```

**Aggregation Pipelines** - Optimize complex queries
```javascript
// Add indexes to support $match stages
// Reorder pipeline stages
// Use $project early to reduce document size
```

### Learning Workflow

The recommended workflow for performance experimentation:

1. **Load baseline data** → `mdbpl init --scale 10k --drop`
2. **Run baseline benchmark** → `mdbpl run --workload range-scan --tag no-index`
3. **Analyze results** → Review metrics (156 ops/sec, 3.83ms avg latency)
4. **Make a change** → `mdbpl index create field0`
5. **Re-benchmark** → `mdbpl run --workload range-scan --tag with-index`
6. **Compare results** → `mdbpl compare --tags no-index,with-index`
   - **Result**: +861% throughput, -92% latency! 🎉
7. **Iterate** → Try compound indexes, different workloads, schema changes

**Real Example Output:**
```
Metric                    No Index        With Index      Change          Status
================================================================================
Throughput (ops/sec)      156.25          1501.98         +861.26%        ✓ (improved)
Latency p50 (ms)          3.42            0.28            -91.84%         ✓ (improved)
Latency p95 (ms)          5.20            0.43            -91.71%         ✓ (improved)
```

**Example Experiment Ideas:**
- Does a single-field index improve query X?
- How does a compound index compare to two single-field indexes?
- Is denormalization faster than using `$lookup`?
- What's the impact of adding a text index?
- How does changing field order in a compound index affect performance?

### Next Steps

- Explore [built-in workloads](#workloads-mvp)
- Create [custom workloads](#query-dsl-example)
- Set up [CI/CD integration](#cli-mode-cicd-integration)
- Read [MongoDB Performance Best Practices](https://www.mongodb.com/docs/manual/administration/analyzing-mongodb-performance/)
- Learn about [Query Optimization](https://www.mongodb.com/docs/manual/core/query-optimization/)
- Study [Indexing Strategies](https://www.mongodb.com/docs/manual/indexes/)

---

## Goals

### MVP
- Run reproducible MongoDB benchmarks
- Compare query performance across indexes
- Visualize latency and execution behavior
- Teach database performance concepts
- Single-node MongoDB only

### Future
- Snapshot ingestion ("production snapshot mode")
- Schema introspection + workload generation
- LLM-generated workloads
- Multi-database benchmarking
- Replica set and sharded cluster support

---

## Core Concept

Three layers:

1. Dataset Layer
2. Workload Layer
3. DSL Layer (query abstraction)

All workloads are defined via a structured DSL rather than raw MongoDB queries.

---

## Dataset (MVP)

Uses **YCSB (Yahoo! Cloud Serving Benchmark)** for data generation.

YCSB-style documents:

```json
{
  "_id": "user0000000001",
  "field0": "random_string_100_chars...",
  "field1": "random_string_100_chars...",
  "field2": "random_string_100_chars...",
  ...
  "field9": "random_string_100_chars..."
}
```

**Data Generation Strategy:**
- YCSB binary handles dataset creation (battle-tested, industry standard)
- Supports Zipfian, uniform, and latest distributions
- Configurable record count and field sizes
- `mdbpl init` wraps YCSB for easy setup

**Workload Execution:**
- Custom DSL-based workload runner (not YCSB's execution engine)
- Full control over metrics, explain plans, and query patterns
- Extensible beyond YCSB's standard workloads

---

## Workloads (MVP)

**Built-in Workloads:**
- `read-heavy`: 95% reads, 5% updates (YCSB Workload B)
- `balanced`: 50% reads, 50% updates (YCSB Workload A)
- `range-scan`: Range queries with sorting
- `compound-index-test`: Multi-field query patterns

All workloads use the declarative YAML DSL for reproducibility.

---

## Workload DSL

Workloads are defined in YAML for readability and reproducibility:

```yaml
name: "read-heavy"
description: "95% reads, 5% updates with zipfian distribution"
database: "perflab"
collection: "usertable"

distribution:
  type: "zipfian"  # 80/20 access pattern

operations:
  - name: "read"
    weight: 95
    operation: "find"
    filter:
      field: "_id"
      operator: "eq"
      value:
        type: "param"
        param: "userId"
    projection:
      field0: 1
      field1: 1
    limit: 1

  - name: "update"
    weight: 5
    operation: "update"
    filter:
      field: "_id"
      operator: "eq"
      value:
        type: "param"
        param: "userId"
    update:
      $set:
        field0:
          type: "random"
          length: 100
```

**Supported Operations:**
- `find` - Point queries, range scans, compound filters
- `update` - Single and bulk updates
- `insert` - Document insertion
- `delete` - Document deletion
- `aggregate` - Aggregation pipelines

**Supported Filters:**
- Simple: `eq`, `ne`, `gt`, `gte`, `lt`, `lte`, `in`, `nin`, `regex`
- Array: `all`, `elemMatch`, `size`
- Field: `exists`, `type`
- Compound: `and`, `or` with nested conditions

**Snapshot Mode Ready**: The DSL is fully designed to handle production schemas and query patterns. Import real data, define workloads matching your production queries, and benchmark optimizations in isolation. See [Snapshot Mode Guide](docs/SNAPSHOT-MODE.md).

See [DSL Specification](docs/DSL-SPEC.md) for complete reference.

---

## Execution Flow

DSL → Compiler → MongoDB → Metrics → UI

---

## Performance Metrics

MongoDB Performance Lab collects comprehensive metrics to help you understand query performance and identify optimization opportunities.

### Core Metrics

**Throughput & Latency**
- **Operations per second** - Total query throughput
- **Latency percentiles** (p50/p95/p99) - Response time distribution
  - p50: 50% of operations complete faster than this
  - p95: 95% of operations complete faster than this (key SLA metric)
  - p99: 99% of operations complete faster than this (outlier detection)

**Query Efficiency**
- **Docs Examined** - Documents MongoDB scanned to answer queries
- **Docs Returned** - Documents actually returned to the application
- **Efficiency Score** - `(Docs Returned / Docs Examined) × 100%`
  - 🟢 >80%: Excellent - index is very selective
  - 🟡 50-80%: Good - index helps but could be improved
  - 🔴 <50%: Poor - needs better indexing or query optimization

**Index Usage**
- **Index Scans** - Queries that used an index (efficient)
- **Collection Scans** - Queries that scanned entire collection (inefficient for large datasets)
- **Index Names** - Which specific indexes were used

### Understanding Efficiency

The efficiency score is the most important metric for optimization:

```
Without Index:
  Docs Examined: 10,000 (full collection scan)
  Docs Returned: 20
  Efficiency: 0.2% 🔴

With Index:
  Docs Examined: 20
  Docs Returned: 20
  Efficiency: 100% 🟢
```

A low efficiency score means MongoDB is scanning far more data than needed - adding the right index can provide **10-100x** performance improvements.

### Sampling Strategy

To minimize benchmark overhead while maintaining accuracy:
- **100% Sampling**: Latency, docs returned (every operation measured)
- **10% Sampling**: Explain analysis (docs examined, index usage)
- **Extrapolation**: Sampled explain metrics scaled to represent full workload

This approach provides accurate metrics with minimal performance impact.

### Detailed Metrics Guide

For in-depth explanations of metrics collection, troubleshooting, and interpretation, see [Performance Metrics Guide](docs/METRICS.md).

---

## Architecture

Frontend → API → Benchmark Engine → DSL Compiler → MongoDB

### Tech Stack

**Backend**
- Python 3.11+
- FastAPI for REST API
- pymongo for MongoDB operations
- SQLite for benchmark result storage

**Frontend**
- Plotly Dash (current - for rapid MVP development)
- Visualization: Plotly.js charts (interactive)
- React/Next.js migration path (API is framework-agnostic)

**Deployment**
- CLI mode for CI/CD integration and terminal workflows
- Web UI (http://localhost:8888/ui) for interactive experimentation
- REST API (/api/*) for programmatic access and frontend integration
- Docker Compose for consistent, reproducible environments

### Target Audience

1. **Learning Mode** (out-of-the-box)
   - Developers learning MongoDB performance concepts
   - Pre-configured workloads and datasets
   - Educational visualizations and explanations

2. **Optimization Mode** (snapshot + custom)
   - DBAs optimizing production schemas
   - Custom workload definitions
   - Production data snapshot ingestion
   - Index recommendation insights

---

## Execution Modes

### CLI Mode (CI/CD Integration)

Run benchmarks from command line or CI/CD pipelines:

```bash
# Run a single workload
mdbpl run --workload read-heavy --dataset ycsb-1M

# Compare against baseline
mdbpl run --workload custom.yaml --baseline main --threshold 10%

# Generate report
mdbpl report --format json --output results.json
```

**Use Cases:**
- Regression testing (detect query performance degradation)
- Pre-merge validation (fail PR if p95 latency exceeds threshold)
- Continuous performance monitoring
- Automated index impact analysis

**Exit Codes:**
- 0: Benchmark passed
- 1: Performance regression detected
- 2: Benchmark execution failed

### API Mode (Dashboard)

The API server and Web UI start automatically with docker-compose:

```bash
docker-compose up -d
```

Access the dashboard at **http://localhost:8888/dashboard** or **http://localhost:8888/ui/**

**REST API Endpoints:**

- `GET /api/demos` - List all available demos
- `GET /api/demos/{name}` - Get demo metadata
- `POST /api/demos/{name}/run` - Execute a demo (returns structured JSON results)

**Features:**
- Interactive demo selector with one-click execution
- Real-time benchmark visualization with Plotly charts
- Before/after comparison tables with improvement percentages
- Step-by-step execution timeline
- Same API powers both Web UI and CLI

**Architecture Note:**
The Web UI is currently built with Plotly Dash for rapid prototyping. The REST API (`/api/*`) is framework-agnostic and designed to support any frontend. When migrating to React/Next.js, simply replace the `/ui` endpoint while keeping the API unchanged.

### Configuration

Both modes share common config:

```yaml
# perf-lab.yaml
mongodb:
  uri: mongodb://localhost:27017
  database: perflab
  
benchmarks:
  warmup_operations: 1000
  measurement_operations: 10000
  threads: 1
  
thresholds:
  p95_latency_ms: 50
  docs_scanned_ratio: 2.0  # scanned/returned ratio
```

---

## Snapshot Mode (Future)

- Import MongoDB dump
- Infer schema
- Generate workloads
- Run isolated benchmarks

---

## Key Idea

All workloads are defined in a DSL, not raw queries.

This enables:
- reproducibility
- extensibility
- safe automation

---

## License

This project is released into the **public domain** under the [Unlicense](https://unlicense.org).

You are free to use, modify, distribute, and do anything with this software without any restrictions. See the [LICENSE](LICENSE) file for details.

**Created by:** [Spencer Shepard](https://github.com/spencershepard)

