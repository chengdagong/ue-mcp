"""
Shared utilities for capture scripts.

These functions are used by capture scripts to:
- Get parameters passed from the MCP server
- Ensure the correct level is loaded
- Output results in the expected format
- Handle errors gracefully

These scripts can be run either:
1. Via MCP server (parameters injected via environment variables)
2. Directly in UE Python console (parameters parsed from sys.argv)
"""

import builtins
import gc
import hashlib
import json
import os
import sys
import time
import unreal

# Environment variable names for script parameter passing (must match _helpers.py)
ENV_VAR_MODE = "UE_MCP_MODE"  # "1" when running via MCP (vs CLI)
ENV_VAR_CALL = "UE_MCP_CALL"  # "<checksum>:<timestamp>:<json_params>" script call info

# Maximum allowed age for injected parameters (in seconds)
# Must match value in _helpers.py
INJECT_TIME_MAX_AGE = 0.2

# Flag to track if running in MCP mode (vs CLI mode)
_mcp_mode = None


class StaleParametersError(RuntimeError):
    """Raised when injected parameters are too old (stale)."""
    pass


class ScriptMismatchError(RuntimeError):
    """Raised when parameters were intended for a different script."""
    pass


def _clean_env_vars() -> None:
    """Clean up all MCP env vars to prevent leakage to other scripts."""
    for var in (ENV_VAR_MODE, ENV_VAR_CALL):
        if var in os.environ:
            del os.environ[var]


def _compute_script_checksum(script_path: str) -> str:
    """Compute a short checksum of the script path for token validation.

    Must match the checksum algorithm in _helpers.py.

    Args:
        script_path: Absolute path to the script file

    Returns:
        8-character hex checksum
    """
    return hashlib.md5(script_path.encode()).hexdigest()[:8]


def _get_current_script_path() -> str:
    """Get the path of the currently executing script.

    Returns:
        The script path, or 'unknown' if it cannot be determined.
    """
    # In UE5 Python, __file__ should be set when executing a script file
    # via EXECUTE_FILE mode
    if '__file__' in dir(builtins):
        return getattr(builtins, '__file__', 'unknown')

    # Try to get from sys.argv[0] as fallback
    if sys.argv and sys.argv[0]:
        return sys.argv[0]

    return 'unknown'


