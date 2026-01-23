"""
Client-specific MCP Initialization Tests using mcp-pytest fixtures.

Tests:
1. Tool listing functionality
2. project_set_path tool visibility and functionality
3. Basic tool operations after project initialization

Usage:
    pytest tests/test_client_init.py -v -s
"""

import json
from typing import Any

import pytest

from mcp_pytest import ToolCaller, ToolCallResult


def parse_tool_result(result: ToolCallResult) -> dict[str, Any]:
    """Parse tool result text content as JSON."""
    text = result.text_content
    if not text:
        return {"is_error": result.is_error, "content": str(result.result.content)}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"raw_text": text}


@pytest.mark.integration
class TestToolListing:
    """Test tool listing before project initialization."""

    @pytest.mark.asyncio
    async def test_list_tools_returns_expected_tools(self, tool_caller: ToolCaller):
        """Test that expected tools are listed."""
        tools = await tool_caller.list_tools()

        # Check core tools are present
        assert "editor_launch" in tools
        assert "editor_stop" in tools
        assert "editor_status" in tools
        assert "editor_execute_code" in tools
        assert "editor_execute_script" in tools
        assert "editor_configure" in tools
        assert "project_build" in tools

    @pytest.mark.asyncio
    async def test_set_path_tool_visibility(self, tool_caller: ToolCaller):
        """Test that project_set_path tool is visible for Automatic-Testing client."""
        tools = await tool_caller.list_tools()

        # project_set_path should be visible for Automatic-Testing clients
        assert "project_set_path" in tools, (
            f"project_set_path not found. Available tools: {sorted(tools)}"
        )


@pytest.mark.integration
class TestInitializedClient:
    """Test tools after project initialization.

    These tests use initialized_tool_caller which has already called
    project_set_path with the EmptyProjectTemplate fixture.
    """

    @pytest.mark.asyncio
    async def test_editor_status_works_without_editor(self, initialized_tool_caller: ToolCaller):
        """Test editor.status works even when editor not running."""
        result = await initialized_tool_caller.call("editor_status", timeout=30)

        data = parse_tool_result(result)
        # Should return status info even when not running
        assert "status" in data or "project_name" in data

    @pytest.mark.asyncio
    async def test_editor_configure_check(self, initialized_tool_caller: ToolCaller):
        """Test editor.configure can check configuration."""
        result = await initialized_tool_caller.call(
            "editor_configure",
            {"auto_fix": False},  # Just check, don't fix
            timeout=30,
        )

        data = parse_tool_result(result)
        # Should return configuration check results with plugin and remote execution info
        assert "python_plugin" in data or "remote_execution" in data or "success" in data
