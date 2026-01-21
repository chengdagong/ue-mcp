"""
PIE (Play-In-Editor) Tool Integration Tests using mcp-pytest fixtures.

Tests the editor_start_pie and editor_stop_pie tools via the mcp-pytest plugin.
Requires a UE5 project with a valid level.

Usage:
    pytest tests/test_pie_mcp.py -v -s

Note: These tests require UE5 to be installed and will launch the editor.
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
class TestPIEToolsBasic:
    """Basic tests for PIE tools (no editor required)."""

    @pytest.mark.asyncio
    async def test_list_tools_includes_pie(self, tool_caller: ToolCaller):
        """Test that PIE tools are listed."""
        tools = await tool_caller.list_tools()

        # Check PIE tools are present
        assert "editor_start_pie" in tools
        assert "editor_stop_pie" in tools

    @pytest.mark.asyncio
    async def test_start_pie_without_editor(self, initialized_tool_caller: ToolCaller):
        """Test start_pie fails gracefully when editor not running."""
        result = await initialized_tool_caller.call(
            "editor_start_pie",
            {},
            timeout=30,
        )

        data = parse_tool_result(result)
        # Should fail with error about editor not running
        assert data.get("success") is False or "error" in data or "raw_text" in data

    @pytest.mark.asyncio
    async def test_stop_pie_without_editor(self, initialized_tool_caller: ToolCaller):
        """Test stop_pie fails gracefully when editor not running."""
        result = await initialized_tool_caller.call(
            "editor_stop_pie",
            {},
            timeout=30,
        )

        data = parse_tool_result(result)
        # Should fail with error about editor not running
        assert data.get("success") is False or "error" in data or "raw_text" in data


@pytest.mark.integration
class TestPIEToolsWithEditor:
    """Integration tests for PIE tools that require a running editor.

    These tests share a single editor instance to avoid repeated startup/shutdown.
    The editor is launched once at the start and stopped at the end.
    """

    @pytest.fixture(scope="class")
    async def editor_session(self, initialized_tool_caller: ToolCaller):
        """Launch editor once for all tests in this class."""
        # Launch editor
        launch_result = await initialized_tool_caller.call(
            "editor_launch",
            {"wait": True, "wait_timeout": 180},
            timeout=240,
        )
        launch_data = parse_tool_result(launch_result)
        assert launch_data.get("success"), f"Editor launch failed: {launch_data}"

        yield initialized_tool_caller

        # Cleanup: stop editor after all tests
        await initialized_tool_caller.call("editor_stop", timeout=30)

    @pytest.mark.asyncio
    async def test_pie_start_stop_cycle(self, editor_session: ToolCaller):
        """Test basic PIE start and stop."""
        tool_caller = editor_session

        # Start PIE
        start_result = await tool_caller.call(
            "editor_start_pie",
            {},
            timeout=30,
        )
        start_data = parse_tool_result(start_result)
        assert start_data.get("success"), f"PIE start failed: {start_data}"
        assert "message" in start_data
        assert "started" in start_data.get("message", "").lower()

        # Stop PIE
        stop_result = await tool_caller.call(
            "editor_stop_pie",
            {},
            timeout=30,
        )
        stop_data = parse_tool_result(stop_result)
        assert stop_data.get("success"), f"PIE stop failed: {stop_data}"
        assert "message" in stop_data
        assert "stopped" in stop_data.get("message", "").lower()

    @pytest.mark.asyncio
    async def test_pie_double_start(self, editor_session: ToolCaller):
        """Test that starting PIE twice reports already running."""
        tool_caller = editor_session

        # Start PIE first time
        start_result = await tool_caller.call(
            "editor_start_pie",
            {},
            timeout=30,
        )
        start_data = parse_tool_result(start_result)
        assert start_data.get("success"), f"PIE start failed: {start_data}"

        # Try to start PIE again (should fail - already running)
        start_again_result = await tool_caller.call(
            "editor_start_pie",
            {},
            timeout=30,
        )
        start_again_data = parse_tool_result(start_again_result)
        # Should indicate PIE is already running
        assert start_again_data.get("success") is False
        assert "already" in start_again_data.get("message", "").lower()

        # Cleanup: stop PIE
        await tool_caller.call("editor_stop_pie", {}, timeout=30)

    @pytest.mark.asyncio
    async def test_pie_double_stop(self, editor_session: ToolCaller):
        """Test that stopping PIE when not running reports not running."""
        tool_caller = editor_session

        # Make sure PIE is not running first
        await tool_caller.call("editor_stop_pie", {}, timeout=30)

        # Try to stop PIE again (should fail - not running)
        stop_result = await tool_caller.call(
            "editor_stop_pie",
            {},
            timeout=30,
        )
        stop_data = parse_tool_result(stop_result)
        # Should indicate PIE is not running
        assert stop_data.get("success") is False
        assert "not running" in stop_data.get("message", "").lower()
