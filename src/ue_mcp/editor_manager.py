"""
UE-MCP Editor Manager

Manages the lifecycle of a single Unreal Editor instance bound to a project.
"""

import asyncio
import atexit
import logging
import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Coroutine, Optional

from .autoconfig import run_config_check
from .pip_install import (
    extract_import_statements,
    get_missing_module_from_result,
    is_import_error,
    module_to_package,
    pip_install,
)
from .remote_client import RemoteExecutionClient
from .utils import (
    find_ue5_build_batch_file,
    find_ue5_editor_for_project,
    get_project_name,
)

logger = logging.getLogger(__name__)

NotifyCallback = Callable[[str, str], Coroutine[Any, Any, None]]
ProgressCallback = Callable[[int, int], Coroutine[Any, Any, None]]


@dataclass
class EditorInstance:
    """Represents a managed Unreal Editor instance."""

    process: subprocess.Popen
    started_at: datetime = field(default_factory=datetime.now)
    status: str = "starting"  # "starting" | "ready" | "stopped"
    remote_client: Optional[RemoteExecutionClient] = None
    node_id: Optional[str] = None  # UE5 remote execution node ID


class EditorManager:
    """
    Manages a single Unreal Editor instance for a bound project.

    This class is designed for one-to-one binding: one EditorManager per project.
    """

    def __init__(self, project_path: Path):
        """
        Initialize EditorManager.

        Args:
            project_path: Path to the .uproject file
        """
        self.project_path = project_path.resolve()
        self.project_root = self.project_path.parent
        self.project_name = get_project_name(self.project_path)
        self._editor: Optional[EditorInstance] = None

        # Register cleanup on exit
        atexit.register(self._cleanup)

        logger.info(f"EditorManager initialized for project: {self.project_name}")
        logger.info(f"Project path: {self.project_path}")

    def _cleanup(self) -> None:
        """Clean up editor instance on exit."""
        if self._editor is not None:
            logger.info("Cleaning up editor instance...")
            self.stop()

    def get_status(self) -> dict[str, Any]:
        """
        Get current editor status.

        Returns:
            Status dictionary with editor information
        """
        if self._editor is None:
            return {
                "status": "not_running",
                "project_name": self.project_name,
                "project_path": str(self.project_path),
            }

        # Check if process is still running
        if self._editor.process.poll() is not None:
            self._editor.status = "stopped"

        return {
            "status": self._editor.status,
            "project_name": self.project_name,
            "project_path": str(self.project_path),
            "pid": self._editor.process.pid,
            "started_at": self._editor.started_at.isoformat(),
            "connected": (
                self._editor.remote_client.is_connected()
                if self._editor.remote_client
                else False
            ),
        }

    def _try_connect(self) -> bool:
        """
        Try to connect to the editor's remote execution.

        Returns:
            True if connected successfully, False otherwise
        """
        if self._editor is None:
            return False

        remote_client = RemoteExecutionClient(project_name=self.project_name)

        if remote_client.find_unreal_instance(timeout=2.0):
            if remote_client.open_connection():
                # Verify PID to ensure we connected to the right process
                if remote_client.verify_pid(self._editor.process.pid):
                    self._editor.node_id = remote_client.get_node_id()
                    self._editor.remote_client = remote_client
                    self._editor.status = "ready"
                    logger.info(
                        f"Connected to editor (node_id: {self._editor.node_id})"
                    )
                    return True
                else:
                    logger.debug("PID mismatch, not our editor instance")
                    remote_client.close_connection()

        return False

    def is_running(self) -> bool:
        """Check if editor is running."""
        if self._editor is None:
            return False
        return self._editor.process.poll() is None

    def is_cpp_project(self) -> bool:
        """
        Check if the project is a C++ project.

        Returns:
            True if project has a 'Source' directory, False otherwise.
        """
        source_dir = self.project_root / "Source"
        return source_dir.exists() and source_dir.is_dir()

    def needs_build(self) -> tuple[bool, str]:
        """
        Check if the project needs to be built.

        Returns:
            Tuple of (needs_build, reason)
        """
        if not self.is_cpp_project():
            return False, ""

        # Default Development Editor DLL path
        # Note: This checks the standard Binaries location for the main project module
        dll_name = f"UnrealEditor-{self.project_name}.dll"
        dll_path = self.project_root / "Binaries" / "Win64" / dll_name

        if not dll_path.exists():
            return True, f"Project binary not found: {dll_name}"

        # Check modification times
        try:
            dll_mtime = dll_path.stat().st_mtime
            
            source_dir = self.project_root / "Source"
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
            logger.warning(f"Error checking build status: {e}")
            # If we can't check, assume safe to launch
            return False, ""

        return False, ""

    async def _prepare_launch(
        self,
        additional_paths: Optional[list[str]] = None,
    ) -> Any:
        """Shared preparation logic for launching the editor."""
        if self.is_running():
            return {
                "success": False,
                "error": "Editor is already running",
                "status": self.get_status(),
            }

        # Check if C++ project needs build
        needs_build, reason = self.needs_build()
        if needs_build:
            return {
                "success": False,
                "error": f"Project needs to be built: {reason}. Please run 'project.build' first.",
            }

        # Run autoconfig
        logger.info("Running project configuration check...")
        config_result = run_config_check(
            self.project_root, auto_fix=True, additional_paths=additional_paths
        )

        if config_result["status"] == "error":
            return {
                "success": False,
                "error": f"Configuration failed: {config_result['summary']}",
                "config_result": config_result,
            }

        if config_result["status"] == "fixed":
            logger.info(f"Configuration fixed: {config_result['summary']}")

        # Find editor executable
        editor_path = find_ue5_editor_for_project(self.project_path)
        if editor_path is None:
            return {
                "success": False,
                "error": "Could not find Unreal Editor executable",
            }

        logger.info(f"Launching editor: {editor_path}")
        logger.info(f"Project: {self.project_path}")

        # Launch editor process
        try:
            # On Windows, use DETACHED_PROCESS to fully separate from parent
            import sys
            creationflags = 0
            if sys.platform == "win32":
                creationflags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
            
            process = subprocess.Popen(
                [str(editor_path), str(self.project_path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                start_new_session=True,  # Create new session
                creationflags=creationflags,
            )
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to launch editor: {e}",
            }

        self._editor = EditorInstance(process=process, status="starting")
        logger.info(f"Editor process started (PID: {process.pid})")
        return process, config_result

    async def launch(
        self,
        notify: Optional[NotifyCallback] = None,
        additional_paths: Optional[list[str]] = None,
        wait_timeout: float = 120.0,
    ) -> dict[str, Any]:
        """
        Launch Unreal Editor and wait for connection (synchronous startup).
        """
        prep_result = await self._prepare_launch(additional_paths)
        if isinstance(prep_result, dict):
            return prep_result
        
        process, config_result = prep_result

        # Helper for null notify
        async def null_notify(level: str, message: str) -> None:
            pass
        actual_notify = notify or null_notify

        return await self._wait_for_connection_async(
            process=process,
            notify=actual_notify,
            wait_timeout=wait_timeout,
        )

    async def launch_async(
        self,
        notify: NotifyCallback,
        additional_paths: Optional[list[str]] = None,
        wait_timeout: float = 120.0,
    ) -> dict[str, Any]:
        """
        Launch Unreal Editor asynchronously (returns immediately).
        """
        prep_result = await self._prepare_launch(additional_paths)
        if isinstance(prep_result, dict):
            return prep_result
        
        process, config_result = prep_result

        # Start background task to wait for connection
        asyncio.create_task(
            self._wait_for_connection_async(
                process=process,
                notify=notify,
                wait_timeout=wait_timeout,
            )
        )

        return {
            "success": True,
            "message": "Editor process started, waiting for connection in background",
            "config_result": config_result,
            "status": self.get_status(),
        }

    async def _background_connect_loop(
        self,
        process: subprocess.Popen,
        notify: NotifyCallback,
        retry_interval: float = 5.0,
    ) -> None:
        """
        Background task to keep trying to connect after initial timeout.
        Runs until connected or process exits.

        Args:
            process: The editor subprocess
            notify: Async callback to send notifications
            retry_interval: Time between connection attempts in seconds
        """
        logger.info("Starting background connection loop...")
        remote_client = RemoteExecutionClient(project_name=self.project_name)

        while True:
            # Check if process crashed
            if process.poll() is not None:
                logger.info("Editor process exited, stopping background connection loop")
                if self._editor:
                    self._editor.status = "stopped"
                return

            # Check if already connected (by another path, e.g., execute() reconnect)
            if self._editor and self._editor.status == "ready":
                logger.info("Editor already connected, stopping background connection loop")
                return

            # Try to connect
            if remote_client.find_unreal_instance(timeout=2.0):
                if remote_client.open_connection():
                    if remote_client.verify_pid(process.pid):
                        # Success!
                        if self._editor:
                            self._editor.node_id = remote_client.get_node_id()
                            self._editor.remote_client = remote_client
                            self._editor.status = "ready"

                        logger.info(
                            f"Background connect succeeded (node_id: {remote_client.get_node_id()})"
                        )
                        await notify(
                            "info",
                            f"Editor connected successfully in background! "
                            f"(PID: {process.pid}, node_id: {remote_client.get_node_id()})"
                        )
                        return
                    else:
                        logger.debug("PID mismatch in background connect, retrying...")
                        remote_client.close_connection()

            await asyncio.sleep(retry_interval)

    async def _wait_for_connection_async(
        self,
        process: subprocess.Popen,
        notify: NotifyCallback,
        wait_timeout: float,
    ) -> dict[str, Any]:
        """
        Task to wait for editor connection and send notifications.

        Args:
            process: The editor subprocess
            notify: Async callback to send notifications
            wait_timeout: Maximum time to wait for connection

        Returns:
            Launch result dictionary
        """
        logger.info(f"Background: Waiting for editor connection (timeout: {wait_timeout}s)...")

        remote_client = RemoteExecutionClient(project_name=self.project_name)
        start_time = time.time()
        connected = False

        while time.time() - start_time < wait_timeout:
            # Check if process crashed
            if process.poll() is not None:
                if self._editor:
                    self._editor.status = "stopped"
                logger.error(f"Editor process exited unexpectedly (exit code: {process.returncode})")
                await notify(
                    "error",
                    f"Editor process exited unexpectedly (exit code: {process.returncode})"
                )
                return {
                    "success": False,
                    "error": "Editor process exited unexpectedly",
                    "exit_code": process.returncode,
                }

            # Try to discover and connect
            if remote_client.find_unreal_instance(timeout=1.0):
                if remote_client.open_connection():
                    # Verify PID to ensure we connected to the right process
                    if remote_client.verify_pid(process.pid):
                        connected = True
                        break
                    else:
                        logger.warning(
                            "Connected to wrong UE5 instance (PID mismatch), retrying..."
                        )
                        remote_client.close_connection()

            # Use asyncio.sleep to allow other tasks to run
            await asyncio.sleep(0.5)

        if not connected:
            logger.warning(
                "Timeout waiting for editor connection, continuing in background..."
            )
            if self._editor:
                self._editor.status = "starting"

            # Start background connection loop to keep trying
            asyncio.create_task(
                self._background_connect_loop(
                    process=process,
                    notify=notify,
                    retry_interval=5.0,
                )
            )

            await notify(
                "warning",
                "Timeout waiting for editor connection. "
                "Continuing to try connecting in background - you will be notified when ready."
            )
            return {
                "success": False,
                "error": "Timeout waiting for editor to enable remote execution. Background connection continues.",
                "status": self.get_status(),
                "background_connecting": True,
            }

        # Store the node_id for future reconnections
        if self._editor:
            self._editor.node_id = remote_client.get_node_id()
            self._editor.remote_client = remote_client
            self._editor.status = "ready"

        elapsed = time.time() - start_time
        logger.info(
            f"Editor connected successfully (node_id: {remote_client.get_node_id()}, "
            f"elapsed: {elapsed:.1f}s)"
        )

        await notify(
            "info",
            f"Editor launched and connected successfully! "
            f"(PID: {process.pid}, node_id: {remote_client.get_node_id()}, "
            f"elapsed: {elapsed:.1f}s)"
        )

        return {
            "success": True,
            "message": "Editor launched and connected",
            "status": self.get_status(),
        }

    def stop(self) -> dict[str, Any]:
        """
        Stop the managed editor instance.

        Uses graceful shutdown first, then forceful termination if needed.

        Returns:
            Stop result dictionary
        """
        if self._editor is None:
            return {
                "success": False,
                "error": "No editor is running",
            }

        if not self.is_running():
            self._editor = None
            return {
                "success": True,
                "message": "Editor was already stopped",
            }

        logger.info("Stopping editor...")

        # Try graceful shutdown via remote execution
        if self._editor.remote_client and self._editor.remote_client.is_connected():
            try:
                logger.info("Attempting graceful shutdown...")
                self._editor.remote_client.execute(
                    "import unreal; unreal.SystemLibrary.quit_editor()",
                    timeout=5.0,
                )
            except Exception as e:
                logger.warning(f"Graceful shutdown command failed: {e}")
            finally:
                self._editor.remote_client.close_connection()

        # Wait for process to exit
        try:
            self._editor.process.wait(timeout=5.0)
            logger.info("Editor stopped gracefully")
        except subprocess.TimeoutExpired:
            logger.warning("Graceful shutdown timed out, forcing termination...")
            self._editor.process.terminate()
            try:
                self._editor.process.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                logger.error("Termination timed out, killing process...")
                self._editor.process.kill()

        self._editor.status = "stopped"
        self._editor = None

        return {
            "success": True,
            "message": "Editor stopped",
        }

    def execute(self, code: str, timeout: float = 30.0) -> dict[str, Any]:
        """
        Execute Python code in the managed editor.

        Args:
            code: Python code to execute
            timeout: Execution timeout in seconds

        Returns:
            Execution result dictionary
        """
        if self._editor is None:
            return {
                "success": False,
                "error": "No editor is running. Call launch() first.",
            }

        if self._editor.status != "ready":
            return {
                "success": False,
                "error": f"Editor is not ready (status: {self._editor.status})",
            }

        if (
            self._editor.remote_client is None
            or not self._editor.remote_client.is_connected()
        ):
            # Try to reconnect using stored node_id
            logger.info("Remote client disconnected, attempting to reconnect...")
            remote_client = RemoteExecutionClient(
                project_name=self.project_name,
                expected_node_id=self._editor.node_id,  # Only accept known node
            )
            if remote_client.find_unreal_instance(timeout=5.0):
                if remote_client.open_connection():
                    # Verify PID to ensure we reconnected to the right process
                    if remote_client.verify_pid(self._editor.process.pid):
                        self._editor.remote_client = remote_client
                    else:
                        remote_client.close_connection()
                        return {
                            "success": False,
                            "error": "PID mismatch during reconnect. Original editor may have crashed.",
                        }
                else:
                    return {
                        "success": False,
                        "error": "Failed to reconnect to editor",
                    }
            else:
                return {
                    "success": False,
                    "error": "Failed to find editor instance. Editor may have crashed.",
                }

        result = self._editor.remote_client.execute(code, timeout=timeout)

        # Check for crash
        if result.get("crashed", False):
            self._editor.status = "stopped"
            return {
                "success": False,
                "error": "Editor connection lost (may have crashed)",
                "details": result,
            }

        return result

    def _get_python_path(self) -> Optional[Path]:
        """
        Get Python interpreter path from the running editor.

        Returns:
            Path to Python interpreter, or None if failed
        """
        try:
            result = self.execute("import unreal; print(unreal.get_interpreter_executable_path())", timeout=5.0)
            if result.get("success") and result.get("output"):
                output = result["output"]
                lines = []
                if isinstance(output, list):
                    for line in output:
                        if isinstance(line, dict):
                            lines.append(str(line.get("output", "")))
                        else:
                            lines.append(str(line))
                else:
                    lines = [str(output)]
                
                # Extract path from output
                for line in lines:
                    for subline in line.strip().split("\n"):
                        subline = subline.strip()
                        if subline and (subline.endswith(".exe") or "python" in subline.lower()):
                            return Path(subline)
        except Exception as e:
            logger.error(f"Failed to get Python path from editor: {e}")
        return None

    def execute_with_auto_install(
        self,
        code: str,
        timeout: float = 30.0,
        max_install_attempts: int = 3,
    ) -> dict[str, Any]:
        """
        Execute Python code with automatic missing module installation.

        New flow:
        1. Extract import statements from code (also checks syntax)
        2. If syntax error, return error immediately
        3. Execute import statements in UE to detect missing modules
        4. Auto-install missing modules and retry imports
        5. Execute the full code

        Args:
            code: Python code to execute
            timeout: Execution timeout in seconds
            max_install_attempts: Maximum number of packages to auto-install

        Returns:
            Execution result dictionary (same as execute())
            Additional fields when auto-install occurs:
            - auto_installed: List of packages that were auto-installed
        """
        installed_packages: list[str] = []

        # Step 1: Extract import statements (also validates syntax)
        import_statements, syntax_error = extract_import_statements(code)

        # Step 2: If syntax error, return immediately
        if syntax_error:
            return {
                "success": False,
                "error": syntax_error,
            }

        if import_statements:
            # Combine all import statements into one code block
            import_code = "\n".join(import_statements)

            # Step 3: Try executing imports, install missing modules and retry
            attempts = 0
            while attempts <= max_install_attempts:
                result = self.execute(import_code, timeout=10.0)

                if result.get("success"):
                    # All imports succeeded
                    break

                # Check if it's an ImportError
                if not is_import_error(result):
                    # Not an import error, skip pre-installation
                    break

                # Extract missing module name
                missing_module = get_missing_module_from_result(result)
                if not missing_module:
                    logger.warning("Import error detected but could not extract module name")
                    break

                # Convert to package name
                package_name = module_to_package(missing_module)

                # Prevent duplicate installation
                if package_name in installed_packages:
                    logger.warning(f"Already attempted to install {package_name}, giving up")
                    break

                # Get Python path from running editor
                python_path = self._get_python_path()

                # Install the missing package
                logger.info(f"Pre-installing missing package: {package_name}")
                install_result = pip_install([package_name], python_path=python_path)

                if not install_result.get("success", False):
                    logger.warning(f"Failed to install {package_name}: {install_result.get('error')}")
                    break

                installed_packages.append(package_name)
                logger.info(f"Successfully pre-installed {package_name}, retrying imports...")
                attempts += 1

        # Step 4: Execute the full code
        result = self.execute(code, timeout=timeout)

        # Add installation info
        if installed_packages:
            result["auto_installed"] = installed_packages

        return result

    def pip_install_packages(
        self,
        packages: list[str],
        upgrade: bool = False,
    ) -> dict[str, Any]:
        """
        Install Python packages in UE5's Python environment.

        Args:
            packages: List of package names to install
            upgrade: Whether to upgrade existing packages

        Returns:
            Installation result dictionary
        """
        python_path = self._get_python_path()
        return pip_install(packages, python_path=python_path, upgrade=upgrade)

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
        if not self.is_cpp_project():
            logger.info(f"Project {self.project_name} is a Blueprint-only project. Skipping build.")
            return {
                "success": True,
                "message": f"Project '{self.project_name}' is a Blueprint-only project (no Source directory). No C++ compilation required.",
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
            target_name = f"{self.project_name}Editor"
        elif target == "Game":
            target_name = self.project_name
        else:
            target_name = f"{self.project_name}{target}"

        # Build command line arguments
        cmd = [str(build_script), target_name, platform, configuration]
        cmd.extend([f"-Project={self.project_path}"])
        cmd.append("-WaitMutex")

        if clean:
            cmd.append("-Clean")

        logger.info(f"Building project: {self.project_name}")
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
        if not self.is_cpp_project():
            logger.info(f"Project {self.project_name} is a Blueprint-only project. Skipping build.")
            return {
                "success": True,
                "message": f"Project '{self.project_name}' is a Blueprint-only project (no Source directory). No C++ compilation required.",
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
            target_name = f"{self.project_name}Editor"
        elif target == "Game":
            target_name = self.project_name
        else:
            target_name = f"{self.project_name}{target}"

        # Build command line arguments
        cmd = [str(build_script), target_name, platform, configuration]
        cmd.extend([f"-Project={self.project_path}"])
        cmd.append("-WaitMutex")

        if clean:
            cmd.append("-Clean")

        logger.info(f"Building project asynchronously: {self.project_name}")
        logger.info(f"Target: {target_name}, Platform: {platform}, Configuration: {configuration}")

        # Start background build task
        asyncio.create_task(
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
                "cwd": str(self.project_root),
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
                    await safe_notify(
                        "error",
                        f"Build timed out after {timeout} seconds"
                    )
                    return {
                        "success": False,
                        "error": f"Build timed out after {timeout} seconds",
                        "output": "\n".join(output_lines),
                    }

                try:
                    line = await asyncio.wait_for(
                        process.stdout.readline(),
                        timeout=1.0
                    )
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
                    elif any(keyword in line_str.lower() for keyword in
                           ["error", "warning", "building", "compiling", "linking"]):
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
                f"({target_name} {platform} {configuration}, {elapsed:.1f}s)"
            )
            return {
                "success": True,
                "output": stdout,
                "return_code": 0,
                "elapsed": elapsed,
            }
        else:
            # Find error lines for notification
            error_lines = [l for l in output_lines if "error" in l.lower()][:5]
            error_summary = "\n".join(error_lines) if error_lines else "Check build log"
            await safe_notify(
                "error",
                f"Build failed (return code: {return_code}). Errors:\n{error_summary}"
            )
            return {
                "success": False,
                "output": stdout,
                "return_code": return_code,
                "error": error_summary,
                "elapsed": elapsed,
            }
