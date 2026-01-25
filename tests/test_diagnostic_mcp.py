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
    async def test_diagnostic_with_editor(self, running_editor: ToolCaller, test_level_path: str):
        """Test diagnostic with editor running."""
        # Editor is already running via running_editor fixture
        # Test diagnostics on a level
        result = await running_editor.call(
            "editor_asset_diagnostic",
            {"asset_path": test_level_path},
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


# Path for the lighting test level (no lighting actors)
NO_LIGHTING_LEVEL_PATH = "/Game/Tests/NoLightingTestLevel"


@pytest.mark.integration
class TestLightingDiagnostic:
    """Integration tests for lighting diagnostic checks."""

    @pytest.mark.asyncio
    async def test_diagnostic_detects_missing_lighting(self, running_editor: ToolCaller):
        """
        Test that diagnostic correctly detects missing lighting actors.

        Creates a minimal level without any lighting actors, runs diagnostic,
        and verifies that missing lighting warning is generated.
        """
        import asyncio

        # Step 1: Create a level without lighting actors
        create_level_code = f'''
import json
import unreal

level_path = "{NO_LIGHTING_LEVEL_PATH}"
level_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)

# Delete existing level if present
if unreal.EditorAssetLibrary.does_asset_exist(level_path):
    # Load default map first to avoid issues
    level_subsystem.load_level("/Game/ThirdPerson/Maps/ThirdPersonMap")
    unreal.EditorAssetLibrary.delete_asset(level_path)

# Create new empty level
success = level_subsystem.new_level(level_path)
if not success:
    print(json.dumps({{"success": False, "error": "Failed to create level"}}))
else:
    # Add only a floor and PlayerStart - NO lighting actors
    # Floor
    floor = actor_subsystem.spawn_actor_from_class(
        unreal.StaticMeshActor, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0)
    )
    floor.set_actor_label("Floor")
    floor.set_actor_scale3d(unreal.Vector(100, 100, 1))
    mesh_comp = floor.get_component_by_class(unreal.StaticMeshComponent)
    if mesh_comp:
        cube = unreal.load_asset("/Engine/BasicShapes/Cube")
        if cube:
            mesh_comp.set_static_mesh(cube)

    # PlayerStart
    player_start = actor_subsystem.spawn_actor_from_class(
        unreal.PlayerStart, unreal.Vector(0, 0, 100), unreal.Rotator(0, 0, 0)
    )
    player_start.set_actor_label("PlayerStart")

    # Save level
    level_subsystem.save_current_level()
    print(json.dumps({{"success": True, "level": level_path}}))
'''
        # Execute level creation
        create_result = await running_editor.call(
            "editor_execute_code",
            {"code": create_level_code},
            timeout=120,
        )

        create_data = parse_tool_result(create_result)
        # Parse the JSON from the output
        output = create_data.get("output", "")
        if isinstance(output, str) and "{" in output:
            # Extract JSON from output
            try:
                json_start = output.rfind("{")
                json_end = output.rfind("}") + 1
                level_result = json.loads(output[json_start:json_end])
                assert level_result.get("success"), f"Failed to create test level: {level_result}"
            except json.JSONDecodeError:
                pass  # Continue anyway

        # Wait for level to stabilize after creation
        await asyncio.sleep(2.0)

        # Step 2: Run diagnostic on the level without lighting
        # Note: The level is already loaded after new_level(), and the diagnostic
        # tool will handle loading via _ensure_level_loaded if needed
        diag_result = await running_editor.call(
            "editor_asset_diagnostic",
            {"asset_path": NO_LIGHTING_LEVEL_PATH},
            timeout=120,
        )

        diag_data = parse_tool_result(diag_result)
        assert diag_data.get("success"), f"Diagnostic failed: {diag_data}"

        # Step 3: Verify missing lighting warning is present in the result
        issues = diag_data.get("issues", [])
        lighting_issues = [
            i for i in issues
            if i.get("category") == "Lighting"
        ]

        assert len(lighting_issues) > 0, (
            f"Expected lighting warning but found none. Issues: {issues}"
        )

        # Verify the warning mentions missing actors
        lighting_issue = lighting_issues[0]
        assert lighting_issue.get("severity") == "WARNING", (
            f"Expected WARNING severity, got: {lighting_issue.get('severity')}"
        )
        assert "4 of 4" in lighting_issue.get("message", ""), (
            f"Expected all 4 lighting actors missing, got: {lighting_issue.get('message')}"
        )

        # Verify metadata
        metadata = diag_data.get("metadata", {})
        assert metadata.get("lighting_actors_missing") == 4, (
            f"Expected 4 missing lighting actors, got: {metadata.get('lighting_actors_missing')}"
        )
        assert metadata.get("lighting_actors_found") == 0, (
            f"Expected 0 found lighting actors, got: {metadata.get('lighting_actors_found')}"
        )

    @pytest.mark.asyncio
    async def test_diagnostic_passes_with_full_lighting(
        self, running_editor: ToolCaller, test_level_path: str
    ):
        """
        Test that diagnostic passes without lighting warning when all actors present.

        Uses the auto-generated test level which has all lighting actors.
        """
        # Run diagnostic on the full test level (has all lighting)
        result = await running_editor.call(
            "editor_asset_diagnostic",
            {"asset_path": test_level_path},
            timeout=120,
        )

        data = parse_tool_result(result)
        assert data.get("success"), f"Diagnostic failed: {data}"

        # Verify NO lighting issues (test level has all lighting actors)
        issues = data.get("issues", [])
        lighting_issues = [
            i for i in issues
            if i.get("category") == "Lighting"
        ]

        assert len(lighting_issues) == 0, (
            f"Expected no lighting warnings (test level has full lighting), "
            f"but found: {lighting_issues}"
        )

        # Verify metadata shows all lighting found
        metadata = data.get("metadata", {})
        assert metadata.get("lighting_actors_found") == 4, (
            f"Expected 4 lighting actors found, got: {metadata.get('lighting_actors_found')}"
        )
        assert metadata.get("lighting_actors_missing") == 0, (
            f"Expected 0 missing lighting actors, got: {metadata.get('lighting_actors_missing')}"
        )
