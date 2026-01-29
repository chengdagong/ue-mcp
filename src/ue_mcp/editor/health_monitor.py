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

from .types import NotifyCallback

if TYPE_CHECKING:
    from .context import EditorContext

logger = logging.getLogger(__name__)


# Windows NTSTATUS crash codes (converted to signed 32-bit integers)
# Reference: https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-erref/596a1078-e883-4972-9bbc-49e60bebca55
WINDOWS_CRASH_CODES: dict[int, str] = {
    -1073741819: "ACCESS_VIOLATION (0xC0000005)",
    -1073741795: "ILLEGAL_INSTRUCTION (0xC000001D)",
    -1073741571: "STACK_OVERFLOW (0xC00000FD)",
    -1073740791: "HEAP_CORRUPTION (0xC0000374)",
    -1073740940: "STATUS_STACK_BUFFER_OVERRUN (0xC0000409)",
    -1073741676: "INTEGER_DIVIDE_BY_ZERO (0xC0000094)",
    -1073741675: "INTEGER_OVERFLOW (0xC0000095)",
    -1073741674: "PRIVILEGED_INSTRUCTION (0xC0000096)",
    -1073741811: "INVALID_HANDLE (0xC0000008)",
    -1073741801: "INVALID_PARAMETER (0xC000000D)",
    -1073740777: "FATAL_APP_EXIT (0xC0000417)",
}


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

    def _check_log_for_crash(self) -> bool:
        """
        Check editor log file for crash indicators.
        
        Windows crash reporting may cause UE to exit with code 0 after showing
        the "Send Report" dialog. We check the log file for crash markers.
        
        Returns:
            True if log contains crash indicators
        """
        from pathlib import Path
        
        # Get log file path from editor instance
        if self._ctx.editor is None or not self._ctx.editor.log_file_path:
            return False
        
        log_path = self._ctx.editor.log_file_path
        if not isinstance(log_path, Path):
            log_path = Path(log_path)
        
        if not log_path.exists():
            return False
        
        # Crash indicators in UE5 log
        crash_indicators = [
            "[CRASH]",
            "Fatal error:",
            "Access violation",
            "Unhandled Exception",
            "SIGSEGV",
            "Assertion failed",
            "Ensure condition failed",
            "LowLevelFatalError",
            "Out of memory",
            "GPU crash",
            "D3D11/12 crash",
            "Rendering thread exception",
            "Game thread exception",
        ]
        
        try:
            # Read last 100KB of log (most recent entries)
            file_size = log_path.stat().st_size
            read_size = min(100 * 1024, file_size)  # Last 100KB
            
            with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
                if read_size < file_size:
                    f.seek(file_size - read_size)
                log_tail = f.read()
            
            # Check for crash indicators
            for indicator in crash_indicators:
                if indicator in log_tail:
                    logger.debug(f"Found crash indicator in log: {indicator}")
                    return True
            
            return False
        except (OSError, IOError, UnicodeDecodeError) as e:
            logger.debug(f"Failed to read log file for crash check: {e}")
            return False

    def analyze_exit(self, exit_code: int) -> dict[str, Any]:
        """
        Analyze process exit code and return detailed exit information.

        Also checks for crash artifacts (folders in Saved/Crashes) because
        Windows crash reporting may cause UE to exit with code 0 after
        showing the "Send Report" dialog.

        Args:
            exit_code: The process exit code

        Returns:
            Dictionary containing:
            - exit_type: "normal", "error", or "crash"
            - exit_code: The raw exit code
            - description: Human-readable description
            - hex_code: (for crashes) Hex representation of the code
        """
        # Check for crash indicators in log even if exit code is 0
        # Windows crash reporting can mask crash with exit code 0
        log_shows_crash = self._check_log_for_crash()
        
        if exit_code == 0 and not log_shows_crash:
            return {
                "exit_type": "normal",
                "exit_code": 0,
                "description": "Editor exited normally",
            }
        elif exit_code == 0 and log_shows_crash:
            # Crash was reported but Windows showed "Send Report" dialog
            return {
                "exit_type": "crash",
                "exit_code": 0,
                "description": "Editor crashed (Windows crash report dialog was shown)",
                "note": "Exit code was 0 due to Windows crash reporting, but log shows crash",
            }
        elif exit_code > 0:
            return {
                "exit_type": "error",
                "exit_code": exit_code,
                "description": f"Editor exited with error code {exit_code}",
            }
        else:
            # Negative exit codes on Windows are NTSTATUS crash codes
            crash_name = WINDOWS_CRASH_CODES.get(exit_code)
            hex_code = hex(exit_code & 0xFFFFFFFF)

            if crash_name:
                description = f"Editor crashed: {crash_name}"
            else:
                description = f"Editor crashed with code {hex_code}"

            return {
                "exit_type": "crash",
                "exit_code": exit_code,
                "hex_code": hex_code,
                "description": description,
            }

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
