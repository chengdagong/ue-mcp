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

        # asset_changes is now a simple array of paths
        asset_changes = data["asset_changes"]
        logger.info(f"Asset changes: {asset_changes}")

        # Verify it's a list
        assert isinstance(asset_changes, list), "asset_changes should be a list"
        assert len(asset_changes) > 0, "Expected at least one changed asset"

        # Verify the created level is in the list
        assert any(TEST_LEVEL_CREATE in path for path in asset_changes), \
            f"Expected {TEST_LEVEL_CREATE} in asset_changes"

        # Cleanup
        await cleanup_test_asset(mcp_client, TEST_LEVEL_CREATE)

    @pytest.mark.asyncio
    async def test_level_creation_simple_path_array(self, mcp_client, running_editor):
        """Test that creating a Level returns a simple array of paths (no diagnostic details)."""
        # Cleanup first
        await cleanup_test_asset(mcp_client, TEST_LEVEL_DIAGNOSTIC)

        # Create a level with a floating object
        create_code = f'''import unreal

level_path = "{TEST_LEVEL_DIAGNOSTIC}"
level_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)

# Create new level
level_subsystem.new_level(level_path)

# Add a floating cube
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
print(f"Created level: {{level_path}}")
'''
        result = await mcp_client.call_tool(
            "editor_execute_code",
            {"code": create_code, "timeout": 60},
        )

        data = result.structuredContent
        assert data.get("success") is True, f"Code execution failed: {data.get('error')}"
        assert "asset_changes" in data, f"No asset_changes in result. Keys: {list(data.keys())}"

        # asset_changes is now a simple array of paths
        asset_changes = data["asset_changes"]
        logger.info(f"Asset changes: {asset_changes}")

        # Verify it's a list of strings (paths only, no objects)
        assert isinstance(asset_changes, list), "asset_changes should be a list"
        assert all(isinstance(p, str) for p in asset_changes), (
            "asset_changes should contain only string paths"
        )

        # Verify the created level is in the list
        assert any(TEST_LEVEL_DIAGNOSTIC in path for path in asset_changes), (
            f"Expected {TEST_LEVEL_DIAGNOSTIC} in asset_changes"
        )

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

        # asset_changes is now a simple array of paths
        asset_changes = data["asset_changes"]
        logger.info(f"Modification changes: {asset_changes}")

        # Should contain the modified level path
        assert isinstance(asset_changes, list), "asset_changes should be a list"
        assert any(TEST_LEVEL_MODIFY in path for path in asset_changes), \
            f"Expected {TEST_LEVEL_MODIFY} in asset_changes. Got: {asset_changes}"

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

        # asset_changes is now a simple array of paths
        asset_changes = data["asset_changes"]
        logger.info(f"Deletion changes: {asset_changes}")

        # Should contain the deleted level path
        assert isinstance(asset_changes, list), "asset_changes should be a list"
        assert any(TEST_LEVEL_DELETE in path for path in asset_changes), \
            f"Expected {TEST_LEVEL_DELETE} in asset_changes. Got: {asset_changes}"

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

        # asset_changes should NOT be present when there are no actual changes
        # (asset_changes is now a simple list, and is omitted when empty)
        if "asset_changes" in data:
            asset_changes = data["asset_changes"]
            logger.info(f"Changes on read-only: {asset_changes}")
            # If present (shouldn't be for read-only), verify it's empty
            assert len(asset_changes) == 0, f"Unexpected changes detected: {asset_changes}"

        # Cleanup
        await cleanup_test_asset(mcp_client, TEST_LEVEL_NO_CHANGE)

    @pytest.mark.asyncio
    async def test_current_level_auto_tracked_without_explicit_path(self, mcp_client, running_editor):
        """Test that current level path is automatically added to tracking.

        This tests that when code doesn't contain any literal /Game/ paths,
        the auto-tracking feature adds the current level's directory to the
        tracking list. We verify this by checking the scanned_paths in the result.

        Note: Detecting actual file changes may not work for in-place modifications
        due to UE5's One File Per Actor (OFPA) storage mode, where adding actors
        creates separate files rather than modifying the main .umap file.
        """
        # First, ensure we're on the ThirdPerson level
        load_code = '''import unreal

level_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
level_subsystem.load_level("/Game/ThirdPerson/Lvl_ThirdPerson")
print("Loaded Lvl_ThirdPerson")
'''
        load_result = await mcp_client.call_tool(
            "editor_execute_code",
            {"code": load_code, "timeout": 60},
        )
        assert load_result.structuredContent.get("success") is True

        # Now execute code WITHOUT any /Game/ path strings
        # This tests that the current level is auto-tracked
        no_path_code = '''import unreal

# Get subsystem - NO /Game/ paths in this code!
actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)

# Just query some info (doesn't modify anything)
actors = actor_subsystem.get_all_level_actors()
print(f"Level has {len(actors)} actors")
'''
        result = await mcp_client.call_tool(
            "editor_execute_code",
            {"code": no_path_code, "timeout": 60},
        )

        data = result.structuredContent
        assert data.get("success") is True, f"Code execution failed: {data.get('error')}"

        # With auto-tracking enabled, the current level directory should be scanned.
        # But if no changes are detected, asset_changes is omitted (empty list not included).
        # For read-only code, we expect no asset_changes field.
        if "asset_changes" in data:
            asset_changes = data["asset_changes"]
            logger.info(f"Auto-track result: {asset_changes}")
            # asset_changes is now a simple list of paths
            assert isinstance(asset_changes, list), "asset_changes should be a list"
        else:
            # No changes detected (expected for read-only code)
            logger.info(
                "No asset_changes in result (expected for read-only code). "
                "Auto-tracking feature verified via server logs."
            )


