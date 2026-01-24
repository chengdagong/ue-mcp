"""
ProjectAnalyzer - Analyzes UE5 project structure and build status.

This subsystem handles project introspection including:
- Detecting C++ vs Blueprint-only projects
- Checking if project needs to be built
"""

import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .context import EditorContext

logger = logging.getLogger(__name__)


class ProjectAnalyzer:
    """
    Analyzes UE5 project structure and build requirements.

    This subsystem provides read-only analysis of the project without
    modifying any state.
    """

    def __init__(self, context: "EditorContext"):
        """
        Initialize ProjectAnalyzer.

        Args:
            context: Shared editor context
        """
        self._ctx = context

    def is_cpp_project(self) -> bool:
        """
        Check if the project is a C++ project.

        Returns:
            True if project has a 'Source' directory or C++ plugins, False otherwise.
        """
        # Check project's own Source directory
        source_dir = self._ctx.project_root / "Source"
        if source_dir.exists() and source_dir.is_dir():
            return True

        # Check for C++ plugins in Plugins directory
        plugins_dir = self._ctx.project_root / "Plugins"
        if plugins_dir.exists() and plugins_dir.is_dir():
            for plugin_dir in plugins_dir.iterdir():
                if plugin_dir.is_dir():
                    plugin_source = plugin_dir / "Source"
                    if plugin_source.exists() and plugin_source.is_dir():
                        return True

        return False

    def needs_build(self) -> tuple[bool, str]:
        """
        Check if the project needs to be built.

        Returns:
            Tuple of (needs_build, reason)
        """
        if not self.is_cpp_project():
            return False, ""

        project_root = self._ctx.project_root
        project_name = self._ctx.project_name

        # Check project's own binary
        dll_name = f"UnrealEditor-{project_name}.dll"
        dll_path = project_root / "Binaries" / "Win64" / dll_name

        # For projects with Source directory, check project binary
        source_dir = project_root / "Source"
        if source_dir.exists() and source_dir.is_dir():
            if not dll_path.exists():
                return True, f"Project binary not found: {dll_name}"

            # Check modification times for project source
            try:
                dll_mtime = dll_path.stat().st_mtime
                latest_source_mtime = 0.0
                latest_source_file = ""

                for root, _, files in os.walk(source_dir):
                    for file in files:
                        if file.endswith((".cpp", ".h", ".cs")):
                            file_path = Path(root) / file
                            mtime = file_path.stat().st_mtime
                            if mtime > latest_source_mtime:
                                latest_source_mtime = mtime
                                latest_source_file = file

                if latest_source_mtime > dll_mtime:
                    return True, f"Source file '{latest_source_file}' is newer than project binary"

            except Exception as e:
                logger.warning(f"Error checking project build status: {e}")

        # Check C++ plugins
        plugins_dir = project_root / "Plugins"
        if plugins_dir.exists() and plugins_dir.is_dir():
            for plugin_dir in plugins_dir.iterdir():
                if not plugin_dir.is_dir():
                    continue

                plugin_source = plugin_dir / "Source"
                if not plugin_source.exists() or not plugin_source.is_dir():
                    continue

                plugin_name = plugin_dir.name
                plugin_dll = plugin_dir / "Binaries" / "Win64" / f"UnrealEditor-{plugin_name}.dll"
                alternative_plugin_dll = (
                    plugin_dir
                    / "Binaries"
                    / "Win64"
                    / f"UnrealEditor-{plugin_name.replace('-', '')}.dll"
                )

                if not plugin_dll.exists() and not alternative_plugin_dll.exists():
                    return True, f"Plugin '{plugin_name}' binary not found"

                # Check if plugin source is newer than binary
                try:
                    plugin_dll_mtime = plugin_dll.stat().st_mtime
                    latest_plugin_source_mtime = 0.0
                    latest_plugin_source_file = ""

                    for root, _, files in os.walk(plugin_source):
                        for file in files:
                            if file.endswith((".cpp", ".h", ".cs")):
                                file_path = Path(root) / file
                                mtime = file_path.stat().st_mtime
                                if mtime > latest_plugin_source_mtime:
                                    latest_plugin_source_mtime = mtime
                                    latest_plugin_source_file = file

                    if latest_plugin_source_mtime > plugin_dll_mtime:
                        return (
                            True,
                            f"Plugin '{plugin_name}' source file '{latest_plugin_source_file}' is newer than binary",
                        )

                except Exception as e:
                    logger.warning(f"Error checking plugin '{plugin_name}' build status: {e}")

        return False, ""
