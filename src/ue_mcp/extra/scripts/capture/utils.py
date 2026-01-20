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
    
    The MCP server injects __PARAMS__ before executing the script.
    For manual testing in UE, set __PARAMS__ = {...} before running.
    """
    return __PARAMS__  # noqa: F821 - Injected by server before execution


def ensure_level_loaded(target_level: str) -> None:
    """
    Ensure the specified level is loaded, checking for dirty state.
    """
    level_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    if not level_subsystem:
        raise RuntimeError("Could not get LevelEditorSubsystem")

    # Get current level package to check name and dirty status
    current_level_obj = level_subsystem.get_current_level()
    if not current_level_obj:
        raise RuntimeError("Could not get current level")
    
    current_package = current_level_obj.get_outermost()
    current_level = current_package.get_name()
    
    if current_level != target_level:
        if current_package.is_dirty():
            raise RuntimeError(
                f"Current level '{current_level}' has unsaved changes. "
                f"Please save or discard them before loading '{target_level}'."
            )
        if not level_subsystem.load_level(target_level):
             raise RuntimeError(f"Failed to load level: {target_level}")


def output_result(data: dict) -> None:
    """
    Output result in format expected by MCP server.
    """
    print("__CAPTURE_RESULT__" + json.dumps(data))



