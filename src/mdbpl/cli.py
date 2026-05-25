"""CLI interface for MongoDB Performance Lab."""

import click
import subprocess
import os
from pymongo import MongoClient


@click.group()
@click.version_option()
def cli():
    """MongoDB Performance Lab - Benchmark your MongoDB queries."""
    pass


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------

@cli.command()
@click.option("--dataset", default="ycsb", help="Dataset type to initialize")
@click.option("--scale", default="10k", show_default=True, help="Dataset scale (e.g., 10k, 100k, 1M)")
@click.option("--collection", default="usertable", show_default=True, help="Target collection name")
@click.option("--database", default="perflab", show_default=True, help="Target database name")
@click.option("--distribution", default="zipfian", show_default=True, help="Key distribution: zipfian | uniform | latest")
@click.option("--fields", default=10, show_default=True, help="Number of fields per document")
@click.option("--field-length", default=100, show_default=True, help="Length of each field value")
@click.option("--no-drop", is_flag=True, help="Keep existing collection (default: drop and recreate)")
def init(dataset, scale, collection, database, distribution, fields, field_length, no_drop):
    """Initialize dataset using YCSB, then add a numeric score field."""
    if dataset != "ycsb":
        click.echo(f"Error: Only 'ycsb' dataset is currently supported", err=True)
        raise click.Abort()

    scale_upper = scale.upper()
    if scale_upper.endswith("K"):
        record_count = int(float(scale_upper[:-1]) * 1000)
    elif scale_upper.endswith("M"):
        record_count = int(float(scale_upper[:-1]) * 1_000_000)
    else:
        try:
            record_count = int(scale)
        except ValueError:
            click.echo(f"Error: Invalid scale '{scale}'. Use format like '10k', '1M', or a raw number.", err=True)
            raise click.Abort()

    drop = not no_drop

    click.echo("Initializing YCSB dataset:")
    click.echo(f"  Target:       {database}.{collection}")
    click.echo(f"  Records:      {record_count:,}")
    click.echo(f"  Distribution: {distribution}")
    click.echo(f"  Fields:       {fields}")
    click.echo(f"  Field length: {field_length}")
    click.echo(f"  Drop existing: {'no' if no_drop else 'yes'}")
    click.echo()

    from mdbpl.ycsb import load_ycsb_data

    try:
        mongodb_uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
        load_ycsb_data(
            mongodb_uri=mongodb_uri,
            record_count=record_count,
            distribution=distribution,
            field_count=fields,
            field_length=field_length,
            database=database,
            collection=collection,
            drop_existing=drop,
        )
        click.echo()
        click.echo("✓ Dataset initialized successfully!")
        click.echo(f"  Collection: {database}.{collection}")
        click.echo(f"  Records:    {record_count:,}")
    except Exception as e:
        click.echo(f"✗ Failed to initialize dataset: {e}", err=True)
        raise click.Abort()


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------

def _parse_scale(scale_str: str) -> int:
    """Parse scale string like '10k', '1M', or raw int to record count."""
    s = scale_str.strip().upper()
    if s.endswith("K"):
        return int(float(s[:-1]) * 1000)
    if s.endswith("M"):
        return int(float(s[:-1]) * 1_000_000)
    return int(s)


def _print_results(result, tag: str):
    click.echo("=" * 60)
    click.echo("BENCHMARK RESULTS")
    click.echo("=" * 60)
    click.echo()
    click.echo(f"Workload:   {result.workload_name}")
    click.echo(f"Tag:        {tag}")
    click.echo(f"Duration:   {result.duration_seconds:.2f}s")
    click.echo()
    click.echo(f"Total ops:  {result.total_operations:,}")
    click.echo(f"Successful: {result.successful_operations:,}")
    click.echo(f"Failed:     {result.failed_operations:,}")
    click.echo(f"Throughput: {result.operations_per_second:.2f} ops/sec")
    click.echo()
    click.echo("Latency (ms):")
    click.echo(f"  p50: {result.latency_p50:.2f}")
    click.echo(f"  p95: {result.latency_p95:.2f}")
    click.echo(f"  p99: {result.latency_p99:.2f}")
    click.echo()
    if result.operations_with_explain > 0:
        click.echo("Query execution (sampled):")
        click.echo(f"  Docs examined:    {result.total_docs_examined:,}")
        click.echo(f"  Docs returned:    {result.total_docs_returned:,}")
        click.echo(f"  Index scans:      {result.index_scans:,}")
        click.echo(f"  Collection scans: {result.collection_scans:,}")
        click.echo()
    click.echo("Per-operation breakdown:")
    for op_name, latencies in result.operation_metrics.items():
        if not latencies:
            continue
        sl = sorted(latencies)
        n = len(sl)
        click.echo(f"  {op_name}: {n:,} ops  "
                   f"avg={sum(latencies)/n:.2f}ms  "
                   f"p50={sl[int(n*0.50)]:.2f}ms  "
                   f"p95={sl[int(n*0.95)]:.2f}ms  "
                   f"p99={sl[int(n*0.99)]:.2f}ms")
    click.echo()


