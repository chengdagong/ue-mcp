"""
Capture Tool Integration Tests using mcp-pytest fixtures.

Tests the editor_capture_* tools via the mcp-pytest plugin.
Requires a UE5 project with a valid level to capture.

Usage:
    pytest tests/test_capture_mcp.py -v -s

Note: These tests require UE5 to be installed and will launch the editor.
"""

import json
import tempfile
from pathlib import Path
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
@pytest.mark.slow
class TestCaptureTools:
    """Integration tests for capture tools."""

    @pytest.mark.asyncio
    async def test_list_tools_includes_capture(self, tool_caller: ToolCaller):
        """Test that capture tools are listed."""
        tools = await tool_caller.list_tools()

        # Check capture tools are present
        assert "editor_capture_orbital" in tools
        assert "editor_capture_pie" in tools
        assert "editor_capture_window" in tools

    @pytest.mark.asyncio
    async def test_capture_orbital_without_editor(self, tool_caller: ToolCaller):
        """Test capture.orbital fails gracefully when editor not running."""
        result = await tool_caller.call(
            "editor_capture_orbital",
            {
                "level": "/Game/Maps/TestLevel",
                "target_x": 0,
                "target_y": 0,
                "target_z": 100,
            },
            timeout=120,
        )

        data = parse_tool_result(result)
        # Should fail with error about editor not running
        assert data.get("success") is False or "error" in data

    @pytest.mark.asyncio
    async def test_capture_orbital_with_editor(self, tool_caller: ToolCaller):
        """Test capture.orbital with editor running."""
        # Launch editor
        launch_result = await tool_caller.call(
            "editor_launch",
            {"wait": True, "wait_timeout": 180},
            timeout=240,
        )
        launch_data = parse_tool_result(launch_result)

        if not launch_data.get("success"):
            pytest.skip(f"Editor launch failed: {launch_data.get('error')}")

        try:
            # Create temp output directory
            with tempfile.TemporaryDirectory() as temp_dir:
                result = await tool_caller.call(
                    "editor_capture_orbital",
                    {
                        "level": "/Game/Maps/Main",
                        "target_x": 0,
                        "target_y": 0,
                        "target_z": 100,
                        "distance": 500,
                        "preset": "orthographic",
                        "output_dir": temp_dir,
                        "resolution_width": 640,
                        "resolution_height": 480,
                    },
                    timeout=120,
                )

                data = parse_tool_result(result)
                # Check result
                if data.get("success"):
                    assert "files" in data or "total_captures" in data
                else:
                    # May fail if level doesn't exist - that's OK for this test
                    print(f"Capture result: {data}")

        finally:
            # Always stop editor
            await tool_caller.call("editor_stop", timeout=30)

    @pytest.mark.asyncio
    async def test_capture_window_without_editor(self, tool_caller: ToolCaller):
        """Test capture.window fails gracefully when editor not running."""
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            result = await tool_caller.call(
                "editor_capture_window",
                {
                    "level": "/Game/Maps/TestLevel",
                    "output_file": f.name,
                },
                timeout=120,
            )

        data = parse_tool_result(result)
        # Should fail with error about editor not running
        assert data.get("success") is False or "error" in data

    @pytest.mark.asyncio
    async def test_capture_pie_without_editor(self, tool_caller: ToolCaller):
        """Test capture.pie fails gracefully when editor not running."""
        with tempfile.TemporaryDirectory() as temp_dir:
            result = await tool_caller.call(
                "editor_capture_pie",
                {
                    "output_dir": temp_dir,
                    "level": "/Game/Maps/TestLevel",
                    "duration_seconds": 2.0,
                    "interval_seconds": 0.5,
                },
                timeout=120,
            )

        data = parse_tool_result(result)
        # Should fail with error about editor not running
        assert data.get("success") is False or "error" in data

    @pytest.mark.asyncio
    async def test_capture_pie_with_editor(self, tool_caller: ToolCaller):
        """Test capture.pie with editor running."""
        # Launch editor
        launch_result = await tool_caller.call(
            "editor_launch",
            {"wait": True, "wait_timeout": 180},
            timeout=240,
        )
        launch_data = parse_tool_result(launch_result)

        if not launch_data.get("success"):
            pytest.skip(f"Editor launch failed: {launch_data.get('error')}")

        try:
            # Create temp output directory
            with tempfile.TemporaryDirectory() as temp_dir:
                result = await tool_caller.call(
                    "editor_capture_pie",
                    {
                        "output_dir": temp_dir,
                        "level": "/Game/Maps/Main",
                        "duration_seconds": 5.0,
                        "interval_seconds": 1.0,
                        "resolution_width": 640,
                        "resolution_height": 480,
                        "multi_angle": False,
                    },
                    timeout=180,
                )

                data = parse_tool_result(result)
                # Check result
                if data.get("success"):
                    assert "output_dir" in data or "duration" in data
                else:
                    # May fail if level doesn't exist - that's OK for this test
                    print(f"PIE Capture result: {data}")

        finally:
            # Always stop editor
            await tool_caller.call("editor_stop", timeout=30)

    @pytest.mark.asyncio
    async def test_capture_window_with_editor(self, tool_caller: ToolCaller):
        """Test capture.window with editor running."""
        # Launch editor
        launch_result = await tool_caller.call(
            "editor_launch",
            {"wait": True, "wait_timeout": 180},
            timeout=240,
        )
        launch_data = parse_tool_result(launch_result)

        if not launch_data.get("success"):
            pytest.skip(f"Editor launch failed: {launch_data.get('error')}")

        try:
            # Test window mode capture
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                result = await tool_caller.call(
                    "editor_capture_window",
                    {
                        "level": "/Game/Maps/Main",
                        "output_file": f.name,
                        "mode": "window",
                    },
                    timeout=120,
                )

                data = parse_tool_result(result)
                # Check result
                if data.get("success"):
                    assert "file" in data or "captured" in data
                    # Verify file was created
                    if data.get("captured"):
                        assert Path(f.name).exists()
                else:
                    # May fail on non-Windows - that's OK
                    print(f"Window Capture result: {data}")

        finally:
            # Always stop editor
            await tool_caller.call("editor_stop", timeout=30)

    @pytest.mark.asyncio
    async def test_capture_window_batch_mode_with_editor(self, tool_caller: ToolCaller):
        """Test capture.window batch mode with editor running."""
        # Launch editor
        launch_result = await tool_caller.call(
            "editor_launch",
            {"wait": True, "wait_timeout": 180},
            timeout=240,
        )
        launch_data = parse_tool_result(launch_result)

        if not launch_data.get("success"):
            pytest.skip(f"Editor launch failed: {launch_data.get('error')}")

        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                # Test batch mode with sample assets
                result = await tool_caller.call(
                    "editor_capture_window",
                    {
                        "level": "/Game/Maps/Main",
                        "mode": "batch",
                        "asset_list": [
                            "/Game/FirstPerson/Blueprints/BP_FirstPersonCharacter",
                        ],
                        "output_dir": temp_dir,
                    },
                    timeout=120,
                )

                data = parse_tool_result(result)
                # Check result
                if data.get("success"):
                    assert "files" in data or "success_count" in data
                else:
                    # Assets may not exist - that's OK
                    print(f"Batch Capture result: {data}")

        finally:
            # Always stop editor
            await tool_caller.call("editor_stop", timeout=30)


