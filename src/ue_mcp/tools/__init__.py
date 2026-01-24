"""MCP Tools package for UE-MCP server.

This package contains all MCP tool definitions organized by functionality:
- project: Project path and build tools
- editor: Editor lifecycle management tools
- execution: Code and script execution tools
- pie: Play-In-Editor control tools
- capture: Screenshot capture and actor tracing tools
- diagnostic: Asset diagnostic and inspection tools
- api_search: UE5 Python API search tools
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastmcp import FastMCP

    from ..state import ServerState


def register_all_tools(mcp: "FastMCP", state: "ServerState") -> None:
    """Register all MCP tools with the server.

    This function imports and registers tools from all tool modules.
    Tools are registered using decorators inside each module's register_tools()
    function, which are executed when this function is called.

    Args:
        mcp: The FastMCP server instance
        state: The server state for accessing EditorManager and other state
    """
    from . import api_search, capture, diagnostic, editor, execution, pie, project

    # Register tools in logical order
    project.register_tools(mcp, state)
    editor.register_tools(mcp, state)
    execution.register_tools(mcp, state)
    pie.register_tools(mcp, state)
    capture.register_tools(mcp, state)
    diagnostic.register_tools(mcp, state)
    api_search.register_tools(mcp, state)
