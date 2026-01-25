"""
Actor-based level change tracking for UE-MCP.

Works with OFPA mode by tracking actors directly instead of file timestamps.
"""
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


def create_level_actor_snapshot(manager) -> dict[str, Any] | None:
    """Create a snapshot of all actors in the currently loaded level."""
    code = '''import json
import unreal

try:
    editor_sub = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    actor_sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    world = editor_sub.get_editor_world()
    if not world:
        print("ACTOR_SNAPSHOT_RESULT:" + json.dumps({"error": "No world loaded"}))
    else:
        level = world.get_outer()
        level_path = level.get_path_name() if level else "Unknown"
        all_actors = actor_sub.get_all_level_actors()
        actors_data = {}
        for actor in all_actors:
            try:
                path_name = actor.get_path_name()
                loc = actor.get_actor_location()
                rot = actor.get_actor_rotation()
                scale = actor.get_actor_scale3d()
                actors_data[path_name] = {
                    "label": actor.get_actor_label(),
                    "class": actor.get_class().get_name(),
                    "location": [loc.x, loc.y, loc.z],
                    "rotation": [rot.pitch, rot.yaw, rot.roll],
                    "scale": [scale.x, scale.y, scale.z],
                }
            except Exception:
                pass
        result = {"level_path": level_path, "actor_count": len(actors_data), "actors": actors_data}
        print("ACTOR_SNAPSHOT_RESULT:" + json.dumps(result))
        del all_actors, world, level
except Exception as e:
    print("ACTOR_SNAPSHOT_RESULT:" + json.dumps({"error": str(e)}))
'''

    result = manager.execute_code(code, timeout=30.0)
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
    if "ACTOR_SNAPSHOT_RESULT:" in output_str:
        json_str = output_str.split("ACTOR_SNAPSHOT_RESULT:", 1)[1].strip()
        try:
            brace_count = 0
            end_idx = 0
            for i, char in enumerate(json_str):
                if char == "{": brace_count += 1
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


def compare_level_actor_snapshots(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """Compare two level actor snapshots and detect changes."""
    before_actors = before.get("actors", {})
    after_actors = after.get("actors", {})
    before_paths = set(before_actors.keys())
    after_paths = set(after_actors.keys())

    created_paths = after_paths - before_paths
    created = [{"path": p, "label": after_actors[p].get("label", ""), "class": after_actors[p].get("class", "Unknown")} for p in created_paths]

    deleted_paths = before_paths - after_paths
    deleted = [{"path": p, "label": before_actors[p].get("label", ""), "class": before_actors[p].get("class", "Unknown")} for p in deleted_paths]

    modified = []
    for path in before_paths & after_paths:
        before_data = before_actors[path]
        after_data = after_actors[path]
        changes = []
        before_loc = before_data.get("location", [0, 0, 0])
        after_loc = after_data.get("location", [0, 0, 0])
        if not _vectors_equal(before_loc, after_loc):
            changes.append({"property": "location", "before": before_loc, "after": after_loc})
        before_rot = before_data.get("rotation", [0, 0, 0])
        after_rot = after_data.get("rotation", [0, 0, 0])
        if not _vectors_equal(before_rot, after_rot, tolerance=0.01):
            changes.append({"property": "rotation", "before": before_rot, "after": after_rot})
        before_scale = before_data.get("scale", [1, 1, 1])
        after_scale = after_data.get("scale", [1, 1, 1])
        if not _vectors_equal(before_scale, after_scale):
            changes.append({"property": "scale", "before": before_scale, "after": after_scale})
        if changes:
            modified.append({"path": path, "label": after_data.get("label", ""), "class": after_data.get("class", "Unknown"), "changes": changes})

    return {"detected": bool(created or deleted or modified), "level_path": after.get("level_path", ""), "created": created, "deleted": deleted, "modified": modified}


def _vectors_equal(v1: list, v2: list, tolerance: float = 0.001) -> bool:
    """Compare two vectors with floating point tolerance."""
    if len(v1) != len(v2):
        return False
    return all(abs(a - b) < tolerance for a, b in zip(v1, v2))
