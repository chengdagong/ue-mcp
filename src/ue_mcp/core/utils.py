"""
UE-MCP Utility Functions

Path discovery and UE5 installation detection utilities.
"""

import os
import platform
from pathlib import Path
from typing import Optional


def find_ue5_project_root(start_dir: Optional[Path] = None) -> Optional[Path]:
    """
    Find UE5 project root by searching for .uproject file upward from start_dir.

    Args:
        start_dir: Starting directory for search (defaults to cwd)

    Returns:
        Path to project root directory containing .uproject file, or None if not found
    """
    if start_dir is None:
        start_dir = Path.cwd()

    current = Path(start_dir).resolve()

    while True:
        try:
            uprojects = list(current.glob("*.uproject"))
            if uprojects:
                return current
        except OSError:
            pass

        parent = current.parent
        if parent == current:
            return None
        current = parent


def find_uproject_file(start_dir: Optional[Path] = None) -> Optional[Path]:
    """
    Find .uproject file by searching upward from start_dir.

    Search order:
    1. CLAUDE_PROJECT_DIR environment variable (if set)
    2. start_dir parameter or cwd

    Args:
        start_dir: Starting directory for search (defaults to cwd)

    Returns:
        Path to .uproject file, or None if not found
    """
    # Check CLAUDE_PROJECT_DIR environment variable first
    claude_project_dir = os.environ.get("CLAUDE_PROJECT_DIR")
    if claude_project_dir:
        project_root = find_ue5_project_root(Path(claude_project_dir))
        if project_root is not None:
            uprojects = list(project_root.glob("*.uproject"))
            if uprojects:
                return uprojects[0]

    # Fall back to start_dir or cwd
    project_root = find_ue5_project_root(start_dir)
    if project_root is None:
        return None

    uprojects = list(project_root.glob("*.uproject"))
    return uprojects[0] if uprojects else None


def get_project_name(uproject_path: Path) -> str:
    """
    Get project name from .uproject file path.

    Args:
        uproject_path: Path to .uproject file

    Returns:
        Project name (filename without extension)
    """
    return uproject_path.stem


def _get_ue5_search_roots() -> list[Path]:
    """Get common UE5 installation search roots based on platform."""
    system = platform.system()

    if system == "Windows":
        program_files = os.environ.get("ProgramFiles", "C:\\Program Files")
        return [
            Path(program_files) / "Epic Games",
            Path("D:\\Epic Games"),
            Path("E:\\Epic Games"),
            Path("C:\\Epic Games"),
        ]
    elif system == "Darwin":  # macOS
        return [
            Path("/Users/Shared/Epic Games"),
            Path.home() / "Epic Games",
        ]
    else:  # Linux
        return [
            Path.home() / "Epic Games",
            Path("/opt/Epic Games"),
        ]


def _find_ue5_installations() -> list[Path]:
    """Find all UE5 installation directories, sorted by version (newest first)."""
    search_roots = _get_ue5_search_roots()
    installations = []

    for base_path in search_roots:
        if not base_path.exists():
            continue

        try:
            for item in base_path.iterdir():
                if item.is_dir() and item.name.startswith("UE_5"):
                    installations.append(item)
        except OSError:
            pass

    installations.sort(key=lambda p: p.name, reverse=True)
    return installations


def find_ue5_editor() -> Optional[Path]:
    """
    Find the latest installed UE5 Editor executable.

    Returns:
        Path to UnrealEditor executable or None if not found
    """
    system = platform.system()

    for install_dir in _find_ue5_installations():
        if system == "Windows":
            editor_path = install_dir / "Engine" / "Binaries" / "Win64" / "UnrealEditor.exe"
        elif system == "Darwin":
            editor_path = (
                install_dir
                / "Engine"
                / "Binaries"
                / "Mac"
                / "UnrealEditor.app"
                / "Contents"
                / "MacOS"
                / "UnrealEditor"
            )
        else:  # Linux
            editor_path = install_dir / "Engine" / "Binaries" / "Linux" / "UnrealEditor"

        if editor_path.exists():
            return editor_path

    return None


