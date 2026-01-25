"""
UE-MCP Pip Install Module

Utilities for installing Python packages in UE5's embedded Python environment.
"""

import ast
import logging
import re
import subprocess
from pathlib import Path
from typing import Any, Optional, Tuple

from .utils import find_ue5_python

logger = logging.getLogger(__name__)

# Common module name to package name mappings
MODULE_TO_PACKAGE = {
    "PIL": "Pillow",
    "cv2": "opencv-python",
    "sklearn": "scikit-learn",
    "yaml": "PyYAML",
    "bs4": "beautifulsoup4",
}

# Bundled modules in our custom site-packages that should be auto-reloaded
BUNDLED_MODULES = frozenset({"asset_diagnostic", "editor_capture"})


def extract_missing_module(error_text: str) -> Optional[str]:
    """
    Extract missing module name from an import error message.

    Args:
        error_text: Error message text that may contain import error

    Returns:
        Module name if found, None otherwise
    """
    # Pattern 1: "No module named 'xxx'" or "No module named \"xxx\""
    pattern1 = r"No module named ['\"]([^'\"]+)['\"]"
    match = re.search(pattern1, error_text)
    if match:
        module = match.group(1)
        # Handle submodule imports like 'PIL.Image' -> 'PIL'
        return module.split(".")[0]

    # Pattern 2: "ModuleNotFoundError: No module named xxx"
    pattern2 = r"ModuleNotFoundError:\s*No module named\s+(\S+)"
    match = re.search(pattern2, error_text)
    if match:
        module = match.group(1).strip("'\"")
        return module.split(".")[0]

    # Pattern 3: "ImportError: cannot import name 'xxx' from 'yyy'"
    pattern3 = r"ImportError: cannot import name ['\"]([^'\"]+)['\"] from ['\"]([^'\"]+)['\"]"
    match = re.search(pattern3, error_text)
    if match:
        return match.group(2).split(".")[0]

    return None


def module_to_package(module_name: str) -> str:
    """
    Convert module name to pip package name.

    Args:
        module_name: Python module name (e.g., 'PIL', 'cv2')

    Returns:
        Pip package name (e.g., 'Pillow', 'opencv-python')
    """
    return MODULE_TO_PACKAGE.get(module_name, module_name)


def extract_import_statements(code: str) -> Tuple[list[str], Optional[str]]:
    """
    Extract all import statements from Python code.

    Args:
        code: Python source code

    Returns:
        Tuple of (import_statements, error):
        - Success: (["import os", "from PIL import Image"], None)
        - Syntax error: ([], "SyntaxError: ...")
    """
    statements = []
    try:
        tree = ast.parse(code)
        lines = code.splitlines()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                # Get the original text of this statement
                if hasattr(node, "lineno") and hasattr(node, "end_lineno"):
                    start = node.lineno - 1
                    end = node.end_lineno
                    stmt = "\n".join(lines[start:end])
                    statements.append(stmt)
        return statements, None
    except SyntaxError as e:
        return [], f"SyntaxError: {e.msg} (line {e.lineno})"


def extract_bundled_module_imports(code: str) -> set[str]:
    """
    Extract bundled module imports from Python code using AST.

    Detects imports of modules from our custom site-packages (asset_diagnostic,
    editor_capture) so they can be reloaded before execution.

    Handles all import forms:
    - import module
    - import module.submodule
    - from module import name
    - from module.submodule import name

    Args:
        code: Python source code

    Returns:
        Set of top-level bundled module names that are imported
    """
    bundled_imports: set[str] = set()

    try:
        tree = ast.parse(code)
    except SyntaxError:
        # Syntax error will be caught by extract_import_statements
        return bundled_imports

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            # import X, import X.Y.Z
            for alias in node.names:
                top_level = alias.name.split(".")[0]
                if top_level in BUNDLED_MODULES:
                    bundled_imports.add(top_level)

        elif isinstance(node, ast.ImportFrom):
            # from X import Y, from X.Y import Z
            if node.module:
                top_level = node.module.split(".")[0]
                if top_level in BUNDLED_MODULES:
                    bundled_imports.add(top_level)

    return bundled_imports


def generate_module_unload_code(modules: set[str]) -> str:
    """
    Generate Python code to remove modules from sys.modules.

    This ensures fresh import of the bundled modules when the code executes.
    Removes both the top-level module and all submodules (anything starting
    with 'module.').

    Args:
        modules: Set of top-level module names to unload

    Returns:
        Python code that removes matching modules from sys.modules,
        or empty string if no modules to unload
    """
    if not modules:
        return ""

    modules_list = sorted(modules)  # Sort for deterministic output

    return f"""import sys as _sys
_bundled_to_unload = {modules_list!r}
_keys_to_remove = [_k for _k in list(_sys.modules.keys()) if any(_k == _m or _k.startswith(_m + '.') for _m in _bundled_to_unload)]
for _k in _keys_to_remove:
    del _sys.modules[_k]
del _bundled_to_unload, _keys_to_remove, _sys
"""


