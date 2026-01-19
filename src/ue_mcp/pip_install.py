"""
UE-MCP Pip Install Module

Utilities for installing Python packages in UE5's embedded Python environment.
"""

import logging
import re
import subprocess
from pathlib import Path
from typing import Any, Optional

from .utils import find_ue5_python, find_ue5_python_for_editor

logger = logging.getLogger(__name__)

# Common module name to package name mappings
MODULE_TO_PACKAGE = {
    "PIL": "Pillow",
    "cv2": "opencv-python",
    "sklearn": "scikit-learn",
    "yaml": "PyYAML",
    "bs4": "beautifulsoup4",
}


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


def is_import_error(result: dict[str, Any]) -> bool:
    """
    Check if an execution result contains an import/module error.

    Args:
        result: Execution result dictionary from EditorManager.execute()

    Returns:
        True if the result indicates a missing module error
    """
    if result.get("success", False):
        return False

    error = result.get("error", "")
    output = result.get("output", "")

    # Combine error and output for checking
    if isinstance(output, list):
        output = "\n".join(output)

    combined = f"{error}\n{output}"

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
        result: Execution result dictionary from EditorManager.execute()

    Returns:
        Module name if found, None otherwise
    """
    error = result.get("error", "")
    output = result.get("output", "")

    # Combine error and output
    if isinstance(output, list):
        output = "\n".join(output)

    combined = f"{error}\n{output}"
    return extract_missing_module(combined)
