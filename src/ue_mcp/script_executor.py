"""
Script execution module for UE-MCP.
Handles searching, loading, and parameter injection for standalone Python scripts.
"""
import json
from pathlib import Path
from typing import Any


def get_scripts_dir() -> Path:
    """Get the capture scripts directory."""
    return Path(__file__).parent / "extra" / "scripts" / "ue_mcp_capture"


def get_diagnostic_scripts_dir() -> Path:
    """Get the diagnostic scripts directory."""
    return Path(__file__).parent / "extra" / "scripts" / "diagnostic"


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
    
    # Prepend parameters as __PARAMS__ variable (JSON injected as dict)
    # We use json.dumps ensures proper Python syntax for dict literals (mostly)
    # but we are injecting it as code, so 'true' becomes 'true' (invalid python)
    # No, wait. json.dumps produces valid JSON which is ALMOST valid Python.
    # But 'true' in JSON is 'true', in Python it is 'True'.
    # Actually, we can just repr() the dict? 
    # repr({'a': True}) -> "{'a': True}" which is valid python code.
    # Let's use repr() for safer python code generation than json.dumps
    
    # Inject __PARAMS__ into builtins so it's accessible from any module
    # This is necessary because utils.py imports get_params() which needs access to __PARAMS__
    # Simply defining __PARAMS__ in the script's global scope won't make it visible to imported modules
    params_code = (
        "import builtins\n"
        f"builtins.__PARAMS__ = {repr(params)}\n"
        f"__PARAMS__ = builtins.__PARAMS__\n\n"
    )
    
    # We also need to add the scripts directory to sys.path so imports work
    # The 'extra/scripts' directory is creating a package structure 'capture'
    # So we should add the PARENT of 'capture' directory to sys.path
    # i.e. .../src/ue_mcp/extra/scripts
    
    # However, 'extra/scripts' contains 'site-packages', 'scripts', etc.
    # In server.py we typically add 'get_bundled_site_packages()' to path.
    # We should also add the directory containing our 'ue_mcp_capture' package.
    
    # Our scripts do `from ue_mcp_capture.utils import ...`
    # So we need to add `.../src/ue_mcp/extra/scripts` to sys.path
    
    scripts_base_dir = scripts_dir.parent
    sys_path_code = (
        "import sys\n"
        f"if r'{scripts_base_dir}' not in sys.path:\n"
        f"    sys.path.insert(0, r'{scripts_base_dir}')\n\n"
    )
    
    full_code = sys_path_code + params_code + script_content
    
    return manager.execute_with_auto_install(full_code, timeout=timeout)
