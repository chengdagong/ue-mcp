"""
Script execution module for UE-MCP.
Handles searching, loading, and parameter injection for standalone Python scripts.
"""
from pathlib import Path
from typing import Any


def get_scripts_dir() -> Path:
    """Get the capture scripts directory."""
    return Path(__file__).parent / "extra" / "scripts" / "ue_mcp_capture"


def get_diagnostic_scripts_dir() -> Path:
    """Get the diagnostic scripts directory."""
    return Path(__file__).parent / "extra" / "scripts" / "diagnostic"


def get_extra_scripts_dir() -> Path:
    """Get the extra scripts root directory."""
    return Path(__file__).parent / "extra" / "scripts"


def execute_script(
    manager,
    script_name: str,
    params: dict[str, Any],
    timeout: float = 120.0
) -> dict[str, Any]:
    """
    Execute a capture script in the UE editor using two-step EXECUTE_FILE mode.

    This enables true hot-reload: the script file is executed directly from disk.

    Args:
        manager: EditorManager instance
        script_name: Name of the script (without .py)
        params: Parameters to pass to the script
        timeout: Execution timeout in seconds

    Returns:
        Execution result from the script

    Raises:
        FileNotFoundError: If the script does not exist
    """
    scripts_dir = get_scripts_dir()
    script_path = scripts_dir / f"{script_name}.py"

    # Use the unified execute_script_from_path function
    return execute_script_from_path(manager, script_path, params, timeout)


def execute_script_from_path(
    manager,
    script_path: Path | str,
    params: dict[str, Any],
    timeout: float = 120.0
) -> dict[str, Any]:
    """
    Execute a script from a specific path in the UE editor using two-step EXECUTE_FILE mode.

    This enables true hot-reload: the script file is executed directly from disk,
    so modifications take effect immediately without restarting the editor or MCP server.

    Step 1: Inject parameters into sys.argv and set MCP mode marker
    Step 2: Execute script file directly (EXECUTE_FILE mode)

    Args:
        manager: EditorManager instance
        script_path: Full path to the script file
        params: Parameters to pass to the script
        timeout: Execution timeout in seconds

    Returns:
        Execution result from the script

    Raises:
        FileNotFoundError: If the script does not exist
    """
    script_path = Path(script_path)

    if not script_path.exists():
        raise FileNotFoundError(f"Script not found: {script_path}")

    # Read script content
    try:
        script_content = script_path.read_text(encoding="utf-8")
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to read script file: {e}",
        }

    # Convert params dict to CLI args for sys.argv compatibility
    import json as json_module
    args = []
    for key, value in params.items():
        # Skip None values - don't pass them as arguments
        if value is None:
            continue

        # Handle boolean flags
        if isinstance(value, bool):
            if value:
                # Only pass the flag if True
                args.append(f"--{key.replace('_', '-')}")
            # If False, don't pass anything (argparse will use default)
        else:
            # Regular arguments with values
            args.append(f"--{key.replace('_', '-')}")
            # Use JSON encoding for lists/dicts to preserve structure
            if isinstance(value, (list, dict)):
                args.append(json_module.dumps(value))
            else:
                args.append(str(value))

    # Build parameter injection code
    injection_code = f"""import sys
import os
sys.argv = {repr([str(script_path)] + args)}
os.environ['UE_MCP_MODE'] = '1'

"""

    # Concatenate injection with script content
    full_code = injection_code + script_content

    # Execute full code with checks (enables hot-reload via file content reading)
    return manager.execute_with_checks(full_code, timeout=timeout)
