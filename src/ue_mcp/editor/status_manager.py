"""
StatusManager - Manages editor status queries and lifecycle operations.

This subsystem handles:
- Getting current editor status
- Reading editor log files
- Checking if editor is running
- Stopping the editor
"""

import logging
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from .context import EditorContext

logger = logging.getLogger(__name__)


class StatusManager:
    """
    Manages editor status queries and basic lifecycle operations.

    This subsystem provides status information and handles the stop operation.
    """

    def __init__(self, context: "EditorContext"):
        """
        Initialize StatusManager.

        Args:
            context: Shared editor context
        """
        self._ctx = context

    def get_status(self) -> dict[str, Any]:
        """
        Get current editor status.

        Returns:
            Status dictionary with editor information
        """
        if self._ctx.editor is None:
            return {
                "status": "not_running",
                "project_name": self._ctx.project_name,
                "project_path": str(self._ctx.project_path),
            }

        # Check if process is still running
        if self._ctx.editor.process.poll() is not None:
            self._ctx.editor.status = "stopped"

        return {
            "status": self._ctx.editor.status,
            "project_name": self._ctx.project_name,
            "project_path": str(self._ctx.project_path),
            "pid": self._ctx.editor.process.pid,
            "started_at": self._ctx.editor.started_at.isoformat(),
            "connected": (
                self._ctx.editor.remote_client.is_connected()
                if self._ctx.editor.remote_client
                else False
            ),
            "log_file_path": (
                str(self._ctx.editor.log_file_path) if self._ctx.editor.log_file_path else None
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
        if self._ctx.editor and self._ctx.editor.log_file_path:
            log_path = self._ctx.editor.log_file_path

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
        if self._ctx.editor is None:
            return False
        return self._ctx.editor.process.poll() is None

    def stop(self, health_monitor: Optional[Any] = None) -> dict[str, Any]:
        """
        Stop the managed editor instance.

        Uses graceful shutdown first, then forceful termination if needed.

        Args:
            health_monitor: Optional HealthMonitor to stop before shutting down editor

        Returns:
            Stop result dictionary
        """
        # Mark as intentional stop BEFORE anything else to prevent auto-restart
        self._ctx._intentional_stop = True

        # Stop health monitor if provided
        if health_monitor is not None:
            health_monitor.stop()

        if self._ctx.editor is None:
            return {
                "success": False,
                "error": "No editor is running",
            }

        if not self.is_running():
            self._ctx.editor = None
            return {
                "success": True,
                "message": "Editor was already stopped",
            }

        logger.info("Stopping editor...")

        # Try graceful shutdown via remote execution
        if self._ctx.editor.remote_client and self._ctx.editor.remote_client.is_connected():
            try:
                logger.info("Attempting graceful shutdown...")
                self._ctx.editor.remote_client.execute(
                    "import unreal; unreal.SystemLibrary.quit_editor()",
                    timeout=5.0,
                )
            except Exception as e:
                logger.warning(f"Graceful shutdown command failed: {e}")
            finally:
                self._ctx.editor.remote_client.close_connection()

        # Wait for process to exit
        try:
            self._ctx.editor.process.wait(timeout=5.0)
            logger.info("Editor stopped gracefully")
        except subprocess.TimeoutExpired:
            logger.warning("Graceful shutdown timed out, forcing termination...")
            self._ctx.editor.process.terminate()
            try:
                self._ctx.editor.process.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                logger.error("Termination timed out, killing process...")
                self._ctx.editor.process.kill()

        self._ctx.editor.status = "stopped"
        self._ctx.editor = None

        return {
            "success": True,
            "message": "Editor stopped",
        }
