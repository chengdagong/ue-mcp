"""
Tests for Asset Change Tracking functionality.

This module tests the asset change tracking feature that automatically detects
created, modified, and deleted assets during code execution, and runs diagnostics
on Level assets.
"""

import logging

import pytest

logger = logging.getLogger(__name__)


# Test asset paths - use unique paths to avoid conflicts
TEST_LEVEL_CREATE = "/Game/Tests/AssetTrackingTestCreate"
TEST_LEVEL_MODIFY = "/Game/Tests/AssetTrackingTestModify"
TEST_LEVEL_DELETE = "/Game/Tests/AssetTrackingTestDelete"
TEST_LEVEL_DIAGNOSTIC = "/Game/Tests/AssetTrackingTestDiagnostic"
TEST_LEVEL_NO_CHANGE = "/Game/Tests/AssetTrackingTestNoChange"


async def cleanup_test_asset(mcp_client, asset_path: str) -> None:
    """Delete a test asset if it exists.

    For Level assets, this function first switches to a different level
    to avoid deleting the currently loaded level (which causes crashes).

    IMPORTANT: Python object references to UE objects must be explicitly released
    before UE's garbage collection can clean up the old level. Simply switching
    levels is not enough - we must `del` UE object references and call gc.collect()
    BEFORE loading the new level.
    """
    cleanup_code = f'''import unreal
import gc
import time

asset_path = "{asset_path}"

# Check if asset exists
if not unreal.EditorAssetLibrary.does_asset_exist(asset_path):
    print(f"Not found: {{asset_path}}")
else:
    # For our test assets in /Game/Tests/, they are ALL Level assets
    # So we always need to switch away before deletion
    is_level = "/Game/Tests/" in asset_path

    if is_level:
        level_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)

        # Get current level info - extract string data immediately
        current_level_obj = level_subsystem.get_current_level()
        if current_level_obj:
            current_package = current_level_obj.get_outermost()
            current_name = current_package.get_name() if current_package else ""
            # CRITICAL: Release UE object references immediately after extracting string data
            # This allows UE's GC to clean up the level when we load a new one
            del current_package
            del current_level_obj
        else:
            current_name = ""

        # Force Python garbage collection BEFORE loading new level
        gc.collect()

        print(f"Switching to Lvl_ThirdPerson before deleting {{asset_path}}...")
        level_subsystem.load_level("/Game/ThirdPerson/Lvl_ThirdPerson")

        # Wait for level to fully load and stabilize
        time.sleep(0.5)

    # Now safe to delete
    success = unreal.EditorAssetLibrary.delete_asset(asset_path)
    if success:
        print(f"Deleted: {{asset_path}}")
    else:
        print(f"Failed to delete: {{asset_path}}")
'''
    await mcp_client.call_tool("editor_execute_code", {"code": cleanup_code, "timeout": 60})


