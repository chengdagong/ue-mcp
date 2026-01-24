"""
Editor subsystem package.

This package contains the modular components of the EditorManager,
implementing the Facade pattern for managing Unreal Editor instances.

Subsystems:
- ProjectAnalyzer: Project structure analysis and build status
- StatusManager: Editor status queries and stop operation
- ExecutionManager: Python code execution in the editor
- BuildManager: Project building with UnrealBuildTool
- HealthMonitor: Editor health monitoring and auto-restart
- LaunchManager: Editor launching and connection management
"""

from .build_manager import BuildManager
from .context import EditorContext
from .execution_manager import ExecutionManager
from .health_monitor import HealthMonitor
from .launch_manager import LaunchManager
from .project_analyzer import ProjectAnalyzer
from .status_manager import StatusManager
from .types import EditorInstance, NotifyCallback, ProgressCallback

__all__ = [
    # Types
    "EditorContext",
    "EditorInstance",
    "NotifyCallback",
    "ProgressCallback",
    # Subsystems
    "BuildManager",
    "ExecutionManager",
    "HealthMonitor",
    "LaunchManager",
    "ProjectAnalyzer",
    "StatusManager",
]
