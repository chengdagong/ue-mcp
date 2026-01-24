"""
EditorContext - Shared state object for all editor subsystems.

This module provides the central context that is injected into all subsystems,
enabling them to share state while maintaining loose coupling.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .types import EditorInstance, NotifyCallback

logger = logging.getLogger(__name__)


@dataclass
class EditorContext:
    """
    Shared context passed to all subsystems via dependency injection.

    This class holds all shared state for the editor management system,
    including project information, editor instance, and background task tracking.
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