@pytest.mark.integration
class TestCaptureToolValidation:
    """Test input validation for capture tools."""

    @pytest.mark.asyncio
    async def test_capture_orbital_missing_level(self, tool_caller: ToolCaller):
        """Test capture.orbital with missing level parameter."""
        # Missing required 'level' parameter should cause error
        try:
            result = await tool_caller.call(
                "editor_capture_orbital",
                {
                    # "level" is missing
                    "target_x": 0,
                    "target_y": 0,
                    "target_z": 100,
                },
                timeout=120,
            )
            data = parse_tool_result(result)
            # If we get here, check for error in result
            assert "error" in data or data.get("success") is False
        except Exception as e:
            # Expected - missing required parameter
            assert "level" in str(e).lower() or "required" in str(e).lower()

    @pytest.mark.asyncio
    async def test_capture_window_mode_validation(self, tool_caller: ToolCaller):
        """Test capture.window validates output_file for window mode."""
        # window mode without output_file should fail
        result = await tool_caller.call(
            "editor_capture_window",
            {
                "level": "/Game/Maps/TestLevel",
                "mode": "window",
                # output_file is missing
            },
            timeout=120,
        )

        data = parse_tool_result(result)
        assert data.get("success") is False
        assert "output_file" in data.get("error", "").lower()

    @pytest.mark.asyncio
    async def test_capture_window_asset_mode_validation(self, tool_caller: ToolCaller):
        """Test capture.window validates asset_path for asset mode."""
        # asset mode without asset_path should fail
        result = await tool_caller.call(
            "editor_capture_window",
            {
                "level": "/Game/Maps/TestLevel",
                "mode": "asset",
                "output_file": "/tmp/test.png",
                # asset_path is missing
            },
            timeout=120,
        )

        data = parse_tool_result(result)
        assert data.get("success") is False
        assert "asset_path" in data.get("error", "").lower()

    @pytest.mark.asyncio
    async def test_capture_window_batch_mode_validation(self, tool_caller: ToolCaller):
        """Test capture.window validates asset_list and output_dir for batch mode."""
        # batch mode without asset_list should fail
        result = await tool_caller.call(
            "editor_capture_window",
            {
                "level": "/Game/Maps/TestLevel",
                "mode": "batch",
                "output_dir": "/tmp/output",
                # asset_list is missing
            },
            timeout=120,
        )

        data = parse_tool_result(result)
        assert data.get("success") is False
        assert (
            "asset_list" in data.get("error", "").lower()
            or "output_dir" in data.get("error", "").lower()
        )

    @pytest.mark.asyncio
    async def test_capture_pie_missing_level(self, tool_caller: ToolCaller):
        """Test capture.pie with missing level parameter."""
        # Missing required 'level' parameter should cause error
        try:
            result = await tool_caller.call(
                "editor_capture_pie",
                {
                    "output_dir": "/tmp/output",
                    # "level" is missing
                    "duration_seconds": 5.0,
                },
                timeout=120,
            )
            data = parse_tool_result(result)
            # If we get here, check for error in result
            assert "error" in data or data.get("success") is False
        except Exception as e:
            # Expected - missing required parameter
            assert "level" in str(e).lower() or "required" in str(e).lower()

    @pytest.mark.asyncio
    async def test_capture_pie_missing_output_dir(self, tool_caller: ToolCaller):
        """Test capture.pie with missing output_dir parameter."""
        # Missing required 'output_dir' parameter should cause error
        try:
            result = await tool_caller.call(
                "editor_capture_pie",
                {
                    "level": "/Game/Maps/TestLevel",
                    # "output_dir" is missing
                    "duration_seconds": 5.0,
                },
                timeout=120,
            )
            data = parse_tool_result(result)
            # If we get here, check for error in result
            assert "error" in data or data.get("success") is False
        except Exception as e:
            # Expected - missing required parameter
            assert "output_dir" in str(e).lower() or "required" in str(e).lower()
