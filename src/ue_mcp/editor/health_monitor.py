"""
HealthMonitor - Monitors editor health and handles auto-restart.

This subsystem handles:
- Periodic health checks of the editor process
- Detecting editor crashes
- Automatic restart with cooldown and attempt limits
"""

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Optional

from .types import NotifyCallback

if TYPE_CHECKING:
    from .context import EditorContext

logger = logging.getLogger(__name__)


class HealthMonitor:
    """
    Monitors editor health and handles automatic restart on crash.

    This subsystem runs a background task that periodically checks if the
    editor process is still alive, and attempts to restart it if it crashes.
    """

    # Configuration constants
    MAX_RESTART_ATTEMPTS = 3
    RESTART_COOLDOWN_SECONDS = 10.0
    HEALTH_CHECK_INTERVAL = 5.0

    def __init__(self, context: "EditorContext"):
        """
        Initialize HealthMonitor.

        Args:
            context: Shared editor context
        """
        self._ctx = context
        self._restart_callback: Optional[Callable[..., Awaitable[dict[str, Any]]]] = None

    def set_restart_callback(
        self, callback: Callable[..., Awaitable[dict[str, Any]]]
    ) -> None:
        """
        Set the callback to use for restart attempts.

        This callback should be the _launch_internal method from LaunchManager.

        Args:
            callback: Async function to call for restart
        """
        self._restart_callback = callback

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

    async def _monitor_loop(self) -> None:
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
                if self._ctx.editor is None:
                    logger.debug("No editor instance, monitor exiting")
                    break

                # Check if process is still running
                exit_code = self._ctx.editor.process.poll()
                if exit_code is not None:
                    # Process has exited
                    self._ctx.editor.status = "stopped"

                    # Check if this was an intentional stop
                    if self._ctx._intentional_stop:
                        logger.info("Editor stopped intentionally, no restart needed")
                        break

                    # Editor crashed - notify and attempt restart
                    logger.warning(f"Editor process exited unexpectedly (exit code: {exit_code})")

                    if self._ctx._notify_callback:
                        try:
                            await self._ctx._notify_callback(
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
                        if self._ctx._notify_callback:
                            try:
                                await self._ctx._notify_callback(
                                    "error",
                                    f"Failed to restart editor after {self._ctx._restart_count} attempts. "
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
        if self._restart_callback is None:
            logger.error("No restart callback set, cannot restart")
            return False

        # Check restart count
        if self._ctx._restart_count >= self.MAX_RESTART_ATTEMPTS:
            logger.error(f"Maximum restart attempts ({self.MAX_RESTART_ATTEMPTS}) reached")
            return False

        # Check cooldown
        current_time = time.time()
        if self._ctx._last_restart_time is not None:
            elapsed = current_time - self._ctx._last_restart_time
            if elapsed < self.RESTART_COOLDOWN_SECONDS:
                # Still in cooldown, wait for remaining time
                remaining = self.RESTART_COOLDOWN_SECONDS - elapsed
                logger.info(f"Restart cooldown: waiting {remaining:.1f}s")
                await asyncio.sleep(remaining)

        # Save launch parameters before cleanup
        if self._ctx.editor is None:
            logger.error("No editor instance to restart from")
            return False

        additional_paths = self._ctx.editor.additional_paths
        wait_timeout = self._ctx.editor.wait_timeout

        # Clean up old connection (but not the process - it's already dead)
        if self._ctx.editor.remote_client:
            self._ctx.editor.remote_client._cleanup_sockets()
        self._ctx.editor = None

        # Update restart tracking
        self._ctx._restart_count += 1
        self._ctx._last_restart_time = time.time()

        logger.info(f"Attempting restart {self._ctx._restart_count}/{self.MAX_RESTART_ATTEMPTS}...")

        # Send restart notification
        if self._ctx._notify_callback:
            try:
                await self._ctx._notify_callback(
                    "info",
                    f"Restarting editor (attempt {self._ctx._restart_count}/{self.MAX_RESTART_ATTEMPTS})...",
                )
            except Exception as e:
                logger.error(f"Failed to send restart notification: {e}")

        # Attempt to launch (don't reset restart count here)
        try:
            result = await self._restart_callback(
                notify=self._ctx._notify_callback,
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
                    if self._ctx._notify_callback:
                        try:
                            await self._ctx._notify_callback(
                                "error",
                                "Editor restart failed: project needs to be built. "
                                "Run 'project_build' and then 'editor_launch' manually.",
                            )
                        except Exception:
                            pass
                    # Exhaust restart attempts to prevent further attempts
                    self._ctx._restart_count = self.MAX_RESTART_ATTEMPTS

                return False

        except Exception as e:
            logger.error(f"Exception during restart: {e}")
            return False
