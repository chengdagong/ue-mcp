"""
EditorSubsystems - Lightweight registry for all editor subsystems.

This module replaces the EditorManager facade with a simpler registry pattern.
Tools access subsystems directly instead of going through a delegation layer.
"""

import atexit
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from .build_manager import BuildManager
from .context import EditorContext
from .execution_manager import ExecutionManager
from .health_monitor import HealthMonitor
from .launch_manager import LaunchManager
from .project_analyzer import ProjectAnalyzer

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


@dataclass
class EditorSubsystems:
    """
    Registry holding all editor subsystems for a bound project.

    This class provides direct access to subsystems without the delegation
    overhead of the previous EditorManager facade pattern.

    Usage:
        subsystems = EditorSubsystems.create(project_path)
        result = subsystems.execution.execute_with_checks(code)
    """

    context: EditorContext
    project_analyzer: ProjectAnalyzer
    execution: ExecutionManager
    lifecycle: LaunchManager  # Renamed from launch for clarity
    build: BuildManager
    health_monitor: HealthMonitor

    @classmethod
    def create(cls, project_path: Path) -> "EditorSubsystems":
        """
        Create and initialize all subsystems for a project.

        Args:
            project_path: Path to the .uproject file

        Returns:
            Initialized EditorSubsystems instance
        """
        from ..utils import get_project_name

        # Create shared context
        resolved_path = project_path.resolve()
        context = EditorContext(
            project_path=resolved_path,
            project_root=resolved_path.parent,
            project_name=get_project_name(resolved_path),
        )

        # Initialize subsystems with shared context
        project_analyzer = ProjectAnalyzer(context)
        execution = ExecutionManager(context)
        health_monitor = HealthMonitor(context)
        build = BuildManager(context, project_analyzer)
        lifecycle = LaunchManager(
            context,
            project_analyzer,
            health_monitor,
            build,
        )

        # Wire up circular dependency: HealthMonitor needs LaunchManager for restart
        health_monitor.set_restart_callback(lifecycle._launch_internal)

        instance = cls(
            context=context,
            project_analyzer=project_analyzer,
            execution=execution,
            lifecycle=lifecycle,
            build=build,
            health_monitor=health_monitor,
        )

        # Register cleanup on exit
        atexit.register(instance.cleanup)

        logger.info(f"EditorSubsystems initialized for project: {context.project_name}")
        logger.info(f"Project path: {context.project_path}")

        return instance

    def cleanup(self) -> None:
        """Clean up all subsystems on exit."""
        self.health_monitor.stop()
        self.context.cancel_all_background_tasks()
        if self.context.editor is not None:
            logger.info("Cleaning up editor instance...")
            self.context._intentional_stop = True
            self.context.stop(health_monitor=self.health_monitor)

    # Convenience properties for common access patterns
    @property
    def project_path(self) -> Path:
        """Path to the .uproject file."""
        return self.context.project_path

    @property
    def project_root(self) -> Path:
        """Path to the project directory."""
        return self.context.project_root

    @property
    def project_name(self) -> str:
        """Name of the project."""
        return self.context.project_name
