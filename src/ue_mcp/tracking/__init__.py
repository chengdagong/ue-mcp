"""
UE-MCP Tracking Module

Change tracking for actors and assets in UE5 projects.
"""

from .actor_snapshot import (
    compare_level_actor_snapshots,
    create_level_actor_snapshot,
)
from .asset_tracker import (
    compare_snapshots,
    create_snapshot,
    extract_game_paths,
    extract_level_paths,
    get_current_level_path,
    get_dirty_asset_paths,
    get_snapshot_script_path,
)
from .log_watcher import (
    CompletionWatcher,
    watch_pie_capture_complete,
)

__all__ = [
    # Actor snapshot
    "create_level_actor_snapshot",
    "compare_level_actor_snapshots",
    # Asset tracker
    "extract_game_paths",
    "extract_level_paths",
    "get_snapshot_script_path",
    "get_current_level_path",
    "get_dirty_asset_paths",
    "create_snapshot",
    "compare_snapshots",
    # Log watcher
    "CompletionWatcher",
    "watch_pie_capture_complete",
]
