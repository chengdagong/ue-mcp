"""
Tests for editor_trace_actors_in_pie MCP tool.

Run with:
    pytest tests/test_trace_actors_mcp.py -v

For tests requiring editor:
    pytest tests/test_trace_actors_mcp.py -v -k "WithEditor"
"""

import json
import os
from pathlib import Path
from typing import Any

import pytest
from mcp_pytest import ToolCaller, ToolCallResult

# Test project fixture path
FIXTURE_PROJECT = Path(__file__).parent / "fixtures" / "ThirdPersonTemplate"


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
class TestTraceActorsToolsBasic:
    """Basic tests that don't require a running editor."""

    @pytest.mark.asyncio
    async def test_list_tools_includes_trace_actors(self, tool_caller: ToolCaller):
        """Verify trace actors tool is registered."""
        tools = await tool_caller.list_tools()

        assert "editor_trace_actors_in_pie" in tools, \
            f"editor_trace_actors_in_pie not found in tools: {list(tools.keys())}"

    @pytest.mark.asyncio
    async def test_trace_actors_without_editor(self, initialized_tool_caller: ToolCaller):
        """Test trace actors fails gracefully when editor not running."""
        result = await initialized_tool_caller.call(
            "editor_trace_actors_in_pie",
            {
                "output_file": "C:/temp/trace.json",
                "level": "/Game/ThirdPersonMap",
                "actor_names": ["ThirdPersonCharacter"],
                "duration_seconds": 1.0,
            },
            timeout=30,
        )

        data = parse_tool_result(result)

        # Should fail because editor is not running
        assert data.get("success") is False or "error" in data or "raw_text" in data, \
            f"Expected failure without editor: {data}"


@pytest.mark.integration
class TestTraceActorsWithEditor:
    """Tests that require a running editor."""

    @pytest.fixture(scope="class")
    async def editor_session(self, initialized_tool_caller: ToolCaller):
        """Fixture that ensures editor is launched and ready."""
        tool_caller = initialized_tool_caller

        # Set project path
        project_path = str(FIXTURE_PROJECT.resolve())

        if not FIXTURE_PROJECT.exists():
            pytest.skip(f"Test project not found at {project_path}")

        set_result = await tool_caller.call(
            "project_set_path",
            {"project_path": project_path},
            timeout=30,
        )
        set_data = parse_tool_result(set_result)
        assert set_data.get("success"), f"Project set failed: {set_data}"

        # Launch editor
        launch_result = await tool_caller.call(
            "editor_launch",
            {"wait": True, "wait_timeout": 180},
            timeout=200,
        )
        launch_data = parse_tool_result(launch_result)

        # Check if build is needed
        if launch_data.get("requires_build"):
            pytest.skip("Project needs to be built first. Run 'project_build' tool.")

        assert launch_data.get("success"), f"Editor launch failed: {launch_data}"

        yield tool_caller

        # Cleanup: stop editor
        await tool_caller.call("editor_stop", {}, timeout=30)

    @pytest.mark.asyncio
    async def test_trace_single_actor(self, editor_session: ToolCaller):
        """Test tracing a single actor (player character)."""
        import tempfile

        # Create temp output file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            output_file = f.name

        try:
            result = await editor_session.call(
                "editor_trace_actors_in_pie",
                {
                    "output_file": output_file,
                    "level": "/Game/ThirdPerson/Maps/ThirdPersonMap",
                    "actor_names": ["BP_ThirdPersonCharacter"],
                    "duration_seconds": 3.0,
                    "interval_seconds": 0.1,
                },
                timeout=120,
            )

            data = parse_tool_result(result)

            # Check result
            assert data.get("success") is True, f"Trace failed: {data}"
            assert data.get("sample_count", 0) > 0, "No samples collected"
            assert data.get("actor_count", 0) >= 1, "No actors tracked"

            # Verify output file exists and has valid JSON
            assert os.path.exists(output_file), f"Output file not created: {output_file}"

            with open(output_file, 'r', encoding='utf-8') as f:
                trace_data = json.load(f)

            # Verify structure
            assert "actors" in trace_data, "Missing 'actors' key"
            assert "metadata" in trace_data, "Missing 'metadata' key"
            assert trace_data["metadata"]["sample_count"] > 0, "No samples in metadata"

            print(f"\n[OK] Trace completed:")
            print(f"  - Samples: {data.get('sample_count')}")
            print(f"  - Actors: {data.get('actor_count')}")
            print(f"  - Duration: {data.get('duration'):.2f}s")
            print(f"  - Output: {output_file}")

        finally:
            # Cleanup
            if os.path.exists(output_file):
                os.remove(output_file)

    @pytest.mark.asyncio
    async def test_trace_actor_not_found(self, editor_session: ToolCaller):
        """Test tracing with non-existent actor name."""
        import tempfile

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            output_file = f.name

        try:
            result = await editor_session.call(
                "editor_trace_actors_in_pie",
                {
                    "output_file": output_file,
                    "level": "/Game/ThirdPerson/Maps/ThirdPersonMap",
                    "actor_names": ["NonExistentActor_12345"],
                    "duration_seconds": 2.0,
                    "interval_seconds": 0.1,
                },
                timeout=120,
            )

            data = parse_tool_result(result)

            # Should complete but report actor not found
            assert "actors_not_found" in data, "Should report not found actors"
            assert "NonExistentActor_12345" in data.get("actors_not_found", []), \
                "Should list the not-found actor"

            print(f"\n[OK] Actor not found test passed:")
            print(f"  - actors_not_found: {data.get('actors_not_found')}")

        finally:
            if os.path.exists(output_file):
                os.remove(output_file)

    @pytest.mark.asyncio
    async def test_trace_multiple_actors(self, editor_session: ToolCaller):
        """Test tracing multiple actors."""
        import tempfile

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            output_file = f.name

        try:
            result = await editor_session.call(
                "editor_trace_actors_in_pie",
                {
                    "output_file": output_file,
                    "level": "/Game/ThirdPerson/Maps/ThirdPersonMap",
                    "actor_names": [
                        "BP_ThirdPersonCharacter",  # Should exist
                        "Floor",                     # Should exist (static mesh)
                        "NonExistent_Actor",         # Should not exist
                    ],
                    "duration_seconds": 2.0,
                    "interval_seconds": 0.2,
                },
                timeout=120,
            )

            data = parse_tool_result(result)

            print(f"\n[INFO] Multiple actors trace result:")
            print(f"  - actor_count: {data.get('actor_count')}")
            print(f"  - actors_not_found: {data.get('actors_not_found')}")
            print(f"  - sample_count: {data.get('sample_count')}")

            # At least one actor should be found
            assert data.get("actor_count", 0) >= 1, "At least one actor should be tracked"

        finally:
            if os.path.exists(output_file):
                os.remove(output_file)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
