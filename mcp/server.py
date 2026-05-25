"""MongoDB Performance Lab MCP server.

Runs inside the perflab container via:
  docker compose exec -i perflab python mcp/server.py

Exposes 5 tools to VS Code agents:
  get_analysis_guide  — how to find MongoDB queries in user code
  get_demo_examples   — workflow instructions + built-in demo source code
  get_best_practices  — indexing and query optimization reference
  get_schema          — introspect a live MongoDB collection
  execute_demo        — run an agent-generated Demo subclass, return results
"""

import importlib.util
import inspect
import json
import os
import tempfile
import traceback
from pathlib import Path

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("mongodb-perflab")

_ROOT = Path(__file__).parent.parent
_DEMOS_DIR = _ROOT / "src" / "mdbpl" / "demos"
_WORKFLOW_GUIDE = _ROOT / "WORKFLOW_AGENT_PROMPT.md"


# ---------------------------------------------------------------------------
# get_analysis_guide
# ---------------------------------------------------------------------------

@mcp.tool()
def get_analysis_guide() -> str:
    """
    Return instructions for finding and analysing MongoDB queries in user code.
    Call this first when the user asks you to optimise their database queries.
    """
    return """\
# MongoDB Query Analysis Guide

## Step 1 — Find queries in the codebase

### JavaScript / TypeScript (Node.js, Mongoose)
Search for:
  db.<collection>.find(...)          db.<collection>.findOne(...)
  db.<collection>.aggregate(...)     db.<collection>.updateOne/Many(...)
  Model.find(...)                    Model.findOne(...)   (Mongoose)
  collection.find(...)               collection.aggregate(...)

Libraries: `mongodb`, `mongoose`, `@types/mongodb`

### Python
Search for:
  collection.find(...)               collection.find_one(...)
  collection.aggregate(...)          collection.update_one/many(...)
  db["collection"].find(...)

Libraries: `pymongo`, `motor`

## Step 2 — Extract the query shape

For each query record:
  - Filter fields   e.g. {userId: X, status: "pending"}
  - Sort fields     e.g. .sort({createdAt: -1})
  - Projection      e.g. {name: 1, email: 1}
  - Limit / skip
  - Collection name and database

## Step 3 — Identify the hot path

Prioritise queries that are:
  - Inside route handlers called on every request
  - Inside loops (N+1 pattern — each loop iteration hits the database)
  - Missing an index on the filter or sort field (call get_schema to check)
  - Performing a sort on a non-indexed field

## Step 4 — Call get_schema

Call get_schema with the user's MongoDB URI and collection name.
Compare the existing indexes against the query's filter + sort fields.
Missing compound indexes are the most common cause of slow queries.

## Red flags
  - COLLSCAN on a large collection (no index on filter field)
  - In-memory sort (sort field not in index)
  - Queries inside for/while loops
  - Missing compound index: existing single-field index only partially covers the query
  - Redundant indexes that are subsets of an existing compound index
"""


# ---------------------------------------------------------------------------
# get_demo_examples
# ---------------------------------------------------------------------------

@mcp.tool()
def get_demo_examples(scenario: str = "all") -> str:
    """
    Return workflow instructions and working Demo class source code for the agent
    to learn from and adapt. Always call this before generating a new workflow.

    scenario: "all" | "index_comparison" | "write_performance"
      index_comparison  — range queries, top-N, point reads; single or compound index
      write_performance — insert throughput degradation from too many indexes
      all               — both examples (default)
    """
    parts = []

    if _WORKFLOW_GUIDE.exists():
        parts.append(_WORKFLOW_GUIDE.read_text(encoding="utf-8"))

    if scenario in ("all", "index_comparison"):
        path = _DEMOS_DIR / "index_performance.py"
        if path.exists():
            parts.append(
                "# Built-in example: src/mdbpl/demos/index_performance.py\n\n"
                f"```python\n{path.read_text(encoding='utf-8')}\n```"
            )

    if scenario in ("all", "write_performance"):
        path = _DEMOS_DIR / "overindexing.py"
        if path.exists():
            parts.append(
                "# Built-in example: src/mdbpl/demos/overindexing.py\n\n"
                f"```python\n{path.read_text(encoding='utf-8')}\n```"
            )

    return "\n\n---\n\n".join(parts)


# ---------------------------------------------------------------------------
# get_best_practices
# ---------------------------------------------------------------------------

