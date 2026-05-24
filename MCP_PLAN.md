# MCP Server Implementation Plan

## Overview

This document outlines the design and implementation plan for the MongoDB Performance Lab MCP (Model Context Protocol) server. The MCP server enables VS Code agents to generate and execute performance testing workflows based on user's application code.

**Key Innovation:** Workflows use the same Demo class format as the built-in demos, ensuring proven patterns and zero learning curve for LLM code generation.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  VS Code Agent (Copilot)                                    │
│  ─────────────────────────────────────────────────────────  │
│  • Has full workspace access                                │
│  • Reads and analyzes user's code directly                  │
│  • Generates Demo subclass workflows based on examples      │
│  • Orchestrates the performance testing flow                │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ↓
┌─────────────────────────────────────────────────────────────┐
│  MCP Server (Knowledge + Execution)                         │
│  ─────────────────────────────────────────────────────────  │
│  Provides:                                                   │
│  • Analysis guidance (how to find queries)                  │
│  • Demo examples (working index_performance.py, etc.)       │
│  • Best practices (indexing strategies)                     │
│  • Schema introspection (current indexes, stats)            │
│  • Demo execution (runs LLM-generated Demo classes)         │
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
│  • MCP executes Demo workflows against this                 │
└──────────────────────────────────────────────────────────────┘
```

## Design Principles

### 1. **Agent-Driven Analysis**
- Agent has workspace access and reads user's code directly
- MCP provides **guidance** and **examples**, not code analysis
- Agent is responsible for finding queries, understanding context

### 2. **Secure Execution**
- Workflows execute in isolated Docker container
- No arbitrary file system access
- Agent-generated Demo classes run in sandbox
- Only benchmark results returned to agent

### 3. **Proven Patterns**
- Workflows use same Demo class format as built-in demos
- LLM learns from working examples (index_performance.py)
- Reuses all existing infrastructure (ShellCommand, MongoshCommand, executor)
- If it works in UI, it works via MCP

### 4. **Structured Code Generation**
- Agent generates Demo subclasses (highly structured)
- Clear patterns: baseline → optimization → comparison
- Rich inline documentation guides LLM
- Type-safe Python classes with validation

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

### 2. `get_demo_examples`

**Purpose:** Provide working Demo class examples for agent to learn from and adapt.

**Input:** 
```json
{
  "scenario": "index_comparison" | "compound_index" | "write_performance" | "all"
}
```

**Output:**
```json
{
  "examples": [
    {
      "name": "index_performance",
      "file": "src/mdbpl/demos/index_performance.py",
      "description": "Compare performance with/without single-field index on numeric field",
      "use_when": [
        "User has slow queries with range filters",
        "Missing indexes detected on filter fields",
        "Queries involve sorting on indexed field",
        "Collection scans detected in query plans"
      ],
      "pattern": "baseline → create_index → optimized → compare",
      "code": "<full index_performance.py source code with inline comments>",
      "key_learnings": [
        "Use ShellCommand for mdbpl CLI (init, run, compare)",
        "Use MongoshCommand for MongoDB operations (createIndex, queries)",
        "Always tag benchmarks for comparison",
        "Include markdown to explain WHY each step matters",
        "collapse_output=False shows detailed command output"
      ]
    }
  ],
  "command_reference": {
    "ShellCommand": {
      "description": "Execute shell commands (mdbpl CLI)",
      "examples": [
        "ShellCommand('mdbpl init --scale 10k')",
        "ShellCommand('mdbpl run --workload range-scan --tag baseline')",
        "ShellCommand('mdbpl compare --tags baseline,optimized')"
      ]
    },
    "MongoshCommand": {
      "description": "Execute mongosh JavaScript code",
      "examples": [
        "MongoshCommand('db.collection.createIndex({field: 1})')",
        "MongoshCommand('db.collection.getIndexes().forEach(...)')"
      ]
    }
  },
  "demo_structure": {
    "class_attributes": {
      "id": "unique-identifier (lowercase-hyphenated)",
      "title": "Display Name",
      "description": "Short description for selection",
      "markdown_file": "Leave empty for inline markdown"
    },
    "steps_method": "Returns List[DemoStep] with sequential steps",
    "demostep_attributes": {
      "id": "step-identifier",
      "title": "Step Title",
      "description": "Brief step description",
      "markdown": "Detailed explanation with context",
      "commands": "List of ShellCommand or MongoshCommand"
    }
  }
}
```

**Agent Usage:** 
1. Agent reads example demos to learn structure
2. Agent adapts pattern to user's specific query
3. Agent generates new Demo subclass based on example
4. Agent ensures generated code follows proven patterns

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

### 5. `execute_demo`

**Purpose:** Execute agent-generated Demo class in isolated container.

**Input:**
```json
{
  "demo_code": "<Python code - complete Demo subclass>",
  "mongodb_uri": "mongodb://...",
  "timeout_seconds": 300
}
```

**Execution Process:**
1. Validate Demo class structure (has id, title, steps() method)
2. Write to temporary module in container
3. Dynamically import Demo class
4. Instantiate and execute via existing Demo executor
5. Capture output and results
6. Return structured results

**Output (Success):**
```json
{
  "success": true,
  "execution_time_seconds": 45.2,
  "demo_id": "user-order-query-optimization",
  "steps_completed": 5,
  "steps": [
    {
      "id": "init",
      "title": "Load Test Data",
      "success": true,
      "output": "Loaded 10,000 documents..."
    },
    {
      "id": "baseline",
      "title": "Baseline Benchmark",
      "success": true,
      "output": "Throughput: 95 ops/sec..."
    },
    {
      "id": "create-index",
      "title": "Create Index",
      "success": true,
      "output": "Index created on {userId: 1, status: 1}"
    },
    {
      "id": "optimized",
      "title": "Optimized Benchmark",
      "success": true,
      "output": "Throughput: 1020 ops/sec..."
    },
    {
      "id": "compare",
      "title": "Compare Results",
      "success": true,
      "output": "10.7x improvement in throughput..."
    }
  ],
  "benchmark_results": {
    "baseline": {
      "run_id": 53,
      "throughput": 95.3,
      "latency_p50": 10.5,
      "latency_p99": 45.2
    },
    "optimized": {
      "run_id": 54,
      "throughput": 1020.4,
      "latency_p50": 0.9,
      "latency_p99": 4.1
    }
  }
}
```

**Output (Error - Syntax):**
```json
{
  "success": false,
  "error": "SyntaxError: invalid syntax",
  "error_type": "syntax",
  "line": 42,
  "message": "Missing closing parenthesis in DemoStep definition",
  "suggestion": "Check DemoStep() calls for matching parentheses"
}
```

**Output (Error - Runtime):**
```json
{
  "success": false,
  "error": "IndexError: list index out of range",
  "error_type": "runtime",
  "step_id": "baseline",
  "traceback": "<full traceback>",
  "steps_completed": 1,
  "steps": [
    {"id": "init", "success": true},
    {"id": "baseline", "success": false, "error": "IndexError..."}
  ]
}
```

**Agent Usage:** 
1. Agent generates Demo subclass code
2. Agent calls execute_demo with generated code
3. If syntax error, agent fixes and retries
4. If runtime error, agent debugs and retries
5. On success, agent presents results to user

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

**4. Agent Calls MCP: `get_demo_examples`**
```json
{"scenario": "index_comparison"}
```

**MCP Returns:** Full `index_performance.py` source code with inline comments and patterns

**5. Agent Generates Demo Subclass**

Agent adapts the example pattern to user's specific query:

```python
"""
Order Query Optimization Demo
Generated for: db.orders.find({userId: X, status: 'pending'}).sort({createdAt: -1})
"""

