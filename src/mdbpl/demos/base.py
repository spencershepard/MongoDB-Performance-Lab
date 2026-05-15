"""Base demo class and utilities."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from typing import Optional, Any
from datetime import datetime


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
        }
