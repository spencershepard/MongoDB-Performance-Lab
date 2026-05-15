"""Demo modules for MongoDB Performance Lab."""

from .base import Demo, DemoStep
from .index_performance import IndexPerformanceDemo
from .overindexing import OverindexingDemo

__all__ = [
    "Demo",
    "DemoStep",
    "IndexPerformanceDemo",
    "OverindexingDemo",
]

# Registry of available demos
DEMOS = {
    "index-performance": IndexPerformanceDemo,
    "overindexing": OverindexingDemo,
}


def get_demo(name: str) -> Demo:
    """Get a demo by name."""
    if name not in DEMOS:
        raise ValueError(f"Unknown demo: {name}. Available: {list(DEMOS.keys())}")
    return DEMOS[name]()


def list_demos() -> list[dict]:
    """List all available demos with metadata."""
    return [
        {
            "name": demo_class.name,
            "title": demo_class.title,
            "description": demo_class.description,
        }
        for demo_class in DEMOS.values()
    ]
