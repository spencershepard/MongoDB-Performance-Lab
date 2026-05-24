"""Base demo class and utilities."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from typing import Optional, Any, Union, List
from datetime import datetime
from pathlib import Path
import subprocess
import tempfile
import os


@dataclass
class Command:
    """Base class for commands that can be executed."""
    
    type: str  # 'shell' or 'mongosh'
    raw: str   # The actual command or script
    collapse_output: bool = False  # If True, UI should collapse/hide verbose output by default
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "type": self.type,
            "command": self.raw,
            "collapse_output": self.collapse_output
        }


@dataclass
class ShellCommand(Command):
    """A shell command (mdbpl CLI command)."""
    
    def __init__(self, command: str, collapse_output: bool = False):
        super().__init__(type="shell", raw=command, collapse_output=collapse_output)


@dataclass
class MongoshCommand(Command):
    """A mongosh script command."""
    
    def __init__(self, script: str, collapse_output: bool = False):
        super().__init__(type="mongosh", raw=script, collapse_output=collapse_output)


@dataclass
class DemoStep:
    """Represents a single step in a demo."""
    
    id: str
    title: str
    description: str = ""  # Short description for UI
    markdown: str = ""  # Full educational markdown content explaining this step
    commands: List[Command] = field(default_factory=list)
    
    # Execution state
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    status: str = "pending"  # pending, running, completed, failed
    error: Optional[str] = None
    outputs: List[dict] = field(default_factory=list)  # Command outputs with stdout/stderr
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "markdown": self.markdown,
            "commands": [cmd.to_dict() for cmd in self.commands],
            "status": self.status,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error": self.error,
            "outputs": self.outputs
        }


class CommandExecutor:
    """Executes demo commands and captures output."""
    
    def __init__(self, mongodb_uri: Optional[str] = None, verbose: bool = True):
        self.mongodb_uri = mongodb_uri or os.getenv("MONGODB_URI", "mongodb://localhost:27017")
        self.verbose = verbose
    
    def execute_shell(self, command: str) -> dict:
        """Execute a shell command and return result."""
        if self.verbose:
            print(f"  $ {command}")
        
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=300,
                cwd=os.getcwd()
            )
            
            output = {
                "exit_code": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "success": result.returncode == 0
            }
            
            if self.verbose and result.stdout:
                print(result.stdout)
            if result.returncode != 0 and result.stderr:
                print(f"  Error: {result.stderr}")
            
            return output
        
        except subprocess.TimeoutExpired:
            return {
                "exit_code": 1,
                "stdout": "",
                "stderr": "Command timed out after 300 seconds",
                "success": False
            }
        except Exception as e:
            return {
                "exit_code": 1,
                "stdout": "",
                "stderr": f"Command execution failed: {e}",
                "success": False
            }
    
    def execute_mongosh(self, script: str) -> dict:
        """Execute a mongosh script and return result."""
        if self.verbose:
            print(f"  [mongosh] Executing script...")
        
        # Write script to temporary file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False, encoding='utf-8') as f:
            f.write(script)
            script_path = f.name
        
        try:
            # Ensure URI includes database name for scripts to work properly
            uri = self.mongodb_uri
            if '/perflab' not in uri and uri.endswith(':27017'):
                uri = uri + '/perflab'
            elif uri.endswith('27017/'):
                uri = uri + 'perflab'
            
            cmd = [
                'mongosh',
                uri,
                '--quiet',
                '--file', script_path
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            output = {
                "exit_code": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "success": result.returncode == 0
            }
            
            if self.verbose and result.stdout:
                print(result.stdout)
            if result.returncode != 0 and result.stderr:
                print(f"  Error: {result.stderr}")
            
            return output
        
        except subprocess.TimeoutExpired:
            return {
                "exit_code": 1,
                "stdout": "",
                "stderr": "Mongosh script timed out after 60 seconds",
                "success": False
            }
        except FileNotFoundError:
            return {
                "exit_code": 1,
                "stdout": "",
                "stderr": "mongosh not found. Is it installed and in PATH?",
                "success": False
            }
        except Exception as e:
            return {
                "exit_code": 1,
                "stdout": "",
                "stderr": f"Mongosh execution failed: {e}",
                "success": False
            }
        finally:
            try:
                os.unlink(script_path)
            except:
                pass
    
    def execute_command(self, command: Command) -> dict:
        """Execute a command and return result."""
        if command.type == "shell":
            return self.execute_shell(command.raw)
        elif command.type == "mongosh":
            return self.execute_mongosh(command.raw)
        else:
            return {
                "exit_code": 1,
                "stdout": "",
                "stderr": f"Unknown command type: {command.type}",
                "success": False
            }


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
    id: str = ""
    title: str = ""
    description: str = ""
    markdown_file: str = ""  # e.g., "index-performance.md"
    
    @abstractmethod
    def steps(self) -> List[DemoStep]:
        """Define the demo steps. Override in subclasses."""
        pass
    
    def execute_step(self, step_index: int, verbose: bool = True) -> tuple[DemoStep, bool]:
        """Execute a single step by index. Returns (step, success).
        
        Args:
            step_index: Zero-based index of step to execute
            verbose: Whether to print output
            
        Returns:
            Tuple of (executed step, success boolean)
        """
        demo_steps = self.steps()
        
        if step_index < 0 or step_index >= len(demo_steps):
            raise ValueError(f"Invalid step index: {step_index}. Valid range: 0-{len(demo_steps)-1}")
        
        step = demo_steps[step_index]
        executor = CommandExecutor(verbose=verbose)
        
        if verbose:
            print(f"\n[Step {step_index + 1}/{len(demo_steps)}] {step.title}")
            if step.description:
                print(f"  {step.description}")
        
        step.started_at = datetime.now()
        step.status = "running"
        
        # Execute each command in the step
        step_failed = False
        for command in step.commands:
            output = executor.execute_command(command)
            step.outputs.append(output)
            
            if not output["success"]:
                step.status = "failed"
                step.error = output["stderr"] or "Command failed"
                step_failed = True
                break
        
        step.completed_at = datetime.now()
        
        if not step_failed:
            step.status = "completed"
            if verbose:
                print(f"  ✓ Step completed")
        else:
            if verbose:
                print(f"  ✗ Step failed: {step.error}")
        
        return step, not step_failed
    
    def run(self, verbose: bool = True, stop_on_error: bool = True) -> DemoResult:
        """Execute the demo by running all steps sequentially.
        
        This is useful for CLI execution. For UI-controlled step-by-step execution,
        use execute_step() instead.
        """
        result = DemoResult(
            demo_name=self.id,
            title=self.title,
            started_at=datetime.now()
        )
        
        print(f"\n{'='*60}")
        print(f"Demo: {self.title}")
        print(f"{'='*60}\n")
        
        if self.description:
            print(self.description)
            print()
        
        # Get steps from subclass
        demo_steps = self.steps()
        result.steps = demo_steps
        
        # Execute each step
        for i in range(len(demo_steps)):
            step, success = self.execute_step(i, verbose=verbose)
            result.steps[i] = step
            
            if not success:
                result.success = False
                result.error = f"Failed at step: {step.id}"
                if stop_on_error:
                    break
        
        result.completed_at = datetime.now()
        
        # Print summary
        print(f"\n{'='*60}")
        if result.success:
            print(f"✓ Demo completed successfully")
        else:
            print(f"✗ Demo failed: {result.error}")
        print(f"{'='*60}\n")
        
        return result
    
    def get_metadata(self) -> dict:
        """Get demo metadata."""
        return {
            "id": self.id,
            "name": self.id,  # Alias for backwards compatibility
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