@cli.command()
@click.option("--workload", required=True,
              help="Workload name or path to a .py file. "
                   "Built-in: insert, update, point-read, range-scan, mixed, top-n, group-by")
# Targeting
@click.option("--collection", default="usertable", show_default=True, help="Collection to benchmark")
@click.option("--database", default="perflab", show_default=True, help="Database to benchmark")
# Execution
@click.option("--threads", default=1, show_default=True, help="Concurrent worker threads")
@click.option("--duration", default="30s", show_default=True, help="Benchmark duration (e.g., 15s, 2m)")
@click.option("--tag", default="run", show_default=True, help="Tag for comparison with mdbpl compare")
@click.option("--distribution", default="uniform", show_default=True,
              help="Key access pattern: uniform | zipfian")
# insert
@click.option("--fields", default=None,
              help="Comma-separated fields to write (insert). Default: field0,field1,field2")
@click.option("--batch-size", default=1, show_default=True,
              help="Documents per insert operation (insert workload)")
# update / point-read / mixed
@click.option("--filter-field", default=None,
              help="Field to filter on (update, point-read, mixed). Default: _id")
@click.option("--update-fields", default=None,
              help="Comma-separated fields to update (update, mixed). Default: field0")
# mixed
@click.option("--read-pct", default=70, show_default=True,
              help="Percentage of read operations (mixed workload)")
# range-scan
@click.option("--field", default=None,
              help="Numeric field for range queries (range-scan). Default: score")
@click.option("--range-size", default=2000, show_default=True,
              help="Range window width (range-scan)")
@click.option("--sort-field", default=None,
              help="Field to sort on (range-scan, top-n). Default: score")
# top-n
@click.option("--sort-direction", default="desc", show_default=True,
              help="Sort direction (top-n): desc | asc")
@click.option("--limit", default=100, show_default=True,
              help="Result limit (top-n)")
@click.option("--match-field", default=None,
              help="Optional pre-filter field (top-n, group-by)")
@click.option("--match-value", default=None,
              help="Value for --match-field filter (top-n, group-by)")
# group-by
@click.option("--group-field", default=None,
              help="Field to group on (group-by). Default: field0")
@click.option("--accumulator", default="count", show_default=True,
              help="Accumulator (group-by): count | sum | avg | min | max")
@click.option("--value-field", default=None,
              help="Field to accumulate for sum/avg/min/max (group-by)")