from typing import List
from mdbpl.demos.base import Demo, DemoStep, ShellCommand, MongoshCommand


class OrderQueryOptimizationDemo(Demo):
    """
    Optimize order lookup query with compound index.
    
    Pattern: baseline → create_compound_index → optimized → compare
    Current: Only indexed on userId (partial match)
    Recommended: Compound index {userId: 1, status: 1, createdAt: -1}
    """
    
    id = "order-query-optimization"
    title = "Orders Query Optimization"
    description = "Optimize userId + status filter with sort on createdAt"
    markdown_file = ""
    
    def steps(self) -> List[DemoStep]:
        return [
            # STEP 1: Initialize realistic order data
            DemoStep(
                id="init",
                title="Load Order Test Data",
                description="Initialize 15,000 order documents matching production schema",
                markdown="""
## Initialize Test Data

Load 15,000 orders to match production scale. Using YCSB base data and adding order-specific fields (userId, status, createdAt).
""",
                commands=[
                    ShellCommand("mdbpl init --scale 15k", collapse_output=False),
                    MongoshCommand("""
// Add order-specific fields
var statuses = ['pending', 'completed', 'cancelled'];
var batch = [];
var now = new Date();

db.usertable.find().forEach(function(doc, idx) {
    batch.push({
        updateOne: {
            filter: {_id: doc._id},
            update: {$set: {
                userId: Math.floor(idx / 10),  // ~10 orders per user
                status: statuses[idx % 3],
                createdAt: new Date(now - Math.random() * 30 * 24 * 60 * 60 * 1000)
            }}
        }
    });
    if (batch.length >= 1000) {
        db.usertable.bulkWrite(batch);
        batch = [];
    }
});
if (batch.length > 0) db.usertable.bulkWrite(batch);

print("✓ Added order fields to 15,000 documents");
""", collapse_output=False)
                ]
            ),
            
            # STEP 2: Baseline with current index
            DemoStep(
                id="baseline",
                title="Baseline Performance (userId index only)",
                description="Test query with existing single-field index",
                markdown="""
## Baseline Performance

Current query uses existing userId index but still needs to:
1. Scan all orders for this userId
2. Filter by status in memory
3. Sort by createdAt in memory

Expected: Moderate performance, in-memory operations.
""",
                commands=[
                    ShellCommand("mdbpl run --query '{\"userId\": 123, \"status\": \"pending\"}' --sort '{\"createdAt\": -1}' --tag baseline")
                ]
            ),
            
            # STEP 3: Create compound index
            DemoStep(
                id="create-index",
                title="Create Compound Index",
                description="Create index on {userId: 1, status: 1, createdAt: -1}",
                markdown="""
## Create Compound Index

Compound index field order:
1. userId (equality filter) - first for efficient user lookup
2. status (equality filter) - second for additional filtering
3. createdAt (sort field) - last, descending to match query sort

This allows MongoDB to use index for entire query execution.
""",
                commands=[
                    MongoshCommand("""
db.usertable.createIndex({userId: 1, status: 1, createdAt: -1});
print("✓ Created compound index: {userId: 1, status: 1, createdAt: -1}");
""")
                ]
            ),
            
            # STEP 4: Optimized benchmark
            DemoStep(
                id="optimized",
                title="Optimized Performance",
                description="Test query with compound index",
                markdown="""
## Optimized Performance

With compound index, MongoDB can:
1. Jump directly to userId=123 in index
2. Filter to status='pending' within that range
3. Results already sorted by createdAt (descending)

Expected: 10-50x improvement, no in-memory operations.
""",
                commands=[
                    ShellCommand("mdbpl run --query '{\"userId\": 123, \"status\": \"pending\"}' --sort '{\"createdAt\": -1}' --tag optimized")
                ]
            ),
            
            # STEP 5: Compare
            DemoStep(
                id="compare",
                title="Compare Results",
                description="Show before/after comparison",
                markdown="""
## Results Comparison

Compare throughput, latency, and query execution stats between baseline and optimized versions.
""",
                commands=[
                    ShellCommand("mdbpl compare --tags baseline,optimized")
                ]
            )
        ]
