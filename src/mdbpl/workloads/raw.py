"""Raw pipeline workload — run any MongoDB aggregation pipeline as a benchmark.

Template variables embedded in the pipeline string are replaced per-operation
with values sampled from the live collection:

  {{fieldName}}               uniform random sample from real collection values
  {{fieldName:uniform}}       same, explicit
  {{fieldName:zipfian}}       zipfian hot-key distribution over sampled values
  {{fieldName:sequential}}    round-robin through sampled values (cache-busting)
  {{fieldName:literal:value}} always substitute the literal string value

Example:
  --pipeline '[{"$match": {"region": "{{region:zipfian}}", "status": "{{status:literal:pending}}"}},
               {"$sort": {"score": -1}}, {"$limit": 10}]'
"""

import itertools
import json
import os
import random
import re
from typing import Any, Callable, Dict, List, Optional, Tuple

from pymongo import MongoClient
from pymongo.collection import Collection

from ..distributions import ZipfianGenerator
from ..workload import Benchmark

# Matches a complete string value that is a template placeholder, e.g. "{{field:dist}}"
_TMPL_RE = re.compile(r'^\{\{([^}]+)\}\}$')


def _find_templates(obj: Any, found: Optional[Dict] = None) -> Dict[str, Tuple[str, Optional[str]]]:
    """
    Walk a parsed pipeline tree (list/dict/str) and collect all template specs.
    Returns {field: (distribution_name, literal_value_or_None)}.
    """
    if found is None:
        found = {}
    if isinstance(obj, str):
        m = _TMPL_RE.match(obj)
        if m:
            parts = m.group(1).split(":", 2)
            field = parts[0]
            dist = parts[1] if len(parts) > 1 else "uniform"
            literal = parts[2] if dist == "literal" and len(parts) > 2 else None
            found[field] = (dist, literal)
    elif isinstance(obj, dict):
        for v in obj.values():
            _find_templates(v, found)
    elif isinstance(obj, list):
        for item in obj:
            _find_templates(item, found)
    return found


def _build_pools(collection: Collection, templates: Dict) -> Dict[str, List[Any]]:
    """Sample up to 10,000 real values for each non-literal template field."""
    pools: Dict[str, List[Any]] = {}
    for field, (dist, _literal) in templates.items():
        if dist == "literal":
            continue
        docs = list(
            collection.find({field: {"$exists": True}}, {field: 1, "_id": 0}).limit(10_000)
        )
        values = [d[field] for d in docs if field in d]
        if not values:
            raise ValueError(
                f"No documents found with field '{field}'. "
                f"Check the field name in your pipeline template."
            )
        pools[field] = values
    return pools


def _build_distributors(
    pools: Dict[str, List[Any]], templates: Dict[str, Tuple[str, Optional[str]]]
) -> Dict[str, Callable[[], Any]]:
    """
    Build a zero-argument callable per field that returns one sampled value.
    All callables are thread-safe (random module uses GIL; itertools.count is C-level atomic).
    """
    distributors: Dict[str, Callable[[], Any]] = {}
    for field, (dist, literal) in templates.items():
        if dist == "literal":
            distributors[field] = lambda v=literal: v
        else:
            pool = pools[field]
            n = len(pool)
            if dist == "zipfian":
                gen = ZipfianGenerator(n)
                distributors[field] = lambda p=pool, g=gen: p[g.next()]
            elif dist == "sequential":
                counter = itertools.count()
                distributors[field] = lambda p=pool, c=counter: p[next(c) % len(p)]
            else:  # uniform (default)
                distributors[field] = lambda p=pool: random.choice(p)
    return distributors


def _substitute(template_pipeline: Any, distributors: Dict[str, Callable]) -> Any:
    """
    Recursively walk the parsed pipeline tree and replace template strings with
    sampled values. Returns actual Python types (ObjectId, int, str, etc.) — no
    JSON serialization, so MongoDB receives the correct BSON types.
    """
    if isinstance(template_pipeline, str):
        m = _TMPL_RE.match(template_pipeline)
        if m:
            field = m.group(1).split(":")[0]
            return distributors[field]()
        return template_pipeline
    elif isinstance(template_pipeline, dict):
        return {k: _substitute(v, distributors) for k, v in template_pipeline.items()}
    elif isinstance(template_pipeline, list):
        return [_substitute(item, distributors) for item in template_pipeline]
    return template_pipeline


def create_raw_benchmark(
    database: str = "perflab",
    collection: str = "usertable",
    record_count: int = 10_000,
    pipeline: str = "[]",
    **kwargs,
) -> Benchmark:
    """
    Create a benchmark that runs an arbitrary MongoDB aggregation pipeline.

    Args:
        database:     MongoDB database name
        collection:   MongoDB collection name
        record_count: Number of records (unused directly; pools are sampled from collection)
        pipeline:     JSON string of the aggregation pipeline, optionally containing
                      {{field:distribution}} template variables

    Example:
        mdbpl run --workload raw \\
          --pipeline '[{"$match": {"region": "{{region:zipfian}}"}}, {"$sort": {"score": -1}}, {"$limit": 100}]' \\
          --duration 15s --tag baseline
    """
    mongodb_uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017")

    try:
        template_pipeline = json.loads(pipeline)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid --pipeline JSON: {e}")

    if not isinstance(template_pipeline, list):
        raise ValueError("--pipeline must be a JSON array (list of aggregation stage objects)")

    benchmark = Benchmark(
        name="raw",
        database=database,
        collection=collection,
        description=f"Raw pipeline: {pipeline[:80]}{'...' if len(pipeline) > 80 else ''}",
    )

    # Parse templates and build pools once at factory time — not per operation.
    templates = _find_templates(template_pipeline)

    if templates:
        client = MongoClient(mongodb_uri)
        coll = client[database][collection]
        pools = _build_pools(coll, templates)
        client.close()
        distributors = _build_distributors(pools, templates)
    else:
        distributors = {}

    @benchmark.operation(weight=100, name="raw")
    def raw_op(col: Collection):
        substituted = _substitute(template_pipeline, distributors)
        return list(col.aggregate(substituted))

    return benchmark
