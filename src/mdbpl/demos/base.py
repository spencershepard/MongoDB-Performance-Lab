"""Base demo class and utilities."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from typing import Optional, Any
from datetime import datetime
from pathlib import Path


@dataclass
class DemoStep:
    """Represents a single step in a demo."""
    
    name: str
    description: str
    result: Optional[dict] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        data = asdict(self)
        # Convert datetimes to ISO strings
        if self.started_at:
            data["started_at"] = self.started_at.isoformat()
        if self.completed_at:
            data["completed_at"] = self.completed_at.isoformat()
        return data


@dataclass
class DemoResult:
    """Complete demo execution result."""
    
    demo_name: str
    title: str
    steps: list[DemoStep] = field(default_factory=list)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    success: bool = True
    error: Optional[str] = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "demo_name": self.demo_name,
            "title": self.title,
            "steps": [step.to_dict() for step in self.steps],
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "success": self.success,
            "error": self.error,
        }


class Demo(ABC):
    """Base class for all demos."""
    
    # Override these in subclasses
    name: str = ""
    title: str = ""
    description: str = ""
    markdown_file: str = ""  # e.g., "index-performance.md"
    
    @abstractmethod
    def run(self) -> DemoResult:
        """Execute the demo and return results."""
        pass
    
    def get_metadata(self) -> dict:
        """Get demo metadata."""
        return {
            "name": self.name,
            "title": self.title,
            "description": self.description,
            "has_docs": bool(self.markdown_file),
        }
    
    def get_markdown_content(self) -> str:
        """Load markdown documentation if available.
        
        Looks for markdown files in docs/demos/ directory at project root.
        The markdown_file attribute should just be the filename (e.g., 'index-performance.md').
        """
        if not self.markdown_file:
            return self.description  # Fallback to simple description
        
        # Navigate to project root (up from src/mdbpl/demos/base.py)
        project_root = Path(__file__).parent.parent.parent.parent
        markdown_path = project_root / "docs" / "demos" / self.markdown_file
        
        try:
            if markdown_path.exists():
                return markdown_path.read_text(encoding='utf-8')
        except Exception as e:
            print(f"Warning: Failed to load markdown file {self.markdown_file}: {e}")
        
        return self.description  # Fallback