@mcp.tool()
def get_best_practices(topic: str = "all") -> str:
    """
    Return MongoDB indexing and query optimisation best practices.

    topic: "all" | "indexing" | "query_patterns"
    """
    indexing = """\
# Indexing Best Practices

## Compound index field order (ESR rule)
Always arrange compound index fields in this order:
  1. Equality predicates first   {status: 1}
  2. Sort fields second          {createdAt: -1}
  3. Range predicates last       {amount: 1}

Example: query is .find({userId: X, status: "pending"}).sort({createdAt: -1})
  Correct:   {userId: 1, status: 1, createdAt: -1}
  Incorrect: {createdAt: -1, userId: 1, status: 1}

The equality fields narrow the result set first; the sort field in the index
eliminates the in-memory sort; the range field is last because it can only
be traversed sequentially after the equality narrowing.

## Covered queries
Include projected fields in the index to avoid document lookups entirely:
  Query:  .find({userId: X}, {email: 1, name: 1})
  Index:  {userId: 1, email: 1, name: 1}
MongoDB satisfies the query entirely from the index — zero document reads.

## Index selectivity
High-cardinality fields (userId, orderId) make more selective indexes than
low-cardinality fields (status: 3 values, boolean: 2 values).
Combine low-cardinality with high-cardinality in compound indexes:
  {status: 1, userId: 1}  — status narrows broadly, userId within that

## Avoid over-indexing
Every secondary index adds overhead to every write (insert, update, delete).
Each index is an additional B-tree that must be updated on every write.
  - Audit unused indexes with: db.collection.aggregate([{$indexStats: {}}])
  - Drop indexes where accesses.ops == 0
  - Replace two single-field indexes with one compound index where queries allow

## Partial indexes
Index only documents that match a filter — smaller index, faster writes:
  db.orders.createIndex({createdAt: 1}, {partialFilterExpression: {status: "active"}})
Useful when queries always include a highly selective equality predicate.
"""

    query_patterns = """\
# Query Pattern Best Practices

## Avoid N+1 queries
Replace loops that query inside each iteration with a single $in query:
  Bad:  for id in ids: db.users.find_one({_id: id})
  Good: db.users.find({_id: {$in: ids}})

## Pagination: prefer range-based over skip
Large .skip() values scan and discard documents — slow at scale:
  Bad:  .find().sort({_id: 1}).skip(50000).limit(100)
  Good: .find({_id: {$gt: lastSeenId}}).sort({_id: 1}).limit(100)

## Always project only needed fields
Reduces document size transferred from server:
  .find({userId: X}, {name: 1, email: 1, _id: 0})

## Verify index usage with explain
  db.collection.find({...}).sort({...}).explain("executionStats")
  Look for: IXSCAN (good) vs COLLSCAN (bad), totalDocsExamined vs nReturned

## Aggregation pipeline ordering
Put $match and $limit as early as possible — they reduce the document set
that subsequent stages must process. An index on the $match field is used
if $match is the first stage.
"""

    if topic == "indexing":
        return indexing
    if topic == "query_patterns":
        return query_patterns
    return indexing + "\n\n---\n\n" + query_patterns


# ---------------------------------------------------------------------------
# get_schema
# ---------------------------------------------------------------------------

@mcp.tool()
def get_schema(mongodb_uri: str, collection: str, database: str = "perflab") -> str:
    """
    Introspect a MongoDB collection: indexes, document count, storage stats,
    a sample document, and inferred field types.

    Use this to check what indexes already exist before recommending new ones.
    """
    from pymongo import MongoClient
    from bson import ObjectId
    from datetime import datetime

    client = MongoClient(mongodb_uri, serverSelectionTimeoutMS=5000)
    try:
        db = client[database]
        coll = db[collection]

        indexes = [
            {
                "name": idx["name"],
                "key": dict(idx["key"]),
                "unique": bool(idx.get("unique", False)),
                "sparse": bool(idx.get("sparse", False)),
            }
            for idx in coll.list_indexes()
        ]

        stats = db.command("collStats", collection)
        sample = coll.find_one({})

        def _type_name(v) -> str:
            if isinstance(v, ObjectId):
                return "ObjectId"
            if isinstance(v, datetime):
                return "datetime"
            return type(v).__name__

        field_types = {k: _type_name(v) for k, v in (sample or {}).items()}
        sample_doc = {k: str(v) for k, v in (sample or {}).items()}

        result = {
            "collection": collection,
            "database": database,
            "indexes": indexes,
            "stats": {
                "count": stats.get("count", 0),
                "size_bytes": stats.get("size", 0),
                "avg_obj_size_bytes": int(stats.get("avgObjSize", 0)),
                "total_index_size_bytes": stats.get("totalIndexSize", 0),
            },
            "sample_doc": sample_doc,
            "field_types": field_types,
        }
        return json.dumps(result, indent=2)
    finally:
        client.close()


# ---------------------------------------------------------------------------
# execute_demo
# ---------------------------------------------------------------------------

@mcp.tool()
def execute_demo(demo_code: str, mongodb_uri: str, timeout_seconds: int = 300) -> str:
    """
    Execute an agent-generated Demo subclass inside the perflab container.

    demo_code must be a complete Python module containing exactly one class
    that subclasses mdbpl.demos.base.Demo and implements steps().

    Returns DemoResult as JSON. Each step's stdout is in steps[].outputs[].stdout.
    The agent should read per-step stdout to extract throughput and latency numbers.

    On success:  {"success": true, "demo_name": "...", "steps": [...]}
    On failure:  {"success": false, "error": "...", "error_type": "syntax|runtime"}
    """
    from mdbpl.demos.base import Demo

    old_uri = os.environ.get("MONGODB_URI")
    tmp_path = None

    try:
        os.environ["MONGODB_URI"] = mongodb_uri

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, dir="/tmp", encoding="utf-8"
        ) as f:
            f.write(demo_code)
            tmp_path = f.name

        spec = importlib.util.spec_from_file_location("_generated_demo", tmp_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        demo_classes = [
            cls
            for _, cls in inspect.getmembers(module, inspect.isclass)
            if issubclass(cls, Demo) and cls is not Demo
        ]

        if not demo_classes:
            return json.dumps({
                "success": False,
                "error": "No Demo subclass found. The module must define a class that subclasses mdbpl.demos.base.Demo.",
                "error_type": "structure",
            })

        demo_instance = demo_classes[0]()
        result = demo_instance.run()
        return json.dumps(result.to_dict(), default=str)

    except SyntaxError as e:
        return json.dumps({
            "success": False,
            "error": f"SyntaxError: {e.msg}",
            "error_type": "syntax",
            "line": e.lineno,
            "suggestion": "Check for mismatched parentheses or quotes in DemoStep/ShellCommand/MongoshCommand calls.",
        })
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": str(e),
            "error_type": "runtime",
            "traceback": traceback.format_exc(),
        })
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
        if old_uri is not None:
            os.environ["MONGODB_URI"] = old_uri
        else:
            os.environ.pop("MONGODB_URI", None)


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run()
