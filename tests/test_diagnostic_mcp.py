"""
Asset Diagnostic Tool Integration Tests using mcp-pytest fixtures.

Tests the editor_asset_diagnostic tool via the mcp-pytest plugin.
Requires a UE5 project with valid assets to diagnose.

Usage:
    pytest tests/test_diagnostic_mcp.py -v -s

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
class TestDiagnosticTools:
    """Integration tests for diagnostic tools."""

    @pytest.mark.asyncio
    async def test_list_tools_includes_diagnostic(self, tool_caller: ToolCaller):
        """Test that diagnostic tool is listed."""
        tools = await tool_caller.list_tools()

        # Check diagnostic tool is present
        assert "editor_asset_diagnostic" in tools

    @pytest.mark.asyncio
    async def test_diagnostic_with_editor(self, running_editor: ToolCaller):
        """Test diagnostic with editor running."""
        # Editor is already running via running_editor fixture
        # Test diagnostics on a level
        result = await running_editor.call(
            "editor_asset_diagnostic",
            {"asset_path": "/Game/ThirdPerson/DefaultAutomaticTestLevel"},
            timeout=120,
        )

        data = parse_tool_result(result)
        assert data.get("success"), f"Diagnostic failed: {data}"
        assert "asset_path" in data
        assert "asset_type" in data
        assert "errors" in data
        assert "warnings" in data
        assert "issues" in data
        assert isinstance(data["issues"], list)


@pytest.mark.integration
class TestDiagnosticToolValidation:
    """Test input validation for diagnostic tools."""

    @pytest.mark.asyncio
    async def test_diagnostic_missing_asset_path(self, tool_caller: ToolCaller):
        """Test diagnostic with missing asset_path parameter."""
        # Missing required 'asset_path' parameter should cause error
        try:
            result = await tool_caller.call(
                "editor_asset_diagnostic",
                {},  # Empty arguments
                timeout=120,
            )
            data = parse_tool_result(result)
            # If we get here, check for error in result
            assert "error" in data or "raw_text" in data or data.get("success") is False
        except Exception as e:
            # Expected - missing required parameter
            assert "asset_path" in str(e).lower() or "required" in str(e).lower()

    @pytest.mark.asyncio
    async def test_diagnostic_invalid_asset_path(self, initialized_tool_caller: ToolCaller):
        """Test diagnostic with invalid asset path format."""
        # Invalid asset path - should fail gracefully
        result = await initialized_tool_caller.call(
            "editor_asset_diagnostic",
            {"asset_path": "not_a_valid_path"},
            timeout=120,
        )

        data = parse_tool_result(result)
        # Should fail since editor is not running
        assert data.get("success") is False or "error" in data or "raw_text" in data
