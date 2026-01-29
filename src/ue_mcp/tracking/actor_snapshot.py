"""
Actor-based level change tracking for UE-MCP.

Works with OFPA mode by tracking actors directly instead of file timestamps.
"""

import json
import logging
from typing import Any

from ..core.constants import MARKER_ACTOR_SNAPSHOT_RESULT

logger = logging.getLogger(__name__)


def create_level_actor_snapshot(manager, level_paths: list[str] | None = None) -> dict[str, Any] | None:
    """
    Create a snapshot of all actors in the specified levels.

    Args:
        manager: ExecutionManager instance
        level_paths: Optional list of level asset paths to snapshot (e.g., ["/Game/Maps/TestLevel"]).
                    If None or empty, snapshots the currently loaded level.

    Returns:
        Snapshot dictionary with actor data for all levels, or None if failed.
        Format: {
            "levels": {
                "/Game/Maps/TestLevel": {
                    "level_path": "/Game/Maps/TestLevel.TestLevel:PersistentLevel",
                    "actor_count": 10,
                    "actors": {...}
                },
                ...
            },
            "current_level": "/Game/Maps/CurrentLevel.CurrentLevel:PersistentLevel"
        }
    """
    import json as json_module

    # Build the list of level paths to pass to the script
    level_paths_json = json_module.dumps(level_paths or [])

    code = f"""import json
import unreal

level_paths_to_check = {level_paths_json}

# Initialize variables for cleanup in finally block
editor_sub = None
actor_sub = None
world = None
current_level = None
all_actors = None

try:
    editor_sub = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    actor_sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    world = editor_sub.get_editor_world()

    if not world:
        print("ACTOR_SNAPSHOT_RESULT:" + json.dumps({{"error": "No world loaded"}}))
    else:
        current_level = world.get_outer()
        current_level_path = current_level.get_path_name() if current_level else "Unknown"

        levels_data = {{}}

        # Always snapshot the current level
        all_actors = actor_sub.get_all_level_actors()
        actors_data = {{}}
        for actor in all_actors:
            try:
                path_name = actor.get_path_name()
                loc = actor.get_actor_location()
                rot = actor.get_actor_rotation()
                scale = actor.get_actor_scale3d()
                actors_data[path_name] = {{
                    "label": actor.get_actor_label(),
                    "class": actor.get_class().get_name(),
                    "location": [loc.x, loc.y, loc.z],
                    "rotation": [rot.pitch, rot.yaw, rot.roll],
                    "scale": [scale.x, scale.y, scale.z],
                }}
            except Exception:
                pass

        # Extract asset path from full level path (remove .LevelName:PersistentLevel suffix)
        current_asset_path = current_level_path.split(".")[0] if "." in current_level_path else current_level_path
        levels_data[current_asset_path] = {{
            "level_path": current_level_path,
            "actor_count": len(actors_data),
            "actors": actors_data,
        }}

        # Note: Streaming level snapshot not supported - UE5 Python API doesn't expose
        # Level.get_level_actors() or World.get_streaming_levels() for sub-level access.
        # Only the current persistent level is snapshotted.

        result = {{
            "levels": levels_data,
            "current_level": current_level_path,
        }}
        print("ACTOR_SNAPSHOT_RESULT:" + json.dumps(result))
except Exception as e:
    print("ACTOR_SNAPSHOT_RESULT:" + json.dumps({{"error": str(e)}}))
finally:
    # Clean up references to prevent World memory leaks
    # Use explicit cleanup since del locals()[x] doesn't work reliably
    all_actors = None
    world = None
    current_level = None
    editor_sub = None
    actor_sub = None
"""

    result = manager._execute_code_impl(code, timeout=30.0)
    if not result.get("success"):
        logger.debug(f"Failed to create actor snapshot: {result.get('error')}")
        return None
    output = result.get("output", [])
    output_str = ""
    if isinstance(output, list):
        for line in output:
            if isinstance(line, dict):
                output_str += str(line.get("output", ""))
            else:
                output_str += str(line)
    else:
        output_str = str(output)
    if MARKER_ACTOR_SNAPSHOT_RESULT in output_str:
        json_str = output_str.split(MARKER_ACTOR_SNAPSHOT_RESULT, 1)[1].strip()
        try:
            brace_count = 0
            end_idx = 0
            for i, char in enumerate(json_str):
                if char == "{":
                    brace_count += 1
                elif char == "}":
                    brace_count -= 1
                    if brace_count == 0:
                        end_idx = i + 1
                        break
            json_str = json_str[:end_idx]
            snapshot = json.loads(json_str)
            if "error" in snapshot:
                logger.debug(f"Actor snapshot error: {snapshot['error']}")
                return None
            return snapshot
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse actor snapshot JSON: {e}")
            return None
    logger.debug("No ACTOR_SNAPSHOT_RESULT found in output")
    return None


