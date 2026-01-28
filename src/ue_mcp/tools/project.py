"""Project management tools."""

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any

from fastmcp import Context
from pydantic import Field

if TYPE_CHECKING:
    from fastmcp import FastMCP

    from ..state import ServerState

logger = logging.getLogger(__name__)


def register_tools(mcp: "FastMCP", state: "ServerState") -> None:
    """Register project management tools."""

    from ..editor.subsystems import EditorSubsystems
    from ..core.utils import find_uproject_file

    @mcp.tool(name="project_set_path")
    def set_project_path(
        project_path: Annotated[
            str,
            Field(description="Absolute path to the directory containing the .uproject file"),
        ],
    ) -> dict[str, Any]:
        """
        Set the UE5 project path for the MCP server.

        This tool can be called from any directory to specify which UE5 project to use.
        It can be called multiple times - if an editor is running, it will be stopped first.

        Args:
            project_path: Absolute path to the directory containing the .uproject file

        Returns:
            Result with success status and detected project information
        """
        # Validate path first
        project_dir = Path(project_path)
        if not project_dir.exists():
            return {"success": False, "error": f"Path does not exist: {project_path}"}

        if not project_dir.is_dir():
            return {
                "success": False,
                "error": f"Path is not a directory: {project_path}",
            }

        # Find .uproject file in the specified directory
        uproject_path = find_uproject_file(start_dir=project_dir)
        if uproject_path is None:
            return {
                "success": False,
                "error": f"No .uproject file found in: {project_path}",
            }

        # Check if we already have a project set
        previous_project = None
        editor_stopped = False
        if state.subsystems is not None:
            previous_project = state.subsystems.project_name
            # Check if editor is running and stop it
            context = state.subsystems.context
            if context.is_running():
                logger.info(f"Stopping running editor for project: {previous_project}")
                health_monitor = state.subsystems.health_monitor
                stop_result = context.stop(health_monitor=health_monitor)
                if stop_result.get("success"):
                    editor_stopped = True
                    logger.info("Editor stopped successfully")
                else:
                    logger.warning(f"Failed to stop editor: {stop_result.get('error')}")

        # Initialize new EditorSubsystems
        logger.info(f"Setting project path: {uproject_path}")
        state.subsystems = EditorSubsystems.create(uproject_path)
        state.project_path_set = True

        result: dict[str, Any] = {
            "success": True,
            "project_name": state.subsystems.project_name,
            "project_path": str(state.subsystems.project_root),
            "uproject_file": str(uproject_path),
        }

        if previous_project is not None:
            result["previous_project"] = previous_project
            result["editor_stopped"] = editor_stopped

        return result

    @mcp.tool(name="project_build")
    async def build_project(
        ctx: Context,
        target: Annotated[
            str,
            Field(
                default="Editor",
                description="Build target type: 'Editor', 'Game', 'Client', or 'Server'",
            ),
        ],
        configuration: Annotated[
            str,
            Field(
                default="Development",
                description="Build configuration: 'Debug', 'DebugGame', 'Development', 'Shipping', or 'Test'",
            ),
        ],
        platform: Annotated[
            str,
            Field(
                default="Win64",
                description="Target platform: 'Win64', 'Mac', 'Linux', etc.",
            ),
        ],
        clean: Annotated[
            bool,
            Field(
                default=False,
                description="Whether to perform a clean build (rebuilds everything)",
            ),
        ],
        wait: Annotated[
            bool,
            Field(default=True, description="Whether to wait for build to complete"),
        ],
        verbose: Annotated[
            bool,
            Field(
                default=False,
                description="Whether to stream all build logs via notifications",
            ),
        ],
        timeout: Annotated[
            float,
            Field(
                default=1800.0,
                description="Build timeout in seconds (default: 30 minutes)",
            ),
        ],
    ) -> dict[str, Any]:
        """
        Build the UE5 project using UnrealBuildTool.

        This tool compiles the project's C++ code. By default, it waits for the build
        to complete (synchronous) and reports real-time progress.

        Args:
            target: Build target type - one of:
                - "Editor": Build for editor (ProjectNameEditor) [default]
                - "Game": Build standalone game (ProjectName)
                - "Client": Build client target (ProjectNameClient)
                - "Server": Build dedicated server (ProjectNameServer)
            configuration: Build configuration - one of:
                - "Debug": Full debugging, no optimizations
                - "DebugGame": Game debugging, engine optimized
                - "Development": Development build with optimizations [default]
                - "Shipping": Final shipping build, fully optimized
                - "Test": Testing configuration
            platform: Target platform - "Win64" [default], "Mac", "Linux", etc.
            clean: Whether to perform a clean build (rebuilds everything) (default: False)
            wait: Whether to wait for build to complete (default: True)
            verbose: Whether to stream all build logs via notifications (default: False)
            timeout: Build timeout in seconds (default: 1800 = 30 minutes)

        Returns:
            If wait=True (default):
                - success: Whether build succeeded
                - output: Full build output/log
                - return_code: Process return code
                - error: Error message (if failed)

            If wait=False:
                - success: True if build started
                - message: Status message
                - target/platform/configuration: Build parameters

        Example:
            # Build project (waits for completion by default)
            build_project(target="Editor", configuration="Development")

            # Start build in background (returns immediately)
            build_project(target="Game", configuration="Shipping", wait=False)
        """
        build = state.get_build_subsystem()

        async def notify(level: str, message: str) -> None:
            await ctx.log(message, level=level)

        async def progress_callback(current: int, total: int) -> None:
            await ctx.report_progress(progress=current, total=total)

        if wait:
            # Synchronous build - wait for completion
            return await build.build(
                notify=notify,
                progress=progress_callback,
                target=target,
                configuration=configuration,
                platform=platform,
                clean=clean,
                timeout=timeout,
                verbose=verbose,
            )
        else:
            # Asynchronous build - return immediately
            return await build.build_async(
                notify=notify,
                progress=progress_callback,
                target=target,
                configuration=configuration,
                platform=platform,
                clean=clean,
                timeout=timeout,
                verbose=verbose,
            )
