"""
Shared utilities for capture scripts.

These functions are used by capture scripts to:
- Get parameters passed from the MCP server
- Ensure the correct level is loaded
- Output results in the expected format
"""
import json
import unreal


def get_params() -> dict:
    """
    Get parameters passed from MCP server.
    
    The MCP server injects __PARAMS__ before executing the script.
    For manual testing in UE, set __PARAMS__ = {...} before running.
    """
    return __PARAMS__  # noqa: F821 - Injected by server before execution


def ensure_level_loaded(target_level: str) -> None:
    """
    Ensure the specified level is loaded, checking for dirty state.
    
    Args:
        target_level: The level path to load (e.g., "/Game/Maps/MyLevel")
    
    Raises:
        RuntimeError: If current level has unsaved changes or world is unavailable
    """
    world = unreal.EditorLevelLibrary.get_editor_world()
    if not world:
        raise RuntimeError("Could not get editor world")
    
    current_level = world.get_package().get_name()
    if current_level != target_level:
        if world.get_package().is_dirty():
            raise RuntimeError(
                f"Current level '{current_level}' has unsaved changes. "
                f"Please save or discard them before loading '{target_level}'."
            )
        unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).load_level(target_level)


def output_result(data: dict) -> None:
    """
    Output result in format expected by MCP server.
    
    Args:
        data: Result dictionary to output as JSON
    """
    print("__CAPTURE_RESULT__" + json.dumps(data))