def run(workload, collection, database, threads, duration, tag, distribution,
        fields, batch_size, filter_field, update_fields, read_pct,
        field, range_size, sort_field, sort_direction, limit,
        match_field, match_value, group_field, accumulator, value_field):
    """Run a benchmark workload."""
    from mdbpl.executor import WorkloadExecutor, parse_duration
    from mdbpl.workloads import REGISTRY
    import importlib.util
    import sys
    from pathlib import Path

    mongodb_uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017")

    # ---- resolve benchmark ------------------------------------------------
    benchmark = None

    if workload.endswith(".py"):
        workload_path = Path(workload)
        if not workload_path.exists():
            click.echo(f"✗ File not found: {workload}", err=True)
            raise click.Abort()
        spec = importlib.util.spec_from_file_location("custom_workload", workload_path)
        module = importlib.util.module_from_spec(spec)
        sys.modules["custom_workload"] = module
        spec.loader.exec_module(module)
        factory = next(
            (getattr(module, n) for n in dir(module)
             if n.startswith("create_") and n.endswith("_benchmark")),
            None
        )
        if factory:
            benchmark = factory()
        elif hasattr(module, "benchmark"):
            benchmark = module.benchmark
        else:
            click.echo("✗ Python file must define a create_*_benchmark() function or 'benchmark' variable.", err=True)
            raise click.Abort()

    elif workload in REGISTRY:
        # ---- detect record count from collection -------------------------
        client = MongoClient(mongodb_uri)
        coll = client[database][collection]
        record_count = coll.count_documents({})
        client.close()

        if record_count == 0:
            click.echo(f"✗ Collection {database}.{collection} is empty. Run 'mdbpl init' first.", err=True)
            raise click.Abort()

        # ---- build workload-specific kwargs ------------------------------
        common = dict(database=database, collection=collection, record_count=record_count)

        if workload == "insert":
            field_list = [f.strip() for f in fields.split(",")] if fields else None
            benchmark = REGISTRY["insert"](**common, fields=field_list, batch_size=batch_size)

        elif workload == "update":
            uf = [f.strip() for f in update_fields.split(",")] if update_fields else None
            benchmark = REGISTRY["update"](
                **common,
                filter_field=filter_field or "_id",
                update_fields=uf,
                distribution=distribution,
            )

        elif workload == "point-read":
            benchmark = REGISTRY["point-read"](
                **common,
                filter_field=filter_field or "_id",
                distribution=distribution,
            )

        elif workload == "range-scan":
            benchmark = REGISTRY["range-scan"](
                **common,
                field=field or "score",
                range_size=range_size,
                sort_field=sort_field or "score",
            )

        elif workload == "mixed":
            uf = [f.strip() for f in update_fields.split(",")] if update_fields else None
            benchmark = REGISTRY["mixed"](
                **common,
                read_pct=read_pct,
                filter_field=filter_field or "_id",
                update_fields=uf,
                distribution=distribution,
            )

        elif workload == "top-n":
            benchmark = REGISTRY["top-n"](
                **common,
                sort_field=sort_field or "score",
                sort_direction=sort_direction,
                limit=limit,
                match_field=match_field,
                match_value=match_value,
            )

        elif workload == "group-by":
            benchmark = REGISTRY["group-by"](
                **common,
                match_field=match_field or "score",
                group_field=group_field or "field0",
                accumulator=accumulator,
                value_field=value_field,
            )

        else:
            benchmark = REGISTRY[workload](**common)

    else:
        click.echo(f"✗ Unknown workload '{workload}'.", err=True)
        click.echo(f"  Built-in: {', '.join(REGISTRY.keys())}", err=True)
        click.echo("  Or provide a .py file path.", err=True)
        raise click.Abort()

    # ---- display workload info -------------------------------------------
    click.echo(f"Workload:   {benchmark.name}")
    click.echo(f"Target:     {benchmark.database}.{benchmark.collection}")
    click.echo(f"Threads:    {threads}")
    click.echo(f"Duration:   {duration}")
    click.echo(f"Tag:        {tag}")
    click.echo()

    # ---- run benchmark ---------------------------------------------------
    duration_seconds = parse_duration(duration)

    # Re-open client for record count (already closed above for built-ins)
    client = MongoClient(mongodb_uri)
    coll_obj = client[benchmark.database][benchmark.collection]
    record_count = coll_obj.count_documents({})
    client.close()

    executor = WorkloadExecutor(benchmark, mongodb_uri, record_count)

    click.echo(f"Running benchmark ({record_count:,} docs in collection)...")
    click.echo()

    try:
        if threads > 1:
            result = executor.run_threaded(duration_seconds, threads=threads)
        else:
            result = executor.run(duration_seconds, tag=tag)
    except Exception as e:
        click.echo(f"✗ Benchmark failed: {e}", err=True)
        import traceback
        traceback.print_exc()
        raise click.Abort()

    # ---- display and save results ----------------------------------------
    _print_results(result, tag)
    click.echo("✓ Benchmark complete!")
    click.echo()

    try:
        from mdbpl.storage import BenchmarkStorage
        storage = BenchmarkStorage()
        run_id = storage.save_result(result, tag)
        click.echo(f"Results saved — tag: '{tag}'  run_id: {run_id}")
    except Exception as e:
        click.echo(f"Warning: Failed to save results: {e}", err=True)


# ---------------------------------------------------------------------------
# report / compare / demo / serve / reset-db / test  (unchanged)
# ---------------------------------------------------------------------------

