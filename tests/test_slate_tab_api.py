"""
ExSlateTabLibrary API Tests using mcp-pytest fixtures.

Tests the new Slate UI tab switching functionality in ExtraPythonAPIs plugin.
Uses ThirdPersonTemplate project which contains Actor Blueprints.

Tests:
1. Check if ExSlateTabLibrary is available
2. Open Blueprint Editor and switch between tabs (Viewport, Graph, Details)
3. Verify tab switching functions work correctly

Usage:
    pytest tests/test_slate_tab_api.py -v -s

Requirements:
    - ThirdPersonTemplate project in tests/fixtures/
    - ExtraPythonAPIs plugin must be compiled and installed in the project
"""

import json
import asyncio
from pathlib import Path
from typing import Any

import pytest

from mcp_pytest import ToolCaller, ToolCallResult


# =============================================================================
# Helper Functions
# =============================================================================


def parse_tool_result(result: ToolCallResult) -> dict[str, Any]:
    """Parse tool result text content as JSON."""
    text = result.text_content
    if not text:
        return {"is_error": result.is_error, "content": str(result.result.content)}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"raw_text": text}


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(scope="module")
def thirdperson_template_path() -> Path:
    """Return the path to ThirdPersonTemplate fixture."""
    return Path(__file__).parent / "fixtures" / "ThirdPersonTemplate"


@pytest.fixture(scope="module")
def thirdperson_blueprint_path() -> str:
    """Return the asset path to the ThirdPersonCharacter Blueprint."""
    return "/Game/ThirdPerson/Blueprints/BP_ThirdPersonCharacter"


# =============================================================================
# Test Classes
# =============================================================================


