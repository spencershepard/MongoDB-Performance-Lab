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


@cli.command()
@click.option('--dataset', default='ycsb', help='Dataset type to initialize')
@click.option('--scale', default='100k', help='Dataset scale (e.g., 100k, 1M, 10M)')
@click.option('--distribution', default='zipfian', help='Key distribution (zipfian, uniform, latest)')
@click.option('--fields', default=10, help='Number of fields per document')
@click.option('--field-length', default=100, help='Length of each field value')
@click.option('--drop', is_flag=True, help='Drop existing collection before loading')
def init(dataset, scale, distribution, fields, field_length, drop):
    """Initialize dataset using YCSB."""
    if dataset != 'ycsb':
        click.echo(f"Error: Only 'ycsb' dataset is currently supported", err=True)
        raise click.Abort()
    
    # Parse scale to record count
    scale_upper = scale.upper()
    if scale_upper.endswith('K'):
        record_count = int(float(scale_upper[:-1]) * 1000)
    elif scale_upper.endswith('M'):
        record_count = int(float(scale_upper[:-1]) * 1000000)
    else:
        try:
            record_count = int(scale)
        except ValueError:
            click.echo(f"Error: Invalid scale '{scale}'. Use format like '100k', '1M', or raw number", err=True)
            raise click.Abort()
    
    click.echo(f"Initializing YCSB dataset:")
    click.echo(f"  Records: {record_count:,}")
    click.echo(f"  Distribution: {distribution}")
    click.echo(f"  Fields: {fields}")
    click.echo(f"  Field length: {field_length}")
    if drop:
        click.echo(f"  Drop existing: yes")
    click.echo()
    
    from mdbpl.ycsb import load_ycsb_data
    
    try:
        mongodb_uri = os.getenv('MONGODB_URI', 'mongodb://localhost:27017')
        load_ycsb_data(
            mongodb_uri=mongodb_uri,
            record_count=record_count,
            distribution=distribution,
            field_count=fields,
            field_length=field_length,
            drop_existing=drop
        )
        click.echo()
        click.echo("✓ Dataset initialized successfully!")
        click.echo(f"  Collection: perflab.usertable")
        click.echo(f"  Records: {record_count:,}")
    except Exception as e:
        click.echo(f"✗ Failed to initialize dataset: {e}", err=True)
        raise click.Abort()