def bootstrap_from_env(script_path: str | None = None) -> tuple[bool, dict]:
    """Bootstrap script parameters from environment variables.

    Reads UE_MCP_MODE and UE_MCP_CALL env vars, validates the call info
    (checksum + timestamp + params), sets up sys.argv, and returns the
    parameters dict.

    This function must be called at the very start of a script's main() function,
    BEFORE argparse.parse_args() is called.

    The call info validation ensures:
    1. Parameters are intended for this specific script (checksum match)
    2. Parameters are fresh, not stale from a previous execution (age < 0.2s)

    Args:
        script_path: Optional explicit script path for checksum validation.
                    If not provided, attempts to detect from __file__ or sys.argv[0].

    Returns:
        Tuple of (is_mcp_mode, params_dict)
        - is_mcp_mode: True if running via MCP (env vars present)
        - params_dict: Parameter dictionary (empty if not MCP mode)

    Raises:
        StaleParametersError: If parameters are older than INJECT_TIME_MAX_AGE
        ScriptMismatchError: If parameters were intended for a different script

    Example:
        def main():
            from ue_mcp_capture.utils import bootstrap_from_env
            bootstrap_from_env()  # Must be before argparse

            parser = argparse.ArgumentParser(...)
            args = parser.parse_args()  # Works normally
            ...
    """
    global _mcp_mode

    # Check if MCP mode is enabled
    mcp_mode_flag = os.environ.get(ENV_VAR_MODE)
    if mcp_mode_flag != "1":
        # Not MCP mode - CLI usage, sys.argv already set by caller
        _mcp_mode = False
        return False, {}

    # MCP mode: get and validate call info
    call_info = os.environ.get(ENV_VAR_CALL)
    if not call_info:
        # No call info - invalid MCP state, clean up and fall back to CLI mode
        print("Warning: MCP mode enabled but no call info found")
        _clean_env_vars()
        _mcp_mode = False
        return False, {}

    # Parse call info: "<checksum>:<timestamp>:<json_params>"
    # Use split with maxsplit=2 since JSON may contain colons
    try:
        parts = call_info.split(":", 2)
        if len(parts) < 3:
            raise ValueError(f"Expected 3 parts, got {len(parts)}")
        call_checksum, timestamp_str, params_json = parts
        inject_time = float(timestamp_str)
    except (ValueError, TypeError) as e:
        print(f"Warning: Invalid call info format: {call_info[:50]}... ({e})")
        _clean_env_vars()
        _mcp_mode = False
        return False, {}

    # Validate timestamp (freshness check)
    current_time = time.time()
    age = current_time - inject_time

    if age > INJECT_TIME_MAX_AGE:
        # Parameters are stale - clean up and raise error
        _clean_env_vars()
        raise StaleParametersError(
            f"Stale MCP parameters detected (age={age:.3f}s > max={INJECT_TIME_MAX_AGE}s). "
            f"This may indicate parameters from a previous script execution. "
            f"Environment variables have been cleaned up."
        )

    # Validate checksum (script identity check)
    if script_path is None:
        script_path = _get_current_script_path()

    if script_path and script_path != 'unknown':
        expected_checksum = _compute_script_checksum(script_path)
        if call_checksum != expected_checksum:
            # Parameters were intended for a different script - clean up and raise error
            _clean_env_vars()
            raise ScriptMismatchError(
                f"Script mismatch: parameters intended for script with checksum '{call_checksum}', "
                f"but current script '{script_path}' has checksum '{expected_checksum}'. "
                f"Environment variables have been cleaned up."
            )

    # Validation passed - parse parameters from call info
    try:
        params = json.loads(params_json) if params_json else {}
    except json.JSONDecodeError as e:
        print(f"Warning: Invalid JSON in call info: {e}")
        _clean_env_vars()
        _mcp_mode = False
        return False, {}

    _mcp_mode = True

    # Build sys.argv from params
    sys.argv = [script_path or "script.py"]

    # Check for raw args (special __args__ key from editor_execute_script)
    raw_args = params.pop("__args__", None)
    if raw_args and isinstance(raw_args, list):
        # Use raw args directly (already in CLI format)
        sys.argv.extend(str(a) for a in raw_args)
    else:
        # Convert dict params to CLI-style args
        for key, value in params.items():
            # Skip None values
            if value is None:
                continue

            # Convert snake_case to kebab-case for CLI style
            cli_key = f"--{key.replace('_', '-')}"

            if isinstance(value, bool):
                # Boolean: only add flag if True
                if value:
                    sys.argv.append(cli_key)
                # False: don't add anything (argparse will use default)
            elif isinstance(value, (list, dict)):
                # Complex types: JSON encode
                sys.argv.append(cli_key)
                sys.argv.append(json.dumps(value))
            else:
                # Simple types: string conversion
                sys.argv.append(cli_key)
                sys.argv.append(str(value))

    # Also set builtins.__PARAMS__ for direct access (legacy support)
    builtins.__PARAMS__ = params

    # Clean up env vars to prevent leakage to other scripts
    _clean_env_vars()

    return True, params


def _is_mcp_mode() -> bool:
    """Check if running in MCP mode (vs CLI mode)."""
    global _mcp_mode
    if _mcp_mode is None:
        # If bootstrap_from_env() was not called, check for env var presence
        _mcp_mode = os.environ.get(ENV_VAR_MODE) == "1"
    return _mcp_mode


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
    # Check if current level has unsaved changes (skip for temp/Untitled levels)
    is_temp_level = current_level_full.startswith("/Temp/") or current_level_name.lower().startswith("untitled")
    if not is_temp_level:
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
    Output result as pure JSON (last line of output).

    The MCP server will parse the last valid JSON object from the output.
    This enables clean output without special markers.

    In MCP mode: Outputs compact JSON for parsing
    In CLI mode: Outputs formatted JSON for readability
    """
    if _is_mcp_mode():
        # MCP mode: compact JSON (will be parsed as last line)
        print(json.dumps(data))
    else:
        # CLI mode: human-readable formatted output
        print("\n" + "=" * 60)
        print("CAPTURE RESULT")
        print("=" * 60)
        print(json.dumps(data, indent=2))
        print("=" * 60)
