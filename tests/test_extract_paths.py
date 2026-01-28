"""Tests for path extraction functions in asset_tracker module."""

from ue_mcp.tracking.asset_tracker import extract_game_paths, extract_level_paths


class TestExtractGamePaths:
    """Tests for extract_game_paths function."""

    def test_simple_path(self):
        """Test extracting a simple /Game/ path."""
        code = 'asset_path = "/Game/Maps/TestLevel"'
        result = extract_game_paths(code)
        assert "/Game/Maps/" in result

    def test_multiple_paths(self):
        """Test extracting multiple /Game/ paths."""
        code = '''
asset1 = "/Game/Maps/Level1"
asset2 = "/Game/Blueprints/BP_Test"
'''
        result = extract_game_paths(code)
        assert "/Game/Maps/" in result
        assert "/Game/Blueprints/" in result

    def test_raw_string(self):
        """Test extracting from raw strings."""
        code = 'path = r"/Game/Materials/M_Test"'
        result = extract_game_paths(code)
        assert "/Game/Materials/" in result

    def test_single_quotes(self):
        """Test extracting from single-quoted strings."""
        code = "path = '/Game/Textures/T_Test'"
        result = extract_game_paths(code)
        assert "/Game/Textures/" in result


class TestExtractLevelPathsEditorAPIs:
    """Tests for extract_level_paths with LevelEditorSubsystem APIs."""

    def test_load_level(self):
        """Test detecting load_level API call."""
        code = 'level_subsystem.load_level("/Game/Maps/TestLevel")'
        result = extract_level_paths(code)
        assert "/Game/Maps/TestLevel" in result

    def test_load_level_single_quotes(self):
        """Test detecting load_level with single quotes."""
        code = "level_subsystem.load_level('/Game/Maps/TestLevel')"
        result = extract_level_paths(code)
        assert "/Game/Maps/TestLevel" in result

    def test_new_level(self):
        """Test detecting new_level API call."""
        code = 'level_subsystem.new_level("/Game/Maps/NewLevel")'
        result = extract_level_paths(code)
        assert "/Game/Maps/NewLevel" in result

    def test_new_level_from_template(self):
        """Test detecting new_level_from_template API call (both args are levels)."""
        code = 'level_subsystem.new_level_from_template("/Game/Maps/NewMap", "/Game/Maps/Template")'
        result = extract_level_paths(code)
        assert "/Game/Maps/NewMap" in result
        assert "/Game/Maps/Template" in result

    def test_load_map(self):
        """Test detecting load_map API call."""
        code = 'unreal.EditorLoadingAndSavingUtils.load_map("/Game/Maps/Level")'
        result = extract_level_paths(code)
        assert "/Game/Maps/Level" in result

    def test_new_map_from_template(self):
        """Test detecting new_map_from_template API call."""
        code = 'utils.new_map_from_template("/Game/Maps/Template", True)'
        result = extract_level_paths(code)
        assert "/Game/Maps/Template" in result


class TestExtractLevelPathsEditorLevelUtils:
    """Tests for extract_level_paths with EditorLevelUtils APIs."""

    def test_add_level_to_world(self):
        """Test detecting add_level_to_world API call."""
        code = 'unreal.EditorLevelUtils.add_level_to_world(world, "/Game/Maps/SubLevel", streaming_class)'
        result = extract_level_paths(code)
        assert "/Game/Maps/SubLevel" in result

    def test_add_level_to_world_with_transform(self):
        """Test detecting add_level_to_world_with_transform API call."""
        code = '''
streaming_level = unreal.EditorLevelUtils.add_level_to_world_with_transform(
    editor_world,
    "/Game/Maps/SubLevel",
    unreal.LevelStreamingDynamic,
    unreal.Transform()
)
'''
        result = extract_level_paths(code)
        assert "/Game/Maps/SubLevel" in result


class TestExtractLevelPathsRuntimeAPIs:
    """Tests for extract_level_paths with GameplayStatics APIs."""

    def test_open_level(self):
        """Test detecting open_level API call."""
        code = 'unreal.GameplayStatics.open_level(self, "/Game/Maps/Level1", True, "")'
        result = extract_level_paths(code)
        assert "/Game/Maps/Level1" in result

    def test_load_stream_level(self):
        """Test detecting load_stream_level API call."""
        code = 'unreal.GameplayStatics.load_stream_level(self, "/Game/Maps/StreamLevel", True, False, latent_info)'
        result = extract_level_paths(code)
        assert "/Game/Maps/StreamLevel" in result

    def test_unload_stream_level(self):
        """Test detecting unload_stream_level API call."""
        code = 'unreal.GameplayStatics.unload_stream_level(ctx, "/Game/Maps/StreamLevel", latent_info, True)'
        result = extract_level_paths(code)
        assert "/Game/Maps/StreamLevel" in result

    def test_get_streaming_level(self):
        """Test detecting get_streaming_level API call."""
        code = 'streaming_level = unreal.GameplayStatics.get_streaming_level(world, "/Game/Maps/StreamLevel")'
        result = extract_level_paths(code)
        assert "/Game/Maps/StreamLevel" in result


