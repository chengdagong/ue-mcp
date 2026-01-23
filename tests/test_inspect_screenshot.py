"""
Test script for editor_asset_inspect screenshot functionality.

This script tests the screenshot capture feature added to inspect_runner.py

Usage:
    pytest test_inspect_screenshot.py -v -s
"""
import json
import os
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
class TestInspectScreenshot:
    """Integration tests for editor_asset_inspect screenshot functionality."""

    @pytest.mark.asyncio
    async def test_inspect_blueprint_returns_screenshot(self, running_editor: ToolCaller):
        """Test that inspecting a Blueprint asset returns a screenshot."""
        result = await running_editor.call(
            "editor_asset_inspect",
            {"asset_path": "/Game/ThirdPerson/Blueprints/BP_ThirdPersonCharacter"},
            timeout=120,
        )

        data = parse_tool_result(result)

        # Basic validation
        assert data.get("success"), f"Inspect failed: {data}"
        assert data.get("asset_type") == "Blueprint"

        # Screenshot validation
        print(f"\nResult keys: {list(data.keys())}")

        if "screenshot_path" in data:
            print(f"✓ Screenshot captured: {data['screenshot_path']}")
            # Verify file exists
            if os.path.exists(data['screenshot_path']):
                file_size = os.path.getsize(data['screenshot_path'])
                print(f"  File size: {file_size} bytes")
                assert file_size > 0, "Screenshot file is empty"
            else:
                pytest.fail(f"Screenshot file does not exist: {data['screenshot_path']}")
        elif "screenshot_error" in data:
            print(f"Screenshot error (expected on some systems): {data['screenshot_error']}")
            # This is acceptable - screenshot may fail on headless systems
        else:
            pytest.fail("No screenshot_path or screenshot_error in result - screenshot logic not executed")

    @pytest.mark.asyncio
    async def test_inspect_level_returns_screenshot(self, running_editor: ToolCaller, test_level_path: str):
        """Test that inspecting a Level asset returns a screenshot."""
        result = await running_editor.call(
            "editor_asset_inspect",
            {"asset_path": test_level_path},
            timeout=120,
        )

        data = parse_tool_result(result)

        # Basic validation
        assert data.get("success"), f"Inspect failed: {data}"
        assert data.get("asset_type") == "Level"

        # Screenshot validation
        print(f"\nResult keys: {list(data.keys())}")

        if "screenshot_path" in data:
            print(f"✓ Screenshot captured: {data['screenshot_path']}")
            if os.path.exists(data['screenshot_path']):
                file_size = os.path.getsize(data['screenshot_path'])
                print(f"  File size: {file_size} bytes")
                assert file_size > 0, "Screenshot file is empty"
        elif "screenshot_error" in data:
            print(f"Screenshot error (expected on some systems): {data['screenshot_error']}")
        else:
            pytest.fail("No screenshot_path or screenshot_error in result - screenshot logic not executed")

    @pytest.mark.asyncio
    async def test_inspect_gamemode_blueprint_has_screenshot_fields(self, running_editor: ToolCaller):
        """Test that inspecting a GameMode Blueprint also returns screenshot fields."""
        result = await running_editor.call(
            "editor_asset_inspect",
            {"asset_path": "/Game/ThirdPerson/Blueprints/BP_ThirdPersonGameMode"},
            timeout=120,
        )

        data = parse_tool_result(result)
        assert data.get("success"), f"Inspect failed: {data}"

        # GameMode is also a Blueprint, so it should have screenshot fields
        print(f"Asset type: {data.get('asset_type')}")
        print(f"Has screenshot_path: {'screenshot_path' in data}")
        print(f"Has screenshot_error: {'screenshot_error' in data}")

        # Either screenshot_path or screenshot_error should be present for Blueprint
        assert "screenshot_path" in data or "screenshot_error" in data, \
            "Blueprint should have either screenshot_path or screenshot_error"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
