"""
Asset change tracking module for UE-MCP.

Detects asset changes (created, deleted, modified) before and after code execution.
"""

import json
import logging
import re
from pathlib import Path
from typing import Any

from ..core.constants import MARKER_CURRENT_LEVEL_PATH, MARKER_SNAPSHOT_RESULT

logger = logging.getLogger(__name__)


def extract_game_paths(code: str) -> list[str]:
    """
    Extract /Game/xxx/ paths from Python code.

    Analyzes the code to find asset path references and returns unique
    parent directories to scan.

    Args:
        code: Python code to analyze

    Returns:
        List of unique directory paths (e.g., ["/Game/Maps/", "/Game/Blueprints/"])
    """
    # Patterns to match /Game/xxx paths in strings
    patterns = [
        r'["\'](/Game/[^"\']+)["\']',  # Simple strings: "/Game/Maps/Test"
        r'r["\'](/Game/[^"\']+)["\']',  # Raw strings: r"/Game/Maps/Test"
    ]

    paths = set()
    for pattern in patterns:
        matches = re.findall(pattern, code)
        for match in matches:
            # Convert to directory path (remove asset name, keep directory)
            # /Game/Maps/TestLevel -> /Game/Maps/
            # /Game/Blueprints/BP_Test -> /Game/Blueprints/
            # /Game/Test -> /Game/Test/  (if no subdirectory)

            # Split by / and take all but the last part (which is likely the asset name)
            parts = match.rstrip("/").split("/")

            if len(parts) >= 3:
                # Has subdirectory: /Game/Maps/TestLevel -> /Game/Maps/
                dir_path = "/".join(parts[:-1]) + "/"
            else:
                # Just /Game/Something -> scan /Game/Something/
                dir_path = match.rstrip("/") + "/"

            paths.add(dir_path)

    return list(paths)


def extract_level_paths(code: str) -> list[str]:
    """
    Extract level asset paths from Python code by detecting UE5 level-related API calls.

    This function identifies level paths by looking for specific UE5 Python API calls
    that operate on levels, rather than guessing based on path naming conventions.

    Detected APIs include:
    - LevelEditorSubsystem: load_level, new_level, new_level_from_template
    - EditorLoadingAndSavingUtils: load_map, new_map_from_template
    - EditorLevelUtils: add_level_to_world, add_level_to_world_with_transform
    - GameplayStatics: open_level, load_stream_level, unload_stream_level, get_streaming_level
    - LevelStreamingDynamic: load_level_instance

    Args:
        code: Python code to analyze

    Returns:
        List of unique level asset paths found in level-related API calls
    """
    # Patterns to match level-related API calls and extract the level path argument
    # Each pattern captures the /Game/... path from a specific API call
    level_api_patterns = [
        # LevelEditorSubsystem methods (first arg is level path)
        # .load_level("/Game/Maps/Level") or .load_level('/Game/Maps/Level')
        r"\.load_level\s*\(\s*[\"'](/Game/[^\"']+)[\"']",
        # .new_level("/Game/Maps/Level")
        r"\.new_level\s*\(\s*[\"'](/Game/[^\"']+)[\"']",
        # .new_level_from_template("/Game/Maps/New", "/Game/Maps/Template") - both are levels
        r"\.new_level_from_template\s*\(\s*[\"'](/Game/[^\"']+)[\"']",
        r"\.new_level_from_template\s*\([^,]+,\s*[\"'](/Game/[^\"']+)[\"']",
        # EditorLoadingAndSavingUtils methods
        # .load_map("/Game/Maps/Level")
        r"\.load_map\s*\(\s*[\"'](/Game/[^\"']+)[\"']",
        # .new_map_from_template("/Game/Maps/Template", ...)
        r"\.new_map_from_template\s*\(\s*[\"'](/Game/[^\"']+)[\"']",
        # EditorLevelUtils methods (second arg is level path)
        # .add_level_to_world(world, "/Game/Maps/SubLevel", ...)
        r"\.add_level_to_world\s*\([^,]+,\s*[\"'](/Game/[^\"']+)[\"']",
        # .add_level_to_world_with_transform(world, "/Game/Maps/SubLevel", ...)
        r"\.add_level_to_world_with_transform\s*\([^,]+,\s*[\"'](/Game/[^\"']+)[\"']",
        # GameplayStatics methods (second arg is level path)
        # .open_level(ctx, "/Game/Maps/Level", ...)
        r"\.open_level\s*\([^,]+,\s*[\"'](/Game/[^\"']+)[\"']",
        # .load_stream_level(ctx, "/Game/Maps/Level", ...)
        r"\.load_stream_level\s*\([^,]+,\s*[\"'](/Game/[^\"']+)[\"']",
        # .unload_stream_level(ctx, "/Game/Maps/Level", ...)
        r"\.unload_stream_level\s*\([^,]+,\s*[\"'](/Game/[^\"']+)[\"']",
        # .get_streaming_level(ctx, "/Game/Maps/Level")
        r"\.get_streaming_level\s*\([^,]+,\s*[\"'](/Game/[^\"']+)[\"']",
        # LevelStreamingDynamic (keyword arg: level_name="/Game/...")
        # .load_level_instance(..., level_name="/Game/Maps/Room", ...)
        r"level_name\s*=\s*[\"'](/Game/[^\"']+)[\"']",
    ]

    paths: set[str] = set()

    for pattern in level_api_patterns:
        matches = re.findall(pattern, code)
        for match in matches:
            # Clean up the path (remove trailing slash if any)
            level_path = match.rstrip("/")
            if level_path:
                paths.add(level_path)

    return list(paths)