class TestExtractLevelPathsLevelStreamingDynamic:
    """Tests for extract_level_paths with LevelStreamingDynamic APIs."""

    def test_load_level_instance_keyword(self):
        """Test detecting load_level_instance with level_name keyword argument."""
        code = '''
streaming_level, success = unreal.LevelStreamingDynamic.load_level_instance(
    world_context_object,
    level_name="/Game/Maps/Room",
    location=unreal.Vector(1000, 2000, 0),
    rotation=unreal.Rotator(0, 45, 0)
)
'''
        result = extract_level_paths(code)
        assert "/Game/Maps/Room" in result


class TestExtractLevelPathsNonLevelAPIs:
    """Tests to ensure non-level API calls are not detected."""

    def test_ignores_load_asset(self):
        """Test that load_asset API is not detected as level."""
        code = 'asset = unreal.EditorAssetLibrary.load_asset("/Game/Blueprints/BP_Character")'
        result = extract_level_paths(code)
        assert "/Game/Blueprints/BP_Character" not in result

    def test_ignores_plain_string_assignment(self):
        """Test that plain string assignments are not detected."""
        code = 'level_path = "/Game/Maps/TestLevel"'
        result = extract_level_paths(code)
        # Without a level-related API call, this should NOT be detected
        assert "/Game/Maps/TestLevel" not in result

    def test_ignores_blueprint_path_in_maps(self):
        """Test that non-level assets in Maps folder are not detected."""
        code = 'bp_path = "/Game/Maps/BP_LevelManager"'
        result = extract_level_paths(code)
        assert "/Game/Maps/BP_LevelManager" not in result


class TestExtractLevelPathsEdgeCases:
    """Edge case tests for extract_level_paths."""

    def test_empty_code(self):
        """Test with empty code string."""
        result = extract_level_paths("")
        assert result == []

    def test_no_game_paths(self):
        """Test with code containing no /Game/ paths."""
        code = "x = 1 + 2\nprint('hello')"
        result = extract_level_paths(code)
        assert result == []

    def test_multiple_api_calls(self):
        """Test extracting from multiple level API calls."""
        code = '''
level_subsystem.load_level("/Game/Maps/Level1")
level_subsystem.new_level("/Game/Maps/Level2")
unreal.GameplayStatics.open_level(self, "/Game/Maps/Level3", True)
'''
        result = extract_level_paths(code)
        assert "/Game/Maps/Level1" in result
        assert "/Game/Maps/Level2" in result
        assert "/Game/Maps/Level3" in result

    def test_deduplication(self):
        """Test that duplicate paths are deduplicated."""
        code = '''
level_subsystem.load_level("/Game/Maps/TestLevel")
level_subsystem.load_level("/Game/Maps/TestLevel")
'''
        result = extract_level_paths(code)
        assert result.count("/Game/Maps/TestLevel") == 1

    def test_whitespace_in_api_call(self):
        """Test API calls with extra whitespace."""
        code = 'level_subsystem.load_level(   "/Game/Maps/TestLevel"   )'
        result = extract_level_paths(code)
        assert "/Game/Maps/TestLevel" in result

    def test_nested_path(self):
        """Test deeply nested level path."""
        code = 'level_subsystem.load_level("/Game/ThirdPerson/Maps/Subdir/TestLevel")'
        result = extract_level_paths(code)
        assert "/Game/ThirdPerson/Maps/Subdir/TestLevel" in result

    def test_trailing_slash_stripped(self):
        """Test that trailing slashes are stripped from paths."""
        code = 'level_subsystem.load_level("/Game/Maps/TestLevel/")'
        result = extract_level_paths(code)
        assert "/Game/Maps/TestLevel" in result

    def test_realistic_code_snippet(self):
        """Test a realistic UE5 Python code snippet."""
        code = '''
import unreal

# Get subsystems
level_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)

# Load the test level
success = level_subsystem.load_level("/Game/ThirdPerson/Maps/ThirdPersonMap")

# Spawn some actors
actor_subsystem.spawn_actor_from_class(
    unreal.StaticMeshActor,
    unreal.Vector(0, 0, 0)
)

# Add a streaming sublevel
unreal.EditorLevelUtils.add_level_to_world(
    level_subsystem.get_current_level(),
    "/Game/Maps/SubLevel_Interior",
    unreal.LevelStreamingDynamic
)
'''
        result = extract_level_paths(code)
        assert "/Game/ThirdPerson/Maps/ThirdPersonMap" in result
        assert "/Game/Maps/SubLevel_Interior" in result
        # Should only have 2 level paths
        assert len(result) == 2
