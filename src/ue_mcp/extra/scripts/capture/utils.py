"""
Shared utilities for capture scripts.

These functions are used by capture scripts to:
- Get parameters passed from the MCP server
- Ensure the correct level is loaded
- Output results in the expected format
- Handle errors gracefully
"""
import json
import unreal


def get_params() -> dict:
    """
    Get parameters passed from MCP server.

    The MCP server injects __PARAMS__ into builtins before executing the script.
    For manual testing in UE, set builtins.__PARAMS__ = {...} before running.
    """
    import builtins
    if hasattr(builtins, "__PARAMS__"):
        return builtins.__PARAMS__
    raise RuntimeError(
        "__PARAMS__ not found. If testing manually, set builtins.__PARAMS__ = {...} first."
    )


def ensure_level_loaded(target_level: str) -> None:
    """
    Ensure the specified level is loaded, checking for dirty state.

    Args:
        target_level: Level path or name to load. Can be:
            - Full path: "/Game/Maps/MyLevel"
            - Just the name: "MyLevel"
            - Temp level name: "Untitled_1"
    """
    level_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    if not level_subsystem:
        raise RuntimeError("Could not get LevelEditorSubsystem")

    # Get current level package to check name
    current_level_obj = level_subsystem.get_current_level()
    if not current_level_obj:
        raise RuntimeError("Could not get current level")

    current_package = current_level_obj.get_outermost()
    current_level_full = current_package.get_name()  # e.g., "/Temp/Untitled_1"
    current_level_path = current_package.get_path_name()

    # Extract just the level name (last component)
    current_level_name = current_level_full.split("/")[-1] if "/" in current_level_full else current_level_full
    target_name = target_level.split("/")[-1] if "/" in target_level else target_level

    # Check if target matches current level (by name or path)
    is_same_level = (
        current_level_name == target_name or
        current_level_full == target_level or
        current_level_path == target_level or
        current_level_path.endswith(f"/{target_name}") or
        # Handle Untitled -> Untitled_N matching (new empty levels)
        (target_name.lower() == "untitled" and current_level_name.lower().startswith("untitled")) or
        current_level_name.startswith(target_name)
    )

    if is_same_level:
        # Already on the correct level
        return

    # Need to load a different level
    # Check if current level has unsaved changes
    try:
        dirty_content = unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()
        dirty_maps = unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()
        if dirty_content or dirty_maps:
            raise RuntimeError(
                f"Current level '{current_level_name}' has unsaved changes. "
                f"Please save or discard them before loading '{target_level}'."
            )
    except AttributeError:
        # EditorLoadingAndSavingUtils may not have these methods in all UE versions
        pass

    if not level_subsystem.load_level(target_level):
        raise RuntimeError(f"Failed to load level: {target_level}")


def output_result(data: dict) -> None:
    """
    Output result in format expected by MCP server.
    """
    print("__CAPTURE_RESULT__" + json.dumps(data))



