"""
Python API Search Tool Tests.

Tests the python_api_search MCP tool and its helper functions.

Usage:
    pytest tests/test_api_search.py -v -s

Note: Integration tests require UE5 to be installed and will launch the editor.
"""

import json
from typing import Any

import pytest

from mcp_pytest import ToolCaller, ToolCallResult

from ue_mcp.server import _parse_json_result


def parse_tool_result(result: ToolCallResult) -> dict[str, Any]:
    """Parse tool result text content as JSON."""
    text = result.text_content
    if not text:
        return {"is_error": result.is_error, "content": str(result.result.content)}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"raw_text": text}


class TestParseJsonResult:
    """Unit tests for _parse_json_result function."""

    def test_parse_successful_result(self):
        """Parse successful execution result with pure JSON output."""
        exec_result = {
            "success": True,
            "output": [
                {"type": "Info", "output": json.dumps({
                    "success": True,
                    "results": [{"name": "Actor", "type": "class"}],
                    "count": 1
                })}
            ]
        }
        result = _parse_json_result(exec_result)

        assert result["success"] is True
        assert len(result["results"]) == 1
        assert result["results"][0]["name"] == "Actor"

    def test_parse_failed_execution(self):
        """Parse failed execution result."""
        exec_result = {
            "success": False,
            "error": "Editor not connected"
        }
        result = _parse_json_result(exec_result)

        assert result["success"] is False
        assert "error" in result

    def test_parse_no_json_in_output(self):
        """Parse result without valid JSON in output."""
        exec_result = {
            "success": True,
            "output": [{"type": "Info", "output": "Some other output"}]
        }
        result = _parse_json_result(exec_result)

        assert result["success"] is False
        assert "No valid JSON found" in result["error"]

    def test_parse_invalid_json(self):
        """Parse result with invalid JSON."""
        exec_result = {
            "success": True,
            "output": [{"type": "Info", "output": "{invalid json}"}]
        }
        result = _parse_json_result(exec_result)

        assert result["success"] is False
        assert "No valid JSON found" in result["error"]

    def test_parse_string_output(self):
        """Parse when output entry is a dict with 'output' key."""
        json_data = json.dumps({"success": True, "results": [], "count": 0})
        exec_result = {
            "success": True,
            "output": [{"type": "Info", "output": json_data}]
        }
        result = _parse_json_result(exec_result)

        assert result["success"] is True
        assert result["count"] == 0

    def test_parse_multiline_output(self):
        """Parse result with multiple output lines, JSON is last valid one."""
        json_data = json.dumps({
            "success": True,
            "class_name": "Actor",
            "properties": [],
            "methods": []
        })
        exec_result = {
            "success": True,
            "output": [
                {"type": "Info", "output": "Loading module...\n"},
                {"type": "Info", "output": json_data + "\n"},
                {"type": "Info", "output": "Done\n"}
            ]
        }
        result = _parse_json_result(exec_result)

        assert result["success"] is True
        assert result["class_name"] == "Actor"


@pytest.mark.integration
class TestApiSearchValidation:
    """Test input validation for python_api_search tool."""

    @pytest.mark.asyncio
    async def test_invalid_mode(self, tool_caller: ToolCaller):
        """Test with invalid mode parameter."""
        result = await tool_caller.call(
            "python_api_search",
            {"mode": "invalid_mode"},
            timeout=30,
        )
        data = parse_tool_result(result)

        assert data.get("success") is False
        assert "Invalid mode" in data.get("error", "")

    @pytest.mark.asyncio
    async def test_class_info_missing_query(self, tool_caller: ToolCaller):
        """Test class_info mode without required query."""
        result = await tool_caller.call(
            "python_api_search",
            {"mode": "class_info"},
            timeout=30,
        )
        data = parse_tool_result(result)

        assert data.get("success") is False
        assert "query parameter required" in data.get("error", "")

    @pytest.mark.asyncio
    async def test_member_info_missing_query(self, tool_caller: ToolCaller):
        """Test member_info mode without required query."""
        result = await tool_caller.call(
            "python_api_search",
            {"mode": "member_info"},
            timeout=30,
        )
        data = parse_tool_result(result)

        assert data.get("success") is False
        assert "query parameter required" in data.get("error", "")

    @pytest.mark.asyncio
    async def test_search_missing_query(self, tool_caller: ToolCaller):
        """Test search mode without required query."""
        result = await tool_caller.call(
            "python_api_search",
            {"mode": "search"},
            timeout=30,
        )
        data = parse_tool_result(result)

        assert data.get("success") is False
        assert "query parameter required" in data.get("error", "")


