"""
BuildManager - Manages UE5 project building.

This subsystem handles:
- Building UE5 projects using UnrealBuildTool
- Synchronous and asynchronous build modes
- Build progress tracking and notifications
"""

import asyncio
import logging
import os
import re
import subprocess
import time
from typing import TYPE_CHECKING, Any, Optional

from ..core.utils import find_ue5_build_batch_file
from .types import NotifyCallback, ProgressCallback

if TYPE_CHECKING:
    from .context import EditorContext
    from .project_analyzer import ProjectAnalyzer

logger = logging.getLogger(__name__)


class BuildManager:
    """
    Manages UE5 project building using UnrealBuildTool.

    This subsystem handles both synchronous and asynchronous builds with
    real-time progress tracking.
    """

    def __init__(self, context: "EditorContext", project_analyzer: "ProjectAnalyzer"):
        """
        Initialize BuildManager.

        Args:
            context: Shared editor context
            project_analyzer: ProjectAnalyzer for checking C++ project status
        """
        self._ctx = context
        self._project_analyzer = project_analyzer

    async def build(
        self,
        notify: Optional[NotifyCallback] = None,
        progress: Optional[ProgressCallback] = None,
        target: str = "Editor",
        configuration: str = "Development",
        platform: str = "Win64",
        clean: bool = False,
        timeout: float = 1800.0,
        verbose: bool = False,
    ) -> dict[str, Any]:
        """
        Build the UE5 project using UnrealBuildTool (synchronous, but async implementation).

        Args:
            notify: Optional async callback to send notifications
            progress: Optional async callback to report progress
            target: Build target - "Editor", "Game", "Client", or "Server" (default: "Editor")
            configuration: Build configuration - "Debug", "DebugGame", "Development",
                          "Shipping", or "Test" (default: "Development")
            platform: Target platform - "Win64", "Mac", "Linux", etc. (default: "Win64")
            clean: Whether to perform a clean build (default: False)
            timeout: Build timeout in seconds (default: 1800 = 30 minutes)
            verbose: Whether to send all build logs via notify (default: False)

        Returns:
            Build result dictionary containing:
            - success: Whether build succeeded
            - output: Build output/log
            - return_code: Process return code
            - error: Error message (if failed)
        """
        # Check if C++ project
        if not self._project_analyzer.is_cpp_project():
            logger.info(
                f"Project {self._ctx.project_name} is a Blueprint-only project. Skipping build."
            )
            return {
                "success": True,
                "message": f"Project '{self._ctx.project_name}' is a Blueprint-only project (no Source directory or C++ plugins). No C++ compilation required.",
                "is_cpp": False,
            }

        # Helper for null notify
        async def null_notify(level: str, message: str) -> None:
            pass

        actual_notify = notify or null_notify

        # Find Build.bat
        build_script = find_ue5_build_batch_file()
        if build_script is None:
            return {
                "success": False,
                "error": "Could not find UE5 Build script (Build.bat/Build.sh)",
            }

        # Construct build target name
        if target == "Editor":
            target_name = f"{self._ctx.project_name}Editor"
        elif target == "Game":
            target_name = self._ctx.project_name
        else:
            target_name = f"{self._ctx.project_name}{target}"

        # Build command line arguments
        cmd = [str(build_script), target_name, platform, configuration]
        cmd.extend([f"-Project={self._ctx.project_path}"])
        cmd.append("-WaitMutex")

        if clean:
            cmd.append("-Clean")

        logger.info(f"Building project: {self._ctx.project_name}")
        logger.info(f"Target: {target_name}, Platform: {platform}, Configuration: {configuration}")

        # Run build and wait for result
        return await self._run_build_async(
            cmd=cmd,
            notify=actual_notify,
            progress=progress,
            target_name=target_name,
            platform=platform,
            configuration=configuration,
            timeout=timeout,
            verbose=verbose,
        )

    async def build_async(
        self,
        notify: NotifyCallback,
        progress: Optional[ProgressCallback] = None,
        target: str = "Editor",
        configuration: str = "Development",
        platform: str = "Win64",
        clean: bool = False,
        timeout: float = 1800.0,
        verbose: bool = False,
    ) -> dict[str, Any]:
        """
        Build the UE5 project asynchronously using UnrealBuildTool.

        This method returns immediately and sends notifications via the callback
        as the build progresses.

        Args:
            notify: Async callback function(level, message) to send notifications
            progress: Optional async callback function(current, total) to report progress
            target: Build target - "Editor", "Game", "Client", or "Server" (default: "Editor")
            configuration: Build configuration - "Debug", "DebugGame", "Development",
                          "Shipping", or "Test" (default: "Development")
            platform: Target platform - "Win64", "Mac", "Linux", etc. (default: "Win64")
            clean: Whether to perform a clean build (default: False)
            timeout: Build timeout in seconds (default: 1800 = 30 minutes)
            verbose: Whether to send all build logs via notify (default: False)

        Returns:
            Initial build result (build started)
        """
        # Check if C++ project
        if not self._project_analyzer.is_cpp_project():
            logger.info(
                f"Project {self._ctx.project_name} is a Blueprint-only project. Skipping build."
            )
            return {
                "success": True,
                "message": f"Project '{self._ctx.project_name}' is a Blueprint-only project (no Source directory or C++ plugins). No C++ compilation required.",
                "is_cpp": False,
            }

        # Find Build.bat
        build_script = find_ue5_build_batch_file()
        if build_script is None:
            return {
                "success": False,
                "error": "Could not find UE5 Build script (Build.bat/Build.sh)",
            }

        # Construct build target name
        if target == "Editor":
            target_name = f"{self._ctx.project_name}Editor"
        elif target == "Game":
            target_name = self._ctx.project_name
        else:
            target_name = f"{self._ctx.project_name}{target}"

        # Build command line arguments
        cmd = [str(build_script), target_name, platform, configuration]
        cmd.extend([f"-Project={self._ctx.project_path}"])
        cmd.append("-WaitMutex")

        if clean:
            cmd.append("-Clean")

        logger.info(f"Building project asynchronously: {self._ctx.project_name}")
        logger.info(f"Target: {target_name}, Platform: {platform}, Configuration: {configuration}")

        # Start background build task
        self._ctx.create_background_task(
            self._run_build_async(
                cmd=cmd,
                notify=notify,
                progress=progress,
                target_name=target_name,
                platform=platform,
                configuration=configuration,
                timeout=timeout,
                verbose=verbose,
            )
        )

        return {
            "success": True,
            "message": f"Build started for {target_name} ({platform} {configuration})",
            "target": target_name,
            "platform": platform,
            "configuration": configuration,
        }

    async def _run_build_async(
        self,
        cmd: list[str],
        notify: NotifyCallback,
        target_name: str,
        platform: str,
        configuration: str,
        timeout: float,
        progress: Optional[ProgressCallback] = None,
        verbose: bool = False,
    ) -> dict[str, Any]:
        """
        Background task to run build process and send notifications.

        Args:
            cmd: Build command line
            notify: Async callback to send notifications
            progress: Optional async callback to report progress
            target_name: Build target name for messages
            platform: Target platform for messages
            configuration: Build configuration for messages
            timeout: Build timeout in seconds
            verbose: Whether to send all build logs via notify

        Returns:
            Build result dictionary
        """

        # Helper to safely send notifications without raising
        async def safe_notify(level: str, message: str) -> None:
            try:
                await notify(level, message)
            except Exception as notify_err:
                logger.warning(f"Failed to send notification: {notify_err}")

        try:
            # On Windows, hide the console window to prevent it from stealing focus
            # and potentially causing subprocess hangs
            import sys

            kwargs: dict[str, Any] = {
                "stdin": asyncio.subprocess.DEVNULL,
                "stdout": asyncio.subprocess.PIPE,
                "stderr": asyncio.subprocess.STDOUT,
                "cwd": str(self._ctx.project_root),
            }
            if sys.platform == "win32":
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
                # Ensure TMP environment variable is set for Build.bat
                # MCP clients may not inherit TMP, only TEMP, which causes
                # Build.bat's lock mechanism to fail (it uses %tmp% for lock file path)
                env = dict(os.environ)
                if "TMP" not in env and "TEMP" in env:
                    env["TMP"] = env["TEMP"]
                    logger.debug(f"Set TMP={env['TMP']} for build subprocess")
                kwargs["env"] = env

            process = await asyncio.create_subprocess_exec(*cmd, **kwargs)
            logger.info(f"Build subprocess started (PID: {process.pid})")
        except Exception as e:
            logger.error(f"Failed to start build process: {e}")
            await safe_notify("error", f"Failed to start build: {e}")
            return {
                "success": False,
                "error": str(e),
            }

        # Read output with timeout
        output_lines: list[str] = []
        start_time = time.time()
        build_error: Optional[str] = None

        try:
            while True:
                if time.time() - start_time > timeout:
                    if process.returncode is None:
                        process.kill()
                    await safe_notify("error", f"Build timed out after {timeout} seconds")
                    return {
                        "success": False,
                        "error": f"Build timed out after {timeout} seconds",
                        "output": "\n".join(output_lines),
                    }

                try:
                    line = await asyncio.wait_for(process.stdout.readline(), timeout=1.0)
                    if not line:
                        break
                    line_str = line.decode("utf-8", errors="replace").rstrip()
                    output_lines.append(line_str)

                    # Parse progress like [1/50]
                    if progress:
                        match = re.search(r"\[(\d+)/(\d+)\]", line_str)
                        if match:
                            current = int(match.group(1))
                            total = int(match.group(2))
                            await progress(current, total)

                    # Send progress notifications for important lines or all if verbose
                    if verbose:
                        await safe_notify("info", line_str)
                    elif any(
                        keyword in line_str.lower()
                        for keyword in ["error", "warning", "building", "compiling", "linking"]
                    ):
                        await safe_notify("info", line_str[:200])  # Truncate long lines
                except asyncio.TimeoutError:
                    if process.returncode is not None:
                        break
                    continue

        except Exception as e:
            build_error = str(e)
            logger.error(f"Build process error: {e}")

        # Wait for process to complete
        try:
            await process.wait()
        except Exception:
            pass

        return_code = process.returncode
        elapsed = time.time() - start_time
        stdout = "\n".join(output_lines)

        # Handle build error during output reading
        if build_error:
            await safe_notify("error", f"Build process error: {build_error}")
            return {
                "success": False,
                "error": build_error,
                "output": stdout,
            }

        # Return result based on return code
        if return_code == 0:
            await safe_notify(
                "info",
                f"Build completed successfully! "
                f"({target_name} {platform} {configuration}, {elapsed:.1f}s)",
            )
            return {
                "success": True,
                "output": stdout,
                "return_code": 0,
                "elapsed": elapsed,
            }
        else:
            # Find error lines for notification
            error_lines = [line for line in output_lines if "error" in line.lower()][:5]
            error_summary = "\n".join(error_lines) if error_lines else "Check build log"
            await safe_notify(
                "error", f"Build failed (return code: {return_code}). Errors:\n{error_summary}"
            )
            return {
                "success": False,
                "output": stdout,
                "return_code": return_code,
                "error": error_summary,
                "elapsed": elapsed,
            }