def pip_install(
    packages: list[str],
    python_path: Optional[Path] = None,
    upgrade: bool = False,
    timeout: float = 300.0,
) -> dict[str, Any]:
    """
    Install Python packages using UE5's embedded pip.

    Args:
        packages: List of package names to install
        python_path: Path to UE5's Python executable (auto-detected if not provided)
        upgrade: Whether to upgrade existing packages
        timeout: Installation timeout in seconds

    Returns:
        Result dictionary with success status and output
    """
    if not packages:
        return {"success": True, "message": "No packages to install"}

    # Find UE5 Python
    if python_path is None:
        python_path = find_ue5_python()

    if python_path is None:
        return {
            "success": False,
            "error": "Could not find UE5 Python executable",
        }

    if not python_path.exists():
        return {
            "success": False,
            "error": f"UE5 Python not found at: {python_path}",
        }

    # Build pip command
    cmd = [str(python_path), "-m", "pip", "install"]
    if upgrade:
        cmd.append("--upgrade")
    cmd.extend(packages)

    logger.info(f"Installing packages: {', '.join(packages)}")
    logger.info(f"Using Python: {python_path}")
    logger.debug(f"Command: {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        if result.returncode == 0:
            logger.info(f"Successfully installed: {', '.join(packages)}")
            return {
                "success": True,
                "packages": packages,
                "output": result.stdout,
                "python_path": str(python_path),
            }
        else:
            logger.error(f"pip install failed: {result.stderr}")
            return {
                "success": False,
                "error": f"pip install failed with exit code {result.returncode}",
                "packages": packages,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "python_path": str(python_path),
            }

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": f"Installation timed out after {timeout} seconds",
            "packages": packages,
        }
    except Exception as e:
        logger.error(f"pip install error: {e}")
        return {
            "success": False,
            "error": str(e),
            "packages": packages,
        }


def pip_list(python_path: Optional[Path] = None) -> dict[str, Any]:
    """
    List installed packages in UE5's Python environment.

    Args:
        python_path: Path to UE5's Python executable (auto-detected if not provided)

    Returns:
        Result dictionary with installed packages
    """
    if python_path is None:
        python_path = find_ue5_python()

    if python_path is None:
        return {
            "success": False,
            "error": "Could not find UE5 Python executable",
        }

    try:
        result = subprocess.run(
            [str(python_path), "-m", "pip", "list", "--format=json"],
            capture_output=True,
            text=True,
            timeout=30.0,
        )

        if result.returncode == 0:
            import json

            packages = json.loads(result.stdout)
            return {
                "success": True,
                "packages": packages,
                "python_path": str(python_path),
            }
        else:
            return {
                "success": False,
                "error": f"pip list failed: {result.stderr}",
            }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


def _process_output(output: Any) -> str:
    """
    Process execution output into a single string, handling list of strings or dicts.
    """
    if isinstance(output, list):
        processed_lines = []
        for line in output:
            if isinstance(line, dict):
                processed_lines.append(str(line.get("output", "")))
            else:
                processed_lines.append(str(line))
        return "\n".join(processed_lines)
    return str(output)


def is_import_error(result: dict[str, Any]) -> bool:
    """
    Check if an execution result contains an import/module error.

    Args:
        result: Execution result dictionary from ExecutionManager.execute_code()

    Returns:
        True if the result indicates a missing module error
    """
    if result.get("success", False):
        return False

    error = result.get("error", "")
    output = _process_output(result.get("output", ""))
    # UE remote execution puts Python traceback in 'result' field
    ue_result = str(result.get("result", ""))

    combined = f"{error}\n{output}\n{ue_result}"

    # Check for import error patterns
    patterns = [
        r"No module named",
        r"ModuleNotFoundError",
        r"ImportError.*cannot import name",
    ]

    for pattern in patterns:
        if re.search(pattern, combined, re.IGNORECASE):
            return True

    return False


def get_missing_module_from_result(result: dict[str, Any]) -> Optional[str]:
    """
    Extract missing module name from an execution result.

    Args:
        result: Execution result dictionary from ExecutionManager.execute_code()

    Returns:
        Module name if found, None otherwise
    """
    error = result.get("error", "")
    output = _process_output(result.get("output", ""))
    # UE remote execution puts Python traceback in 'result' field
    ue_result = str(result.get("result", ""))

    combined = f"{error}\n{output}\n{ue_result}"
    return extract_missing_module(combined)