@cli.command()
@click.option('--workload', required=True, help='Workload name or Python file path')
@click.option('--duration', default='30s', help='Benchmark duration')
@click.option('--tag', default='baseline', help='Tag for this benchmark run')
def run(workload, duration, tag):
    """Run a benchmark workload."""
    from mdbpl.executor import WorkloadExecutor, parse_duration
    import importlib.util
    import sys
    from pathlib import Path
    
    click.echo(f"Loading workload: {workload}")
    click.echo()
    
    try:
        benchmark = None
        
        # Check if it's a Python file
        if workload.endswith('.py'):
            # Load Python workload from file
            click.echo("Loading Python workload from file...")
            
            workload_path = Path(workload)
            if not workload_path.exists():
                click.echo(f"✗ Error: File not found: {workload}", err=True)
                raise click.Abort()
            
            # Load the module dynamically
            spec = importlib.util.spec_from_file_location("custom_workload", workload_path)
            module = importlib.util.module_from_spec(spec)
            sys.modules["custom_workload"] = module
            spec.loader.exec_module(module)
            
            # Look for create_*_benchmark function or a 'benchmark' variable
            benchmark_func = None
            for name in dir(module):
                if name.startswith('create_') and name.endswith('_benchmark'):
                    benchmark_func = getattr(module, name)
                    break
            
            if benchmark_func:
                benchmark = benchmark_func()
            elif hasattr(module, 'benchmark'):
                benchmark = module.benchmark
            else:
                click.echo(f"✗ Error: Python file must define a create_*_benchmark() function or 'benchmark' variable", err=True)
                raise click.Abort()
                
        # Check if it's a built-in workload name
        elif workload in ['read-heavy', 'balanced', 'write-heavy', 'range-scan']:
            click.echo(f"Loading built-in workload: {workload}")
            
            # Import built-in workload
            if workload == 'read-heavy':
                from mdbpl import create_read_heavy_benchmark
                benchmark = create_read_heavy_benchmark()
            elif workload == 'balanced':
                from mdbpl import create_balanced_benchmark
                benchmark = create_balanced_benchmark()
            elif workload == 'write-heavy':
                from mdbpl import create_write_heavy_benchmark
                benchmark = create_write_heavy_benchmark()
            elif workload == 'range-scan':
                from mdbpl import create_range_scan_benchmark
                benchmark = create_range_scan_benchmark()
        else:
            click.echo(f"✗ Error: Unknown workload '{workload}'", err=True)
            click.echo("Available workloads: read-heavy, balanced, write-heavy, range-scan", err=True)
            click.echo("Or provide a .py file path with a custom workload", err=True)
            raise click.Abort()
        
        # Display workload info
        click.echo(f"Workload: {benchmark.name}")
        click.echo(f"Description: {benchmark.description}")
        click.echo(f"Database: {benchmark.database}")
        click.echo(f"Collection: {benchmark.collection}")
        click.echo(f"Operations: {len(benchmark.operations)}")
        for op in benchmark.operations:
            pct = (op.weight / benchmark.get_total_weight()) * 100
            click.echo(f"  - {op.name}: {op.weight} ({pct:.1f}%)")
        
        click.echo()
        
        # Get MongoDB connection
        mongodb_uri = os.getenv('MONGODB_URI', 'mongodb://localhost:27017')
        
        # Count records in collection to determine distribution range
        click.echo("Connecting to MongoDB...")
        client = MongoClient(mongodb_uri)
        db = client[benchmark.database]
        collection = db[benchmark.collection]
        
        record_count = collection.count_documents({})
        
        if record_count == 0:
            click.echo("✗ Error: Collection is empty. Run 'mdbpl init' first.", err=True)
            client.close()
            raise click.Abort()
        
        click.echo(f"Found {record_count:,} records in collection")
        click.echo()
        
        # Parse duration
        duration_seconds = parse_duration(duration)
        
        # Create executor
        click.echo(f"Starting benchmark (duration: {duration}, tag: {tag})...")
        click.echo()
        
        executor = WorkloadExecutor(benchmark, mongodb_uri, record_count)
        
        # Run benchmark
        result = executor.run(duration_seconds, tag)
        
        # Display results
        click.echo("=" * 60)
        click.echo("BENCHMARK RESULTS")
        click.echo("=" * 60)
        click.echo()
        click.echo(f"Workload: {result.workload_name}")
        click.echo(f"Tag: {tag}")
        click.echo(f"Duration: {result.duration_seconds:.2f}s")
        click.echo()
        click.echo(f"Total Operations: {result.total_operations:,}")
        click.echo(f"Successful: {result.successful_operations:,}")
        click.echo(f"Failed: {result.failed_operations:,}")
        click.echo(f"Throughput: {result.operations_per_second:.2f} ops/sec")
        click.echo()
        click.echo("Latency (ms):")
        click.echo(f"  p50: {result.latency_p50:.2f}")
        click.echo(f"  p95: {result.latency_p95:.2f}")
        click.echo(f"  p99: {result.latency_p99:.2f}")
        click.echo()
        
        # Per-operation breakdown
        click.echo("Per-Operation Metrics:")
        for op_name, latencies in result.operation_metrics.items():
            if latencies:
                sorted_latencies = sorted(latencies)
                n = len(sorted_latencies)
                p50 = sorted_latencies[int(n * 0.50)]
                p95 = sorted_latencies[int(n * 0.95)]
                p99 = sorted_latencies[int(n * 0.99)]
                avg = sum(latencies) / len(latencies)
                
                click.echo(f"  {op_name}:")
                click.echo(f"    Count: {len(latencies):,}")
                click.echo(f"    Avg: {avg:.2f}ms")
                click.echo(f"    p50: {p50:.2f}ms  p95: {p95:.2f}ms  p99: {p99:.2f}ms")
        
        click.echo()
        click.echo("✓ Benchmark complete!")
        click.echo()
        
        # Save results to storage
        try:
            from mdbpl.storage import BenchmarkStorage
            storage = BenchmarkStorage()
            run_id = storage.save_result(result, tag)
            click.echo(f"Results saved with tag '{tag}' (run_id: {run_id})")
        except Exception as e:
            click.echo(f"Warning: Failed to save results: {e}", err=True)
        
        client.close()
        
    except FileNotFoundError as e:
        click.echo(f"✗ Error: {e}", err=True)
        raise click.Abort()
    except Exception as e:
        click.echo(f"✗ Benchmark failed: {e}", err=True)
        import traceback
        traceback.print_exc()
        raise click.Abort()


