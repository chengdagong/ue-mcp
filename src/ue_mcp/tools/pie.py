"""Play-In-Editor (PIE) control tools."""

from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any

from pydantic import Field

if TYPE_CHECKING:
    from fastmcp import FastMCP

    from ..state import ServerState


def register_tools(mcp: "FastMCP", state: "ServerState") -> None:
    """Register PIE control tools."""

    from ..script_executor import execute_script_from_path

    from ._helpers import parse_json_result

    @mcp.tool(name="editor_start_pie")
    def start_pie() -> dict[str, Any]:
        """
        Start a Play-In-Editor (PIE) session.

        This will request the editor to begin playing the current level in PIE mode.
        If PIE is already running, it will return a warning.

        Returns:
            Result containing:
            - success: Whether PIE start was requested successfully
            - message: Status message
            - error: Error message (if failed)
        """
        manager = state.get_editor_manager()

        script_path = (
            Path(__file__).parent.parent / "extra" / "scripts" / "pie_control.py"
        )

        result = execute_script_from_path(
            manager,
            script_path,
            params={"command": "start"},
            timeout=10.0,
        )

        return parse_json_result(result)

    @mcp.tool(name="editor_stop_pie")
    def stop_pie() -> dict[str, Any]:
        """
        Stop the current Play-In-Editor (PIE) session.

        This will request the editor to stop the current PIE session.
        If PIE is not running, it will return a warning.

        Returns:
            Result containing:
            - success: Whether PIE stop was requested successfully
            - message: Status message
            - error: Error message (if failed)
        """
        manager = state.get_editor_manager()

        script_path = (
            Path(__file__).parent.parent / "extra" / "scripts" / "pie_control.py"
        )

        result = execute_script_from_path(
            manager,
            script_path,
            params={"command": "stop"},
            timeout=10.0,
        )

        return parse_json_result(result)

    @mcp.tool(name="editor_load_level")
    def load_level(
        level_path: Annotated[
            str,
            Field(
                description="Path to the level to load (e.g., /Game/Maps/MyLevel)"
            ),
        ],
    ) -> dict[str, Any]:
        """
        Load a level in the editor.

        This uses LevelEditorSubsystem.load_level() to open a level in the editor.

        Args:
            level_path: Path to the level to load (must start with /Game/)

        Returns:
            Result containing:
            - success: Whether level was loaded successfully
            - message: Status message
            - level_path: The level path that was loaded
            - error: Error message (if failed)
        """
        manager = state.get_editor_manager()

        script_path = (
            Path(__file__).parent.parent / "extra" / "scripts" / "level_load.py"
        )

        result = execute_script_from_path(
            manager,
            script_path,
            params={"level_path": level_path},
            timeout=30.0,
        )

        return parse_json_result(result)