@cli.command()
@click.option("--last", is_flag=True, help="Show last benchmark result")
@click.option("--tag", help="Show result by tag")
@click.option("--list", "list_runs", is_flag=True, help="List all benchmark runs")
def report(last, tag, list_runs):
    """View benchmark results."""
    from mdbpl.storage import BenchmarkStorage
    storage = BenchmarkStorage()

    if list_runs:
        runs = storage.list_runs()
        if not runs:
            click.echo("No benchmark runs found")
            return
        click.echo("Recent Benchmark Runs:")
        click.echo()
        click.echo(f"{'ID':<6} {'Workload':<20} {'Tag':<15} {'Timestamp':<20} {'Throughput':<15}")
        click.echo("=" * 80)
        for run in runs:
            timestamp = run["timestamp"][:19].replace("T", " ")
            click.echo(
                f"{run['id']:<6} {run['workload_name']:<20} {run['tag']:<15} "
                f"{timestamp:<20} {run['operations_per_second']:<15.2f}"
            )
        click.echo()
        click.echo(f"Total runs: {len(runs)}")
        return

    if tag:
        run_data = storage.get_run_by_tag(tag)
        if not run_data:
            click.echo(f"✗ No run found with tag: {tag}", err=True)
            raise click.Abort()
    elif last:
        run_data = storage.get_last_run()
        if not run_data:
            click.echo("✗ No benchmark runs found", err=True)
            raise click.Abort()
    else:
        click.echo("Error: Specify --last, --tag, or --list")
        raise click.Abort()

    click.echo("=" * 60)
    click.echo("BENCHMARK RESULTS")
    click.echo("=" * 60)
    click.echo()
    click.echo(f"Run ID:     {run_data['id']}")
    click.echo(f"Workload:   {run_data['workload_name']}")
    click.echo(f"Tag:        {run_data['tag']}")
    click.echo(f"Timestamp:  {run_data['timestamp']}")
    click.echo(f"Duration:   {run_data['duration_seconds']:.2f}s")
    click.echo()
    click.echo(f"Total ops:  {run_data['total_operations']:,}")
    click.echo(f"Successful: {run_data['successful_operations']:,}")
    click.echo(f"Failed:     {run_data['failed_operations']:,}")
    click.echo(f"Throughput: {run_data['operations_per_second']:.2f} ops/sec")
    click.echo()
    click.echo("Latency (ms):")
    click.echo(f"  p50: {run_data['latency_p50']:.2f}")
    click.echo(f"  p95: {run_data['latency_p95']:.2f}")
    click.echo(f"  p99: {run_data['latency_p99']:.2f}")
    click.echo()
    if run_data["operations"]:
        click.echo("Per-Operation Metrics:")
        for op in run_data["operations"]:
            click.echo(f"  {op['operation_name']}:")
            click.echo(f"    Count: {op['operation_count']:,}")
            click.echo(f"    Avg: {op['avg_latency']:.2f}ms  "
                       f"p50: {op['p50_latency']:.2f}ms  "
                       f"p95: {op['p95_latency']:.2f}ms  "
                       f"p99: {op['p99_latency']:.2f}ms")


@cli.command()
@click.option("--tags", required=True, help="Comma-separated tags to compare (exactly 2)")
def compare(tags):
    """Compare two benchmark results side-by-side."""
    from mdbpl.storage import BenchmarkStorage

    tag_list = [t.strip() for t in tags.split(",")]
    if len(tag_list) != 2:
        click.echo("Error: Exactly 2 tags required for comparison", err=True)
        raise click.Abort()

    tag1, tag2 = tag_list
    storage = BenchmarkStorage()

    try:
        comparison = storage.compare_runs(tag1, tag2)
    except ValueError as e:
        click.echo(f"✗ {e}", err=True)
        raise click.Abort()

    run1, run2, deltas = comparison["run1"], comparison["run2"], comparison["deltas"]

    def fmt_delta(v):
        return f"+{v:.2f}%" if v > 0 else f"{v:.2f}%"

    def indicator(v, lower_is_better=False):
        improved = v < -5 if lower_is_better else v > 5
        regressed = v > 5 if lower_is_better else v < -5
        return "✓ improved" if improved else ("✗ regressed" if regressed else "≈ similar")

    click.echo("=" * 80)
    click.echo("BENCHMARK COMPARISON")
    click.echo("=" * 80)
    click.echo()
    click.echo(f"Run 1: {run1['workload_name']}  tag={run1['tag']}  {run1['timestamp'][:19]}")
    click.echo(f"Run 2: {run2['workload_name']}  tag={run2['tag']}  {run2['timestamp'][:19]}")
    click.echo()
    click.echo(f"{'Metric':<25} {'Run 1':>12} {'Run 2':>12} {'Change':>10}  Status")
    click.echo("=" * 80)
    click.echo(
        f"{'Throughput (ops/sec)':<25} "
        f"{run1['operations_per_second']:>12.2f} "
        f"{run2['operations_per_second']:>12.2f} "
        f"{fmt_delta(deltas['throughput']):>10}  "
        f"{indicator(deltas['throughput'])}"
    )
    for metric, label, lib in [
        ("latency_p50", "Latency p50 (ms)", True),
        ("latency_p95", "Latency p95 (ms)", True),
        ("latency_p99", "Latency p99 (ms)", True),
    ]:
        click.echo(
            f"{label:<25} "
            f"{run1[metric]:>12.2f} "
            f"{run2[metric]:>12.2f} "
            f"{fmt_delta(deltas[metric]):>10}  "
            f"{indicator(deltas[metric], lower_is_better=True)}"
        )
    click.echo()
    if comparison["operations"]:
        click.echo("Per-Operation Comparison:")
        for op_name, opc in comparison["operations"].items():
            if not opc["deltas"]:
                continue
            o1, o2 = opc["run1"], opc["run2"]
            d = opc["deltas"]
            click.echo(f"  {op_name}:")
            click.echo(f"    avg: {o1['avg_latency']:.2f}ms → {o2['avg_latency']:.2f}ms ({fmt_delta(d['avg_latency'])})")
            click.echo(f"    p95: {o1['p95_latency']:.2f}ms → {o2['p95_latency']:.2f}ms ({fmt_delta(d['p95_latency'])})")


