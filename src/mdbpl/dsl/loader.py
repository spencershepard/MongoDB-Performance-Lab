"""DSL workload loader."""

import yaml
from pathlib import Path
from typing import Union

from .models import WorkloadSpec


class WorkloadLoader:
    """Loads and validates workload specifications from YAML files."""
    
    @staticmethod
    def load_from_file(path: Union[str, Path]) -> WorkloadSpec:
        """
        Load a workload specification from a YAML file.
        
        Args:
            path: Path to the workload YAML file
            
        Returns:
            Parsed and validated workload specification
        """
        path = Path(path)
        
        if not path.exists():
            raise FileNotFoundError(f"Workload file not found: {path}")
        
        with open(path, 'r') as f:
            data = yaml.safe_load(f)
        
        return WorkloadSpec(**data)
    
    @staticmethod
    def load_builtin(name: str) -> WorkloadSpec:
        """
        Load a built-in workload by name.
        
        Args:
            name: Name of the built-in workload (e.g., 'read-heavy')
            
        Returns:
            Parsed workload specification
        """
        # Find workloads directory relative to this file
        workloads_dir = Path(__file__).parent.parent.parent.parent / "workloads"
        workload_file = workloads_dir / f"{name}.yaml"
        
        if not workload_file.exists():
            raise ValueError(f"Unknown built-in workload: {name}")
        
        return WorkloadLoader.load_from_file(workload_file)
    
    @staticmethod
    def list_builtin_workloads() -> list[str]:
        """
        List available built-in workloads.
        
        Returns:
            List of workload names
        """
        workloads_dir = Path(__file__).parent.parent.parent.parent / "workloads"
        
        if not workloads_dir.exists():
            return []
        
        return [f.stem for f in workloads_dir.glob("*.yaml")]
