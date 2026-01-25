"""
EditorContext - Shared state object for all editor subsystems.

This module provides the central context that is injected into all subsystems,
enabling them to share state while maintaining loose coupling.

Status management methods (get_status, read_log, is_running, stop) are included
directly in this class since they are simple context queries.
"""

import asyncio
import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from .types import EditorInstance, NotifyCallback

if TYPE_CHECKING:
    from .health_monitor import HealthMonitor

logger = logging.getLogger(__name__)


@dataclass
class EditorContext:
    """
    Shared context passed to all subsystems via dependency injection.

    This class holds all shared state for the editor management system,
    including project information, editor instance, and background task tracking.

    It also provides status query and lifecycle methods (merged from StatusManager).
    """

    # Project information (immutable after init)
    project_path: Path
    project_root: Path
    project_name: str

    # Editor instance (mutable, shared across subsystems)
    _editor: Optional[EditorInstance] = field(default=None, repr=False)

    # Health monitor state
    _monitor_task: Optional[asyncio.Task] = field(default=None, repr=False)
    _notify_callback: Optional[NotifyCallback] = field(default=None, repr=False)
    _restart_count: int = 0
    _last_restart_time: Optional[float] = None
    _intentional_stop: bool = False

    # Background task tracking
    _background_tasks: set[asyncio.Task] = field(default_factory=set, repr=False)

    @property
    def editor(self) -> Optional[EditorInstance]:
        """Get the current editor instance."""
        return self._editor

    @editor.setter
    def editor(self, value: Optional[EditorInstance]) -> None:
        """Set the current editor instance."""
        self._editor = value

    def create_background_task(self, coro) -> asyncio.Task:
        """
        Create a background task and track it for cleanup.

        Args:
            coro: Coroutine to run as a task

        Returns:
            The created task
        """
        task = asyncio.create_task(coro)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        return task

    def cancel_all_background_tasks(self) -> None:
        """Cancel all tracked background tasks."""
        for task in list(self._background_tasks):
            if not task.done():
                task.cancel()
                logger.debug(f"Cancelled background task: {task.get_name()}")
        self._background_tasks.clear()

    def reset_restart_state(self) -> None:
        """Reset restart tracking state for fresh launches."""
        self._restart_count = 0
        self._last_restart_time = None
        self._intentional_stop = False

    # =========================================================================
    # Status Methods (merged from StatusManager)
    # =========================================================================

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

    def is_running(self) -> bool:
        """Check if editor is running."""
        if self._editor is None:
            return False
        return self._editor.process.poll() is None

    def stop(self, health_monitor: Optional["HealthMonitor"] = None) -> dict[str, Any]:
        """
        Stop the managed editor instance.

        Uses graceful shutdown first, then forceful termination if needed.

        Args:
            health_monitor: Optional HealthMonitor to stop before shutting down editor

        Returns:
            Stop result dictionary
        """
        # Mark as intentional stop BEFORE anything else to prevent auto-restart
        self._intentional_stop = True

        # Stop health monitor if provided
        if health_monitor is not None:
            health_monitor.stop()

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
