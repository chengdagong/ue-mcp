"""
HealthMonitor - Monitors editor health and notifies on exit.

This subsystem handles:
- Periodic health checks of the editor process
- Detecting editor exit (normal or crash)
- Notifying MCP client with exit reason and details
"""

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from .crash_detector import CrashDetector
from .types import NotifyCallback

if TYPE_CHECKING:
    from .context import EditorContext

logger = logging.getLogger(__name__)


class HealthMonitor:
    """
    Monitors editor health and notifies MCP client on exit.

    This subsystem runs a background task that periodically checks if the
    editor process is still alive. When the editor exits (for any reason),
    it notifies the MCP client with exit details and stops monitoring.
    """

    # Configuration constants
    HEALTH_CHECK_INTERVAL = 5.0

    def __init__(self, context: "EditorContext"):
        """
        Initialize HealthMonitor.

        Args:
            context: Shared editor context
        """
        self._ctx = context

    def start(self, notify: NotifyCallback) -> None:
        """
        Start the health monitor background task.

        Args:
            notify: Async callback to send notifications to MCP client
        """
        # Only start if not already running
        if self._ctx._monitor_task is not None and not self._ctx._monitor_task.done():
            logger.debug("Health monitor already running")
            return

        self._ctx._notify_callback = notify
        self._ctx._intentional_stop = False  # Reset flag
        self._ctx._monitor_task = self._ctx.create_background_task(self._monitor_loop())
        logger.info("Health monitor started")

    def stop(self) -> None:
        """Stop the health monitor background task."""
        if self._ctx._monitor_task is not None:
            self._ctx._monitor_task.cancel()
            self._ctx._monitor_task = None

        self._ctx._notify_callback = None
        logger.info("Health monitor stopped")

    def analyze_exit(self, exit_code: int) -> dict[str, Any]:
        """
        Analyze process exit code and return detailed exit information.

        Uses CrashDetector to handle Windows crash reporting case where
        exit code is 0 but log shows crash.

        Args:
            exit_code: The process exit code

        Returns:
            Dictionary containing exit analysis
        """
        # Get log file path if available
        log_path = None
        if self._ctx.editor and self._ctx.editor.log_file_path:
            log_path = self._ctx.editor.log_file_path

        # Use CrashDetector for comprehensive analysis
        return CrashDetector.analyze_exit_with_log_check(exit_code, log_path)

    async def _monitor_loop(self) -> None:
        """
        Background coroutine that monitors editor health.

        Periodically checks if the editor process is alive.
        When the process exits, sends notification to MCP client with exit details.
        """
        logger.info("Health monitor loop started")

        try:
            while True:
                await asyncio.sleep(self.HEALTH_CHECK_INTERVAL)

                # Check if editor instance exists
                if self._ctx.editor is None:
                    logger.debug("No editor instance, monitor exiting")
                    break

                # Check if process is still running
                exit_code = self._ctx.editor.process.poll()
                if exit_code is not None:
                    # Process has exited
                    self._ctx.editor.status = "stopped"

                    # Analyze exit reason
                    exit_info = self.analyze_exit(exit_code)
                    exit_type = exit_info["exit_type"]
                    description = exit_info["description"]

                    # Check if this was an intentional stop (via editor_stop tool)
                    if self._ctx._intentional_stop:
                        logger.info(f"Editor stopped intentionally: {description}")
                        # Still notify but with info level
                        if self._ctx._notify_callback:
                            try:
                                await self._ctx._notify_callback(
                                    "info",
                                    f"Editor stopped: {description}. "
                                    f"Use 'editor_launch' to restart.",
                                )
                            except Exception as e:
                                logger.error(f"Failed to send stop notification: {e}")
                        break

                    # Determine notification level based on exit type
                    if exit_type == "normal":
                        level = "info"
                        logger.info(f"Editor exited normally (exit code: {exit_code})")
                    elif exit_type == "error":
                        level = "warning"
                        logger.warning(f"Editor exited with error (exit code: {exit_code})")
                    else:  # crash
                        level = "error"
                        logger.error(
                            f"Editor crashed (exit code: {exit_code}, "
                            f"hex: {exit_info.get('hex_code', 'N/A')})"
                        )

                    # Notify MCP client
                    if self._ctx._notify_callback:
                        try:
                            await self._ctx._notify_callback(
                                level,
                                f"{description}. Use 'editor_launch' to restart.",
                            )
                        except Exception as e:
                            logger.error(f"Failed to send exit notification: {e}")

                    # Clean up remote client connection
                    if self._ctx.editor and self._ctx.editor.remote_client:
                        self._ctx.editor.remote_client._cleanup_sockets()

                    # Exit monitor loop - no auto-restart
                    break

        except asyncio.CancelledError:
            logger.info("Health monitor cancelled")
        except Exception as e:
            logger.error(f"Health monitor error: {e}")
        finally:
            logger.info("Health monitor loop exited")
