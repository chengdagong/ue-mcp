"""
Type definitions for the editor subsystem.

This module contains shared type definitions used across all editor subsystems.
"""

import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Coroutine, Optional

from ..remote_client import RemoteExecutionClient

# Callback type definitions
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
    unattended: bool = False  # Whether editor was launched with -unattended flag