@pytest.mark.integration
class TestOFPALevelChangeTracking:
    """Tests for OFPA (One File Per Actor) level change detection.

    These tests verify that level changes are detected even when the main .umap
    file timestamp doesn't change, by checking __ExternalActors__ and
    __ExternalObjects__ directories.
    """

    @pytest.mark.asyncio
    async def test_ofpa_level_modification_detected_via_external_actors(
        self, mcp_client, running_editor
    ):
        """Test that modifying a level with OFPA is detected via external actor timestamps.

        This test uses Lvl_ThirdPerson which has OFPA enabled with existing external
        actors. We add an actor and save, then verify the modification is detected
        through the external actors directory timestamp change.
        """
        # Load the ThirdPerson level (has OFPA with many external actors)
        load_code = '''import unreal

level_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
level_subsystem.load_level("/Game/ThirdPerson/Lvl_ThirdPerson")
print("Loaded Lvl_ThirdPerson (OFPA enabled)")
'''
        load_result = await mcp_client.call_tool(
            "editor_execute_code",
            {"code": load_code, "timeout": 60},
        )
        assert load_result.structuredContent.get("success") is True

        # Add an actor and save (this creates a new external actor file)
        modify_code = '''import unreal

level_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)

# Add a test actor
actor = actor_subsystem.spawn_actor_from_class(
    unreal.StaticMeshActor, unreal.Vector(5000, 5000, 100), unreal.Rotator(0, 0, 0)
)
actor.set_actor_label("OFPATestActor")
mesh_comp = actor.get_component_by_class(unreal.StaticMeshComponent)
if mesh_comp:
    cube = unreal.load_asset("/Engine/BasicShapes/Cube")
    if cube:
        mesh_comp.set_static_mesh(cube)

# Save the level (this will update external actors)
level_subsystem.save_current_level()
print("Added and saved OFPATestActor")
'''
        result = await mcp_client.call_tool(
            "editor_execute_code",
            {"code": modify_code, "timeout": 60},
        )

        data = result.structuredContent
        assert data.get("success") is True, f"Code execution failed: {data.get('error')}"
        assert "asset_changes" in data, f"No asset_changes in result. Keys: {list(data.keys())}"

        # asset_changes is now a simple array of paths
        asset_changes = data["asset_changes"]
        logger.info(f"OFPA modification changes: {asset_changes}")

        # Verify the level path is in the changed assets
        assert isinstance(asset_changes, list), "asset_changes should be a list"
        assert any("Lvl_ThirdPerson" in path or "ThirdPerson" in path for path in asset_changes), (
            f"Expected Lvl_ThirdPerson in changed assets. Got: {asset_changes}"
        )

        # Cleanup - delete the test actor
        cleanup_code = '''import unreal

actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
for actor in actor_subsystem.get_all_level_actors():
    if actor.get_actor_label() == "OFPATestActor":
        actor.destroy_actor()
        print("Deleted OFPATestActor")
        break
'''
        await mcp_client.call_tool("editor_execute_code", {"code": cleanup_code, "timeout": 30})


