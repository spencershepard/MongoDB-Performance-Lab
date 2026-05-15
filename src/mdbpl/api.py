"""FastAPI application for MongoDB Performance Lab."""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel
from typing import Optional, List
import asyncio
import os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from mdbpl.demos import list_demos, get_demo
from mdbpl.frontend.dash_app import create_dash_app
from mdbpl.dsl.loader import WorkloadLoader
from mdbpl.executor import WorkloadExecutor, BenchmarkResult
from mdbpl.storage import BenchmarkStorage

app = FastAPI(
    title="MongoDB Performance Lab API",
    description="YCSB-inspired MongoDB benchmarking platform",
    version="0.1.0"
)

# Enable CORS for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Thread pool for running demos (they're CPU/IO intensive)
executor = ThreadPoolExecutor(max_workers=2)

# Initialize storage
MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://mongodb:27017")
storage = BenchmarkStorage("/data/benchmarks.db")


# Request/Response models
class RunBenchmarkRequest(BaseModel):
    workload_name: str
    duration_seconds: int = 30
    tag: Optional[str] = None
    record_count: int = 10000


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "MongoDB Performance Lab",
        "version": "0.1.0",
        "status": "running"
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}


# ============================================================================
# Workload Endpoints
# ============================================================================

@app.get("/api/workloads")
async def get_workloads():
    """List all available workloads."""
    workloads = WorkloadLoader.list_builtin_workloads()
    return {"workloads": workloads}


@app.get("/api/workloads/{workload_name}")
async def get_workload_info(workload_name: str):
    """Get details about a specific workload."""
    try:
        workload = WorkloadLoader.load_builtin(workload_name)
        return {
            "name": workload.name,
            "description": workload.description,
            "database": workload.database,
            "collection": workload.collection,
            "distribution": workload.distribution.type if workload.distribution else "uniform",
            "operations": len(workload.operations)
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ============================================================================
# Benchmark Endpoints
# ============================================================================

@app.get("/api/benchmarks")
async def list_benchmarks(limit: int = 20):
    """List recent benchmark results."""
    runs = storage.list_runs(limit=limit)
    return {"benchmarks": runs}


@app.get("/api/benchmarks/{run_id}")
async def get_benchmark_result(run_id: int):
    """Get detailed results for a specific benchmark run."""
    result = storage.get_run_by_id(run_id)
    if not result:
        raise HTTPException(status_code=404, detail="Benchmark not found")
    return result


@app.get("/api/benchmarks/tag/{tag}")
async def get_benchmark_by_tag(tag: str):
    """Get benchmark results by tag."""
    result = storage.get_run_by_tag(tag)
    if not result:
        raise HTTPException(status_code=404, detail=f"No benchmark found with tag: {tag}")
    return result


@app.get("/api/benchmarks/compare")
async def compare_benchmarks(baseline: str, optimized: str):
    """Compare two benchmark runs by their tags."""
    comparison = storage.compare_runs(baseline, optimized)
    if not comparison:
        raise HTTPException(status_code=404, detail="One or both benchmarks not found")
    return comparison


@app.post("/api/benchmarks/run")
async def run_benchmark(request: RunBenchmarkRequest):
    """
    Execute a benchmark workload.
    
    Args:
        request: Benchmark parameters including workload, duration, and tag
        
    Returns:
        Complete benchmark results including metrics and operation breakdown
    """
    try:
        # Load workload
        workload = WorkloadLoader.load_builtin(request.workload_name)
        
        # Create executor
        executor_instance = WorkloadExecutor(
            workload=workload,
            mongodb_uri=MONGODB_URI,
            record_count=request.record_count
        )
        
        # Run benchmark in thread pool
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            executor,
            lambda: executor_instance.run(request.duration_seconds, request.tag)
        )
        
        # Save to storage
        run_id = storage.save_result(
            result=result,
            tag=request.tag or ""
        )
        
        # Return result with run_id
        result_dict = {
            "run_id": run_id,
            "workload_name": request.workload_name,
            "tag": request.tag,
            "duration_seconds": request.duration_seconds,
            "throughput": result.operations_per_second,
            "latency_p50": result.latency_p50,
            "latency_p95": result.latency_p95,
            "latency_p99": result.latency_p99,
            "total_operations": result.total_operations,
            "operation_metrics": result.operation_metrics
        }
        
        return result_dict
        
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Benchmark failed: {str(e)}")


# ============================================================================
# Demo Endpoints
# ============================================================================

@app.get("/api/demos")
async def get_demos():
    """
    List all available demos.
    
    Returns metadata for each demo including name, title, and description.
    """
    return {
        "demos": list_demos()
    }


