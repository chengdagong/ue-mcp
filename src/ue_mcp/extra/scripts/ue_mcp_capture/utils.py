"""
Shared utilities for capture scripts.

These functions are used by capture scripts to:
- Get parameters passed from the MCP server
- Ensure the correct level is loaded
- Output results in the expected format
- Handle errors gracefully

These scripts can be run either:
1. Via MCP server (parameters injected via builtins.__PARAMS__)
2. Directly in UE Python console (parameters parsed from sys.argv)
"""

import gc
import json
import sys
import unreal

# Flag to track if running in MCP mode (vs CLI mode)
_mcp_mode = None


def _is_mcp_mode() -> bool:
    """Check if running in MCP mode (vs CLI mode)."""
    global _mcp_mode
    if _mcp_mode is None:
        import builtins
        _mcp_mode = hasattr(builtins, "__PARAMS__")
    return _mcp_mode


def _parse_cli_value(value_str: str):
    """
    Parse a CLI argument value string to appropriate Python type.

    Supports: bool, int, float, None, list (JSON), string
    """
    # Handle None
    if value_str.lower() in ("none", "null"):
        return None

    # Handle bool
    if value_str.lower() in ("true", "yes", "1"):
        return True
    if value_str.lower() in ("false", "no", "0"):
        return False

    # Try int
    try:
        return int(value_str)
    except ValueError:
        pass

    # Try float
    try:
        return float(value_str)
    except ValueError:
        pass

    # Try JSON (for lists/dicts)
    if value_str.startswith("[") or value_str.startswith("{"):
        try:
            return json.loads(value_str)
        except json.JSONDecodeError:
            pass

    # Return as string
    return value_str


def parse_cli_args(defaults: dict = None) -> dict:
    """
    Parse CLI arguments in the format --key=value or --key value.

    Args:
        defaults: Default parameter values

    Returns:
        Dictionary of parsed parameters merged with defaults
    """
    params = dict(defaults) if defaults else {}

    args = sys.argv[1:]  # Skip script name
    i = 0
    while i < len(args):
        arg = args[i]

        if arg.startswith("--"):
            # Remove -- prefix
            arg = arg[2:]

            if "=" in arg:
                # Format: --key=value
                key, value = arg.split("=", 1)
                params[key.replace("-", "_")] = _parse_cli_value(value)
            elif i + 1 < len(args) and not args[i + 1].startswith("--"):
                # Format: --key value
                key = arg.replace("-", "_")
                params[key] = _parse_cli_value(args[i + 1])
                i += 1
            else:
                # Boolean flag: --key means True
                params[arg.replace("-", "_")] = True

        i += 1

    return params


def get_params(defaults: dict = None, required: list = None) -> dict:
    """
    Get parameters from MCP server or CLI arguments.

    The MCP server injects __PARAMS__ into builtins before executing the script.
    For direct execution, parameters are parsed from sys.argv.

    Args:
        defaults: Default parameter values (used for CLI mode)
        required: List of required parameter names (validated in CLI mode)

    Returns:
        Dictionary of parameters

    Raises:
        RuntimeError: If required parameters are missing

    Examples:
        # In UE Python console or via script:
        # python capture_orbital.py --level=/Game/Maps/Test --target-x=0 --target-y=0 --target-z=100
    """
    import builtins

    # Check MCP mode first
    if hasattr(builtins, "__PARAMS__"):
        return builtins.__PARAMS__

    # CLI mode: parse arguments
    params = parse_cli_args(defaults)

    # Validate required parameters
    if required:
        missing = [p for p in required if p not in params or params[p] is None]
        if missing:
            raise RuntimeError(
                f"Missing required parameters: {', '.join(missing)}\n"
                f"Use --{missing[0].replace('_', '-')}=<value> to provide them.\n"
                f"Example: python script.py --{missing[0].replace('_', '-')}=value"
            )

    return params


def ensure_level_loaded(target_level: str) -> None:
    """
    Ensure the specified level is loaded, checking for dirty state.

    IMPORTANT: This function carefully manages UE object references to avoid
    memory leaks. When loading a new level, UE's garbage collector needs to
    clean up the old level. If Python holds references to old level objects,
    this causes "World Memory Leaks" assertion failures.

    Args:
        target_level: Level path or name to load. Can be:
            - Full path: "/Game/Maps/MyLevel"
            - Just the name: "MyLevel"
            - Temp level name: "Untitled_1"
    """
    level_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    if not level_subsystem:
        raise RuntimeError("Could not get LevelEditorSubsystem")

    # Get current level info - extract all needed data immediately
    # and release UE object references to avoid blocking GC
    current_level_obj = level_subsystem.get_current_level()
    if not current_level_obj:
        raise RuntimeError("Could not get current level")

    current_package = current_level_obj.get_outermost()
    current_level_full = current_package.get_name()  # e.g., "/Temp/Untitled_1"
    current_level_path = current_package.get_path_name()
    current_level_name = (
        current_level_full.split("/")[-1] if "/" in current_level_full else current_level_full
    )

    # CRITICAL: Release UE object references immediately after extracting string data
    # This allows UE's GC to clean up the old level when we load a new one
    del current_package
    del current_level_obj

    # Extract target name for comparison
    target_name = target_level.split("/")[-1] if "/" in target_level else target_level

    # Check if target matches current level (by name or path)
    is_same_level = (
        current_level_name == target_name
        or current_level_full == target_level
        or current_level_path == target_level
        or current_level_path.endswith(f"/{target_name}")
        or
        # Handle Untitled -> Untitled_N matching (new empty levels)
        (target_name.lower() == "untitled" and current_level_name.lower().startswith("untitled"))
        or current_level_name.startswith(target_name)
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

    # Force Python garbage collection before loading new level
    # This ensures any remaining UE object references are released
    gc.collect()

    if not level_subsystem.load_level(target_level):
        raise RuntimeError(f"Failed to load level: {target_level}")


def output_result(data: dict) -> None:
    """
    Output result in format appropriate for current mode.

    In MCP mode: Outputs JSON with special prefix for parsing.
    In CLI mode: Outputs human-readable formatted JSON.
    """
    if _is_mcp_mode():
        # MCP mode: prefix for server parsing
        print("__CAPTURE_RESULT__" + json.dumps(data))
    else:
        # CLI mode: human-readable output
        print("\n" + "=" * 60)
        print("CAPTURE RESULT")
        print("=" * 60)
        print(json.dumps(data, indent=2))
        print("=" * 60)
