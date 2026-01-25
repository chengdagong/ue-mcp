"""
Script execution module for UE-MCP.
Handles searching, loading, and parameter injection for standalone Python scripts.

Uses true EXECUTE_FILE mode with environment variable parameter passing:
1. Inject parameters via environment variables (EXECUTE_STATEMENT)
2. Execute script file directly (EXECUTE_FILE)

Scripts read parameters via bootstrap_from_env() which converts env vars to sys.argv.
"""
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .tools._helpers import build_env_injection_code

if TYPE_CHECKING:
    from .editor.execution_manager import ExecutionManager


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
    execution: "ExecutionManager",
    script_name: str,
    params: dict[str, Any],
    timeout: float = 120.0
) -> dict[str, Any]:
    """
    Execute a capture script in the UE editor using true EXECUTE_FILE mode.

    This enables true hot-reload: the script file is executed directly from disk
    by UE5, so modifications take effect immediately without restarting.

    Args:
        execution: ExecutionManager instance
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
    return execute_script_from_path(execution, script_path, params, timeout)


def execute_script_from_path(
    execution: "ExecutionManager",
    script_path: Path | str,
    params: dict[str, Any],
    timeout: float = 120.0
) -> dict[str, Any]:
    """
    Execute a script from a specific path in the UE editor using true EXECUTE_FILE mode.

    This enables true hot-reload: the script file is executed directly from disk
    by UE5, so modifications take effect immediately without restarting.

    Execution flow:
    1. Inject parameters via environment variables (EXECUTE_STATEMENT)
    2. Execute script file directly (EXECUTE_FILE) - UE5 reads file from disk

    Scripts must call bootstrap_from_env() at the start of main() to read
    parameters from env vars and set up sys.argv for argparse.

    Args:
        execution: ExecutionManager instance
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

    # Step 1: Inject parameters via environment variables
    injection_code = build_env_injection_code(str(script_path), params)
    inject_result = execution.execute_code(injection_code, timeout=5.0)

    if not inject_result.get("success"):
        return {
            "success": False,
            "error": f"Failed to inject parameters: {inject_result.get('error')}",
        }

    # Step 2: Execute script file directly (true hot-reload)
    # UE5 reads the file from disk, so any modifications take effect immediately
    return execution.execute_script_file(str(script_path), timeout=timeout)
