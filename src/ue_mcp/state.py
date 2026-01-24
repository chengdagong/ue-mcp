"""Global state management for UE-MCP server."""

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .editor_manager import EditorManager

logger = logging.getLogger(__name__)


class ServerState:
    """Centralized state for the MCP server.

    This class manages all global state for the UE-MCP server, including:
    - EditorManager instance
    - Client name (detected from MCP client)
    - Project path initialization status
    """

    def __init__(self) -> None:
        self._editor_manager: Optional["EditorManager"] = None
        self._client_name: Optional[str] = None
        self._project_path_set: bool = False

    @property
    def editor_manager(self) -> Optional["EditorManager"]:
        """Get the EditorManager instance (may be None)."""
        return self._editor_manager

    @editor_manager.setter
    def editor_manager(self, value: Optional["EditorManager"]) -> None:
        """Set the EditorManager instance."""
        self._editor_manager = value

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

    def get_editor_manager(self) -> "EditorManager":
        """Get the EditorManager, raising RuntimeError if not initialized.

        Returns:
            EditorManager instance

        Raises:
            RuntimeError: If EditorManager has not been initialized
        """
        if self._editor_manager is None:
            raise RuntimeError(
                "EditorManager not initialized. "
                "Please call the 'project_set_path' tool first to set the UE5 project directory."
            )
        return self._editor_manager

    def initialize_from_cwd(self) -> Optional["EditorManager"]:
        """Try to initialize EditorManager from current working directory.

        Searches for a .uproject file in the current directory and initializes
        the EditorManager if found.

        Returns:
            EditorManager instance if successful, None otherwise
        """
        from .editor_manager import EditorManager
        from .utils import find_uproject_file

        logger.info("Initializing UE-MCP server...")
        logger.info(f"Working directory: {Path.cwd()}")

        uproject_path = find_uproject_file()
        if uproject_path is None:
            logger.error(
                "No .uproject file found. "
                "Please run this server from a UE5 project directory."
            )
            return None

        logger.info(f"Detected project: {uproject_path}")
        self._editor_manager = EditorManager(uproject_path)
        return self._editor_manager

    def cleanup(self) -> None:
        """Clean up resources.

        Called during server shutdown to properly clean up the EditorManager.
        """
        if self._editor_manager is not None:
            try:
                self._editor_manager._cleanup()
                logger.info("EditorManager cleanup completed")
            except Exception as e:
                logger.error(f"Error during EditorManager cleanup: {e}")


# Global singleton instance
server_state = ServerState()
