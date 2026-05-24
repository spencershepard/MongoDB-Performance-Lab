# MCP Server Implementation Plan

## Overview

This document outlines the design and implementation plan for the MongoDB Performance Lab MCP (Model Context Protocol) server. The MCP server enables VS Code agents to generate and execute performance testing workflows based on user's application code.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  VS Code Agent (Copilot)                                    │
│  ─────────────────────────────────────────────────────────  │
│  • Has full workspace access                                │
│  • Reads and analyzes user's code directly                  │
│  • Generates Python workflows based on analysis             │
│  • Orchestrates the performance testing flow                │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ↓
┌─────────────────────────────────────────────────────────────┐
│  MCP Server (Knowledge + Execution)                         │
│  ─────────────────────────────────────────────────────────  │
│  Provides:                                                   │
│  • Analysis guidance (how to find queries)                  │
│  • Workflow templates (example code structure)              │
│  • Best practices (indexing strategies)                     │
│  • Schema introspection (current indexes, stats)            │
│  • Workflow execution (isolated container)                  │
│                                                              │
│  Does NOT:                                                   │
│  • Analyze user's code (agent does this)                    │
│  • Generate workflows (agent does this)                     │
│  • Access user's filesystem (except via tools)              │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ↓
┌─────────────────────────────────────────────────────────────┐
│  User's MongoDB (Test Database)                             │
│  ─────────────────────────────────────────────────────────  │
│  • Agent-controlled connection URI                          │
│  • Test database only (not production)                      │
│  • MCP executes workflows against this                      │
└──────────────────────────────────────────────────────────────┘
```

## Design Principles

### 1. **Agent-Driven Analysis**
- Agent has workspace access and reads user's code directly
- MCP provides **guidance**, not code analysis
- Agent is responsible for finding queries, understanding context

### 2. **Secure Execution**
- Workflows execute in isolated Docker container
- No arbitrary file system access
- Agent-generated Python code runs in sandbox
- Only benchmark results returned to agent

### 3. **Knowledge Provider**
- MCP provides templates, patterns, best practices
- Agent uses these to guide workflow generation
- Separation of knowledge (MCP) from analysis (agent)

### 4. **Flexible Workflow Generation**
- Agent generates full Python workflows
- Python allows complex scenarios (loops, conditionals, realistic data)
- LLM excels at Python generation
- No DSL constraints

## MCP Tools

### 1. `get_analysis_guide`

**Purpose:** Provide instructions for how agent should analyze user's code to find MongoDB queries.

**Input:** None (or optionally language hint)

**Output:**
```json
{
  "languages": {
    "javascript": {
      "patterns": [
        "db.collection.find(...)",
        "collection.findOne(...)",
        "Model.find(...)",
        "Model.findOne(...)",
        "collection.aggregate(...)"
      ],
      "libraries": ["mongodb", "mongoose"],
      "extract": ["query", "sort", "projection", "limit", "skip"]
    },
    "python": {
      "patterns": [
        "collection.find(...)",
        "db['collection'].find(...)",
        "collection.aggregate(...)"
      ],
      "libraries": ["pymongo", "motor"],
      "extract": ["filter", "sort", "projection", "limit", "skip"]
    },
    "typescript": {
      "patterns": ["<same as JavaScript>"],
      "libraries": ["mongodb", "mongoose", "@types/mongodb"]
    }
  },
  "analysis_steps": [
    "1. Search for MongoDB query patterns in codebase",
    "2. Extract query predicates, sort fields, and projections",
    "3. Identify collections being queried",
    "4. Note query frequency (route handlers, hot paths)",
    "5. Check for N+1 query patterns",
    "6. Look for queries inside loops"
  ],
  "red_flags": [
    "Queries without indexes on filter fields",
    "Sort without index",
    "Queries in loops (N+1)",
    "Missing compound indexes for multi-field filters",
    "Full collection scans"
  ]
}
```

**Agent Usage:** Agent reads this to understand how to find and analyze MongoDB queries in user's codebase.

---

### 2. `get_workflow_template`

**Purpose:** Provide example Python workflow structure for agent to use as template.

**Input:** 
```json
{
  "scenario": "index_comparison" | "write_performance" | "compound_index" | "general"
}
```

**Output:**
```json
{
  "template": "<Python code string>",
  "description": "Template for comparing performance with/without index",
  "api_reference": {
    "init": {
      "signature": "init(collection: str, scale: str | int, distribution: str = 'zipfian')",
      "description": "Load test data into collection",
      "examples": [
        "init(collection='orders', scale=10000)",
        "init(collection='users', scale='50k', distribution='uniform')"
      ]
    },
    "benchmark": {
      "signature": "benchmark(query: dict, sort: dict = None, tag: str = None) -> dict",
      "description": "Run benchmark against query pattern",
      "examples": [
        "benchmark(query={'userId': 123}, tag='baseline')",
        "benchmark(query={'status': 'active'}, sort={'createdAt': -1})"
      ]
    },
    "create_index": {
      "signature": "create_index(spec: dict, collection: str = None)",
      "description": "Create index on collection",
      "examples": [
        "create_index({'userId': 1})",
        "create_index({'userId': 1, 'status': 1, 'createdAt': -1})"
      ]
    },
    "compare": {
      "signature": "compare(tags: list[str]) -> dict",
      "description": "Compare benchmark results by tag",
      "examples": [
        "compare(['baseline', 'with_index'])"
      ]
    }
  },
  "template_code": """
from mdbpl import init, benchmark, create_index, compare

# Step 1: Initialize test data
print("Loading test data...")
init(collection='orders', scale=10000)

# Step 2: Baseline benchmark (no index)
print("Running baseline benchmark...")
baseline = benchmark(
    query={'userId': 123, 'status': 'pending'},
    sort={'createdAt': -1},
    tag='baseline'
)
print(f"Baseline throughput: {baseline['throughput']} ops/sec")

# Step 3: Create recommended index
print("Creating compound index...")
create_index({
    'userId': 1,
    'status': 1,
    'createdAt': -1
})

# Step 4: Benchmark with index
print("Running optimized benchmark...")
optimized = benchmark(
    query={'userId': 123, 'status': 'pending'},
    sort={'createdAt': -1},
    tag='optimized'
)
print(f"Optimized throughput: {optimized['throughput']} ops/sec")

# Step 5: Compare results
print("\\nComparison:")
results = compare(['baseline', 'optimized'])
improvement = optimized['throughput'] / baseline['throughput']
print(f"Improvement: {improvement:.1f}x faster")
"""
}
```

**Agent Usage:** Agent uses this template to generate workflows tailored to user's specific queries.

---

### 3. `get_best_practices`

**Purpose:** Provide MongoDB indexing and query optimization best practices.

**Input:** 
```json
{
  "topic": "indexing" | "query_patterns" | "schema_design" | "all"
}
```

**Output:**
```json
{
  "indexing": {
    "compound_index_order": [
      "Equality filters first",
      "Sort fields second",
      "Range filters last",
      "Example: {userId: 1, status: 1, createdAt: -1} for find({userId: X, status: Y}).sort({createdAt: -1})"
    ],
    "covered_queries": [
      "Include all projected fields in index",
      "Eliminates need to read documents",
      "Significant performance gain"
    ],
    "index_selectivity": [
      "High cardinality fields make better indexes",
      "Low cardinality (boolean, enum) less effective alone",
      "Combine low cardinality with high cardinality in compound indexes"
    ],
    "avoid": [
      "Too many indexes (write performance penalty)",
      "Unused indexes (maintenance overhead)",
      "Redundant indexes (covered by compound indexes)"
    ]
  },
  "query_patterns": {
    "n_plus_1": "Avoid queries in loops - use $in or aggregation",
    "projection": "Always project only needed fields",
    "limit": "Use .limit() for pagination, not .skip() on large offsets",
    "explain": "Use .explain('executionStats') to verify index usage"
  }
}
```

**Agent Usage:** Agent references this when making recommendations to user.

---

### 4. `get_schema`

**Purpose:** Introspect MongoDB to understand current database state.

**Input:**
```json
{
  "mongodb_uri": "mongodb://...",
  "collection": "orders"
}
```

**Output:**
```json
{
  "collection": "orders",
  "database": "myapp",
  "indexes": [
    {
      "name": "_id_",
      "key": {"_id": 1},
      "unique": true
    },
    {
      "name": "userId_1",
      "key": {"userId": 1}
    }
  ],
  "stats": {
    "count": 15000,
    "size": 7680000,
    "avgObjSize": 512,
    "storageSize": 8192000,
    "totalIndexSize": 245760
  },
  "sample_doc": {
    "_id": "...",
    "userId": 123,
    "status": "pending",
    "items": [...],
    "createdAt": "2026-05-20T..."
  },
  "field_types": {
    "userId": "int",
    "status": "string",
    "items": "array",
    "createdAt": "date"
  }
}
```

**Agent Usage:** Agent calls this to understand what indexes already exist and what the document structure looks like.

---

### 5. `execute_workflow`

**Purpose:** Execute agent-generated Python workflow in isolated container.

**Input:**
```json
{
  "workflow_code": "<Python code string>",
  "mongodb_uri": "mongodb://...",
  "timeout_seconds": 300
}
```

**Output:**
```json
{
  "success": true,
  "execution_time_seconds": 45.2,
  "stdout": "<captured output>",
  "stderr": "",
  "exit_code": 0,
  "results": {
    "baseline": {
      "throughput": 100.5,
      "latency_p50": 10.2,
      "latency_p99": 45.3
    },
    "optimized": {
      "throughput": 1050.2,
      "latency_p50": 1.1,
      "latency_p99": 4.8
    }
  }
}
```

**Error Output:**
```json
{
  "success": false,
  "execution_time_seconds": 2.1,
  "stdout": "",
  "stderr": "IndexError: list index out of range\n...",
  "exit_code": 1,
  "error": "Workflow execution failed"
}
```

**Agent Usage:** Agent sends generated workflow code for execution and receives benchmark results.

---

## Usage Flow

### Example: User Asks "Is my order query optimized?"

**1. Agent Analysis (Workspace Access)**
```
Agent reads: src/routes/orders.js
Agent finds: 
  Line 42: db.orders.find({userId: req.userId, status: 'pending'})
                    .sort({createdAt: -1})
                    .limit(10)