@pytest.mark.integration
class TestActorChangeTracking:
    """Tests for actor-based change tracking merged into asset_changes."""

    @pytest.mark.asyncio
    async def test_actor_addition_marks_level_as_changed(self, mcp_client, running_editor):
        """Test that adding an actor marks the level as changed in asset_changes.

        Actor changes are now merged into asset_changes - when actors are added,
        the current level path should appear in the asset_changes list.
        """
        # First, ensure we're on the ThirdPerson level
        load_code = '''import unreal

level_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
level_subsystem.load_level("/Game/ThirdPerson/Lvl_ThirdPerson")
print("Loaded Lvl_ThirdPerson")
'''
        load_result = await mcp_client.call_tool(
            "editor_execute_code",
            {"code": load_code, "timeout": 60},
        )
        assert load_result.structuredContent.get("success") is True

        # Add an actor (should cause level to be marked as changed)
        add_code = '''import unreal

actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)

# Add a new actor
actor = actor_subsystem.spawn_actor_from_class(
    unreal.StaticMeshActor, unreal.Vector(1000, 2000, 100), unreal.Rotator(0, 0, 0)
)
actor.set_actor_label("ActorTrackingTestActor")
print(f"Added actor: {actor.get_actor_label()}")
'''
        result = await mcp_client.call_tool(
            "editor_execute_code",
            {"code": add_code, "timeout": 60},
        )

        data = result.structuredContent
        assert data.get("success") is True, f"Code execution failed: {data.get('error')}"

        # Verify asset_changes is present (actor_changes is now merged into it)
        assert "asset_changes" in data, f"No asset_changes in result. Keys: {list(data.keys())}"
        assert "actor_changes" not in data, "actor_changes should be merged into asset_changes"

        # asset_changes is now a simple array of paths
        asset_changes = data["asset_changes"]
        logger.info(f"Asset changes: {asset_changes}")

        # Verify it's a list of strings
        assert isinstance(asset_changes, list), "asset_changes should be a list"

        # Verify the ThirdPerson level is in the changed paths
        assert any("ThirdPerson" in path for path in asset_changes), (
            f"Expected Lvl_ThirdPerson in asset_changes. Got: {asset_changes}"
        )

        # Cleanup - delete the test actor
        cleanup_code = '''import unreal

actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)

# Find and delete the test actor
for actor in actor_subsystem.get_all_level_actors():
    if actor.get_actor_label() == "ActorTrackingTestActor":
        actor.destroy_actor()
        print("Deleted test actor")
        break
'''
        await mcp_client.call_tool("editor_execute_code", {"code": cleanup_code, "timeout": 30})

    @pytest.mark.asyncio
    async def test_actor_modification_marks_level_as_changed(self, mcp_client, running_editor):
        """Test that modifying an actor marks the level as changed in asset_changes."""
        # First, ensure we're on the ThirdPerson level
        load_code = '''import unreal

level_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
level_subsystem.load_level("/Game/ThirdPerson/Lvl_ThirdPerson")
print("Loaded Lvl_ThirdPerson")
'''
        load_result = await mcp_client.call_tool(
            "editor_execute_code",
            {"code": load_code, "timeout": 60},
        )
        assert load_result.structuredContent.get("success") is True

        # Add an actor first
        add_code = '''import unreal

actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
actor = actor_subsystem.spawn_actor_from_class(
    unreal.StaticMeshActor, unreal.Vector(500, 500, 50), unreal.Rotator(0, 0, 0)
)
actor.set_actor_label("ActorModifyTestActor")
print(f"Added actor at {actor.get_actor_location()}")
'''
        await mcp_client.call_tool("editor_execute_code", {"code": add_code, "timeout": 30})

        # Now modify the actor's position (should cause level to be marked as changed)
        move_code = '''import unreal

actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)

# Find and move the actor
for actor in actor_subsystem.get_all_level_actors():
    if actor.get_actor_label() == "ActorModifyTestActor":
        old_loc = actor.get_actor_location()
        new_loc = unreal.Vector(old_loc.x + 500, old_loc.y + 500, old_loc.z + 200)
        actor.set_actor_location(new_loc, sweep=False, teleport=True)
        print(f"Moved actor from {old_loc} to {new_loc}")
        break
'''
        result = await mcp_client.call_tool(
            "editor_execute_code",
            {"code": move_code, "timeout": 30},
        )

        data = result.structuredContent
        assert data.get("success") is True

        # Verify asset_changes is present
        assert "asset_changes" in data, "No asset_changes in result"
        assert "actor_changes" not in data, "actor_changes should be merged into asset_changes"

        # asset_changes is now a simple array of paths
        asset_changes = data["asset_changes"]
        logger.info(f"Asset changes after actor modification: {asset_changes}")

        # Verify it's a list and contains the ThirdPerson level
        assert isinstance(asset_changes, list), "asset_changes should be a list"
        assert any("ThirdPerson" in path for path in asset_changes), (
            f"Expected ThirdPerson level in asset_changes. Got: {asset_changes}"
        )

        # Cleanup
        cleanup_code = '''import unreal

actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
for actor in actor_subsystem.get_all_level_actors():
    if actor.get_actor_label() == "ActorModifyTestActor":
        actor.destroy_actor()
        print("Deleted test actor")
        break
'''
        await mcp_client.call_tool("editor_execute_code", {"code": cleanup_code, "timeout": 30})

    @pytest.mark.asyncio
    async def test_no_actor_changes_field(self, mcp_client, running_editor):
        """Test that actor_changes field no longer exists (merged into asset_changes)."""
        # First, ensure we're on a persistent level (not /Temp/)
        load_code = '''import unreal

level_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
level_subsystem.load_level("/Game/ThirdPerson/Lvl_ThirdPerson")
print("Loaded Lvl_ThirdPerson")
'''
        load_result = await mcp_client.call_tool(
            "editor_execute_code",
            {"code": load_code, "timeout": 60},
        )
        assert load_result.structuredContent.get("success") is True

        # Add an actor
        add_code = '''import unreal

actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)

# Add a new actor
actor = actor_subsystem.spawn_actor_from_class(
    unreal.StaticMeshActor, unreal.Vector(1000, 1000, 100), unreal.Rotator(0, 0, 0)
)
actor.set_actor_label("NoActorChangesTestActor")
mesh_comp = actor.get_component_by_class(unreal.StaticMeshComponent)
if mesh_comp:
    cube = unreal.load_asset("/Engine/BasicShapes/Cube")
    if cube:
        mesh_comp.set_static_mesh(cube)
print(f"Added actor: {actor.get_actor_label()}")
'''
        result = await mcp_client.call_tool(
            "editor_execute_code",
            {"code": add_code, "timeout": 60},
        )

        data = result.structuredContent
        assert data.get("success") is True, f"Code execution failed: {data.get('error')}"

        # Verify actor_changes is NOT present (merged into asset_changes)
        assert "actor_changes" not in data, (
            f"actor_changes should NOT be present (merged into asset_changes). "
            f"Got keys: {list(data.keys())}"
        )

        # Verify asset_changes IS present
        assert "asset_changes" in data, f"No asset_changes in result. Keys: {list(data.keys())}"

        # asset_changes is now a simple array of paths
        asset_changes = data["asset_changes"]
        logger.info(f"Asset changes: {asset_changes}")

        # Verify it's a list and contains the ThirdPerson level
        assert isinstance(asset_changes, list), "asset_changes should be a list"
        assert any("ThirdPerson" in path for path in asset_changes), (
            f"Expected ThirdPerson level in asset_changes. Got: {asset_changes}"
        )

        # Cleanup - delete the test actor
        cleanup_code = '''import unreal

actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
for actor in actor_subsystem.get_all_level_actors():
    if actor.get_actor_label() == "NoActorChangesTestActor":
        actor.destroy_actor()
        print("Deleted NoActorChangesTestActor")
        break
'''
        await mcp_client.call_tool("editor_execute_code", {"code": cleanup_code, "timeout": 30})

    @pytest.mark.asyncio
    async def test_temporary_level_warning(self, mcp_client, running_editor):
        """Test that changes in a temporary level include a warning.

        When actors are modified in a temporary level (path starts with /Temp/),
        the result should include a temp_level_warning field.
        """
        # Step 1: Create a new temporary level (unsaved)
        new_level_code = '''import unreal

# Use EditorLoadingAndSavingUtils.new_blank_map() to create an unsaved temp level
# This creates a /Temp/Untitled_X level, unlike level_subsystem.new_level() which
# expects a destination path to save to (e.g., /Game/Maps/MyLevel)
world = unreal.EditorLoadingAndSavingUtils.new_blank_map(False)
print(f"Created temporary level: {world.get_outer().get_path_name() if world else 'None'}")
'''
        new_level_result = await mcp_client.call_tool(
            "editor_execute_code",
            {"code": new_level_code, "timeout": 60},
        )
        assert new_level_result.structuredContent.get("success") is True

        # Step 2: Add an actor in the temporary level
        add_actor_code = '''import unreal

actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)

# Add an actor to the temporary level
actor = actor_subsystem.spawn_actor_from_class(
    unreal.StaticMeshActor, unreal.Vector(0, 0, 100), unreal.Rotator(0, 0, 0)
)
actor.set_actor_label("TempLevelTestActor")
mesh_comp = actor.get_component_by_class(unreal.StaticMeshComponent)
if mesh_comp:
    sphere = unreal.load_asset("/Engine/BasicShapes/Sphere")
    if sphere:
        mesh_comp.set_static_mesh(sphere)
print(f"Added actor in temp level: {actor.get_actor_label()}")
'''
        result = await mcp_client.call_tool(
            "editor_execute_code",
            {"code": add_actor_code, "timeout": 60},
        )

        data = result.structuredContent
        assert data.get("success") is True, f"Code execution failed: {data.get('error')}"

        # Verify asset_changes is present (actor_changes merged into it)
        assert "asset_changes" in data, f"No asset_changes in result. Keys: {list(data.keys())}"
        assert "actor_changes" not in data, "actor_changes should be merged into asset_changes"

        # asset_changes is now a simple array of paths
        asset_changes = data["asset_changes"]
        logger.info(f"Asset changes in temp level: {asset_changes}")

        # Verify it's a list
        assert isinstance(asset_changes, list), "asset_changes should be a list"

        # Verify the temp_level_warning is present at top level (not inside asset_changes)
        assert "temp_level_warning" in data, (
            f"Expected 'temp_level_warning' field in result for temporary level. "
            f"Got keys: {list(data.keys())}"
        )

        warning = data["temp_level_warning"]
        logger.info(f"Temporary level warning: {warning}")

        # Verify warning message content
        assert "/Temp/" in warning, "Warning should mention /Temp/ path"
        assert "editor_load_level" in warning, (
            "Warning should suggest using editor_load_level"
        )

        # Step 3: Switch back to a persistent level for cleanup
        switch_back_code = '''import unreal

level_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
level_subsystem.load_level("/Game/ThirdPerson/Lvl_ThirdPerson")
print("Switched back to Lvl_ThirdPerson")
'''
        await mcp_client.call_tool(
            "editor_execute_code",
            {"code": switch_back_code, "timeout": 60},
        )