@pytest.mark.integration
class TestApiSearchListClasses:
    """Integration tests for list_classes mode."""

    @pytest.mark.asyncio
    async def test_list_all_classes(self, running_editor: ToolCaller):
        """Test listing all classes without pattern."""
        result = await running_editor.call(
            "python_api_search",
            {"mode": "list_classes", "limit": 10},
            timeout=60,
        )
        data = parse_tool_result(result)

        assert data.get("success") is True
        assert "results" in data
        assert len(data["results"]) <= 10
        assert data["count"] > 0
        # All results should be classes
        for item in data["results"]:
            assert item["type"] == "class"

    @pytest.mark.asyncio
    async def test_list_classes_with_pattern(self, running_editor: ToolCaller):
        """Test listing classes with wildcard pattern."""
        result = await running_editor.call(
            "python_api_search",
            {"mode": "list_classes", "query": "*Actor*", "limit": 10},
            timeout=60,
        )
        data = parse_tool_result(result)

        assert data.get("success") is True
        assert data.get("pattern") == "*Actor*"
        # All results should contain "Actor"
        for item in data["results"]:
            assert "Actor" in item["name"]

    @pytest.mark.asyncio
    async def test_list_classes_prefix_pattern(self, running_editor: ToolCaller):
        """Test listing classes with prefix pattern."""
        result = await running_editor.call(
            "python_api_search",
            {"mode": "list_classes", "query": "Static*", "limit": 10},
            timeout=60,
        )
        data = parse_tool_result(result)

        assert data.get("success") is True
        for item in data["results"]:
            assert item["name"].startswith("Static")


@pytest.mark.integration
class TestApiSearchListFunctions:
    """Integration tests for list_functions mode."""

    @pytest.mark.asyncio
    async def test_list_module_functions(self, running_editor: ToolCaller):
        """Test listing module-level functions."""
        result = await running_editor.call(
            "python_api_search",
            {"mode": "list_functions", "limit": 10},
            timeout=60,
        )
        data = parse_tool_result(result)

        assert data.get("success") is True
        assert data.get("scope") == "module"
        for item in data["results"]:
            assert item["type"] == "function"

    @pytest.mark.asyncio
    async def test_list_class_methods(self, running_editor: ToolCaller):
        """Test listing all methods of a class."""
        result = await running_editor.call(
            "python_api_search",
            {"mode": "list_functions", "query": "Actor.*", "limit": 10},
            timeout=60,
        )
        data = parse_tool_result(result)

        assert data.get("success") is True
        assert data.get("scope") == "class"
        assert data.get("class_pattern") == "Actor"
        for item in data["results"]:
            assert item["type"] == "method"
            assert item["name"].startswith("Actor.")

    @pytest.mark.asyncio
    async def test_list_class_methods_with_pattern(self, running_editor: ToolCaller):
        """Test listing methods matching a pattern."""
        result = await running_editor.call(
            "python_api_search",
            {"mode": "list_functions", "query": "Actor.*location*", "limit": 10},
            timeout=60,
        )
        data = parse_tool_result(result)

        assert data.get("success") is True
        for item in data["results"]:
            assert "location" in item["name"].lower()

    @pytest.mark.asyncio
    async def test_list_functions_nonexistent_class(self, running_editor: ToolCaller):
        """Test listing methods of non-existent class."""
        result = await running_editor.call(
            "python_api_search",
            {"mode": "list_functions", "query": "NonExistentClass.*"},
            timeout=60,
        )
        data = parse_tool_result(result)

        assert data.get("success") is False
        assert "not found" in data.get("error", "")