```

**2. Agent Calls MCP: `get_schema`**
```json
{
  "mongodb_uri": "mongodb://localhost:27017",
  "collection": "orders"
}
```

**MCP Returns:**
```json
{
  "collection": "orders",
  "indexes": [
    {"name": "_id_", "key": {"_id": 1}},
    {"name": "userId_1", "key": {"userId": 1}}
  ],
  "stats": {"count": 15000}
}
```

**3. Agent Analysis**
- Query filters on `userId` and `status`
- Sorts by `createdAt`
- Only has index on `userId`
- Missing compound index!

**4. Agent Calls MCP: `get_workflow_template`**
```json
{"scenario": "index_comparison"}
```

**MCP Returns:** Template code

**5. Agent Generates Workflow**
```python
from mdbpl import init, benchmark, create_index, compare

# Load realistic order data
init(collection='orders', scale=15000)

# Test current query without compound index
baseline = benchmark(
    query={'userId': 123, 'status': 'pending'},
    sort={'createdAt': -1},
    tag='current'
)

# Create recommended compound index
create_index({'userId': 1, 'status': 1, 'createdAt': -1})

# Test with compound index
optimized = benchmark(
    query={'userId': 123, 'status': 'pending'},
    sort={'createdAt': -1},
    tag='optimized'
)