@cli.command()
@click.option('--last', is_flag=True, help='Show last benchmark result')
@click.option('--tag', help='Show result by tag')
@click.option('--list', 'list_runs', is_flag=True, help='List all benchmark runs')
def report(last, tag, list_runs):
    """View benchmark results."""
    from mdbpl.storage import BenchmarkStorage
    
    storage = BenchmarkStorage()
    
    if list_runs:
        # List all runs
        runs = storage.list_runs()
        
        if not runs:
            click.echo("No benchmark runs found")
            return
        
        click.echo("Recent Benchmark Runs:")
        click.echo()
        click.echo(f"{'ID':<6} {'Workload':<20} {'Tag':<15} {'Timestamp':<20} {'Throughput':<15}")
        click.echo("=" * 80)
        
        for run in runs:
            timestamp = run['timestamp'][:19].replace('T', ' ')
            click.echo(
                f"{run['id']:<6} "
                f"{run['workload_name']:<20} "
                f"{run['tag']:<15} "
                f"{timestamp:<20} "
                f"{run['operations_per_second']:<15.2f}"
            )
        
        click.echo()
        click.echo(f"Total runs: {len(runs)}")
        return
    
    # Get specific run
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
    
    # Display run details
    click.echo("=" * 60)
    click.echo("BENCHMARK RESULTS")
    click.echo("=" * 60)
    click.echo()
    click.echo(f"Run ID: {run_data['id']}")
    click.echo(f"Workload: {run_data['workload_name']}")
    click.echo(f"Tag: {run_data['tag']}")
    click.echo(f"Timestamp: {run_data['timestamp']}")
    click.echo(f"Duration: {run_data['duration_seconds']:.2f}s")
    click.echo()
    click.echo(f"Total Operations: {run_data['total_operations']:,}")
    click.echo(f"Successful: {run_data['successful_operations']:,}")
    click.echo(f"Failed: {run_data['failed_operations']:,}")
    click.echo(f"Throughput: {run_data['operations_per_second']:.2f} ops/sec")
    click.echo()
    click.echo("Latency (ms):")
    click.echo(f"  p50: {run_data['latency_p50']:.2f}")
    click.echo(f"  p95: {run_data['latency_p95']:.2f}")
    click.echo(f"  p99: {run_data['latency_p99']:.2f}")
    click.echo()
    
    if run_data['operations']:
        click.echo("Per-Operation Metrics:")
        for op in run_data['operations']:
            click.echo(f"  {op['operation_name']}:")
            click.echo(f"    Count: {op['operation_count']:,}")
            click.echo(f"    Avg: {op['avg_latency']:.2f}ms")
            click.echo(f"    p50: {op['p50_latency']:.2f}ms  p95: {op['p95_latency']:.2f}ms  p99: {op['p99_latency']:.2f}ms")


