"""Global state management for UE-MCP server."""

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .editor.build_manager import BuildManager
    from .editor.context import EditorContext
    from .editor.execution_manager import ExecutionManager
    from .editor.health_monitor import HealthMonitor
    from .editor.launch_manager import LaunchManager
    from .editor.project_analyzer import ProjectAnalyzer
    from .editor.subsystems import EditorSubsystems

logger = logging.getLogger(__name__)


class ServerState:
    """Centralized state for the MCP server.

    This class manages all global state for the UE-MCP server, including:
    - EditorSubsystems instance (replaces EditorManager)
    - Client name (detected from MCP client)
    - Project path initialization status

    Tools access subsystems directly via get_*_subsystem() methods.
    """

    def __init__(self) -> None:
        self._subsystems: Optional["EditorSubsystems"] = None
        self._client_name: Optional[str] = None
        self._project_path_set: bool = False

    @property
    def subsystems(self) -> Optional["EditorSubsystems"]:
        """Get the EditorSubsystems instance (may be None)."""
        return self._subsystems

    @subsystems.setter
    def subsystems(self, value: Optional["EditorSubsystems"]) -> None:
        """Set the EditorSubsystems instance."""
        self._subsystems = value

    @property
    def client_name(self) -> Optional[str]:
        """Get the MCP client name."""
        return self._client_name

    @client_name.setter
    def client_name(self, value: Optional[str]) -> None:
        """Set the MCP client name."""
        self._client_name = value

    @property
    def project_path_set(self) -> bool:
        """Check if project path has been set via project_set_path tool."""
        return self._project_path_set

    @project_path_set.setter
    def project_path_set(self, value: bool) -> None:
        """Set the project path initialization status."""
        self._project_path_set = value

    def _require_subsystems(self) -> "EditorSubsystems":
        """Get subsystems, raising RuntimeError if not initialized."""
        if self._subsystems is None:
            raise RuntimeError(
                "EditorSubsystems not initialized. "
                "Please call the 'project_set_path' tool first to set the UE5 project directory."
            )
        return self._subsystems

    # =========================================================================
    # Subsystem Accessors (direct access pattern)
    # =========================================================================

    def get_context(self) -> "EditorContext":
        """Get the EditorContext for status queries.

        Returns:
            EditorContext instance

        Raises:
            RuntimeError: If subsystems have not been initialized
        """
        return self._require_subsystems().context

    def get_execution_subsystem(self) -> "ExecutionManager":
        """Get the ExecutionManager for code execution.

        Returns:
            ExecutionManager instance

        Raises:
            RuntimeError: If subsystems have not been initialized
        """
        return self._require_subsystems().execution

    def get_editor_lifecycle_subsystem(self) -> "LaunchManager":
        """Get the LaunchManager for editor lifecycle operations.

        Returns:
            LaunchManager instance

        Raises:
            RuntimeError: If subsystems have not been initialized
        """
        return self._require_subsystems().lifecycle

    def get_build_subsystem(self) -> "BuildManager":
        """Get the BuildManager for project building.

        Returns:
            BuildManager instance

        Raises:
            RuntimeError: If subsystems have not been initialized
        """
        return self._require_subsystems().build

    def get_project_analyzer(self) -> "ProjectAnalyzer":
        """Get the ProjectAnalyzer for project analysis.

        Returns:
            ProjectAnalyzer instance

        Raises:
            RuntimeError: If subsystems have not been initialized
        """
        return self._require_subsystems().project_analyzer

    def get_health_monitor(self) -> "HealthMonitor":
        """Get the HealthMonitor for editor health tracking.

        Returns:
            HealthMonitor instance

        Raises:
            RuntimeError: If subsystems have not been initialized
        """
        return self._require_subsystems().health_monitor

    # =========================================================================
    # Initialization and Cleanup
    # =========================================================================

    def initialize_from_cwd(self) -> Optional["EditorSubsystems"]:
        """Try to initialize EditorSubsystems from current working directory.

        Searches for a .uproject file in the current directory and initializes
        the subsystems if found.

        Returns:
            EditorSubsystems instance if successful, None otherwise
        """
        from .editor.subsystems import EditorSubsystems
        from .core.utils import find_uproject_file

        logger.info("Initializing UE-MCP server...")
        logger.info(f"Working directory: {Path.cwd()}")

        uproject_path = find_uproject_file()
        if uproject_path is None:
            logger.error(
                "No .uproject file found. Please run this server from a UE5 project directory."
            )
            return None

        logger.info(f"Detected project: {uproject_path}")
        self._subsystems = EditorSubsystems.create(uproject_path)
        return self._subsystems

    def initialize_from_path(self, project_path: Path) -> "EditorSubsystems":
        """Initialize EditorSubsystems from a specific project path.

        Args:
            project_path: Path to the .uproject file

        Returns:
            EditorSubsystems instance
        """
        from .editor.subsystems import EditorSubsystems

        logger.info(f"Initializing from path: {project_path}")
        self._subsystems = EditorSubsystems.create(project_path)
        return self._subsystems

    def cleanup(self) -> None:
        """Clean up resources.

        Called during server shutdown to properly clean up the subsystems.
        """
        if self._subsystems is not None:
            try:
                self._subsystems.cleanup()
                logger.info("EditorSubsystems cleanup completed")
            except Exception as e:
                logger.error(f"Error during EditorSubsystems cleanup: {e}")


# Global singleton instance
server_state = ServerState()
