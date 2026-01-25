"""
UE-MCP Editor Manager

Facade for managing the lifecycle of a single Unreal Editor instance bound to a project.

This module implements the Facade pattern, delegating to specialized subsystems
while maintaining a single, stable external API for server.py compatibility.
"""

import atexit
import logging
from pathlib import Path
from typing import Any, Optional

from .editor.build_manager import BuildManager
from .editor.context import EditorContext
from .editor.execution_manager import ExecutionManager
from .editor.health_monitor import HealthMonitor
from .editor.launch_manager import LaunchManager
from .editor.project_analyzer import ProjectAnalyzer
from .editor.status_manager import StatusManager
from .editor.types import EditorInstance, NotifyCallback, ProgressCallback
from .utils import get_project_name

logger = logging.getLogger(__name__)

# Re-export types for backwards compatibility
__all__ = ["EditorManager", "EditorInstance", "NotifyCallback", "ProgressCallback"]


class EditorManager:
    """
    Facade for managing a single Unreal Editor instance for a bound project.

    This class provides a stable external API while delegating to specialized
    subsystems for the actual implementation. The subsystems are:

    - ProjectAnalyzer: Project structure analysis and build status
    - StatusManager: Editor status queries and stop operation
    - ExecutionManager: Python code execution in the editor
    - BuildManager: Project building with UnrealBuildTool
    - HealthMonitor: Editor health monitoring and auto-restart
    - LaunchManager: Editor launching and connection management

    This class is designed for one-to-one binding: one EditorManager per project.
    """

    # Re-export health monitor constants for backwards compatibility
    MAX_RESTART_ATTEMPTS = HealthMonitor.MAX_RESTART_ATTEMPTS
    RESTART_COOLDOWN_SECONDS = HealthMonitor.RESTART_COOLDOWN_SECONDS
    HEALTH_CHECK_INTERVAL = HealthMonitor.HEALTH_CHECK_INTERVAL

    def __init__(self, project_path: Path):
        """
        Initialize EditorManager.

        Args:
            project_path: Path to the .uproject file
        """
        # Create shared context
        resolved_path = project_path.resolve()
        self._context = EditorContext(
            project_path=resolved_path,
            project_root=resolved_path.parent,
            project_name=get_project_name(resolved_path),
        )

        # Initialize subsystems with shared context
        self._project_analyzer = ProjectAnalyzer(self._context)
        self._status_manager = StatusManager(self._context)
        self._execution_manager = ExecutionManager(self._context)
        self._health_monitor = HealthMonitor(self._context)
        self._build_manager = BuildManager(self._context, self._project_analyzer)
        self._launch_manager = LaunchManager(
            self._context,
            self._project_analyzer,
            self._health_monitor,
            self._build_manager,
        )

        # Wire up circular dependency: HealthMonitor needs LaunchManager for restart
        self._health_monitor.set_restart_callback(self._launch_manager._launch_internal)

        # Register cleanup on exit
        atexit.register(self._cleanup)

        logger.info(f"EditorManager initialized for project: {self._context.project_name}")
        logger.info(f"Project path: {self._context.project_path}")

    # =========================================================================
    # Properties (unchanged API)
    # =========================================================================

    @property
    def project_path(self) -> Path:
        """Path to the .uproject file."""
        return self._context.project_path

    @property
    def project_root(self) -> Path:
        """Path to the project directory."""
        return self._context.project_root

    @property
    def project_name(self) -> str:
        """Name of the project."""
        return self._context.project_name

    # =========================================================================
    # Status Methods (delegated to StatusManager)
    # =========================================================================

    def get_status(self) -> dict[str, Any]:
        """
        Get current editor status.

        Returns:
            Status dictionary with editor information
        """
        return self._status_manager.get_status()

    def read_log(self, tail_lines: Optional[int] = None) -> dict[str, Any]:
        """
        Read the editor log file content.

        Args:
            tail_lines: If specified, only return the last N lines of the log

        Returns:
            Dictionary containing log content and metadata
        """
        return self._status_manager.read_log(tail_lines)

    def is_running(self) -> bool:
        """Check if editor is running."""
        return self._status_manager.is_running()

    def stop(self) -> dict[str, Any]:
        """
        Stop the managed editor instance.

        Uses graceful shutdown first, then forceful termination if needed.

        Returns:
            Stop result dictionary
        """
        return self._status_manager.stop(health_monitor=self._health_monitor)

    # =========================================================================
    # Project Analysis Methods (delegated to ProjectAnalyzer)
    # =========================================================================

    def is_cpp_project(self) -> bool:
        """
        Check if the project is a C++ project.

        Returns:
            True if project has a 'Source' directory or C++ plugins, False otherwise.
        """
        return self._project_analyzer.is_cpp_project()

    def needs_build(self) -> tuple[bool, str]:
        """
        Check if the project needs to be built.

        Returns:
            Tuple of (needs_build, reason)
        """
        return self._project_analyzer.needs_build()

    # =========================================================================
    # Launch Methods (delegated to LaunchManager)
    # =========================================================================

    async def launch(
        self,
        notify: Optional[NotifyCallback] = None,
        additional_paths: Optional[list[str]] = None,
        wait_timeout: float = 120.0,
    ) -> dict[str, Any]:
        """
        Launch Unreal Editor and wait for connection (synchronous startup).

        Args:
            notify: Optional async callback to send notifications
            additional_paths: Optional list of additional Python paths
            wait_timeout: Maximum time to wait for editor connection

        Returns:
            Launch result dictionary
        """
        return await self._launch_manager.launch(
            notify=notify,
            additional_paths=additional_paths,
            wait_timeout=wait_timeout,
        )

    async def launch_async(
        self,
        notify: NotifyCallback,
        additional_paths: Optional[list[str]] = None,
        wait_timeout: float = 120.0,
    ) -> dict[str, Any]:
        """
        Launch Unreal Editor asynchronously (returns immediately).

        Args:
            notify: Async callback to send notifications
            additional_paths: Optional list of additional Python paths
            wait_timeout: Maximum time to wait for editor connection

        Returns:
            Initial launch result (editor starting in background)
        """
        return await self._launch_manager.launch_async(
            notify=notify,
            additional_paths=additional_paths,
            wait_timeout=wait_timeout,
        )

    # =========================================================================
    # Execution Methods (delegated to ExecutionManager)
    # =========================================================================

    def execute_code(self, code: str, timeout: float = 30.0) -> dict[str, Any]:
        """
        Execute Python code in the editor without additional checks.

        This is a low-level execution method intended for internal use
        (e.g., parameter injection, simple variable assignments).
        For general code execution, use execute_with_checks() instead.

        Args:
            code: Python code to execute
            timeout: Execution timeout in seconds

        Returns:
            Execution result dictionary
        """
        return self._execution_manager._execute_code(code=code, timeout=timeout)

    def execute_with_checks(
        self,
        code: str,
        timeout: float = 30.0,
        max_install_attempts: int = 3,
    ) -> dict[str, Any]:
        """
        Execute Python code with automatic missing module installation
        and bundled module reloading.

        Args:
            code: Python code to execute
            timeout: Execution timeout in seconds
            max_install_attempts: Maximum number of packages to auto-install

        Returns:
            Execution result dictionary
        """
        return self._execution_manager.execute_with_checks(
            code=code,
            timeout=timeout,
            max_install_attempts=max_install_attempts,
        )

    def execute_script_file(self, script_path: str, timeout: float = 120.0) -> dict[str, Any]:
        """
        Execute a Python script file using EXECUTE_FILE mode.

        This enables true hot-reload as the file is executed directly from disk.

        Args:
            script_path: Absolute path to the Python script file
            timeout: Execution timeout in seconds

        Returns:
            Execution result dictionary
        """
        return self._execution_manager.execute_script_file(
            script_path=script_path,
            timeout=timeout,
        )

    def pip_install_packages(
        self,
        packages: list[str],
        upgrade: bool = False,
    ) -> dict[str, Any]:
        """
        Install Python packages in UE5's Python environment.

        Args:
            packages: List of package names to install
            upgrade: Whether to upgrade existing packages

        Returns:
            Installation result dictionary
        """
        return self._execution_manager.pip_install_packages(
            packages=packages,
            upgrade=upgrade,
        )

    # =========================================================================
    # Build Methods (delegated to BuildManager)
    # =========================================================================

    async def build(
        self,
        notify: Optional[NotifyCallback] = None,
        progress: Optional[ProgressCallback] = None,
        target: str = "Editor",
        configuration: str = "Development",
        platform: str = "Win64",
        clean: bool = False,
        timeout: float = 1800.0,
        verbose: bool = False,
    ) -> dict[str, Any]:
        """
        Build the UE5 project using UnrealBuildTool (synchronous, but async implementation).

        Args:
            notify: Optional async callback to send notifications
            progress: Optional async callback to report progress
            target: Build target - "Editor", "Game", "Client", or "Server"
            configuration: Build configuration
            platform: Target platform
            clean: Whether to perform a clean build
            timeout: Build timeout in seconds
            verbose: Whether to send all build logs via notify

        Returns:
            Build result dictionary
        """
        return await self._build_manager.build(
            notify=notify,
            progress=progress,
            target=target,
            configuration=configuration,
            platform=platform,
            clean=clean,
            timeout=timeout,
            verbose=verbose,
        )

    async def build_async(
        self,
        notify: NotifyCallback,
        progress: Optional[ProgressCallback] = None,
        target: str = "Editor",
        configuration: str = "Development",
        platform: str = "Win64",
        clean: bool = False,
        timeout: float = 1800.0,
        verbose: bool = False,
    ) -> dict[str, Any]:
        """
        Build the UE5 project asynchronously using UnrealBuildTool.

        This method returns immediately and sends notifications via the callback
        as the build progresses.

        Args:
            notify: Async callback function to send notifications
            progress: Optional async callback to report progress
            target: Build target - "Editor", "Game", "Client", or "Server"
            configuration: Build configuration
            platform: Target platform
            clean: Whether to perform a clean build
            timeout: Build timeout in seconds
            verbose: Whether to send all build logs via notify

        Returns:
            Initial build result (build started)
        """
        return await self._build_manager.build_async(
            notify=notify,
            progress=progress,
            target=target,
            configuration=configuration,
            platform=platform,
            clean=clean,
            timeout=timeout,
            verbose=verbose,
        )

    # =========================================================================
    # Internal Methods
    # =========================================================================

    def _cleanup(self) -> None:
        """Clean up editor instance on exit."""
        self._health_monitor.stop()
        self._context.cancel_all_background_tasks()
        if self._context.editor is not None:
            logger.info("Cleaning up editor instance...")
            self._context._intentional_stop = True
            self.stop()
