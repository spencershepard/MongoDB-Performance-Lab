"""MongoDB Performance Lab MCP server.

Runs inside the perflab container via:
  docker compose exec -i perflab python mcp/server.py

Exposes 6 tools to VS Code agents:
  get_analysis_guide  — how to find MongoDB queries in user code
  get_demo_examples   — workflow instructions + built-in demo source code
  get_best_practices  — indexing and query optimization reference
  get_schema          — introspect a live MongoDB collection
  explain_query       — run explain("executionStats") on any pipeline or find query
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

### PHP
Search for:
  $collection->find(...)             $collection->findOne(...)
  $collection->aggregate(...)        $collection->updateOne/Many(...)
  $db->selectCollection(...)

Libraries: `mongodb/mongodb`, `doctrine/mongodb-odm` (Doctrine ODM)
Doctrine ODM: look for `$dm->createQueryBuilder(...)` and `->field(...)->equals(...)`

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

def _discover_demos() -> dict:
    """
    Scan _DEMOS_DIR for *.py files (excluding __init__ and base), import each
    via the mdbpl.demos package, and return {demo_id: (file_path, Demo_class)}.
    Fully dynamic — dropping a new demo file in the directory is sufficient.
    """
    import importlib
    import inspect
    from mdbpl.demos.base import Demo

    result = {}
    for path in sorted(_DEMOS_DIR.glob("*.py")):
        if path.stem in ("__init__", "base"):
            continue
        try:
            mod = importlib.import_module(f"mdbpl.demos.{path.stem}")
        except Exception:
            continue
        for _, cls in inspect.getmembers(mod, inspect.isclass):
            if issubclass(cls, Demo) and cls is not Demo and hasattr(cls, "id"):
                result[cls.id] = (path, cls)
                break
    return result


@mcp.tool()
def get_demo_examples(demo_name: str = "list") -> str:
    """
    Return the workflow guide and Demo class source code for the agent to learn
    from and adapt when building new benchmarks.

    demo_name:
      "list"   — (default) return the workflow guide + a compact registry of all
                 available demos discovered from the demos directory. Use this
                 first to pick the closest match to the user's scenario.
      "<id>"   — return the workflow guide + full source for that specific demo.
                 Call with demo_name="list" first to see valid IDs.

    Workflow:
      1. Call get_demo_examples() to see available demos and pick the closest match.
      2. Call get_demo_examples(demo_name="<id>") to load that demo's full source.
      3. Adapt it for the user's schema and run via execute_demo().
    """
    guide = _WORKFLOW_GUIDE.read_text(encoding="utf-8") if _WORKFLOW_GUIDE.exists() else ""
    demos = _discover_demos()

    if demo_name == "list":
        rows = []
        for demo_id, (_, cls) in demos.items():
            step_count = len(cls().steps())
            rows.append(f"  {demo_id:<24} {step_count} steps  {cls.description}")
        registry = (
            "# Available Demo Examples\n\n"
            + "\n".join(rows)
            + "\n\nCall get_demo_examples(demo_name=\"<id>\") to load the full source for any demo."
        )
        return (guide + "\n\n---\n\n" + registry) if guide else registry

    if demo_name not in demos:
        available = ", ".join(f'"{k}"' for k in demos)
        return f'Unknown demo "{demo_name}". Available: {available}. Use demo_name="list" to see descriptions.'

    path, _ = demos[demo_name]
    source_block = (
        f"# Source: src/mdbpl/demos/{path.name}\n\n"
        f"```python\n{path.read_text(encoding='utf-8')}\n```"
    )
    return (guide + "\n\n---\n\n" + source_block) if guide else source_block


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

    mongodb_uri: use "mongodb://mongodb:27017" when running against the lab's
    built-in MongoDB instance (Docker service name is "mongodb", not "mongo"
    or "localhost").

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
# explain_query
# ---------------------------------------------------------------------------

def _extract_lookup_stages(explain_result: dict) -> list:
    """
    Scan the top-level stages array for $lookup entries and extract strategy info.
    Strategy is inferred from stage-level sibling keys (indexesUsed, collectionScans),
    not from inside the $lookup sub-dict where it does not appear in MongoDB 7.0.
    """
    lookup_info = []
    for stage in explain_result.get("stages", []):
        lookup = stage.get("$lookup")
        if not lookup or not isinstance(lookup, dict):
            continue
        indexes_used = stage.get("indexesUsed", [])
        collection_scans = stage.get("collectionScans", 0)
        info = {
            "from": lookup.get("from", "unknown"),
            "localField": lookup.get("localField", ""),
            "foreignField": lookup.get("foreignField", ""),
        }
        if indexes_used:
            info["strategy"] = "IndexedLoopJoin"
            info["indexName"] = indexes_used[0]
        elif collection_scans > 0:
            info["strategy"] = "NestedLoopJoin"
        else:
            info["strategy"] = "unknown"
        lookup_info.append(info)
    return lookup_info


def _walk_stages(stage):
    """
    Recursively walk an executionStages tree.
    Returns (scan_types, index_names, has_in_memory_sort).
    """
    if not stage or not isinstance(stage, dict):
        return [], [], False

    scan_types, index_names, has_sort = [], [], False
    name = stage.get("stage", "")

    if name == "IXSCAN":
        scan_types.append("IXSCAN")
        if "indexName" in stage:
            index_names.append(stage["indexName"])
    elif name == "COLLSCAN":
        scan_types.append("COLLSCAN")
    elif name == "SORT":
        has_sort = True

    for key in ("inputStage", "inputStages", "outerStage", "innerStage"):
        sub = stage.get(key)
        if not sub:
            continue
        items = sub if isinstance(sub, list) else [sub]
        for s in items:
            st, ix, hs = _walk_stages(s)
            scan_types.extend(st)
            index_names.extend(ix)
            has_sort = has_sort or hs

    return scan_types, index_names, has_sort


def _summarise_stats(stats: dict, has_sort: bool, scan_types: list, index_names: list) -> dict:
    docs_examined = stats.get("totalDocsExamined", 0)
    keys_examined = stats.get("totalKeysExamined", 0)
    docs_returned = stats.get("nReturned", 0)
    exec_ms = stats.get("executionTimeMillis", 0)

    if docs_examined == 0 and keys_examined > 0:
        docs_examined = keys_examined

    ratio = round(docs_examined / docs_returned, 1) if docs_returned > 0 else None

    primary_scan = "IXSCAN" if "IXSCAN" in scan_types else ("COLLSCAN" if "COLLSCAN" in scan_types else "UNKNOWN")

    if primary_scan == "COLLSCAN":
        verdict = "COLLSCAN — no usable index found. Add an index on the filter/sort fields."
    elif primary_scan == "IXSCAN" and has_sort:
        verdict = "IXSCAN with in-memory SORT — index used for filtering but sort is not covered. Extend the index to include the sort field (ESR rule)."
    elif primary_scan == "IXSCAN" and ratio is not None and ratio > 10:
        verdict = f"IXSCAN but low efficiency (examined/returned = {ratio}:1) — consider a more selective compound index."
    elif primary_scan == "IXSCAN":
        verdict = "EFFICIENT — IXSCAN with no in-memory sort. Index covers this query well."
    else:
        verdict = "Unable to determine scan type from explain output."

    return {
        "scan_type": primary_scan,
        "index_names": list(dict.fromkeys(index_names)),  # deduplicate, preserve order
        "in_memory_sort": has_sort,
        "docs_examined": docs_examined,
        "keys_examined": keys_examined,
        "docs_returned": docs_returned,
        "examined_to_returned_ratio": ratio,
        "execution_time_ms": exec_ms,
        "verdict": verdict,
    }


@mcp.tool()
def explain_query(
    mongodb_uri: str,
    collection: str,
    database: str = "perflab",
    pipeline: str = "",
    filter: str = "",
    sort: str = "",
    projection: str = "",
) -> str:
    """
    Run explain("executionStats") on a MongoDB query and return a structured
    summary: scan type, index used, docs examined vs returned, in-memory sort
    detection, efficiency verdict, and the raw explain output.

    mongodb_uri: use "mongodb://mongodb:27017" for the lab's built-in MongoDB
    instance (Docker service is "mongodb", not "localhost" or "mongo").

    Provide either:
      pipeline    — JSON array string for an aggregation query
      filter      — JSON object string for a find() filter (optionally with sort/projection)

    Both pipeline and filter can be left empty but at least one must be provided.

    Returns JSON with keys:
      scan_type, index_names, in_memory_sort, docs_examined, keys_examined,
      docs_returned, examined_to_returned_ratio, execution_time_ms, verdict,
      raw_explain (full explain output for deep inspection)
    """
    import json as _json
    from pymongo import MongoClient

    client = MongoClient(mongodb_uri, serverSelectionTimeoutMS=5000)
    try:
        db = client[database]
        coll = db[collection]

        if pipeline and pipeline.strip():
            try:
                parsed_pipeline = _json.loads(pipeline)
            except _json.JSONDecodeError as e:
                return _json.dumps({"error": f"Invalid pipeline JSON: {e}"})

            explain_result = db.command(
                "explain",
                {"aggregate": collection, "pipeline": parsed_pipeline, "cursor": {}},
                verbosity="executionStats",
            )

            stats = explain_result.get("executionStats")
            exec_stages = None
            if stats is None:
                for stage in explain_result.get("stages", []):
                    cursor_stage = stage.get("$cursor", {})
                    if "executionStats" in cursor_stage:
                        stats = cursor_stage["executionStats"]
                        exec_stages = cursor_stage["executionStats"].get("executionStages", {})
                        break
            if stats and exec_stages is None:
                exec_stages = stats.get("executionStages", {})

        elif filter and filter.strip():
            try:
                parsed_filter = _json.loads(filter)
            except _json.JSONDecodeError as e:
                return _json.dumps({"error": f"Invalid filter JSON: {e}"})

            parsed_sort = _json.loads(sort) if sort and sort.strip() else None
            parsed_proj = _json.loads(projection) if projection and projection.strip() else None

            find_cmd = {"find": collection, "filter": parsed_filter}
            if parsed_sort:
                find_cmd["sort"] = parsed_sort
            if parsed_proj:
                find_cmd["projection"] = parsed_proj

            explain_result = db.command("explain", find_cmd, verbosity="executionStats")
            stats = explain_result.get("executionStats")
            exec_stages = stats.get("executionStages", {}) if stats else {}

        else:
            return _json.dumps({"error": "Provide either 'pipeline' (JSON array) or 'filter' (JSON object)."})

        if not stats:
            return _json.dumps({
                "error": "No executionStats found in explain output.",
                "raw_explain": explain_result,
            }, default=str)

        scan_types, index_names, has_sort = _walk_stages(exec_stages)
        summary = _summarise_stats(stats, has_sort, scan_types, index_names)

        # $lookup stages report strategy separately from executionStages.
        lookup_stages = _extract_lookup_stages(explain_result)
        if lookup_stages:
            summary["lookup_stages"] = lookup_stages
            unindexed = [s for s in lookup_stages if s.get("strategy") == "NestedLoopJoin"]
            if unindexed:
                froms = ", ".join(s["from"] for s in unindexed)
                summary["verdict"] = (
                    f"$lookup NestedLoopJoin on [{froms}] — no index on the foreign field. "
                    f"Add an index on {{{unindexed[0]['foreignField']}: 1}} in the '{unindexed[0]['from']}' collection."
                )

        summary["raw_explain"] = explain_result

        return _json.dumps(summary, default=str)

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

    mongodb_uri: always use "mongodb://mongodb:27017". The MCP server runs inside
    the perflab Docker container; the MongoDB service is named "mongodb" in
    docker-compose.yml. Do not use localhost, mongo, or any other hostname.

    Before calling this tool, tell the user the expected runtime: sum the --duration
    value from every `mdbpl run` step and add a few seconds per init/index step.

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

        # Persist to user demos directory so the UI can discover and re-run it
        user_demos_dir = Path("/data/user_demos")
        user_demos_dir.mkdir(parents=True, exist_ok=True)
        (user_demos_dir / f"{demo_classes[0].id}.py").write_text(demo_code, encoding="utf-8")

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
