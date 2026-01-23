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
from .code_inspector import inspect_code
from .pip_install import (
    extract_bundled_module_imports,
    extract_import_statements,
    generate_module_unload_code,
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
    log_file_path: Optional[Path] = None  # Path to editor log file
    # Launch parameters for auto-restart
    additional_paths: Optional[list[str]] = None
    wait_timeout: float = 120.0
    multicast_port: int = 6766  # Allocated multicast port for this instance


class EditorManager:
    """
    Manages a single Unreal Editor instance for a bound project.

    This class is designed for one-to-one binding: one EditorManager per project.
    """

    # Auto-restart configuration
    MAX_RESTART_ATTEMPTS = 3
    RESTART_COOLDOWN_SECONDS = 10.0
    HEALTH_CHECK_INTERVAL = 5.0

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

        # Health monitor state
        self._monitor_task: Optional[asyncio.Task] = None
        self._notify_callback: Optional[NotifyCallback] = None
        self._restart_count = 0
        self._last_restart_time: Optional[float] = None
        self._intentional_stop = False  # Flag to prevent restart on intentional stop

        # Register cleanup on exit
        atexit.register(self._cleanup)

        logger.info(f"EditorManager initialized for project: {self.project_name}")
        logger.info(f"Project path: {self.project_path}")

    def _cleanup(self) -> None:
        """Clean up editor instance on exit."""
        self._stop_health_monitor()
        if self._editor is not None:
            logger.info("Cleaning up editor instance...")
            self._intentional_stop = True
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
                self._editor.remote_client.is_connected() if self._editor.remote_client else False
            ),
            "log_file_path": (
                str(self._editor.log_file_path) if self._editor.log_file_path else None
            ),
        }

    def read_log(self, tail_lines: Optional[int] = None) -> dict[str, Any]:
        """
        Read the editor log file content.

        Args:
            tail_lines: If specified, only return the last N lines of the log

        Returns:
            Dictionary containing:
            - success: Whether read succeeded
            - log_file_path: Path to the log file
            - content: Log file content (or last N lines if tail_lines specified)
            - file_size: Size of the log file in bytes
            - error: Error message (if failed)
        """
        # Get log file path from current or previous editor instance
        log_path: Optional[Path] = None
        if self._editor and self._editor.log_file_path:
            log_path = self._editor.log_file_path

        if log_path is None:
            return {
                "success": False,
                "error": "No log file path available. Editor may not have been launched yet.",
            }

        if not log_path.exists():
            return {
                "success": False,
                "error": f"Log file does not exist: {log_path}",
                "log_file_path": str(log_path),
            }

        try:
            file_size = log_path.stat().st_size

            if tail_lines is not None and tail_lines > 0:
                # Read only last N lines
                with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()
                    content = "".join(lines[-tail_lines:])
            else:
                # Read entire file
                content = log_path.read_text(encoding="utf-8", errors="replace")

            return {
                "success": True,
                "log_file_path": str(log_path),
                "content": content,
                "file_size": file_size,
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to read log file: {e}",
                "log_file_path": str(log_path),
            }

    def _try_connect(self) -> bool:
        """
        Try to connect to the editor's remote execution.

        Returns:
            True if connected successfully, False otherwise
        """
        if self._editor is None:
            return False

        remote_client = RemoteExecutionClient(
            project_name=self.project_name,
            expected_pid=self._editor.process.pid,  # Pass PID for verification
            multicast_group=("239.0.0.1", self._editor.multicast_port),
        )

        # Use find_and_verify_instance which handles multiple instances
        if remote_client.find_and_verify_instance(timeout=2.0):
            self._editor.node_id = remote_client.get_node_id()
            self._editor.remote_client = remote_client
            self._editor.status = "ready"
            logger.info(f"Connected to editor (node_id: {self._editor.node_id})")
            return True

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
            True if project has a 'Source' directory or C++ plugins, False otherwise.
        """
        # Check project's own Source directory
        source_dir = self.project_root / "Source"
        if source_dir.exists() and source_dir.is_dir():
            return True

        # Check for C++ plugins in Plugins directory
        plugins_dir = self.project_root / "Plugins"
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

        # Check project's own binary
        dll_name = f"UnrealEditor-{self.project_name}.dll"
        dll_path = self.project_root / "Binaries" / "Win64" / dll_name

        # For projects with Source directory, check project binary
        source_dir = self.project_root / "Source"
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
        plugins_dir = self.project_root / "Plugins"
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

    async def _prepare_launch(
        self,
        notify: Optional[NotifyCallback] = None,
        additional_paths: Optional[list[str]] = None,
        wait_timeout: float = 120.0,
    ) -> Any:
        """Shared preparation logic for launching the editor."""
        if self.is_running():
            return {
                "success": False,
                "error": "Editor is already running",
                "status": self.get_status(),
            }

        # Check if C++ project needs build - auto-build if necessary
        needs_build, reason = self.needs_build()
        if needs_build:
            logger.info(f"Project needs build: {reason}. Starting auto-build...")
            if notify:
                await notify("info", f"Project needs build: {reason}. Starting auto-build...")
            
            build_result = await self.build(notify=notify)
            if not build_result.get("success"):
                return {
                    "success": False,
                    "error": f"Auto-build failed: {build_result.get('error', 'Unknown error')}",
                    "build_result": build_result,
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

            # If plugin was installed, re-check if build is needed
            # (needs_build will detect the missing plugin binary)
            extra_apis_info = config_result.get("extra_python_apis", {})
            if extra_apis_info.get("modified", False):
                needs_build, reason = self.needs_build()
                if needs_build:
                    logger.info(f"Plugin installed, build needed: {reason}. Starting auto-build...")
                    if notify:
                        await notify("info", f"Plugin installed, build needed: {reason}. Starting auto-build...")
                    
                    build_result = await self.build(notify=notify)
                    if not build_result.get("success"):
                        return {
                            "success": False,
                            "error": f"Auto-build failed: {build_result.get('error', 'Unknown error')}",
                            "build_result": build_result,
                        }

        # Find editor executable
        editor_path = find_ue5_editor_for_project(self.project_path)
        if editor_path is None:
            return {
                "success": False,
                "error": "Could not find Unreal Editor executable",
            }

        # Allocate dynamic multicast port for this editor instance
        from .port_allocator import find_available_port

        allocated_port = find_available_port()
        logger.info(f"Allocated multicast port: {allocated_port}")

        logger.info(f"Launching editor: {editor_path}")
        logger.info(f"Project: {self.project_path}")

        # Generate log file path for engine logs (includes project name and timestamp)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_filename = f"ue-mcp-{self.project_name}-{timestamp}.log"
        log_file_path = self.project_root / "Saved" / "Logs" / log_filename
        logger.info(f"Editor log file: {log_file_path}")

        # Launch editor process
        try:
            # On Windows, use DETACHED_PROCESS to fully separate from parent
            import sys

            creationflags = 0
            if sys.platform == "win32":
                creationflags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP

            # Build command line override for multicast port
            # FIPv4Endpoint expects "IP:Port" string format
            ini_override = (
                f"-ini:Engine:[/Script/PythonScriptPlugin.PythonScriptPluginSettings]:"
                f"RemoteExecutionMulticastGroupEndpoint=239.0.0.1:{allocated_port}"
            )

            process = subprocess.Popen(
                [
                    str(editor_path),
                    str(self.project_path),
                    f"-ABSLOG={log_file_path}",
                    ini_override,
                ],
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

        # Save launch parameters for potential restart
        self._editor = EditorInstance(
            process=process,
            status="starting",
            log_file_path=log_file_path,
            additional_paths=additional_paths,
            wait_timeout=wait_timeout,
            multicast_port=allocated_port,
        )
        logger.info(f"Editor process started (PID: {process.pid})")
        return process, config_result

    async def _launch_internal(
        self,
        notify: Optional[NotifyCallback] = None,
        additional_paths: Optional[list[str]] = None,
        wait_timeout: float = 120.0,
        reset_restart_state: bool = True,
    ) -> dict[str, Any]:
        """
        Internal launch implementation shared by launch(), launch_async(), and restart.

        Args:
            notify: Optional async callback to send notifications
            additional_paths: Optional list of additional Python paths
            wait_timeout: Maximum time to wait for editor connection
            reset_restart_state: If True, reset restart counter (for fresh launches)

        Returns:
            Launch result dictionary
        """
        # Reset restart state on fresh launch (not on auto-restart)
        if reset_restart_state:
            self._restart_count = 0
            self._last_restart_time = None
            self._intentional_stop = False

        # Helper for null notify
        async def null_notify(level: str, message: str) -> None:
            pass

        actual_notify = notify or null_notify

        prep_result = await self._prepare_launch(actual_notify, additional_paths, wait_timeout)
        if isinstance(prep_result, dict):
            return prep_result

        process, config_result = prep_result

        result = await self._wait_for_connection_async(
            process=process,
            notify=actual_notify,
            wait_timeout=wait_timeout,
        )

        # Start health monitor after launch attempt
        if result.get("success") or result.get("background_connecting"):
            self._start_health_monitor(actual_notify)

        return result

    async def launch(
        self,
        notify: Optional[NotifyCallback] = None,
        additional_paths: Optional[list[str]] = None,
        wait_timeout: float = 120.0,
    ) -> dict[str, Any]:
        """
        Launch Unreal Editor and wait for connection (synchronous startup).

        Args:
            notify: Optional async callback to send notifications
            additional_paths: Optional list of additional Python paths
            wait_timeout: Maximum time to wait for editor connection

        Returns:
            Launch result dictionary
        """
        return await self._launch_internal(
            notify=notify,
            additional_paths=additional_paths,
            wait_timeout=wait_timeout,
            reset_restart_state=True,
        )

    async def launch_async(
        self,
        notify: NotifyCallback,
        additional_paths: Optional[list[str]] = None,
        wait_timeout: float = 120.0,
    ) -> dict[str, Any]:
        """
        Launch Unreal Editor asynchronously (returns immediately).

        Args:
            notify: Async callback to send notifications
            additional_paths: Optional list of additional Python paths
            wait_timeout: Maximum time to wait for editor connection

        Returns:
            Initial launch result (editor starting in background)
        """
        # Reset restart state on fresh launch
        self._restart_count = 0
        self._last_restart_time = None
        self._intentional_stop = False

        prep_result = await self._prepare_launch(notify, additional_paths, wait_timeout)
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

        # Start health monitor
        self._start_health_monitor(notify)

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
        remote_client = RemoteExecutionClient(
            project_name=self.project_name,
            expected_pid=process.pid,  # Pass PID for verification
            multicast_group=("239.0.0.1", self._editor.multicast_port),
        )

        try:
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

                # Try to connect with PID verification
                if remote_client.find_and_verify_instance(timeout=2.0):
                    # Success! Transfer ownership to _editor
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
                        f"(PID: {process.pid}, node_id: {remote_client.get_node_id()})",
                    )
                    # Don't cleanup - remote_client is now owned by _editor
                    return

                await asyncio.sleep(retry_interval)
        finally:
            # Clean up if we exit without successful connection
            if self._editor is None or self._editor.remote_client is not remote_client:
                remote_client._cleanup_sockets()

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

        remote_client = RemoteExecutionClient(
            project_name=self.project_name,
            expected_pid=process.pid,  # Pass PID for verification
            multicast_group=("239.0.0.1", self._editor.multicast_port),
        )
        start_time = time.time()
        connected = False

        while time.time() - start_time < wait_timeout:
            # Check if process crashed
            if process.poll() is not None:
                if self._editor:
                    self._editor.status = "stopped"
                logger.error(
                    f"Editor process exited unexpectedly (exit code: {process.returncode})"
                )
                remote_client._cleanup_sockets()
                await notify(
                    "error", f"Editor process exited unexpectedly (exit code: {process.returncode})"
                )
                return {
                    "success": False,
                    "error": "Editor process exited unexpectedly",
                    "exit_code": process.returncode,
                }

            # Try to discover and connect with PID verification
            if remote_client.find_and_verify_instance(timeout=1.0):
                connected = True
                break

            # Use asyncio.sleep to allow other tasks to run
            await asyncio.sleep(0.5)

        if not connected:
            logger.warning("Timeout waiting for editor connection, continuing in background...")
            if self._editor:
                self._editor.status = "starting"

            # Clean up the current remote_client before starting background loop
            # (background loop creates its own client)
            remote_client._cleanup_sockets()

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
                "Continuing to try connecting in background - you will be notified when ready.",
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
            f"elapsed: {elapsed:.1f}s)",
        )

        return {
            "success": True,
            "message": "Editor launched and connected",
            "status": self.get_status(),
        }

    # =========================================================================
    # Health Monitor Methods
    # =========================================================================

    def _start_health_monitor(self, notify: NotifyCallback) -> None:
        """
        Start the health monitor background task.

        Args:
            notify: Async callback to send notifications to MCP client
        """
        # Only start if not already running
        if self._monitor_task is not None and not self._monitor_task.done():
            logger.debug("Health monitor already running")
            return

        self._notify_callback = notify
        self._intentional_stop = False  # Reset flag
        self._monitor_task = asyncio.create_task(self._health_monitor_loop())
        logger.info("Health monitor started")

    def _stop_health_monitor(self) -> None:
        """
        Stop the health monitor background task.
        """
        if self._monitor_task is not None:
            self._monitor_task.cancel()
            self._monitor_task = None

        self._notify_callback = None
        logger.info("Health monitor stopped")

    async def _health_monitor_loop(self) -> None:
        """
        Background coroutine that monitors editor health.

        Periodically checks if the editor process is alive.
        If the process crashes, sends notification and attempts restart.
        """
        logger.info("Health monitor loop started")

        try:
            while True:
                await asyncio.sleep(self.HEALTH_CHECK_INTERVAL)

                # Check if editor instance exists
                if self._editor is None:
                    logger.debug("No editor instance, monitor exiting")
                    break

                # Check if process is still running
                exit_code = self._editor.process.poll()
                if exit_code is not None:
                    # Process has exited
                    self._editor.status = "stopped"

                    # Check if this was an intentional stop
                    if self._intentional_stop:
                        logger.info("Editor stopped intentionally, no restart needed")
                        break

                    # Editor crashed - notify and attempt restart
                    logger.warning(f"Editor process exited unexpectedly (exit code: {exit_code})")

                    if self._notify_callback:
                        try:
                            await self._notify_callback(
                                "warning",
                                f"Editor process crashed (exit code: {exit_code}). "
                                f"Attempting automatic restart...",
                            )
                        except Exception as e:
                            logger.error(f"Failed to send crash notification: {e}")

                    # Attempt restart
                    restart_success = await self._attempt_restart()

                    if not restart_success:
                        # Restart failed, exit monitor loop
                        if self._notify_callback:
                            try:
                                await self._notify_callback(
                                    "error",
                                    f"Failed to restart editor after {self._restart_count} attempts. "
                                    f"Please restart manually using editor_launch.",
                                )
                            except Exception as e:
                                logger.error(f"Failed to send restart failure notification: {e}")
                        break

                    # Restart succeeded, continue monitoring

        except asyncio.CancelledError:
            logger.info("Health monitor cancelled")
        except Exception as e:
            logger.error(f"Health monitor error: {e}")
        finally:
            logger.info("Health monitor loop exited")

    async def _attempt_restart(self) -> bool:
        """
        Attempt to restart the editor after a crash.

        Implements:
        - Restart count limiting (MAX_RESTART_ATTEMPTS)
        - Cooldown period (RESTART_COOLDOWN_SECONDS)
        - Uses saved launch parameters from EditorInstance

        Returns:
            True if restart succeeded, False if restart failed or not allowed
        """
        # Check restart count
        if self._restart_count >= self.MAX_RESTART_ATTEMPTS:
            logger.error(f"Maximum restart attempts ({self.MAX_RESTART_ATTEMPTS}) reached")
            return False

        # Check cooldown
        current_time = time.time()
        if self._last_restart_time is not None:
            elapsed = current_time - self._last_restart_time
            if elapsed < self.RESTART_COOLDOWN_SECONDS:
                # Still in cooldown, wait for remaining time
                remaining = self.RESTART_COOLDOWN_SECONDS - elapsed
                logger.info(f"Restart cooldown: waiting {remaining:.1f}s")
                await asyncio.sleep(remaining)

        # Save launch parameters before cleanup
        if self._editor is None:
            logger.error("No editor instance to restart from")
            return False

        additional_paths = self._editor.additional_paths
        wait_timeout = self._editor.wait_timeout

        # Clean up old connection (but not the process - it's already dead)
        if self._editor.remote_client:
            self._editor.remote_client._cleanup_sockets()
        self._editor = None

        # Update restart tracking
        self._restart_count += 1
        self._last_restart_time = time.time()

        logger.info(f"Attempting restart {self._restart_count}/{self.MAX_RESTART_ATTEMPTS}...")

        # Send restart notification
        if self._notify_callback:
            try:
                await self._notify_callback(
                    "info",
                    f"Restarting editor (attempt {self._restart_count}/{self.MAX_RESTART_ATTEMPTS})...",
                )
            except Exception as e:
                logger.error(f"Failed to send restart notification: {e}")

        # Attempt to launch (don't reset restart count here)
        try:
            result = await self._launch_internal(
                notify=self._notify_callback,
                additional_paths=additional_paths,
                wait_timeout=wait_timeout,
                reset_restart_state=False,  # Keep restart count
            )

            if result.get("success") or result.get("background_connecting"):
                logger.info("Editor restart successful")
                return True
            else:
                logger.error(f"Editor restart failed: {result.get('error')}")

                # Check if requires_build - don't keep trying
                if result.get("requires_build"):
                    logger.error("Editor requires build. Cannot auto-restart until built.")
                    if self._notify_callback:
                        try:
                            await self._notify_callback(
                                "error",
                                "Editor restart failed: project needs to be built. "
                                "Run 'project_build' and then 'editor_launch' manually.",
                            )
                        except Exception:
                            pass
                    # Exhaust restart attempts to prevent further attempts
                    self._restart_count = self.MAX_RESTART_ATTEMPTS

                return False

        except Exception as e:
            logger.error(f"Exception during restart: {e}")
            return False

    def stop(self) -> dict[str, Any]:
        """
        Stop the managed editor instance.

        Uses graceful shutdown first, then forceful termination if needed.

        Returns:
            Stop result dictionary
        """
        # Mark as intentional stop BEFORE anything else to prevent auto-restart
        self._intentional_stop = True

        # Stop health monitor
        self._stop_health_monitor()

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

    def _execute(self, code: str, timeout: float = 30.0) -> dict[str, Any]:
        """
        Execute Python code in the managed editor (internal use only).

        External callers should use execute_with_auto_install() instead.

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

        if self._editor.remote_client is None or not self._editor.remote_client.is_connected():
            # Try to reconnect using stored node_id and PID
            logger.info("Remote client disconnected, attempting to reconnect...")

            # Clean up old remote_client if it exists
            if self._editor.remote_client is not None:
                self._editor.remote_client._cleanup_sockets()
                self._editor.remote_client = None

            remote_client = RemoteExecutionClient(
                project_name=self.project_name,
                expected_node_id=self._editor.node_id,  # Prefer known node
                expected_pid=self._editor.process.pid,  # Verify PID
                multicast_group=("239.0.0.1", self._editor.multicast_port),
            )

            # Use find_and_verify_instance for reconnection
            if remote_client.find_and_verify_instance(timeout=5.0):
                self._editor.remote_client = remote_client
                logger.info("Reconnected successfully")
            else:
                remote_client._cleanup_sockets()
                return {
                    "success": False,
                    "error": "Failed to reconnect to editor. Editor may have crashed.",
                }

        # Wrap multi-line code in exec() since EXECUTE_STATEMENT only handles single statements
        # For single-line code without newlines, execute directly
        if "\n" in code:
            # Escape the code for use in exec()
            escaped_code = code.replace("\\", "\\\\").replace("'", "\\'")
            wrapped_code = f"exec('''{escaped_code}''')"
            result = self._editor.remote_client.execute(
                wrapped_code,
                exec_type=self._editor.remote_client.ExecTypes.EXECUTE_STATEMENT,
                timeout=timeout,
            )
        else:
            result = self._editor.remote_client.execute(
                code,
                exec_type=self._editor.remote_client.ExecTypes.EXECUTE_STATEMENT,
                timeout=timeout,
            )

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
            result = self._execute(
                "import unreal; print(unreal.get_interpreter_executable_path())", timeout=5.0
            )
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
        Execute Python code with automatic missing module installation
        and bundled module reloading.

        Flow:
        1. Extract import statements from code (also checks syntax)
        2. If syntax error, return error immediately
        2.5. Detect bundled module imports and inject unload code
        3. Execute import statements in UE to detect missing modules
        4. Auto-install missing modules and retry imports
        5. Execute the full code

        The bundled module reload feature (step 2.5) detects imports of modules
        from our custom site-packages (asset_diagnostic, editor_capture) and
        removes them from sys.modules before execution, ensuring the latest
        code is always used without requiring editor restart.

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

        # Step 2.5: Code inspection for blocking calls and other issues
        inspection = inspect_code(code)
        if not inspection.allowed:
            return {
                "success": False,
                "error": inspection.format_error(),
                "inspection_issues": [i.to_dict() for i in inspection.issues],
            }

        # Step 3: Detect and prepare bundled module reload
        # This ensures bundled modules are reloaded to pick up latest code changes
        bundled_imports = extract_bundled_module_imports(code)
        if bundled_imports:
            unload_code = generate_module_unload_code(bundled_imports)
            code = unload_code + code
            logger.debug(f"Injected unload code for bundled modules: {bundled_imports}")

        if import_statements:
            # Combine all import statements into one code block
            import_code = "\n".join(import_statements)

            # Step 3: Try executing imports, install missing modules and retry
            attempts = 0
            while attempts <= max_install_attempts:
                result = self._execute(import_code, timeout=10.0)

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
                    logger.warning(
                        f"Failed to install {package_name}: {install_result.get('error')}"
                    )
                    break

                installed_packages.append(package_name)
                logger.info(f"Successfully pre-installed {package_name}, retrying imports...")
                attempts += 1

        # Step 4: Execute the full code
        result = self._execute(code, timeout=timeout)

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
                "message": f"Project '{self.project_name}' is a Blueprint-only project (no Source directory or C++ plugins). No C++ compilation required.",
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
                "message": f"Project '{self.project_name}' is a Blueprint-only project (no Source directory or C++ plugins). No C++ compilation required.",
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
            error_lines = [l for l in output_lines if "error" in l.lower()][:5]
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