def compare_level_actor_snapshots(
    before: dict[str, Any], after: dict[str, Any]
) -> dict[str, list[str]]:
    """
    Compare two multi-level actor snapshots and detect changes.

    Args:
        before: Pre-execution snapshot with "levels" dict
        after: Post-execution snapshot with "levels" dict

    Returns:
        Dictionary mapping level asset paths to lists of changed actor paths.
        Only includes levels that have changes.
        Format: {
            "/Game/Maps/TestLevel": [actor_path1, actor_path2, ...],
            ...
        }
    """
    # Handle both old format (single level) and new format (multiple levels)
    if "levels" in before and "levels" in after:
        before_levels = before.get("levels", {})
        after_levels = after.get("levels", {})
    else:
        # Old format compatibility: convert to new format
        before_level_path = before.get("level_path", "")
        after_level_path = after.get("level_path", "")
        before_asset_path = (
            before_level_path.split(".")[0] if "." in before_level_path else before_level_path
        )
        after_asset_path = (
            after_level_path.split(".")[0] if "." in after_level_path else after_level_path
        )

        before_levels = {before_asset_path: before} if before_asset_path else {}
        after_levels = {after_asset_path: after} if after_asset_path else {}

    changed_levels: dict[str, list[str]] = {}

    # Compare each level
    all_level_paths = set(before_levels.keys()) | set(after_levels.keys())

    for level_path in all_level_paths:
        before_level = before_levels.get(level_path, {"actors": {}})
        after_level = after_levels.get(level_path, {"actors": {}})

        before_actors = before_level.get("actors", {})
        after_actors = after_level.get("actors", {})

        before_paths = set(before_actors.keys())
        after_paths = set(after_actors.keys())

        changed_actors: list[str] = []

        # New actors (created)
        changed_actors.extend(after_paths - before_paths)

        # Deleted actors
        changed_actors.extend(before_paths - after_paths)

        # Modified actors
        for actor_path in before_paths & after_paths:
            before_data = before_actors[actor_path]
            after_data = after_actors[actor_path]

            is_modified = False

            before_loc = before_data.get("location", [0, 0, 0])
            after_loc = after_data.get("location", [0, 0, 0])
            if not _vectors_equal(before_loc, after_loc):
                is_modified = True

            if not is_modified:
                before_rot = before_data.get("rotation", [0, 0, 0])
                after_rot = after_data.get("rotation", [0, 0, 0])
                if not _vectors_equal(before_rot, after_rot, tolerance=0.01):
                    is_modified = True

            if not is_modified:
                before_scale = before_data.get("scale", [1, 1, 1])
                after_scale = after_data.get("scale", [1, 1, 1])
                if not _vectors_equal(before_scale, after_scale):
                    is_modified = True

            if is_modified:
                changed_actors.append(actor_path)

        if changed_actors:
            changed_levels[level_path] = changed_actors

    return changed_levels


def _vectors_equal(v1: list, v2: list, tolerance: float = 0.001) -> bool:
    """Compare two vectors with floating point tolerance."""
    if len(v1) != len(v2):
        return False
    return all(abs(a - b) < tolerance for a, b in zip(v1, v2))