@pytest.mark.integration
class TestAssetChangeTracking:
    """Tests for asset change tracking functionality."""

    @pytest.mark.asyncio
    async def test_level_creation_detected(self, mcp_client, running_editor):
        """Test that creating a new Level is detected in asset_changes."""
        # Cleanup first
        await cleanup_test_asset(mcp_client, TEST_LEVEL_CREATE)

        # Create a simple level
        create_code = f'''import unreal

level_path = "{TEST_LEVEL_CREATE}"
level_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
level_subsystem.new_level(level_path)
level_subsystem.save_current_level()
print(f"Created: {{level_path}}")
'''
        result = await mcp_client.call_tool(
            "editor_execute_code",
            {"code": create_code, "timeout": 60},
        )

        data = result.structuredContent
        assert data.get("success") is True, f"Code execution failed: {data.get('error')}"

        # Verify asset_changes is present
        assert "asset_changes" in data, f"No asset_changes in result. Keys: {list(data.keys())}"

        changes = data["asset_changes"]
        logger.info(f"Asset changes: {changes}")

        # Verify detection
        assert changes.get("detected") is True, "Expected detected=True"
        assert len(changes.get("created", [])) > 0, "Expected at least one created asset"

        # Verify Level is in created list
        created_levels = [c for c in changes["created"] if c["asset_type"] == "Level"]
        assert len(created_levels) > 0, "Expected Level in created list"
        assert any(TEST_LEVEL_CREATE in c["path"] for c in created_levels), \
            f"Expected {TEST_LEVEL_CREATE} in created levels"

        # Cleanup
        await cleanup_test_asset(mcp_client, TEST_LEVEL_CREATE)

    @pytest.mark.asyncio
    async def test_level_diagnostic_on_creation(self, mcp_client, running_editor):
        """Test that creating a Level with issues triggers diagnostic."""
        # Cleanup first
        await cleanup_test_asset(mcp_client, TEST_LEVEL_DIAGNOSTIC)

        # Create a level with a floating object (should trigger diagnostic warning)
        create_code = f'''import unreal

level_path = "{TEST_LEVEL_DIAGNOSTIC}"
level_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)

# Create new level
level_subsystem.new_level(level_path)

# Add a floor
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

# Add a floating cube (should trigger diagnostic ERROR)
floating = actor_subsystem.spawn_actor_from_class(
    unreal.StaticMeshActor, unreal.Vector(0, 0, 500), unreal.Rotator(0, 0, 0)
)
floating.set_actor_label("FloatingCube")
mesh_comp2 = floating.get_component_by_class(unreal.StaticMeshComponent)
if mesh_comp2:
    cube2 = unreal.load_asset("/Engine/BasicShapes/Cube")
    if cube2:
        mesh_comp2.set_static_mesh(cube2)

# Save
level_subsystem.save_current_level()
print(f"Created level with floating object: {{level_path}}")
'''
        result = await mcp_client.call_tool(
            "editor_execute_code",
            {"code": create_code, "timeout": 60},
        )

        data = result.structuredContent
        assert data.get("success") is True, f"Code execution failed: {data.get('error')}"
        assert "asset_changes" in data, f"No asset_changes in result. Keys: {list(data.keys())}"

        changes = data["asset_changes"]
        logger.info(f"Asset changes with diagnostic: {changes}")

        # Find the Level in created list
        created_levels = [c for c in changes.get("created", []) if c["asset_type"] == "Level"]
        assert len(created_levels) > 0, "Expected Level in created list"

        # Verify diagnostic details
        level_change = created_levels[0]
        assert "details" in level_change, f"Expected details in level change: {level_change}"

        details = level_change["details"]
        logger.info(f"Diagnostic details: {details}")

        # Should have errors (floating object + no PlayerStart)
        assert details.get("errors", 0) > 0, "Expected at least one error in diagnostic"
        assert "issues" in details, "Expected issues in details"

        # Verify floating object is detected
        issues = details["issues"]
        floating_issues = [i for i in issues if "floating" in i.get("message", "").lower()]
        assert len(floating_issues) > 0, f"Expected floating object issue. Issues: {issues}"

        # Cleanup
        await cleanup_test_asset(mcp_client, TEST_LEVEL_DIAGNOSTIC)

    @pytest.mark.asyncio
    async def test_level_modification_detected(self, mcp_client, running_editor):
        """Test that modifying an existing Level is detected."""
        # Cleanup first
        await cleanup_test_asset(mcp_client, TEST_LEVEL_MODIFY)

        # Step 1: Create the level
        create_code = f'''import unreal

level_path = "{TEST_LEVEL_MODIFY}"
level_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
level_subsystem.new_level(level_path)
level_subsystem.save_current_level()
print(f"Created: {{level_path}}")
'''
        create_result = await mcp_client.call_tool(
            "editor_execute_code",
            {"code": create_code, "timeout": 60},
        )
        assert create_result.structuredContent.get("success") is True

        # Step 2: Modify the level (add an actor)
        modify_code = f'''import unreal

level_path = "{TEST_LEVEL_MODIFY}"
level_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)

# Load the level
level_subsystem.load_level(level_path)

# Add an actor
actor = actor_subsystem.spawn_actor_from_class(
    unreal.StaticMeshActor, unreal.Vector(100, 100, 50), unreal.Rotator(0, 0, 0)
)
actor.set_actor_label("AddedActor")

# Save
level_subsystem.save_current_level()
print(f"Modified: {{level_path}}")
'''
        modify_result = await mcp_client.call_tool(
            "editor_execute_code",
            {"code": modify_code, "timeout": 60},
        )

        data = modify_result.structuredContent
        assert data.get("success") is True, f"Code execution failed: {data.get('error')}"
        assert "asset_changes" in data, f"No asset_changes in result. Keys: {list(data.keys())}"

        changes = data["asset_changes"]
        logger.info(f"Modification changes: {changes}")

        # Verify detection
        assert changes.get("detected") is True, "Expected detected=True"

        # Should be in modified list (not created, since it already existed)
        modified_levels = [c for c in changes.get("modified", []) if c["asset_type"] == "Level"]
        assert len(modified_levels) > 0, \
            f"Expected Level in modified list. Changes: {changes}"

        # Cleanup
        await cleanup_test_asset(mcp_client, TEST_LEVEL_MODIFY)

    @pytest.mark.asyncio
    async def test_level_deletion_detected(self, mcp_client, running_editor):
        """Test that deleting a Level is detected."""
        # Cleanup first
        await cleanup_test_asset(mcp_client, TEST_LEVEL_DELETE)

        # Step 1: Create the level first (in a separate call to avoid multi-level diagnostics)
        create_code = f'''import unreal

level_path = "{TEST_LEVEL_DELETE}"
level_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
level_subsystem.new_level(level_path)
level_subsystem.save_current_level()
print(f"Created: {{level_path}}")
'''
        create_result = await mcp_client.call_tool(
            "editor_execute_code",
            {"code": create_code, "timeout": 60},
        )
        assert create_result.structuredContent.get("success") is True

        # Step 2: Switch to a different level (separate call to avoid triggering
        # asset tracking diagnostics on multiple levels simultaneously)
        switch_code = '''import unreal

level_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
# Load the default Lvl_ThirdPerson to safely switch away from test level
level_subsystem.load_level("/Game/ThirdPerson/Lvl_ThirdPerson")
print("Switched to Lvl_ThirdPerson")
'''
        switch_result = await mcp_client.call_tool(
            "editor_execute_code",
            {"code": switch_code, "timeout": 60},
        )
        assert switch_result.structuredContent.get("success") is True

        # Step 3: Delete the level
        delete_code = f'''import unreal

level_path = "{TEST_LEVEL_DELETE}"
if unreal.EditorAssetLibrary.does_asset_exist(level_path):
    unreal.EditorAssetLibrary.delete_asset(level_path)
    print(f"Deleted: {{level_path}}")
else:
    print(f"Not found: {{level_path}}")
'''
        delete_result = await mcp_client.call_tool(
            "editor_execute_code",
            {"code": delete_code, "timeout": 60},
        )

        data = delete_result.structuredContent
        assert data.get("success") is True, f"Code execution failed: {data.get('error')}"
        assert "asset_changes" in data, f"No asset_changes in result. Keys: {list(data.keys())}"

        changes = data["asset_changes"]
        logger.info(f"Deletion changes: {changes}")

        # Verify detection
        assert changes.get("detected") is True, "Expected detected=True"

        # Should be in deleted list
        deleted_levels = [c for c in changes.get("deleted", []) if c["asset_type"] == "Level"]
        assert len(deleted_levels) > 0, \
            f"Expected Level in deleted list. Changes: {changes}"

    @pytest.mark.asyncio
    async def test_no_changes_when_only_reading(self, mcp_client, running_editor):
        """Test that reading without modifying doesn't trigger asset_changes."""
        # First ensure a level exists
        await cleanup_test_asset(mcp_client, TEST_LEVEL_NO_CHANGE)

        setup_code = f'''import unreal

level_path = "{TEST_LEVEL_NO_CHANGE}"
level_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
level_subsystem.new_level(level_path)
level_subsystem.save_current_level()
print(f"Setup: {{level_path}}")
'''
        await mcp_client.call_tool("editor_execute_code", {"code": setup_code, "timeout": 60})

        # Now just check if asset exists (read-only operation)
        read_code = f'''import unreal

level_path = "{TEST_LEVEL_NO_CHANGE}"
exists = unreal.EditorAssetLibrary.does_asset_exist(level_path)
print(f"Exists: {{exists}}")
'''
        read_result = await mcp_client.call_tool(
            "editor_execute_code",
            {"code": read_code, "timeout": 30},
        )

        data = read_result.structuredContent
        assert data.get("success") is True

        # Should either have no asset_changes, or detected=False
        if "asset_changes" in data:
            changes = data["asset_changes"]
            logger.info(f"Changes on read-only: {changes}")
            # If present, should show no changes
            assert changes.get("detected") is False or (
                len(changes.get("created", [])) == 0 and
                len(changes.get("modified", [])) == 0 and
                len(changes.get("deleted", [])) == 0
            ), f"Unexpected changes detected: {changes}"

        # Cleanup
        await cleanup_test_asset(mcp_client, TEST_LEVEL_NO_CHANGE)
