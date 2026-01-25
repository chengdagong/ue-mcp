"""
File-based completion watcher for UE-MCP.

Monitors for {task_id}_completed files in Saved/Logs directory.
Used for async notification when PIE capture completes.
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional, Union

logger = logging.getLogger(__name__)


class CompletionWatcher:
    """Watches for task completion file."""

    def __init__(self, completion_file: Path, poll_interval: float = 0.5):
        """
        Initialize completion watcher.

        Args:
            completion_file: Path to completion file to watch for
            poll_interval: How often to check for file (seconds)
        """
        self.completion_file = completion_file
        self.poll_interval = poll_interval
        self._stop_event = asyncio.Event()

    async def wait_for_completion(
        self,
        callback: Optional[Callable[[dict[str, Any]], Union[None, Awaitable[None]]]] = None,
        timeout: Optional[float] = None,
    ) -> Optional[dict[str, Any]]:
        """
        Wait for completion file to appear, read result, delete file.

        Args:
            callback: Function to call when completion found (receives parsed JSON)
            timeout: Maximum time to wait (None = indefinite)

        Returns:
            Parsed result dict if found, None if timeout
        """
        self._stop_event.clear()
        start_time = asyncio.get_event_loop().time()

        logger.info(f"Watching for completion file: {self.completion_file}")

        while not self._stop_event.is_set():
            # Check timeout
            if timeout is not None:
                elapsed = asyncio.get_event_loop().time() - start_time
                if elapsed >= timeout:
                    logger.warning(f"Completion watcher timeout after {timeout}s")
                    return None

            # Check if file exists
            if self.completion_file.exists():
                try:
                    # Read result JSON from file
                    content = self.completion_file.read_text(encoding="utf-8")
                    result = json.loads(content)
                    logger.info(f"Found completion file, result: {result}")

                    # Delete file
                    self.completion_file.unlink()
                    logger.info(f"Deleted completion file: {self.completion_file}")

                    # Call callback (supports both sync and async)
                    if callback is not None:
                        cb_result = callback(result)
                        if asyncio.iscoroutine(cb_result):
                            await cb_result

                    return result
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse JSON from completion file: {e}")
                    # Try to delete corrupt file
                    try:
                        self.completion_file.unlink()
                    except Exception:
                        pass
                    return None
                except Exception as e:
                    logger.error(f"Error reading completion file: {e}")
                    return None

            await asyncio.sleep(self.poll_interval)

        return None

    def stop(self):
        """Stop watching."""
        self._stop_event.set()


async def watch_pie_capture_complete(
    project_root: Path,
    task_id: str,
    callback: Optional[Callable[[dict[str, Any]], Union[None, Awaitable[None]]]] = None,
    timeout: Optional[float] = None,
) -> Optional[dict[str, Any]]:
    """
    Watch for PIE capture completion.

    Args:
        project_root: UE5 project root directory
        task_id: Unique task identifier
        callback: Function to call when capture completes
        timeout: Maximum time to wait

    Returns:
        Capture result dict if found, None if timeout
    """
    # Completion file: {project}/Saved/Logs/{task_id}_completed
    completion_file = project_root / "Saved" / "Logs" / f"{task_id}_completed"

    watcher = CompletionWatcher(completion_file)
    return await watcher.wait_for_completion(callback, timeout)