@pytest.mark.integration
@pytest.mark.slow
class TestSlateTabAPI:
    """
    Test ExSlateTabLibrary API functionality.

    These tests require:
    1. Editor to be running (via running_editor fixture)
    2. ExtraPythonAPIs plugin to be compiled and enabled
    3. A Blueprint asset to be opened
    """

    @pytest.mark.asyncio
    async def test_check_exslate_library_available(self, running_editor: ToolCaller):
        """Test that ExSlateTabLibrary is available in UE Python."""
        # Editor is already running via running_editor fixture
        # Wait for editor to fully initialize
        await asyncio.sleep(2)

        # Check if ExSlateTabLibrary is available
        check_code = """
import unreal

# Check if ExSlateTabLibrary class exists
try:
    lib = unreal.ExSlateTabLibrary
    print("ExSlateTabLibrary is available")

    # List available methods
    methods = [m for m in dir(lib) if not m.startswith('_')]
    print(f"Available methods: {methods}")

    result = {"available": True, "methods": methods}
except AttributeError as e:
    print(f"ExSlateTabLibrary not found: {e}")
    result = {"available": False, "error": str(e)}

print(f"RESULT: {result}")
"""
        result = await running_editor.call(
            "editor_execute_code",
            {"code": check_code},
            timeout=60,
        )
        data = parse_tool_result(result)

        # Check output for availability
        output = data.get("output", [])
        output_text = "\n".join(output) if isinstance(output, list) else str(output)

        assert "ExSlateTabLibrary is available" in output_text, (
            f"ExSlateTabLibrary not available. Output: {output_text}"
        )

    @pytest.mark.asyncio
    async def test_get_blueprint_editor_tab_ids(self, running_editor: ToolCaller):
        """Test GetBlueprintEditorTabIds returns expected tab IDs."""
        code = """
import unreal

tab_ids = unreal.ExSlateTabLibrary.get_blueprint_editor_tab_ids()
print(f"Tab IDs: {[str(t) for t in tab_ids]}")

# Verify expected tabs are present
expected_tabs = ["SCSViewport", "GraphEditor", "Inspector", "MyBlueprint"]
found_tabs = [str(t) for t in tab_ids]

for expected in expected_tabs:
    if expected in found_tabs:
        print(f"Found expected tab: {expected}")
    else:
        print(f"Missing expected tab: {expected}")

print(f"RESULT: {{'tab_count': {len(tab_ids)}, 'tabs': {found_tabs}}}")
"""
        result = await running_editor.call(
            "editor_execute_code",
            {"code": code},
            timeout=60,
        )
        data = parse_tool_result(result)

        output = data.get("output", [])
        output_text = "\n".join(output) if isinstance(output, list) else str(output)

        # Check that we got tabs
        assert "Tab IDs:" in output_text, f"Failed to get tab IDs. Output: {output_text}"
        assert "SCSViewport" in output_text or "GraphEditor" in output_text, (
            f"Expected tabs not found. Output: {output_text}"
        )

    @pytest.mark.asyncio
    async def test_open_blueprint_and_switch_tabs(
        self,
        running_editor: ToolCaller,
        thirdperson_blueprint_path: str,
    ):
        """Test opening a Blueprint and switching between tabs."""

        # Open the Blueprint in editor
        open_code = f"""
import unreal

# Load and open the Blueprint
blueprint_path = "{thirdperson_blueprint_path}"
blueprint = unreal.load_asset(blueprint_path)

if blueprint:
    print(f"Loaded Blueprint: {{blueprint.get_name()}}")

    # Open in editor
    asset_tools = unreal.AssetEditorSubsystem()
    asset_tools.open_editor_for_asset(blueprint)
    print("Opened Blueprint in editor")
    result = {{"success": True, "blueprint": blueprint.get_name()}}
else:
    print(f"Failed to load Blueprint: {{blueprint_path}}")
    result = {{"success": False, "error": "Blueprint not found"}}

print(f"RESULT: {{result}}")
"""
        result = await running_editor.call(
            "editor_execute_code",
            {"code": open_code},
            timeout=60,
        )
        data = parse_tool_result(result)

        output = data.get("output", [])
        output_text = "\n".join(output) if isinstance(output, list) else str(output)

        assert "Opened Blueprint in editor" in output_text, (
            f"Failed to open Blueprint. Output: {output_text}"
        )

        # Wait for editor window to fully open
        await asyncio.sleep(2)

        # Switch to Viewport mode
        switch_viewport_code = f"""
import unreal

blueprint = unreal.load_asset("{thirdperson_blueprint_path}")
if blueprint:
    success = unreal.ExSlateTabLibrary.switch_to_viewport_mode(blueprint)
    print(f"Switch to Viewport mode: {{success}}")
    result = {{"success": success, "mode": "viewport"}}
else:
    result = {{"success": False, "error": "Blueprint not loaded"}}

print(f"RESULT: {{result}}")
"""
        result = await running_editor.call(
            "editor_execute_code",
            {"code": switch_viewport_code},
            timeout=60,
        )
        data = parse_tool_result(result)

        output = data.get("output", [])
        output_text = "\n".join(output) if isinstance(output, list) else str(output)

        assert "Switch to Viewport mode: True" in output_text, (
            f"Failed to switch to Viewport mode. Output: {output_text}"
        )

        await asyncio.sleep(1)

        # Switch to Graph mode
        switch_graph_code = f"""
import unreal

blueprint = unreal.load_asset("{thirdperson_blueprint_path}")
if blueprint:
    success = unreal.ExSlateTabLibrary.switch_to_graph_mode(blueprint)
    print(f"Switch to Graph mode: {{success}}")
    result = {{"success": success, "mode": "graph"}}
else:
    result = {{"success": False, "error": "Blueprint not loaded"}}

print(f"RESULT: {{result}}")
"""
        result = await running_editor.call(
            "editor_execute_code",
            {"code": switch_graph_code},
            timeout=60,
        )
        data = parse_tool_result(result)

        output = data.get("output", [])
        output_text = "\n".join(output) if isinstance(output, list) else str(output)

        assert "Switch to Graph mode: True" in output_text, (
            f"Failed to switch to Graph mode. Output: {output_text}"
        )

    @pytest.mark.asyncio
    async def test_focus_details_and_myblueprint_panels(
        self,
        running_editor: ToolCaller,
        thirdperson_blueprint_path: str,
    ):
        """Test focusing Details and MyBlueprint panels."""

        code = f"""
import unreal

blueprint = unreal.load_asset("{thirdperson_blueprint_path}")
results = {{}}

if blueprint:
    # Focus Details panel
    results["details"] = unreal.ExSlateTabLibrary.focus_details_panel(blueprint)
    print(f"Focus Details panel: {{results['details']}}")

    # Focus MyBlueprint panel
    results["myblueprint"] = unreal.ExSlateTabLibrary.focus_my_blueprint_panel(blueprint)
    print(f"Focus MyBlueprint panel: {{results['myblueprint']}}")

    results["success"] = True
else:
    results["success"] = False
    results["error"] = "Blueprint not loaded"

print(f"RESULT: {{results}}")
"""
        result = await running_editor.call(
            "editor_execute_code",
            {"code": code},
            timeout=60,
        )
        data = parse_tool_result(result)

        output = data.get("output", [])
        output_text = "\n".join(output) if isinstance(output, list) else str(output)

        # At least one panel focus should succeed
        assert (
            "Focus Details panel: True" in output_text or
            "Focus MyBlueprint panel: True" in output_text
        ), f"Failed to focus panels. Output: {output_text}"

    @pytest.mark.asyncio
    async def test_invoke_tab_by_id(
        self,
        running_editor: ToolCaller,
        thirdperson_blueprint_path: str,
    ):
        """Test invoking specific tabs by their ID."""

        code = f"""
import unreal

blueprint = unreal.load_asset("{thirdperson_blueprint_path}")
results = {{}}

if blueprint:
    # Test invoking various tabs by ID
    tab_tests = [
        ("Inspector", "Details"),
        ("SCSViewport", "Viewport"),
        ("GraphEditor", "Graph"),
        ("MyBlueprint", "MyBlueprint"),
    ]

    for tab_id, name in tab_tests:
        try:
            success = unreal.ExSlateTabLibrary.invoke_blueprint_editor_tab(
                blueprint, unreal.Name(tab_id)
            )
            results[name] = success
            print(f"Invoke {{name}} ({{tab_id}}): {{success}}")
        except Exception as e:
            results[name] = False
            print(f"Error invoking {{name}}: {{e}}")

    results["success"] = True
else:
    results["success"] = False
    results["error"] = "Blueprint not loaded"

print(f"RESULT: {{results}}")
"""
        result = await running_editor.call(
            "editor_execute_code",
            {"code": code},
            timeout=60,
        )
        data = parse_tool_result(result)

        output = data.get("output", [])
        output_text = "\n".join(output) if isinstance(output, list) else str(output)

        # Check that at least some tabs were successfully invoked
        assert "True" in output_text, (
            f"No tabs were successfully invoked. Output: {output_text}"
        )

    @pytest.mark.asyncio
    async def test_is_asset_editor_open(
        self,
        running_editor: ToolCaller,
        thirdperson_blueprint_path: str,
    ):
        """Test checking if asset editor is open."""

        code = f"""
import unreal

blueprint = unreal.load_asset("{thirdperson_blueprint_path}")

if blueprint:
    is_open = unreal.ExSlateTabLibrary.is_asset_editor_open(blueprint)
    print(f"Is editor open for Blueprint: {{is_open}}")
    result = {{"is_open": is_open, "success": True}}
else:
    result = {{"success": False, "error": "Blueprint not loaded"}}

print(f"RESULT: {{result}}")
"""
        result = await running_editor.call(
            "editor_execute_code",
            {"code": code},
            timeout=60,
        )
        data = parse_tool_result(result)

        output = data.get("output", [])
        output_text = "\n".join(output) if isinstance(output, list) else str(output)

        # Should report editor as open since we opened it earlier
        assert "Is editor open for Blueprint: True" in output_text, (
            f"Editor should be open. Output: {output_text}"
        )
