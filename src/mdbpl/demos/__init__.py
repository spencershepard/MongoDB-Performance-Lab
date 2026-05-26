"""Demo modules for MongoDB Performance Lab."""
from pathlib import Path

from .base import Demo, DemoStep, Command, ShellCommand, MongoshCommand, WorkloadCommand, CommandExecutor
from .index_performance import IndexPerformanceDemo
from .overindexing import OverindexingDemo
from .compound_index import CompoundIndexDemo
from .aggregation_pipeline import AggregationPipelineDemo
from .lookup import LookupDemo
from .covering_index import CoveringIndexDemo

__all__ = [
    "Demo",
    "DemoStep",
    "Command",
    "ShellCommand",
    "MongoshCommand",
    "WorkloadCommand",
    "CommandExecutor",
    "IndexPerformanceDemo",
    "OverindexingDemo",
    "CompoundIndexDemo",
    "AggregationPipelineDemo",
    "LookupDemo",
    "CoveringIndexDemo",
    "get_demo",
    "list_demos",
    "list_user_demos",
]

# Registry of available demos
DEMOS = {
    "index-performance": IndexPerformanceDemo,
    "overindexing": OverindexingDemo,
    "compound-index": CompoundIndexDemo,
    "aggregation-pipeline": AggregationPipelineDemo,
    "lookup": LookupDemo,
    "covering-index": CoveringIndexDemo,
}


_USER_DEMOS_DIR = Path("/data/user_demos")


def get_demo(name: str) -> Demo:
    """Get a demo by name — built-ins first, then user demos directory."""
    if name in DEMOS:
        return DEMOS[name]()
    user_path = _USER_DEMOS_DIR / f"{name}.py"
    if user_path.exists():
        import importlib.util
        import inspect as _inspect
        spec = importlib.util.spec_from_file_location(f"_user_demo_{name}", user_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        for _, cls in _inspect.getmembers(mod, _inspect.isclass):
            if issubclass(cls, Demo) and cls is not Demo:
                return cls()
    raise ValueError(f"Unknown demo: {name}. Available: {list(DEMOS.keys())}")


def list_user_demos() -> list[dict]:
    """List agent-generated demos from the user demos directory."""
    if not _USER_DEMOS_DIR.exists():
        return []
    import importlib.util
    import inspect as _inspect
    result = []
    for path in sorted(_USER_DEMOS_DIR.glob("*.py")):
        try:
            spec = importlib.util.spec_from_file_location(f"_user_demo_{path.stem}", path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            for _, cls in _inspect.getmembers(mod, _inspect.isclass):
                if issubclass(cls, Demo) and cls is not Demo and hasattr(cls, "id"):
                    result.append({
                        "name": cls.id,
                        "title": getattr(cls, "title", cls.id),
                        "description": getattr(cls, "description", ""),
                    })
                    break
        except Exception:
            continue
    return result


def list_demos() -> list[dict]:
    """List all available demos with metadata."""
    return [
        {
            "name": demo_class.id,  # Use id, not name (name is a property)
            "id": demo_class.id,
            "title": demo_class.title,
            "description": demo_class.description,
        }
        for demo_class in DEMOS.values()
    ]
