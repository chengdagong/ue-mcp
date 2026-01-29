"""
LaunchManager - Manages Unreal Editor launching and connection.

This subsystem handles:
- Launching the Unreal Editor
- Waiting for remote execution connection
- Background connection retry logic
"""

import asyncio
import logging
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from ..autoconfig import run_config_check
from ..remote_client import RemoteExecutionClient
from ..core.utils import find_ue5_editor_for_project
from .types import EditorInstance, NotifyCallback

if TYPE_CHECKING:
    from .build_manager import BuildManager
    from .context import EditorContext
    from .health_monitor import HealthMonitor
    from .project_analyzer import ProjectAnalyzer

logger = logging.getLogger(__name__)


class LaunchManager:
    """
    Manages Unreal Editor launching and connection establishment.

    This subsystem handles the complex process of launching the editor,
    waiting for it to become ready, and establishing remote execution connection.
    """

    def __init__(
        self,
        context: "EditorContext",
        project_analyzer: "ProjectAnalyzer",
        health_monitor: "HealthMonitor",
        build_manager: "BuildManager",
    ):
        """
        Initialize LaunchManager.

        Args:
            context: Shared editor context
            project_analyzer: ProjectAnalyzer for build status checking
            health_monitor: HealthMonitor for starting monitoring after launch
            build_manager: BuildManager for auto-building when needed
        """
        self._ctx = context
        self._project_analyzer = project_analyzer
        self._health_monitor = health_monitor
        self._build_manager = build_manager

    def _try_connect(self) -> bool:
        """
        Try to connect to the editor's remote execution.

        Returns:
            True if connected successfully, False otherwise
        """
        if self._ctx.editor is None:
            return False

        remote_client = RemoteExecutionClient(
            project_name=self._ctx.project_name,
            expected_pid=self._ctx.editor.process.pid,  # Pass PID for verification
            multicast_group=("239.0.0.1", self._ctx.editor.multicast_port),
        )

        # Use find_and_verify_instance which handles multiple instances
        if remote_client.find_and_verify_instance(timeout=2.0):
            self._ctx.editor.node_id = remote_client.get_node_id()
            self._ctx.editor.remote_client = remote_client
            self._ctx.editor.status = "ready"
            logger.info(f"Connected to editor (node_id: {self._ctx.editor.node_id})")
            return True

        return False

    async def _prepare_launch(
        self,
        notify: NotifyCallback,
        additional_paths: Optional[list[str]] = None,
        wait_timeout: float = 120.0,
    ) -> Any:
        """
        Shared preparation logic for launching the editor.

        Returns:
            Either an error dict, or a tuple of (process, config_result)
        """
        # Check if already running
        if self._ctx.editor is not None and self._ctx.editor.process.poll() is None:
            return {
                "success": False,
                "error": "Editor is already running",
                "status": self._ctx.get_status(),
            }

        # Check if C++ project needs build - auto-build if necessary
        needs_build, reason = self._project_analyzer.needs_build()
        if needs_build:
            logger.info(f"Project needs build: {reason}. Starting auto-build...")
            await notify("info", f"Project needs build: {reason}. Starting auto-build...")

            build_result = await self._build_manager.build(notify=notify)
            if not build_result.get("success"):
                return {
                    "success": False,
                    "error": f"Auto-build failed: {build_result.get('error', 'Unknown error')}",
                    "build_result": build_result,
                }

        # Run autoconfig
        logger.info("Running project configuration check...")
        config_result = run_config_check(
            self._ctx.project_root, auto_fix=True, additional_paths=additional_paths
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
                needs_build, reason = self._project_analyzer.needs_build()
                if needs_build:
                    logger.info(f"Plugin installed, build needed: {reason}. Starting auto-build...")
                    await notify(
                        "info", f"Plugin installed, build needed: {reason}. Starting auto-build..."
                    )

                    build_result = await self._build_manager.build(notify=notify)
                    if not build_result.get("success"):
                        return {
                            "success": False,
                            "error": f"Auto-build failed: {build_result.get('error', 'Unknown error')}",
                            "build_result": build_result,
                        }

        # Find editor executable
        editor_path = find_ue5_editor_for_project(self._ctx.project_path)
        if editor_path is None:
            return {
                "success": False,
                "error": "Could not find Unreal Editor executable",
            }

        # Allocate dynamic multicast port for this editor instance
        from ..core.port_allocator import find_available_port

        allocated_port = find_available_port()
        logger.info(f"Allocated multicast port: {allocated_port}")

        logger.info(f"Launching editor: {editor_path}")
        logger.info(f"Project: {self._ctx.project_path}")

        # Generate log file path for engine logs (includes project name and timestamp)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_filename = f"ue-mcp-{self._ctx.project_name}-{timestamp}.log"
        log_file_path = self._ctx.project_root / "Saved" / "Logs" / log_filename
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
                    str(self._ctx.project_path),
                    f"-ABSLOG={log_file_path}",
                    ini_override,
                    "-AutoDeclinePackageRecovery",  # Skip package recovery dialogs on startup
                    "-NoLiveCoding",  # Disable Live Coding to allow builds while editor is running
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
        self._ctx.editor = EditorInstance(
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
    ) -> dict[str, Any]:
        """
        Internal launch implementation shared by launch() and launch_async().

        Args:
            notify: Optional async callback to send notifications
            additional_paths: Optional list of additional Python paths
            wait_timeout: Maximum time to wait for editor connection

        Returns:
            Launch result dictionary
        """
        # Reset monitor state on launch
        self._ctx.reset_monitor_state()

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
            self._health_monitor.start(actual_notify)

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
        # Reset monitor state on fresh launch
        self._ctx.reset_monitor_state()

        prep_result = await self._prepare_launch(notify, additional_paths, wait_timeout)
        if isinstance(prep_result, dict):
            return prep_result

        process, config_result = prep_result

        # Start background task to wait for connection
        self._ctx.create_background_task(
            self._wait_for_connection_async(
                process=process,
                notify=notify,
                wait_timeout=wait_timeout,
            )
        )

        # Start health monitor
        self._health_monitor.start(notify)

        return {
            "success": True,
            "message": "Editor process started, waiting for connection in background",
            "config_result": config_result,
            "status": self._ctx.get_status(),
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
            project_name=self._ctx.project_name,
            expected_pid=process.pid,  # Pass PID for verification
            multicast_group=("239.0.0.1", self._ctx.editor.multicast_port),
        )

        try:
            while True:
                # Check if process crashed
                if process.poll() is not None:
                    logger.info("Editor process exited, stopping background connection loop")
                    if self._ctx.editor:
                        self._ctx.editor.status = "stopped"
                    return

                # Check if already connected (by another path, e.g., execute() reconnect)
                if self._ctx.editor and self._ctx.editor.status == "ready":
                    logger.info("Editor already connected, stopping background connection loop")
                    return

                # Try to connect with PID verification
                if remote_client.find_and_verify_instance(timeout=2.0):
                    # Success! Transfer ownership to _editor
                    if self._ctx.editor:
                        self._ctx.editor.node_id = remote_client.get_node_id()
                        self._ctx.editor.remote_client = remote_client
                        self._ctx.editor.status = "ready"

                    # Run editor initialization (monkey patches, etc.)
                    await self._run_editor_init()

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
            if self._ctx.editor is None or self._ctx.editor.remote_client is not remote_client:
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
            project_name=self._ctx.project_name,
            expected_pid=process.pid,  # Pass PID for verification
            multicast_group=("239.0.0.1", self._ctx.editor.multicast_port),
        )
        start_time = time.time()
        connected = False

        while time.time() - start_time < wait_timeout:
            # Check if process crashed
            if process.poll() is not None:
                if self._ctx.editor:
                    self._ctx.editor.status = "stopped"
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
            if self._ctx.editor:
                self._ctx.editor.status = "starting"

            # Clean up the current remote_client before starting background loop
            # (background loop creates its own client)
            remote_client._cleanup_sockets()

            # Start background connection loop to keep trying
            self._ctx.create_background_task(
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
                "status": self._ctx.get_status(),
                "background_connecting": True,
            }

        # Store the node_id for future reconnections
        if self._ctx.editor:
            self._ctx.editor.node_id = remote_client.get_node_id()
            self._ctx.editor.remote_client = remote_client
            self._ctx.editor.status = "ready"

        # Run editor initialization (monkey patches, etc.)
        await self._run_editor_init()

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
            "status": self._ctx.get_status(),
        }

    async def _run_editor_init(self) -> None:
        """
        Run editor initialization script after connection.

        This applies monkey patches and other initialization that needs
        to happen once after the editor is connected (e.g., patching
        LevelEditorSubsystem.load_level to call RefreshSlateView).
        """
        from ..core.paths import get_scripts_dir

        if self._ctx.editor is None or self._ctx.editor.status != "ready":
            logger.warning("Cannot run editor init: editor not ready")
            return

        if self._ctx.editor.remote_client is None:
            logger.warning("Cannot run editor init: no remote client")
            return

        init_script = get_scripts_dir() / "editor_init.py"
        if not init_script.exists():
            logger.warning(f"Editor init script not found: {init_script}")
            return

        try:
            logger.info("Running editor initialization script...")
            result = self._ctx.editor.remote_client.execute(
                str(init_script),
                exec_type=self._ctx.editor.remote_client.ExecTypes.EXECUTE_FILE,
                timeout=10.0,
            )
            if result.get("success"):
                logger.info("Editor initialization completed successfully")
            else:
                logger.warning(f"Editor initialization returned failure: {result}")
        except Exception as e:
            logger.warning(f"Editor initialization failed: {e}")