```

**6. Agent Calls MCP: `execute_demo`**
```json
{
  "demo_code": "<generated Demo subclass code>",
  "mongodb_uri": "mongodb://localhost:27017"
}
```

**MCP Returns:**
```json
{
  "success": true,
  "steps_completed": 5,
  "benchmark_results": {
    "baseline": {
      "run_id": 53,
      "throughput": 95.3,
      "latency_p50": 10.5
    },
    "optimized": {
      "run_id": 54,
      "throughput": 1020.4,
      "latency_p50": 0.9
    }
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

I've run a performance test to verify - see the full comparison in the Results tab.
```

---

## Implementation Structure

```
mongodb-performance-lab/
├── src/mdbpl/              # Existing CLI/library
│   ├── demos/
│   │   ├── base.py        # Demo, DemoStep, Command classes
│   │   └── index_performance.py  # ✨ Enhanced with LLM guidance comments
│   ├── executor.py        # Step execution engine
│   └── ...
│
├── mcp/                    # NEW: MCP server
│   ├── server.py          # Main MCP server (stdio protocol)
│   ├── Dockerfile         # MCP container
│   ├── requirements.txt   # mcp, pymongo
│   │
│   └── tools/             # MCP tool implementations
│       ├── __init__.py
│       ├── analysis_guide.py    # get_analysis_guide
│       ├── demo_examples.py     # get_demo_examples (returns demo source)
│       ├── best_practices.py    # get_best_practices
│       ├── schema.py            # get_schema (introspect MongoDB)
│       └── executor.py          # execute_demo (run LLM-generated Demo)
│
├── docker-compose.yml     # Add mcp-server service
└── MCP_PLAN.md           # This document
```

### Key Files

**`src/mdbpl/demos/index_performance.py`** (Enhanced)
- Added comprehensive inline comments for LLM learning
- Command pattern examples (ShellCommand, MongoshCommand)
- Clear step progression: baseline → optimization → comparison
- Serves as primary template for LLM-generated demos

**`mcp/tools/demo_examples.py`** (New)
- Reads actual demo source files
- Returns full code with annotations
- Provides structure reference
- Maps scenarios to appropriate demo examples

**`mcp/tools/executor.py`** (New)
- Validates generated Demo class structure
- Dynamically imports and instantiates Demo
- Executes via existing Demo.execute_step() infrastructure
- Returns structured results with benchmark data

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
- **Multiple demo templates**: Add compound_index, write_performance, aggregation_pipeline demos
- **Baseline tracking**: Store and compare against previous runs
- **CI/CD integration**: Automated performance regression testing
- **Schema recommendations**: Suggest schema optimizations beyond indexing
- **Aggregation pipeline analysis**: Optimize complex pipelines
- **Template patterns documentation**: Add structured pattern catalog at top of demo files for easier LLM parsing (e.g., JSON/YAML frontmatter describing common workflow patterns)

### Phase 3: UI Integration
- **Web dashboard**: Visualize benchmark results (already exists, extend for MCP-generated demos)
- **Real-time monitoring**: Watch workflow execution progress
- **History**: Track performance over time
- **Demo library**: Browse and run LLM-generated demos from UI

### Phase 4: Multi-Database
- **PostgreSQL support**: Expand beyond MongoDB
- **Redis benchmarking**: Cache performance testing
- **Elasticsearch**: Search performance

---

## Implementation Checklist

### Phase 1: Core MCP Server
- [x] Enhance `index_performance.py` with inline LLM guidance comments
- [ ] Create `mcp/` directory structure
- [ ] Implement `mcp/server.py` with MCP protocol (stdio)
- [ ] Implement `get_analysis_guide` tool
- [ ] Implement `get_demo_examples` tool (reads demo source files)
- [ ] Implement `get_best_practices` tool
- [ ] Implement `get_schema` tool (MongoDB introspection)
- [ ] Implement `execute_demo` tool (dynamic import + execution)

### Phase 2: Infrastructure
- [ ] Create `mcp/Dockerfile`
- [ ] Update `docker-compose.yml` with mcp-server service
- [ ] Add validation for Demo class structure
- [ ] Add sandbox security (resource limits, timeout)
- [ ] Test dynamic Demo import and execution

### Phase 3: Testing & Documentation
- [ ] Test MCP server with VS Code agent
- [ ] Create example LLM-generated demos
- [ ] Verify error handling (syntax, runtime errors)
- [ ] Document usage in README.md
- [ ] Add MCP configuration examples for VS Code

---

## Notes

### Why Demo Classes Instead of Python API?

**Advantages:**
- **Proven patterns**: Reuses working demo infrastructure
- **Self-documenting**: Markdown explains WHY, not just HOW
- **Structured**: Clear class hierarchy, type hints
- **Visual**: Generated demos can run in UI too
- **LLM-friendly**: Python classes are easy for LLMs to generate
- **Zero new code**: No separate API layer needed

**Tradeoffs:**
- Slightly more verbose than imperative API
- Requires understanding of class structure
- But: LLM learns from examples easily

### Agent vs MCP Responsibilities

**Agent (Has Workspace Access):**
- Read user's source code
- Find MongoDB queries and patterns
- Analyze query structure (filters, sorts, projections)
- Generate Demo subclass based on examples
- Interpret results and make recommendations

**MCP (Sandboxed Execution):**
- Provide demo examples to learn from
- Provide best practices and guidance
- Introspect MongoDB schema (with user-provided URI)
- Execute generated Demo classes safely
- Return structured benchmark results

### Security Model

**Container Isolation:**
- Demo execution happens in Docker container
- No access to host filesystem
- Limited network (MongoDB only)
- Resource limits (CPU, memory, timeout)

**Code Validation:**
- Syntax check before execution
- Validate Demo class structure
- Ensure required methods exist
- Timeout enforcement (default 5 minutes)

**MongoDB Access:**
- User provides test database URI
- Never connect to production
- Agent-controlled credentials
- Recommend read-only user for schema introspection