def get_snapshot_script_path() -> Path:
    """Get the path to the asset_snapshot.py script."""
    return Path(__file__).parent.parent / "extra" / "scripts" / "diagnostic" / "asset_snapshot.py"


def get_current_level_path(manager) -> str | None:
    """
    Get the path of the currently loaded level in the editor.

    This executes a simple script in UE5 to query the current level path.
    Used to auto-track changes to the current level even when the code
    doesn't explicitly reference a /Game/ path.

    Args:
        manager: ExecutionManager instance

    Returns:
        Current level path as a directory (e.g., "/Game/ThirdPerson/Maps/")
        or None if no level is loaded or query failed
    """
    # Python code to get current level path in UE5
    code = """
import unreal

try:
    editor_subsystem = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    world = editor_subsystem.get_editor_world()
    if world:
        level = world.get_outer()
        if level:
            path = level.get_path_name()
            del level
            del world
            # Only return paths under /Game/ (not temp levels)
            if path.startswith("/Game/"):
                print("CURRENT_LEVEL_PATH:" + path)
            else:
                print("CURRENT_LEVEL_PATH:NONE")
        else:
            print("CURRENT_LEVEL_PATH:NONE")
    else:
        print("CURRENT_LEVEL_PATH:NONE")
except Exception as e:
    print("CURRENT_LEVEL_PATH:NONE")
"""

    # Use _execute directly to avoid recursion
    result = manager._execute_code_impl(code, timeout=10.0)

    if not result.get("success"):
        logger.debug(f"Failed to get current level path: {result.get('error')}")
        return None

    # Parse the output
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

    # Extract the path
    if MARKER_CURRENT_LEVEL_PATH in output_str:
        path = output_str.split(MARKER_CURRENT_LEVEL_PATH, 1)[1].strip()
        # Handle potential trailing content (newlines, etc.)
        path = path.split("\n")[0].strip()
        if path and path != "NONE":
            # Convert to directory path: /Game/Maps/TestLevel -> /Game/Maps/
            parts = path.rstrip("/").split("/")
            if len(parts) >= 3:
                dir_path = "/".join(parts[:-1]) + "/"
                logger.debug(f"Current level directory: {dir_path}")
                return dir_path
            elif len(parts) >= 2:
                return path.rstrip("/") + "/"

    return None


