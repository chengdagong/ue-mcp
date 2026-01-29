"""Play-In-Editor (PIE) control tools."""

from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any

from pydantic import Field

if TYPE_CHECKING:
    from fastmcp import FastMCP

    from ..state import ServerState


def register_tools(mcp: "FastMCP", state: "ServerState") -> None:
    """Register PIE control tools."""

    from ..core.paths import get_scripts_dir

    from ._helpers import parse_json_result

    @mcp.tool(name="editor_start_pie")
    async def start_pie() -> dict[str, Any]:
        """
        Start a Play-In-Editor (PIE) session.

        This will request the editor to begin playing the current level in PIE mode.
        If PIE is already running, it will return a warning.

        If the editor is not running, it will be automatically launched.

        Returns:
            Result containing:
            - success: Whether PIE start was requested successfully
            - message: Status message
            - error: Error message (if failed)
        """
        execution = state.get_execution_subsystem()

        script_path = get_scripts_dir() / "pie_control.py"

        result = await execution.execute_script(
            str(script_path),
            params={"command": "start"},
            timeout=10.0,
        )

        return parse_json_result(result)

    @mcp.tool(name="editor_stop_pie")
    async def stop_pie() -> dict[str, Any]:
        """
        Stop the current Play-In-Editor (PIE) session.

        This will request the editor to stop the current PIE session.
        If PIE is not running, it will return a warning.

        If the editor is not running, it will be automatically launched.

        Returns:
            Result containing:
            - success: Whether PIE stop was requested successfully
            - message: Status message
            - error: Error message (if failed)
        """
        execution = state.get_execution_subsystem()

        script_path = get_scripts_dir() / "pie_control.py"

        result = await execution.execute_script(
            str(script_path),
            params={"command": "stop"},
            timeout=10.0,
        )

        return parse_json_result(result)