# Show results
results = compare(['current', 'optimized'])
print(f"Improvement: {optimized['throughput']/baseline['throughput']:.1f}x")
```

**6. Agent Calls MCP: `execute_workflow`**
```json
{
  "workflow_code": "<generated code>",
  "mongodb_uri": "mongodb://localhost:27017"
}
```

**MCP Returns:**
```json
{
  "success": true,
  "results": {
    "current": {"throughput": 95},
    "optimized": {"throughput": 1020}
  }
}
```

**7. Agent Response to User**
```
Your order lookup query can be 10x faster! 

Current performance: 95 ops/sec
With compound index: 1,020 ops/sec

Recommendation:
db.orders.createIndex({userId: 1, status: 1, createdAt: -1})

This compound index will:
✓ Filter efficiently on userId and status
✓ Sort using the index (no in-memory sort)
✓ Dramatically reduce query latency
```

---

## Implementation Structure

```
mongodb-performance-lab/
├── src/mdbpl/              # Existing CLI/library
│   ├── api.py             # Python API for workflows
│   └── ...
│
├── mcp/                    # NEW: MCP server
│   ├── server.py          # Main MCP server
│   ├── Dockerfile         # MCP container
│   ├── requirements.txt   # mcp, pymongo
│   │
│   └── tools/             # MCP tool implementations
│       ├── __init__.py
│       ├── analysis_guide.py    # get_analysis_guide
│       ├── templates.py         # get_workflow_template
│       ├── best_practices.py    # get_best_practices
│       ├── schema.py            # get_schema
│       └── executor.py          # execute_workflow
│
├── docker-compose.yml     # Add mcp-server service
└── MCP_PLAN.md           # This document
```

---

## Docker Integration

### docker-compose.yml (additions)

```yaml
services:
  # ... existing mongodb, perflab services ...

  mcp-server:
    build:
      context: .
      dockerfile: mcp/Dockerfile
    depends_on:
      - mongodb
    environment:
      MONGODB_URI: mongodb://mongodb:27017
    volumes:
      - mcp_workflows:/tmp/workflows  # Temp workflow execution
    stdin_open: true
    tty: true
    command: ["python", "mcp/server.py"]