@cli.group()
def demo():
    """Run interactive demos."""
    pass


@demo.command("list")
def demo_list():
    """List available demos."""
    from mdbpl.demos import list_demos
    click.echo("Available demos:")
    click.echo()
    for d in list_demos():
        click.echo(f"  {d['name']}")
        click.echo(f"    {d['title']}")
        click.echo(f"    {d['description']}")
        click.echo()


@demo.command("run")
@click.argument("demo_name")
@click.option("--output", type=click.Choice(["text", "json"]), default="text")
def demo_run(demo_name, output):
    """Run a specific demo."""
    from mdbpl.demos import get_demo
    import json

    try:
        demo_instance = get_demo(demo_name)
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        raise click.Abort()

    click.echo(f"Running demo: {demo_instance.title}")
    click.echo()
    result = demo_instance.run()

    if output == "json":
        click.echo(json.dumps(result.to_dict(), indent=2))
    else:
        click.echo(f"{'='*60}")
        click.echo(f"Demo: {result.title}  success={result.success}")
        if result.error:
            click.echo(f"Error: {result.error}", err=True)
        click.echo(f"{'='*60}")


@cli.command()
@click.option("--host", default="0.0.0.0", help="Host to bind to")
@click.option("--port", default=8888, help="Port to bind to")
def serve(host, port):
    """Start the API server."""
    click.echo(f"Starting API server on {host}:{port}...")
    import uvicorn
    uvicorn.run("mdbpl.api:app", host=host, port=port, log_level="info")


@cli.command()
@click.confirmation_option(prompt="This will delete all benchmark results. Continue?")
def reset_db():
    """Delete the benchmark database and start fresh."""
    from mdbpl.storage import BenchmarkStorage
    try:
        storage = BenchmarkStorage()
        if storage.reset_db():
            click.echo("✓ Database reset successfully")
        else:
            click.echo("Database file not found (already clean)")
    except Exception as e:
        click.echo(f"✗ Failed to reset database: {e}", err=True)
        raise click.Abort()


@cli.command()
def test():
    """Test YCSB installation and MongoDB connection."""
    click.echo("Testing YCSB installation...")
    ycsb_home = os.getenv("YCSB_HOME", "/opt/ycsb")
    if not os.path.exists(ycsb_home):
        click.echo(f"✗ YCSB not found at {ycsb_home}")
    else:
        click.echo(f"✓ YCSB found at {ycsb_home}")
        try:
            result = subprocess.run(["java", "-version"], capture_output=True, text=True, timeout=5)
            version_line = result.stderr.split("\n")[0] if result.stderr else "Unknown"
            click.echo(f"✓ Java: {version_line}")
        except Exception as e:
            click.echo(f"✗ Java not found: {e}")

    click.echo()
    click.echo("Testing MongoDB connection...")
    mongodb_uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
    click.echo(f"  URI: {mongodb_uri}")
    try:
        client = MongoClient(mongodb_uri, serverSelectionTimeoutMS=3000)
        client.admin.command("ping")
        click.echo("✓ MongoDB connection OK")
        client.close()
    except Exception as e:
        click.echo(f"✗ MongoDB connection failed: {e}")


if __name__ == "__main__":
    cli()
