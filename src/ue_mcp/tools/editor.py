"""Editor management tools."""

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any, Optional

from fastmcp import Context
from pydantic import Field

if TYPE_CHECKING:
    from fastmcp import FastMCP

    from ..state import ServerState

logger = logging.getLogger(__name__)


def register_tools(mcp: "FastMCP", state: "ServerState") -> None:
    """Register editor management tools."""

    from ..autoconfig import get_bundled_site_packages, run_config_check
    from ..core.paths import get_scripts_dir

    from ._helpers import parse_json_result, query_project_assets

    @mcp.tool(name="editor_launch")
    async def launch_editor(
        ctx: Context,
        additional_paths: Annotated[
            list[str],
            Field(
                default=[],
                description="Optional list of additional Python paths to add to the editor's sys.path",
            ),
        ],
        wait: Annotated[
            bool,
            Field(
                default=True,
                description="Whether to wait for the editor to connect before returning",
            ),
        ],
        wait_timeout: Annotated[
            float,
            Field(
                default=120.0,
                description="Maximum time in seconds to wait for editor connection",
            ),
        ],
    ) -> dict[str, Any]:
        """
        Launch Unreal Editor for the bound project.

        This will:
        1. Check and auto-fix project configuration (Python plugin, remote execution)
        2. Automatically include bundled Python packages (asset_diagnostic, editor_capture)
        3. Start the editor process
        4. By default, wait for the editor to become ready for remote execution.

        Args:
            additional_paths: Optional list of additional Python paths to add to the editor's sys.path
            wait: Whether to wait for the editor to connect before returning (default: True)
            wait_timeout: Maximum time in seconds to wait for editor connection (default: 120)

        Returns:
            Launch result with status information.
        """
        lifecycle = state.get_editor_lifecycle_subsystem()
        execution = state.get_execution_subsystem()

        # Create notification callback using ctx.log
        async def notify(level: str, message: str) -> None:
            """Send notification to client via MCP log message."""
            await ctx.log(message, level=level)

        # Include bundled site-packages automatically
        all_paths = list(additional_paths) if additional_paths else []
        bundled_path = get_bundled_site_packages()
        if bundled_path.exists():
            bundled_path_str = str(bundled_path.resolve())
            if bundled_path_str not in all_paths:
                all_paths.insert(0, bundled_path_str)
                logger.info(f"Including bundled site-packages: {bundled_path_str}")

        if wait:
            result = await lifecycle.launch(
                notify=notify,
                additional_paths=all_paths if all_paths else None,
                wait_timeout=wait_timeout,
            )
        else:
            result = await lifecycle.launch_async(
                notify=notify,
                additional_paths=all_paths if all_paths else None,
                wait_timeout=wait_timeout,
            )

        # Query project assets if launch was successful
        if result.get("success"):
            assets_result = query_project_assets(execution)
            if assets_result.get("success"):
                result["project_assets"] = assets_result.get("assets", {})
            else:
                # Include error info but don't fail the launch
                result["project_assets_error"] = assets_result.get("error", "Unknown error")

        return result

    @mcp.tool(name="editor_status")
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
            - log_file_path: Path to the editor log file (if launched)
        """
        context = state.get_context()
        return context.get_status()

    @mcp.tool(name="editor_read_log")
    def read_editor_log(
        tail_lines: Annotated[
            Optional[int],
            Field(
                default=None,
                description="If specified, only return the last N lines of the log. Useful for large log files.",
            ),
        ],
    ) -> dict[str, Any]:
        """
        Read the Unreal Editor log file content.

        The log file is created when the editor is launched via editor_launch.
        Each launch creates a unique log file with the project name and timestamp.

        Args:
            tail_lines: If specified, only return the last N lines of the log.
                       Useful for large log files. If not specified, returns entire log.

        Returns:
            Result containing:
            - success: Whether read succeeded
            - log_file_path: Path to the log file
            - content: Log file content (or last N lines if tail_lines specified)
            - file_size: Size of the log file in bytes
            - error: Error message (if failed)
        """
        context = state.get_context()
        return context.read_log(tail_lines=tail_lines)

    @mcp.tool(name="editor_stop")
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
        context = state.get_context()
        health_monitor = state.get_health_monitor()
        return context.stop(health_monitor=health_monitor)

    @mcp.tool(name="editor_configure")
    def configure_project(
        auto_fix: Annotated[
            bool,
            Field(default=True, description="Whether to automatically fix issues"),
        ],
        additional_paths: Annotated[
            list[str],
            Field(
                default=[],
                description="Optional list of additional Python paths to configure",
            ),
        ],
    ) -> dict[str, Any]:
        """
        Check and optionally fix project configuration for Python remote execution.

        This checks:
        1. Python plugin enabled in .uproject
        2. Remote execution settings in DefaultEngine.ini
        3. Additional Python paths (bundled packages are automatically included)

        Bundled packages (asset_diagnostic, editor_capture) are automatically added
        to the editor's Python path.

        Args:
            auto_fix: Whether to automatically fix issues (default: True)
            additional_paths: Optional list of additional Python paths to configure

        Returns:
            Configuration check result with status and details for each check
        """
        context = state.get_context()
        return run_config_check(
            context.project_root,
            auto_fix=auto_fix,
            additional_paths=additional_paths if additional_paths else None,
            include_bundled_packages=True,
        )

    @mcp.tool(name="editor_load_level")
    async def load_level(
        level_path: Annotated[
            str,
            Field(description="Path to the level to load (e.g., /Game/Maps/MyLevel)"),
        ],
    ) -> dict[str, Any]:
        """
        Load a level in the editor.

        This uses LevelEditorSubsystem.load_level() to open a level in the editor.

        If the editor is not running, it will be automatically launched.

        Args:
            level_path: Path to the level to load (must start with /Game/)

        Returns:
            Result containing:
            - success: Whether level was loaded successfully
            - message: Status message
            - level_path: The level path that was loaded
            - error: Error message (if failed)
        """
        execution = state.get_execution_subsystem()

        script_path = get_scripts_dir() / "level_load.py"

        result = await execution.execute_script_with_auto_launch(
            str(script_path),
            params={"level_path": level_path},
            timeout=30.0,
        )

        return parse_json_result(result)