def create_snapshot(manager, paths: list[str], project_dir: str) -> dict[str, Any] | None:
    """
    Create an asset snapshot by executing the snapshot script in UE5.

    Args:
        manager: ExecutionManager instance
        paths: List of directory paths to scan
        project_dir: Project directory path for filesystem path conversion

    Returns:
        Snapshot dictionary or None if failed
    """
    if not paths:
        return None

    script_path = get_snapshot_script_path()
    if not script_path.exists():
        logger.warning(f"Snapshot script not found: {script_path}")
        return None

    # Read script content
    try:
        script_content = script_path.read_text(encoding="utf-8")
    except Exception as e:
        logger.warning(f"Failed to read snapshot script: {e}")
        return None

    # Build parameters
    params = {
        "paths": paths,
        "project_dir": project_dir,
    }

    # Build CLI args
    import json as json_module

    args = []
    for key, value in params.items():
        args.append(f"--{key.replace('_', '-')}")
        # Use JSON encoding for lists/dicts to preserve structure
        if isinstance(value, (list, dict)):
            args.append(json_module.dumps(value))
        else:
            args.append(str(value))

    # Build parameter injection code
    injection_code = f"""import sys
import os
sys.argv = {repr([str(script_path)] + args)}
os.environ['UE_MCP_MODE'] = '1'

"""

    # Concatenate injection with script content
    full_code = injection_code + script_content

    # Execute full code (avoid execute_with_checks to prevent recursion)
    result = manager._execute_code_impl(full_code, timeout=30.0)

    if not result.get("success"):
        logger.warning(f"Snapshot execution failed: {result.get('error')}")
        return None

    # Parse the JSON output from the script
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

    # Find JSON in output (marked with SNAPSHOT_RESULT:)
    if MARKER_SNAPSHOT_RESULT in output_str:
        json_str = output_str.split(MARKER_SNAPSHOT_RESULT, 1)[1].strip()
        # Handle potential trailing content
        try:
            # Find the end of JSON (closing brace at same nesting level)
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
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse snapshot JSON: {e}")
            return None

    logger.warning("No SNAPSHOT_RESULT found in output")
    return None


def compare_snapshots(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    """
    Compare two snapshots and return paths of changed assets.

    Args:
        before: Pre-execution snapshot
        after: Post-execution snapshot

    Returns:
        List of paths of assets that were created, deleted, or modified
    """
    before_assets = before.get("assets", {})
    after_assets = after.get("assets", {})

    before_paths = set(before_assets.keys())
    after_paths = set(after_assets.keys())

    changed_paths: set[str] = set()

    # New assets (created)
    changed_paths.update(after_paths - before_paths)

    # Deleted assets
    changed_paths.update(before_paths - after_paths)

    # Modified assets (timestamp changed or external file count changed for Levels)
    for path in before_paths & after_paths:
        before_ts = before_assets[path].get("timestamp", 0)
        after_ts = after_assets[path].get("timestamp", 0)

        # Check if timestamp increased
        is_modified = after_ts > before_ts

        # For Level assets, also check external file count (detects file additions/deletions)
        if not is_modified:
            before_count = before_assets[path].get("external_file_count")
            after_count = after_assets[path].get("external_file_count")
            if before_count is not None and after_count is not None:
                if before_count != after_count:
                    is_modified = True

        if is_modified:
            changed_paths.add(path)

    return sorted(changed_paths)


def get_dirty_asset_paths(manager) -> list[str]:
    """
    Get paths of dirty (unsaved) packages in the editor.

    Uses UE5's EditorLoadingAndSavingUtils to query dirty content and map packages.

    Args:
        manager: ExecutionManager instance

    Returns:
        List of package paths that have unsaved changes
    """
    code = '''import json
import unreal

try:
    dirty_content = unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()
    dirty_maps = unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()

    paths = []
    for pkg in dirty_content:
        if pkg:
            paths.append(pkg.get_path_name())
    for pkg in dirty_maps:
        if pkg:
            paths.append(pkg.get_path_name())

    print(json.dumps({"success": True, "paths": paths}))
except AttributeError:
    # EditorLoadingAndSavingUtils may not have these methods in all UE versions
    print(json.dumps({"success": True, "paths": []}))
except Exception as e:
    print(json.dumps({"success": False, "error": str(e), "paths": []}))
'''
    result = manager._execute_code_impl(code, timeout=30.0)
    if not result.get("success"):
        logger.debug(f"Failed to get dirty asset paths: {result.get('error')}")
        return []

    # Parse JSON output
    output = result.get("output", [])
    for line in reversed(output):
        line_str = str(line.get("output", "")) if isinstance(line, dict) else str(line)
        line_str = line_str.strip()
        if line_str.startswith("{"):
            try:
                data = json.loads(line_str)
                return data.get("paths", [])
            except json.JSONDecodeError:
                continue
    return []