@cli.command()
@click.option('--tags', required=True, help='Comma-separated tags to compare')
def compare(tags):
    """Compare benchmark results."""
    from mdbpl.storage import BenchmarkStorage
    
    tag_list = [t.strip() for t in tags.split(',')]
    
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
    
    run1 = comparison['run1']
    run2 = comparison['run2']
    deltas = comparison['deltas']
    
    # Display comparison
    click.echo("=" * 80)
    click.echo("BENCHMARK COMPARISON")
    click.echo("=" * 80)
    click.echo()
    click.echo(f"Run 1: {run1['workload_name']} (tag: {run1['tag']})")
    click.echo(f"  Timestamp: {run1['timestamp']}")
    click.echo(f"  Duration: {run1['duration_seconds']:.2f}s")
    click.echo()
    click.echo(f"Run 2: {run2['workload_name']} (tag: {run2['tag']})")
    click.echo(f"  Timestamp: {run2['timestamp']}")
    click.echo(f"  Duration: {run2['duration_seconds']:.2f}s")
    click.echo()
    click.echo("=" * 80)
    click.echo()
    
    def format_delta(value):
        """Format delta with color indicators."""
        if value > 0:
            return f"+{value:.2f}%"
        else:
            return f"{value:.2f}%"
    
    def delta_indicator(value, lower_is_better=False):
        """Get indicator for improvement/regression."""
        if lower_is_better:
            if value < -5:
                return "✓ (improved)"
            elif value > 5:
                return "✗ (regressed)"
            else:
                return "≈ (similar)"
        else:
            if value > 5:
                return "✓ (improved)"
            elif value < -5:
                return "✗ (regressed)"
            else:
                return "≈ (similar)"
    
    # Overall metrics
    click.echo(f"{'Metric':<25} {'Run 1':<15} {'Run 2':<15} {'Change':<15} {'Status'}")
    click.echo("=" * 80)
    
    click.echo(
        f"{'Throughput (ops/sec)':<25} "
        f"{run1['operations_per_second']:<15.2f} "
        f"{run2['operations_per_second']:<15.2f} "
        f"{format_delta(deltas['throughput']):<15} "
        f"{delta_indicator(deltas['throughput'], lower_is_better=False)}"
    )
    
    click.echo(
        f"{'Latency p50 (ms)':<25} "
        f"{run1['latency_p50']:<15.2f} "
        f"{run2['latency_p50']:<15.2f} "
        f"{format_delta(deltas['latency_p50']):<15} "
        f"{delta_indicator(deltas['latency_p50'], lower_is_better=True)}"
    )
    
    click.echo(
        f"{'Latency p95 (ms)':<25} "
        f"{run1['latency_p95']:<15.2f} "
        f"{run2['latency_p95']:<15.2f} "
        f"{format_delta(deltas['latency_p95']):<15} "
        f"{delta_indicator(deltas['latency_p95'], lower_is_better=True)}"
    )
    
    click.echo(
        f"{'Latency p99 (ms)':<25} "
        f"{run1['latency_p99']:<15.2f} "
        f"{run2['latency_p99']:<15.2f} "
        f"{format_delta(deltas['latency_p99']):<15} "
        f"{delta_indicator(deltas['latency_p99'], lower_is_better=True)}"
    )
    
    click.echo()
    click.echo("Per-Operation Comparison:")
    click.echo()
    
    for op_name, op_comparison in comparison['operations'].items():
        if not op_comparison['deltas']:
            continue
        
        op1 = op_comparison['run1']
        op2 = op_comparison['run2']
        op_deltas = op_comparison['deltas']
        
        click.echo(f"  {op_name}:")
        click.echo(
            f"    Avg latency: {op1['avg_latency']:.2f}ms → {op2['avg_latency']:.2f}ms "
            f"({format_delta(op_deltas['avg_latency'])})"
        )
        click.echo(
            f"    p95 latency: {op1['p95_latency']:.2f}ms → {op2['p95_latency']:.2f}ms "
            f"({format_delta(op_deltas['p95_latency'])})"
        )


@cli.group()
def index():
    """Manage MongoDB indexes."""
    pass


@index.command('create')
@click.argument('fields')
@click.option('--database', default='perflab', help='Database name')
@click.option('--collection', default='usertable', help='Collection name')
@click.option('--desc', is_flag=True, help='Create descending index (default: ascending)')
@click.option('--name', help='Custom index name')
def index_create(fields, database, collection, desc, name):
    """
    Create an index on one or more fields.
    
    FIELDS: Comma-separated list of fields (e.g., "field0" or "field0,field1")
    """
    mongodb_uri = os.getenv('MONGODB_URI', 'mongodb://localhost:27017')
    
    try:
        client = MongoClient(mongodb_uri)
        db = client[database]
        coll = db[collection]
        
        # Parse fields
        field_list = [f.strip() for f in fields.split(',')]
        
        # Build index specification
        direction = -1 if desc else 1
        index_spec = [(field, direction) for field in field_list]
        
        click.echo(f"Creating index on {database}.{collection}:")
        for field, dir_val in index_spec:
            dir_str = "descending" if dir_val == -1 else "ascending"
            click.echo(f"  {field} ({dir_str})")
        
        # Create index
        kwargs = {}
        if name:
            kwargs['name'] = name
        
        index_name = coll.create_index(index_spec, **kwargs)
        
        click.echo()
        click.echo(f"✓ Index created: {index_name}")
        
        client.close()
        
    except Exception as e:
        click.echo(f"✗ Failed to create index: {e}", err=True)
        raise click.Abort()


@index.command('drop')
@click.argument('index_name')
@click.option('--database', default='perflab', help='Database name')
@click.option('--collection', default='usertable', help='Collection name')
def index_drop(index_name, database, collection):
    """Drop an index by name."""
    mongodb_uri = os.getenv('MONGODB_URI', 'mongodb://localhost:27017')
    
    try:
        client = MongoClient(mongodb_uri)
        db = client[database]
        coll = db[collection]
        
        click.echo(f"Dropping index '{index_name}' from {database}.{collection}...")
        
        coll.drop_index(index_name)
        
        click.echo(f"✓ Index dropped: {index_name}")
        
        client.close()
        
    except Exception as e:
        click.echo(f"✗ Failed to drop index: {e}", err=True)
        raise click.Abort()