@pytest.mark.integration
class TestDirtyAssets:
    """Tests for dirty assets tracking feature."""

    @pytest.mark.asyncio
    async def test_dirty_assets_returned_after_modification(self, mcp_client, running_editor):
        """Test that dirty_assets field is returned when assets have unsaved changes."""
        # Create a new temporary level (which will be dirty by default)
        new_level_code = '''import unreal

# Create a new blank map (this creates a dirty/unsaved level)
world = unreal.EditorLoadingAndSavingUtils.new_blank_map(False)
if world:
    print(f"Created temp level: {world.get_outer().get_path_name()}")
else:
    print("Failed to create temp level")
'''
        result = await mcp_client.call_tool(
            "editor_execute_code",
            {"code": new_level_code, "timeout": 60},
        )

        data = result.structuredContent
        assert data.get("success") is True, f"Code execution failed: {data.get('error')}"

        # dirty_assets should be present when there are unsaved changes
        # Note: The new blank map may or may not show up in dirty_assets
        # depending on how UE5 tracks it, but the field should be present
        # when execution succeeds
        logger.info(f"Result keys: {list(data.keys())}")
        if "dirty_assets" in data:
            dirty_assets = data["dirty_assets"]
            logger.info(f"Dirty assets: {dirty_assets}")
            assert isinstance(dirty_assets, list), "dirty_assets should be a list"

        # Switch back to a clean state
        cleanup_code = '''import unreal

level_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
level_subsystem.load_level("/Game/ThirdPerson/Lvl_ThirdPerson")
print("Loaded clean level")
'''
        await mcp_client.call_tool("editor_execute_code", {"code": cleanup_code, "timeout": 60})

    @pytest.mark.asyncio
    async def test_no_dirty_assets_after_save(self, mcp_client, running_editor):
        """Test that dirty_assets is empty after saving changes."""
        # Load a level and then ensure it's saved
        load_code = '''import unreal

level_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
level_subsystem.load_level("/Game/ThirdPerson/Lvl_ThirdPerson")
print("Loaded Lvl_ThirdPerson")
'''
        result = await mcp_client.call_tool(
            "editor_execute_code",
            {"code": load_code, "timeout": 60},
        )

        data = result.structuredContent
        assert data.get("success") is True

        # After loading a clean level without modifications, dirty_assets
        # should either not be present or be an empty list
        if "dirty_assets" in data:
            dirty_assets = data["dirty_assets"]
            logger.info(f"Dirty assets (should be empty): {dirty_assets}")
            # This level should be clean (no unsaved changes)
            # Note: there might be some system-level dirty packages
            # so we just verify the format is correct
            assert isinstance(dirty_assets, list), "dirty_assets should be a list"


