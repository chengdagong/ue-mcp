"""
Editor subsystem package.

This package contains modular components for managing Unreal Editor instances.
Tools access subsystems directly via EditorSubsystems registry.

Subsystems:
- ProjectAnalyzer: Project structure analysis and build status
- ExecutionManager: Python code execution in the editor
- BuildManager: Project building with UnrealBuildTool
- HealthMonitor: Editor health monitoring and auto-restart
- LaunchManager: Editor launching and connection management
- EditorContext: Shared state and status queries (formerly StatusManager)
"""

from .build_manager import BuildManager
from .context import EditorContext
from .execution_manager import ExecutionManager
from .health_monitor import HealthMonitor
from .launch_manager import LaunchManager
from .project_analyzer import ProjectAnalyzer
from .subsystems import EditorSubsystems
from .types import EditorInstance, NotifyCallback, ProgressCallback

__all__ = [
    # Types
    "EditorContext",
    "EditorInstance",
    "NotifyCallback",
    "ProgressCallback",
    # Subsystems
    "BuildManager",
    "EditorSubsystems",
    "ExecutionManager",
    "HealthMonitor",
    "LaunchManager",
    "ProjectAnalyzer",
]
