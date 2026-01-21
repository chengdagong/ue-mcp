"""
Client-specific MCP Initialization Tests using mcp-pytest fixtures.

Tests:
1. Tool listing functionality
2. project_set_path tool visibility and functionality

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
class TestClientInitialization:
    """Test client initialization and tool visibility."""

    @pytest.mark.asyncio
    async def test_list_tools_returns_expected_tools(self, tool_caller: ToolCaller):
        """Test that expected tools are listed."""
        tools = await tool_caller.list_tools()

        # Check core tools are present
        assert "editor_launch" in tools
        assert "editor_stop" in tools
        assert "editor_status" in tools
        assert "editor_execute" in tools
        assert "editor_configure" in tools
        assert "project_build" in tools

    @pytest.mark.asyncio
    async def test_editor_status_works_without_editor(self, tool_caller: ToolCaller):
        """Test editor.status works even when editor not running."""
        result = await tool_caller.call("editor_status", timeout=30)

        data = parse_tool_result(result)
        # Should return status info even when not running
        assert "status" in data or "project_name" in data

    @pytest.mark.asyncio
    async def test_editor_configure_check(self, tool_caller: ToolCaller):
        """Test editor.configure can check configuration."""
        result = await tool_caller.call(
            "editor_configure",
            {"auto_fix": False},  # Just check, don't fix
            timeout=30,
        )

        data = parse_tool_result(result)
        # Should return configuration check results
        assert "success" in data or "checks" in data


@pytest.mark.integration
class TestSetPathTool:
    """Test project.set_path tool functionality."""

    @pytest.mark.asyncio
    async def test_set_path_tool_visibility(self, tool_caller: ToolCaller):
        """Test that project_set_path tool may or may not be visible."""
        tools = await tool_caller.list_tools()

        # project_set_path visibility depends on client name
        # It should be visible for claude-ai and Automatic-Testing clients
        # The test just verifies the tool listing works
        print(f"Available tools: {sorted(tools)}")
        print(f"project_set_path visible: {'project_set_path' in tools}")

    @pytest.mark.asyncio
    async def test_set_path_with_invalid_path(self, tool_caller: ToolCaller):
        """Test project.set_path with non-existent path."""
        tools = await tool_caller.list_tools()

        if "project_set_path" not in tools:
            pytest.skip("project_set_path tool not visible for this client")

        result = await tool_caller.call(
            "project_set_path",
            {"project_path": "D:\\NonExistentPath\\12345"},
            timeout=30,
        )

        data = parse_tool_result(result)
        # Should fail because path doesn't exist
        assert data.get("success") is False
        assert "does not exist" in data.get("error", "").lower() or "error" in data