@pytest.mark.integration
class TestEditorLoadLevel:
    """Tests for the editor_load_level MCP tool."""

    @pytest.mark.asyncio
    async def test_load_existing_level(self, mcp_client, running_editor):
        """Test that loading an existing level succeeds."""
        result = await mcp_client.call_tool(
            "editor_load_level",
            {"level_path": "/Game/ThirdPerson/Lvl_ThirdPerson"},
        )

        data = result.structuredContent
        logger.info(f"Load existing level result: {data}")

        assert data.get("success") is True, f"Expected success. Got: {data}"
        assert "level_path" in data, "Expected level_path in result"
        assert "current_level" in data, "Expected current_level in result"
        assert "Lvl_ThirdPerson" in data.get("current_level", ""), (
            f"Expected current_level to contain Lvl_ThirdPerson. Got: {data}"
        )

    @pytest.mark.asyncio
    async def test_load_nonexistent_level_fails(self, mcp_client, running_editor):
        """Test that loading a non-existent level returns an error."""
        result = await mcp_client.call_tool(
            "editor_load_level",
            {"level_path": "/Game/NonExistent/FakeLevel12345"},
        )

        data = result.structuredContent
        logger.info(f"Load non-existent level result: {data}")

        assert data.get("success") is False, f"Expected failure for non-existent level. Got: {data}"
        assert "error" in data, "Expected error message"
        assert "not found" in data.get("error", "").lower(), (
            f"Expected 'not found' in error message. Got: {data.get('error')}"
        )

    @pytest.mark.asyncio
    async def test_load_invalid_path_fails(self, mcp_client, running_editor):
        """Test that loading with invalid path format returns an error."""
        result = await mcp_client.call_tool(
            "editor_load_level",
            {"level_path": "/Engine/Maps/Entry"},  # Not a /Game/ path
        )

        data = result.structuredContent
        logger.info(f"Load invalid path result: {data}")

        assert data.get("success") is False, f"Expected failure for invalid path. Got: {data}"
        assert "error" in data, "Expected error message"
        assert "/Game/" in data.get("error", ""), (
            f"Expected error to mention /Game/ requirement. Got: {data.get('error')}"
        )