volumes:
  mongodb_data:
  perflab_data:
  mcp_workflows:  # NEW
```

### mcp/Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy and install mdbpl library first
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN pip install --no-cache-dir -e .

# Install MCP server dependencies
COPY mcp/requirements.txt mcp/
RUN pip install --no-cache-dir -r mcp/requirements.txt

# Default command
CMD ["python", "mcp/server.py"]
```

---

## VS Code Configuration

User adds to their workspace settings:

**.vscode/settings.json:**
```json
{
  "mcp.servers": {
    "mongodb-perflab": {
      "command": "docker",
      "args": [
        "compose",
        "-f",
        "c:/Repos/spencershepard@hotmail.com/mongodb-performance-lab/docker-compose.yml",
        "run",
        "--rm",
        "mcp-server"
      ]
    }
  }
}
```

Or use stdio over Docker exec:
```json
{
  "mcp.servers": {
    "mongodb-perflab": {
      "command": "docker",
      "args": ["exec", "-i", "mongodb-performance-lab-mcp-server-1", "python", "mcp/server.py"]
    }
  }
}
```

---

## Security Considerations

### 1. **Isolated Execution**
- Workflows run in Docker container
- No access to host filesystem
- Limited network access (MongoDB only)

### 2. **No Code Analysis**
- MCP never accesses user's source code
- Agent does all code reading (already sandboxed)

### 3. **MongoDB Access Control**
- User controls MongoDB URI
- Recommend test database only
- Never connect to production

### 4. **Workflow Validation**
- Basic syntax checking before execution
- Timeout enforcement (default 5 minutes)
- Resource limits on container

---

## Future Enhancements

### Phase 2: Advanced Features
- **Baseline tracking**: Store and compare against previous runs
- **CI/CD integration**: Automated performance regression testing
- **Schema recommendations**: Suggest schema optimizations
- **Aggregation pipeline analysis**: Optimize complex pipelines

### Phase 3: UI Integration
- **Web dashboard**: Visualize benchmark results
- **Real-time monitoring**: Watch workflow execution
- **History**: Track performance over time

### Phase 4: Multi-Database
- **PostgreSQL support**: Expand beyond MongoDB
- **Redis benchmarking**: Cache performance testing
- **Elasticsearch**: Search performance

---

## Implementation Checklist

- [ ] Create `mcp/` directory structure
- [ ] Implement `mcp/server.py` with MCP protocol
- [ ] Implement `get_analysis_guide` tool
- [ ] Implement `get_workflow_template` tool
- [ ] Implement `get_best_practices` tool
- [ ] Implement `get_schema` tool
- [ ] Implement `execute_workflow` tool
- [ ] Create `mcp/Dockerfile`
- [ ] Update `docker-compose.yml`
- [ ] Create Python API in `src/mdbpl/api.py` for workflows
- [ ] Test MCP server with VS Code agent
- [ ] Document usage in README.md

---

## Notes

- **Agent is the brain**: All analysis and generation happens in agent
- **MCP is the executor**: Provides knowledge and runs workflows
- **Python workflows**: Full expressiveness, LLM-friendly
- **Security through isolation**: Container sandboxing protects user
