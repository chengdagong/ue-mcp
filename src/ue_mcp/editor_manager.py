"""
UE-MCP Editor Manager

Manages the lifecycle of a single Unreal Editor instance bound to a project.
"""

import atexit
import logging
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from .autoconfig import run_config_check
from .remote_client import RemoteExecutionClient
from .utils import find_ue5_editor_for_project, get_project_name

logger = logging.getLogger(__name__)


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

    def is_running(self) -> bool:
        """Check if editor is running."""
        if self._editor is None:
            return False
        return self._editor.process.poll() is None

    def launch(
        self,
        additional_paths: Optional[list[str]] = None,
        wait_timeout: float = 120.0,
    ) -> dict[str, Any]:
        """
        Launch Unreal Editor for the bound project.

        Args:
            additional_paths: Optional list of additional Python paths to configure
            wait_timeout: Maximum time to wait for editor to become ready

        Returns:
            Launch result dictionary
        """
        if self.is_running():
            return {
                "success": False,
                "error": "Editor is already running",
                "status": self.get_status(),
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
            process = subprocess.Popen(
                [str(editor_path), str(self.project_path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=False,  # Keep in same process group for cleanup
            )
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to launch editor: {e}",
            }

        self._editor = EditorInstance(process=process, status="starting")

        # Wait for editor to become ready
        logger.info(f"Waiting for editor to start (timeout: {wait_timeout}s)...")
        logger.info(f"Editor PID: {process.pid}")

        remote_client = RemoteExecutionClient(project_name=self.project_name)
        start_time = time.time()
        connected = False
        verified = False

        while time.time() - start_time < wait_timeout:
            # Check if process crashed
            if process.poll() is not None:
                self._editor.status = "stopped"
                return {
                    "success": False,
                    "error": "Editor process exited unexpectedly",
                    "exit_code": process.returncode,
                }

            # Try to discover and connect
            if remote_client.find_unreal_instance(timeout=2.0):
                if remote_client.open_connection():
                    # Verify PID to ensure we connected to the right process
                    if remote_client.verify_pid(process.pid):
                        connected = True
                        verified = True
                        break
                    else:
                        logger.warning(
                            "Connected to wrong UE5 instance (PID mismatch), retrying..."
                        )
                        remote_client.close_connection()

            time.sleep(2.0)

        if not connected:
            logger.error("Timeout waiting for editor to enable remote execution")
            # Don't kill the editor, just report the timeout
            self._editor.status = "starting"
            return {
                "success": False,
                "error": "Timeout waiting for editor to enable remote execution. Editor may still be loading.",
                "status": self.get_status(),
            }

        # Store the node_id for future reconnections
        self._editor.node_id = remote_client.get_node_id()
        self._editor.remote_client = remote_client
        self._editor.status = "ready"

        logger.info(
            f"Editor launched and connected successfully (node_id: {self._editor.node_id})"
        )

        return {
            "success": True,
            "message": "Editor launched and connected",
            "config_result": config_result,
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