@pytest.mark.integration
class TestApiSearchClassInfo:
    """Integration tests for class_info mode."""

    @pytest.mark.asyncio
    async def test_class_info_actor(self, running_editor: ToolCaller):
        """Test getting Actor class information."""
        result = await running_editor.call(
            "python_api_search",
            {"mode": "class_info", "query": "Actor", "limit": 10},
            timeout=60,
        )
        data = parse_tool_result(result)

        assert data.get("success") is True
        assert data.get("class_name") == "Actor"
        assert "base_classes" in data
        assert "docstring" in data
        assert "properties" in data
        assert "methods" in data
        assert data.get("property_count", 0) > 0
        assert data.get("method_count", 0) > 0

    @pytest.mark.asyncio
    async def test_class_info_with_inherited(self, running_editor: ToolCaller):
        """Test class info with inherited members tracking."""
        result = await running_editor.call(
            "python_api_search",
            {"mode": "class_info", "query": "Actor", "include_inherited": True},
            timeout=60,
        )
        data = parse_tool_result(result)

        assert data.get("success") is True
        assert "inherited_from" in data

    @pytest.mark.asyncio
    async def test_class_info_nonexistent(self, running_editor: ToolCaller):
        """Test class info for non-existent class."""
        result = await running_editor.call(
            "python_api_search",
            {"mode": "class_info", "query": "NonExistentClass"},
            timeout=60,
        )
        data = parse_tool_result(result)

        assert data.get("success") is False
        assert "not found" in data.get("error", "")


@pytest.mark.integration
class TestApiSearchMemberInfo:
    """Integration tests for member_info mode."""

    @pytest.mark.asyncio
    async def test_member_info_class(self, running_editor: ToolCaller):
        """Test getting info for a class."""
        result = await running_editor.call(
            "python_api_search",
            {"mode": "member_info", "query": "Actor"},
            timeout=60,
        )
        data = parse_tool_result(result)

        assert data.get("success") is True
        assert data.get("member_name") == "Actor"
        assert data.get("member_type") == "class"

    @pytest.mark.asyncio
    async def test_member_info_method(self, running_editor: ToolCaller):
        """Test getting info for a class method."""
        result = await running_editor.call(
            "python_api_search",
            {"mode": "member_info", "query": "Actor.get_actor_location"},
            timeout=60,
        )
        data = parse_tool_result(result)

        assert data.get("success") is True
        assert data.get("member_name") == "get_actor_location"
        assert data.get("member_type") == "method"
        assert "signature" in data

    @pytest.mark.asyncio
    async def test_member_info_property(self, running_editor: ToolCaller):
        """Test getting info for a class property."""
        result = await running_editor.call(
            "python_api_search",
            {"mode": "member_info", "query": "Actor.root_component"},
            timeout=60,
        )
        data = parse_tool_result(result)

        assert data.get("success") is True
        assert data.get("member_name") == "root_component"
        assert data.get("member_type") == "property"

    @pytest.mark.asyncio
    async def test_member_info_nonexistent_member(self, running_editor: ToolCaller):
        """Test member info for non-existent member."""
        result = await running_editor.call(
            "python_api_search",
            {"mode": "member_info", "query": "Actor.nonexistent_method"},
            timeout=60,
        )
        data = parse_tool_result(result)

        assert data.get("success") is False
        assert "not found" in data.get("error", "")


@pytest.mark.integration
class TestApiSearchSearch:
    """Integration tests for search mode."""

    @pytest.mark.asyncio
    async def test_search_spawn(self, running_editor: ToolCaller):
        """Test searching for 'spawn' related APIs."""
        result = await running_editor.call(
            "python_api_search",
            {"mode": "search", "query": "spawn", "limit": 10},
            timeout=60,
        )
        data = parse_tool_result(result)

        assert data.get("success") is True
        assert "results" in data
        assert data["count"] > 0
        # Results should contain 'spawn' in name
        for item in data["results"]:
            assert "spawn" in item["name"].lower()

    @pytest.mark.asyncio
    async def test_search_actor(self, running_editor: ToolCaller):
        """Test searching for 'actor' related APIs."""
        result = await running_editor.call(
            "python_api_search",
            {"mode": "search", "query": "actor", "limit": 10},
            timeout=60,
        )
        data = parse_tool_result(result)

        assert data.get("success") is True
        assert data["count"] > 0


@pytest.mark.integration
class TestApiSearchToolListed:
    """Test that python_api_search tool is properly registered."""

    @pytest.mark.asyncio
    async def test_tool_is_listed(self, tool_caller: ToolCaller):
        """Test that python_api_search tool is in the tool list."""
        tools = await tool_caller.list_tools()
        assert "python_api_search" in tools