@app.get("/api/demos/{demo_name}")
async def get_demo_info(demo_name: str):
    """
    Get metadata for a specific demo.
    
    Args:
        demo_name: Name of the demo (e.g., 'index-performance')
    """
    try:
        demo = get_demo(demo_name)
        return demo.get_metadata()
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/api/demos/{demo_name}/docs")
async def get_demo_docs(demo_name: str):
    """
    Get markdown documentation for a specific demo.
    
    Args:
        demo_name: Name of the demo (e.g., 'index-performance')
        
    Returns:
        Dictionary with markdown content and metadata.
        
    Note:
        This is a convenience endpoint. For general doc access, use /api/docs/{path}
    """
    try:
        demo = get_demo(demo_name)
        metadata = demo.get_metadata()
        return {
            "markdown": demo.get_markdown_content(),
            "has_docs": metadata.get("has_docs", False),
            "title": metadata.get("title", ""),
            "description": metadata.get("description", "")
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/api/docs")
async def list_documentation():
    """
    List all available documentation files in the docs/ directory.
    
    Returns:
        Dictionary with categorized documentation files.
    """
    # Get project root (up from src/mdbpl/api.py)
    project_root = Path(__file__).parent.parent.parent
    docs_dir = project_root / "docs"
    
    if not docs_dir.exists():
        return {"docs": [], "demos": []}
    
    # Find all markdown files
    docs = []
    demos = []
    
    try:
        # Root level docs
        for doc_path in docs_dir.glob("*.md"):
            docs.append({
                "name": doc_path.stem,
                "filename": doc_path.name,
                "path": doc_path.name
            })
        
        # Demo docs
        demos_dir = docs_dir / "demos"
        if demos_dir.exists():
            for doc_path in demos_dir.glob("*.md"):
                demos.append({
                    "name": doc_path.stem,
                    "filename": doc_path.name,
                    "path": f"demos/{doc_path.name}"
                })
        
        return {
            "docs": sorted(docs, key=lambda x: x["name"]),
            "demos": sorted(demos, key=lambda x: x["name"])
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing docs: {str(e)}")


@app.get("/api/docs/{path:path}")
async def get_documentation(path: str):
    """
    Serve markdown documentation from the docs/ directory.
    
    Args:
        path: Relative path to markdown file (e.g., 'demos/index-performance.md' or 'METRICS.md')
        
    Returns:
        Dictionary with markdown content and metadata.
        
    Examples:
        - GET /api/docs/demos/index-performance.md
        - GET /api/docs/METRICS.md
        - GET /api/docs/DSL-SPEC.md
    """
    # Get project root (up from src/mdbpl/api.py)
    project_root = Path(__file__).parent.parent.parent
    doc_path = project_root / "docs" / path
    
    # Security: Prevent directory traversal
    try:
        doc_path = doc_path.resolve()
        docs_dir = (project_root / "docs").resolve()
        if not str(doc_path).startswith(str(docs_dir)):
            raise HTTPException(status_code=403, detail="Access forbidden")
    except Exception:
        raise HTTPException(status_code=403, detail="Invalid path")
    
    # Check if file exists
    if not doc_path.exists() or not doc_path.is_file():
        raise HTTPException(status_code=404, detail="Documentation not found")
    
    # Only serve markdown files
    if not doc_path.suffix.lower() in [".md", ".markdown"]:
        raise HTTPException(status_code=400, detail="Only markdown files are supported")
    
    # Read and return content
    try:
        content = doc_path.read_text(encoding='utf-8')
        return {
            "markdown": content,
            "path": path,
            "filename": doc_path.name,
            "title": doc_path.stem.replace("-", " ").title()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading file: {str(e)}")


@app.post("/api/demos/{demo_name}/run")
async def run_demo(demo_name: str):
    """
    Execute a specific demo.
    
    Args:
        demo_name: Name of the demo to run
        
    Returns:
        Complete demo execution results including all steps and metrics.
        
    Note:
        This endpoint runs synchronously and may take 1-2 minutes.
        For production, consider using background tasks with status polling.
    """
    try:
        demo = get_demo(demo_name)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    
    # Run demo in thread pool to avoid blocking the event loop
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(executor, demo.run)
    
    return result.to_dict()


# ============================================================================
# Frontend Integration
# ============================================================================

# Create and mount Dash app
dash_app = create_dash_app(requests_pathname_prefix="/ui/")

# Mount Dash app on FastAPI
from starlette.middleware.wsgi import WSGIMiddleware
app.mount("/ui", WSGIMiddleware(dash_app.server))


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_redirect():
    """Redirect /dashboard to /ui/ for convenience."""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <meta http-equiv="refresh" content="0; url=/ui/" />
        <title>Redirecting...</title>
    </head>
    <body>
        <p>Redirecting to <a href="/ui/">dashboard</a>...</p>
    </body>
    </html>
    """
