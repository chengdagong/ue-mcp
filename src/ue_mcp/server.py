"""
UE-MCP Server

FastMCP-based MCP server for Unreal Editor interaction.
"""

import logging
import sys
from pathlib import Path
from typing import Any, Optional

from fastmcp import FastMCP

from .editor_manager import EditorManager
from .utils import find_uproject_file

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Global state
_editor_manager: Optional[EditorManager] = None


def _get_editor_manager() -> EditorManager:
    """Get the global EditorManager instance."""
    if _editor_manager is None:
        raise RuntimeError(
            "EditorManager not initialized. "
            "MCP server must be started from a directory containing a UE5 project."
        )
    return _editor_manager


def _initialize_server() -> Optional[EditorManager]:
    """
    Initialize the MCP server by detecting and binding to a UE5 project.

    Returns:
        EditorManager instance if successful, None otherwise
    """
    global _editor_manager

    logger.info("Initializing UE-MCP server...")
    logger.info(f"Working directory: {Path.cwd()}")

    # Auto-detect project
    uproject_path = find_uproject_file()

    if uproject_path is None:
        logger.error(
            "No .uproject file found. "
            "Please run this server from a UE5 project directory."
        )
        return None

    logger.info(f"Detected project: {uproject_path}")

    _editor_manager = EditorManager(uproject_path)
    return _editor_manager


# Initialize server on module load
_initialize_server()

# Create FastMCP instance
mcp = FastMCP(
    name="ue-mcp",
    instructions="""
UE-MCP is an MCP server for interacting with Unreal Editor.

This server is bound to a specific UE5 project (detected from the working directory).
All tools operate on the bound project's editor instance.

Available tools:
- editor.launch: Start the Unreal Editor for the bound project
- editor.status: Get the current editor status
- editor.stop: Stop the running editor
- editor.execute: Execute Python code in the editor
- editor.configure: Check and fix project configuration
""",
)


@mcp.tool(name="editor.launch")
def launch_editor(
    additional_paths: list[str] = [],
    wait_timeout: float = 120.0,
) -> dict[str, Any]:
    """
    Launch Unreal Editor for the bound project.

    This will:
    1. Check and auto-fix project configuration (Python plugin, remote execution)
    2. Start the editor process
    3. Wait for the editor to become ready for remote execution
    4. Establish a connection for executing Python code

    Args:
        additional_paths: Optional list of additional Python paths to add to the editor's sys.path
        wait_timeout: Maximum time in seconds to wait for editor to start (default: 120)

    Returns:
        Launch result with status information
    """
    manager = _get_editor_manager()
    return manager.launch(
        additional_paths=additional_paths if additional_paths else None,
        wait_timeout=wait_timeout,
    )


@mcp.tool(name="editor.status")
def get_editor_status() -> dict[str, Any]:
    """
    Get the current status of the managed Unreal Editor.

    Returns:
        Status dictionary containing:
        - status: "not_running", "starting", "ready", or "stopped"
        - project_name: Name of the bound project
        - project_path: Path to the .uproject file
        - pid: Process ID (if running)
        - started_at: Timestamp when editor was started (if running)
        - connected: Whether remote execution is connected (if running)
    """
    manager = _get_editor_manager()
    return manager.get_status()


@mcp.tool(name="editor.stop")
def stop_editor() -> dict[str, Any]:
    """
    Stop the managed Unreal Editor.

    This will:
    1. Attempt graceful shutdown via unreal.SystemLibrary.quit_editor()
    2. Wait up to 5 seconds for graceful exit
    3. Force terminate if graceful shutdown fails

    Returns:
        Stop result with success status
    """
    manager = _get_editor_manager()
    return manager.stop()


@mcp.tool(name="editor.execute")
def execute_code(code: str, timeout: float = 30.0) -> dict[str, Any]:
    """
    Execute Python code in the managed Unreal Editor.

    The code is executed in the editor's Python environment with access to
    the 'unreal' module and all editor APIs.

    Args:
        code: Python code to execute
        timeout: Execution timeout in seconds (default: 30)

    Returns:
        Execution result containing:
        - success: Whether execution succeeded
        - result: Return value (if any)
        - output: Console output from the code
        - error: Error message (if failed)

    Example:
        execute_code("import unreal; print(unreal.EditorAssetLibrary.list_assets('/Game/'))")
    """
    manager = _get_editor_manager()
    return manager.execute(code, timeout=timeout)


@mcp.tool(name="editor.configure")
def configure_project(
    auto_fix: bool = True,
    additional_paths: list[str] = [],
) -> dict[str, Any]:
    """
    Check and optionally fix project configuration for Python remote execution.

    This checks:
    1. Python plugin enabled in .uproject
    2. Remote execution settings in DefaultEngine.ini
    3. Additional Python paths (if specified)

    Args:
        auto_fix: Whether to automatically fix issues (default: True)
        additional_paths: Optional list of additional Python paths to configure

    Returns:
        Configuration check result with status and details for each check
    """
    from .autoconfig import run_config_check

    manager = _get_editor_manager()
    return run_config_check(
        manager.project_root,
        auto_fix=auto_fix,
        additional_paths=additional_paths if additional_paths else None,
    )


def main():
    """Main entry point for the MCP server."""
    if _editor_manager is None:
        logger.error("Failed to initialize server. Exiting.")
        sys.exit(1)

    logger.info(f"Starting UE-MCP server for project: {_editor_manager.project_name}")
    mcp.run()


if __name__ == "__main__":
    main()