def find_ue5_editor_for_project(uproject_path: Path) -> Optional[Path]:
    """
    Find UE5 Editor executable that matches the project's engine version.

    For now, this just returns the latest installed editor.
    Future improvement: parse .uproject to get EngineAssociation and find matching editor.

    Args:
        uproject_path: Path to .uproject file

    Returns:
        Path to UnrealEditor executable or None if not found
    """
    # TODO: Parse uproject_path to get EngineAssociation
    # and find the specific engine version
    return find_ue5_editor()


def find_ue5_python() -> Optional[Path]:
    """
    Find the latest installed UE5 Python executable.

    Returns:
        Path to Python executable or None if not found
    """
    system = platform.system()

    for install_dir in _find_ue5_installations():
        if system == "Windows":
            python_path = (
                install_dir
                / "Engine"
                / "Binaries"
                / "ThirdParty"
                / "Python3"
                / "Win64"
                / "python.exe"
            )
        elif system == "Darwin":
            python_path = (
                install_dir
                / "Engine"
                / "Binaries"
                / "ThirdParty"
                / "Python3"
                / "Mac"
                / "bin"
                / "python3"
            )
        else:  # Linux
            python_path = (
                install_dir
                / "Engine"
                / "Binaries"
                / "ThirdParty"
                / "Python3"
                / "Linux"
                / "bin"
                / "python3"
            )

        if python_path.exists():
            return python_path

    return None


def find_ue5_python_for_editor(editor_path: Path) -> Optional[Path]:
    """
    Find the UE5 Python executable corresponding to the given editor.

    Args:
        editor_path: Path to UnrealEditor executable

    Returns:
        Path to Python executable or None if not found
    """
    system = platform.system()
    engine_binaries = editor_path.parent.parent.parent

    if system == "Windows":
        python_path = engine_binaries / "ThirdParty" / "Python3" / "Win64" / "python.exe"
    elif system == "Darwin":
        # editor_path is usually .../Engine/Binaries/Mac/UnrealEditor.app/Contents/MacOS/UnrealEditor
        # engine_binaries is .../Engine/Binaries
        python_path = engine_binaries / "ThirdParty" / "Python3" / "Mac" / "bin" / "python3"
    else:  # Linux
        python_path = engine_binaries / "ThirdParty" / "Python3" / "Linux" / "bin" / "python3"

    if python_path.exists():
        return python_path

    return find_ue5_python()


def find_ue5_build_batch_file() -> Optional[Path]:
    """
    Find the UE5 Build.bat file for running UnrealBuildTool.

    Returns:
        Path to Build.bat or None if not found
    """
    system = platform.system()

    for install_dir in _find_ue5_installations():
        if system == "Windows":
            build_bat = install_dir / "Engine" / "Build" / "BatchFiles" / "Build.bat"
        elif system == "Darwin":
            build_bat = install_dir / "Engine" / "Build" / "BatchFiles" / "Mac" / "Build.sh"
        else:  # Linux
            build_bat = install_dir / "Engine" / "Build" / "BatchFiles" / "Linux" / "Build.sh"

        if build_bat.exists():
            return build_bat

    return None


def find_ue5_runuat() -> Optional[Path]:
    """
    Find the UE5 RunUAT script for running Unreal Automation Tool.

    Returns:
        Path to RunUAT.bat/.sh or None if not found
    """
    system = platform.system()

    for install_dir in _find_ue5_installations():
        if system == "Windows":
            runuat = install_dir / "Engine" / "Build" / "BatchFiles" / "RunUAT.bat"
        elif system == "Darwin":
            runuat = install_dir / "Engine" / "Build" / "BatchFiles" / "RunUAT.sh"
        else:  # Linux
            runuat = install_dir / "Engine" / "Build" / "BatchFiles" / "RunUAT.sh"

        if runuat.exists():
            return runuat

    return None


def get_ue5_engine_root(uproject_path: Optional[Path] = None) -> Optional[Path]:
    """
    Get the UE5 engine root directory.

    Args:
        uproject_path: Optional path to .uproject file (for future engine association lookup)

    Returns:
        Path to UE5 engine root or None if not found
    """
    installations = _find_ue5_installations()
    if installations:
        return installations[0]
    return None
