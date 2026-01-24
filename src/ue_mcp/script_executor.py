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
    Execute a capture script in the UE editor.
    
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
    
    if not script_path.exists():
        raise FileNotFoundError(f"Script not found: {script_path}")
    
    try:
        script_content = script_path.read_text(encoding="utf-8")
    except Exception as e:
        raise RuntimeError(f"Failed to read script {script_path}: {e}")
    
    # Inject __PARAMS__ into builtins so it's accessible from any module
    # This is necessary because utils.py imports get_params() which needs access to __PARAMS__
    # Simply defining __PARAMS__ in the script's global scope won't make it visible to imported modules
    #
    # Note: The extra/scripts directory (containing ue_mcp_capture package) is automatically
    # added to UE5's Python path via autoconfig.py, so no sys.path manipulation needed here.
    params_code = (
        "import builtins\n"
        f"builtins.__PARAMS__ = {repr(params)}\n"
        f"__PARAMS__ = builtins.__PARAMS__\n\n"
    )

    full_code = params_code + script_content

    return manager.execute_with_checks(full_code, timeout=timeout)


def execute_script_from_path(
    manager,
    script_path: Path | str,
    params: dict[str, Any],
    timeout: float = 120.0
) -> dict[str, Any]:
    """
    Execute a script from a specific path in the UE editor.

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

    try:
        script_content = script_path.read_text(encoding="utf-8")
    except Exception as e:
        raise RuntimeError(f"Failed to read script {script_path}: {e}")

    # Inject __PARAMS__ into builtins so it's accessible from any module
    params_code = (
        "import builtins\n"
        f"builtins.__PARAMS__ = {repr(params)}\n"
        f"__PARAMS__ = builtins.__PARAMS__\n\n"
    )

    full_code = params_code + script_content

    return manager.execute_with_checks(full_code, timeout=timeout)