@index.command('list')
@click.option('--database', default='perflab', help='Database name')
@click.option('--collection', default='usertable', help='Collection name')
def index_list(database, collection):
    """List all indexes on a collection."""
    mongodb_uri = os.getenv('MONGODB_URI', 'mongodb://localhost:27017')
    
    try:
        client = MongoClient(mongodb_uri)
        db = client[database]
        coll = db[collection]
        
        indexes = list(coll.list_indexes())
        
        if not indexes:
            click.echo(f"No indexes found on {database}.{collection}")
            client.close()
            return
        
        click.echo(f"Indexes on {database}.{collection}:")
        click.echo()
        
        for idx in indexes:
            name = idx['name']
            keys = idx['key']
            
            # Format keys
            key_parts = []
            for field, direction in keys.items():
                dir_str = "↓" if direction == -1 else "↑"
                key_parts.append(f"{field}{dir_str}")
            
            keys_str = ", ".join(key_parts)
            
            # Show additional properties
            props = []
            if idx.get('unique'):
                props.append("unique")
            if idx.get('sparse'):
                props.append("sparse")
            if idx.get('background'):
                props.append("background")
            
            props_str = f" [{', '.join(props)}]" if props else ""
            
            click.echo(f"  {name:<30} {keys_str}{props_str}")
        
        click.echo()
        click.echo(f"Total indexes: {len(indexes)}")
        
        client.close()
        
    except Exception as e:
        click.echo(f"✗ Failed to list indexes: {e}", err=True)
        raise click.Abort()


@cli.group()
def demo():
    """Run interactive demos."""
    pass


@demo.command('list')
def demo_list():
    """List available demos."""
    from mdbpl.demos import list_demos
    
    click.echo("Available demos:")
    click.echo()
    
    for demo_info in list_demos():
        click.echo(f"  {demo_info['name']}")
        click.echo(f"    {demo_info['title']}")
        click.echo(f"    {demo_info['description']}")
        click.echo()


@demo.command('run')
@click.argument('demo_name')
@click.option('--output', type=click.Choice(['text', 'json']), default='text', help='Output format')
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
    
    if output == 'json':
        click.echo(json.dumps(result.to_dict(), indent=2))
    else:
        # Text output
        click.echo(f"{'='*60}")
        click.echo(f"Demo: {result.title}")
        click.echo(f"Started: {result.started_at}")
        click.echo(f"Completed: {result.completed_at}")
        click.echo(f"Success: {result.success}")
        if result.error:
            click.echo(f"Error: {result.error}", err=True)
        click.echo(f"{'='*60}")
        click.echo()
        
        for i, step in enumerate(result.steps, 1):
            click.echo(f"Step {i}: {step.name}")
            click.echo(f"  {step.description}")
            if step.result:
                click.echo(f"  Result: {json.dumps(step.result, indent=4)}")
            click.echo()


@cli.command()
@click.option('--host', default='0.0.0.0', help='Host to bind to')
@click.option('--port', default=8080, help='Port to bind to')
def serve(host, port):
    """Start the API server."""
    click.echo(f"Starting API server on {host}:{port}...")
    import uvicorn
    uvicorn.run("mdbpl.api:app", host=host, port=port, log_level="info")


@cli.command()
@click.confirmation_option(prompt='This will delete all benchmark results. Continue?')
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
    """Test YCSB installation."""
    click.echo("Testing YCSB installation...")
    
    ycsb_home = os.getenv('YCSB_HOME', '/opt/ycsb')
    if not os.path.exists(ycsb_home):
        click.echo(f"✗ YCSB not found at {ycsb_home}")
    else:
        click.echo(f"✓ YCSB found at {ycsb_home}")
        
        # Test Java
        try:
            result = subprocess.run(['java', '-version'], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                version_line = result.stderr.split('\n')[0] if result.stderr else "Unknown"
                click.echo(f"✓ Java is installed: {version_line}")
            else:
                click.echo("✗ Java test failed")
        except Exception as e:
            click.echo(f"✗ Java not found: {e}")
        
        # Test our wrapper
        try:
            from mdbpl.ycsb_wrapper import run_ycsb
            click.echo("✓ YCSB Python wrapper is available")
        except Exception as e:
            click.echo(f"✗ YCSB wrapper import failed: {e}")
    
    click.echo("\nTesting MongoDB connection...")
    mongodb_uri = os.getenv('MONGODB_URI', 'mongodb://localhost:27017')
    click.echo(f"MongoDB URI: {mongodb_uri}")
    # TODO: Test MongoDB connection


if __name__ == '__main__':
    cli()
