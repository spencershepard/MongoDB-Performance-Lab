## To Do

- [x] Improve explain coverage for aggregation pipelines (Option C). Aggregate explain working for single-cursor pipelines and `$lookup` pipelines. `executor.py` reads stage-level `indexesUsed`/`collectionScans` sibling keys (not the `$lookup` sub-dict, which has no strategy field in MongoDB 7.0) to classify each operation as index_scan or collection_scan. MCP `explain_query` tool uses the same fix in `_extract_lookup_stages`. Verified end-to-end: NLJ → collection_scans, ILJ → index_scans, with 6800%+ throughput delta on the lookup demo.

- [x] Implement Python-native data generation with schema presets (videogame, ecommerce, iot, events, customers, orders). Supports `string`, `int`, `float`, `date`, `bool`, `choice`, `formatted_sequential`, and `ref` field types. `ref` type samples foreign key values from an existing collection at load time, enabling multi-collection demos. Replaces YCSB.

- [x] Add a `raw` workload to `mdbpl run` that accepts a MongoDB aggregation pipeline directly with `{{fieldName:distribution}}` template variable substitution. Supports `uniform`, `zipfian`, `sequential`, and `literal` distributions.

- [x] Add an `explain_query` MCP tool that runs `explain("executionStats")` on a pipeline or find query. Returns scan type, index used, docs examined vs returned, in-memory sort detection, `$lookup` join strategy, and actionable verdict.

- [x] Demos implemented:
  - `index-performance` — single-field index on range scan (COLLSCAN → IXSCAN, 50–100x)
  - `overindexing` — write throughput degradation from excess indexes
  - `compound-index` — two single-field indexes vs one ESR compound index on multi-predicate query (5–15x)
  - `aggregation-pipeline` — compound index eliminating blocking sort in `$match → $sort → $group` (10–30x)
  - `lookup` — `$lookup` NestedLoopJoin → IndexedLoopJoin via foreign field index (100–1000x)

- [ ] **More demos** — gaps in current coverage:

  **High priority (common real-world pitfalls, not covered anywhere):**

  - [x] **Covering index** — `covering-index` demo implemented (6 steps). `{status: 1}` baseline vs `{status: 1, score: 1}` covering. Inline explain in each benchmark step shows `totalDocsExamined: 1000 → 0`. +25–31% throughput in Docker (small in-memory docs); 2–10x at production scale with large docs or cold cache. Verified end-to-end.

  - **Partial index** — index only documents matching a filter expression (`{partialFilterExpression: {status: "active"}}`). Smaller index, faster writes, ideal for high-selectivity equality predicates that always appear in queries. Good complement to the overindexing demo: shows how to get index benefits without the full write overhead.

  - **Sort/pagination anti-pattern** — `skip(N).limit(M)` is O(N) at large offsets; range-based pagination (`{_id: {$gt: lastId}}`) stays O(log n). Common cause of "queries get slower as the dataset grows" complaints. Would use a `point-read` or `range-scan` workload variant.

  **Medium priority:**

  - **Text / regex search** — why `{field: /pattern/}` forces a COLLSCAN regardless of indexes; when to use a text index. Practical demo: search-as-you-type vs full-text index.

  - **Sparse index** — index only documents where the field exists. Useful for optional fields with high null rates. Shows index size vs query selectivity tradeoff.

  - **TTL index** — automatic document expiry. Useful for session, log, and event data. Demonstrates background deletes and storage reclamation.

- [x] Update `get_demo_examples` in `mcp/server.py` — now supports all 5 demos. Default `demo_name="list"` returns a compact registry table (5 lines). Specific name returns workflow guide + that demo's source only (~600 lines max per call). Replaced broad `scenario` categories with per-demo lookup.

- [ ] Implement a "snapshot mode" demo that shows how to benchmark against production-like imported data.

- [ ] Create a CICD pipeline demo that shows how to integrate the benchmark into a CI/CD workflow for automated performance regression testing.

- [ ] Create a 'CICD integration test' for this project's own CI/CD pipeline — runs a benchmark against a known dataset and checks for expected performance improvements after indexing.

- [ ] Atlas-specific feature coverage — Atlas Search indexes, time series collections, Atlas Vector Search performance, and the Atlas Performance Advisor workflow.

- [ ] Allow MCP generated workflows to be viewed/run from the UI.  This should happen at the tool level - generated code should end up in a non-ephemeral directory that the UI can read from. 

- [ ] MCP generated benchmarks should link to the workflow and results in the UI for easy navigation.

- [ ] Consider reducing default benchmark runtime for quicker iteration; in demos and agent workflows.

- [ ] Add demo for scale comparison (will need to use different collection names for same dataset at different scales)