"""
Asset change tracking module for UE-MCP.

Detects asset changes (created, deleted, modified) before and after code execution.
"""
import json
import logging
import re
from pathlib import Path
from typing import Any

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


def get_snapshot_script_path() -> Path:
    """Get the path to the asset_snapshot.py script."""
    return Path(__file__).parent / "extra" / "scripts" / "diagnostic" / "asset_snapshot.py"


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
    code = '''
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
'''

    # Use _execute directly to avoid recursion
    result = manager._execute(code, timeout=10.0)

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
    if "CURRENT_LEVEL_PATH:" in output_str:
        path = output_str.split("CURRENT_LEVEL_PATH:", 1)[1].strip()
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
        manager: EditorManager instance
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

    try:
        script_content = script_path.read_text(encoding="utf-8")
    except Exception as e:
        logger.warning(f"Failed to read snapshot script: {e}")
        return None

    # Inject parameters
    params = {
        "paths": paths,
        "project_dir": project_dir,
    }

    params_code = (
        "import builtins\n"
        f"builtins.__PARAMS__ = {repr(params)}\n"
        f"__PARAMS__ = builtins.__PARAMS__\n\n"
    )

    full_code = params_code + script_content

    # Use _execute directly to avoid recursion (execute_with_checks would trigger tracking again)
    result = manager._execute(full_code, timeout=30.0)

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
    if "SNAPSHOT_RESULT:" in output_str:
        json_str = output_str.split("SNAPSHOT_RESULT:", 1)[1].strip()
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


def compare_snapshots(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """
    Compare two snapshots and detect changes.

    Args:
        before: Pre-execution snapshot
        after: Post-execution snapshot

    Returns:
        Dictionary with detected changes:
        {
            "detected": bool,
            "scanned_paths": [...],
            "created": [{"path": ..., "asset_type": ...}, ...],
            "deleted": [{"path": ..., "asset_type": ...}, ...],
            "modified": [{"path": ..., "asset_type": ...}, ...]
        }
    """
    before_assets = before.get("assets", {})
    after_assets = after.get("assets", {})

    before_paths = set(before_assets.keys())
    after_paths = set(after_assets.keys())

    # New assets
    created_paths = after_paths - before_paths
    created = [
        {
            "path": path,
            "asset_type": after_assets[path].get("asset_type", "Unknown"),
        }
        for path in created_paths
    ]

    # Deleted assets
    deleted_paths = before_paths - after_paths
    deleted = [
        {
            "path": path,
            "asset_type": before_assets[path].get("asset_type", "Unknown"),
        }
        for path in deleted_paths
    ]

    # Modified assets (timestamp changed or external file count changed for Levels)
    modified = []
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
            modified.append({
                "path": path,
                "asset_type": after_assets[path].get("asset_type", "Unknown"),
            })

    return {
        "detected": bool(created or deleted or modified),
        "scanned_paths": after.get("scanned_paths", []),
        "created": created,
        "deleted": deleted,
        "modified": modified,
    }


def gather_change_details(manager, changes: dict[str, Any]) -> dict[str, Any]:
    """
    Gather detailed information for changed assets.

    For Level assets: runs diagnostic
    For other assets: runs lightweight inspect

    Args:
        manager: EditorManager instance
        changes: Changes dictionary from compare_snapshots

    Returns:
        Updated changes dictionary with details populated
    """
    from .script_executor import get_diagnostic_scripts_dir

    diagnostic_script = get_diagnostic_scripts_dir() / "diagnostic_runner.py"
    inspect_script = get_diagnostic_scripts_dir() / "inspect_runner.py"

    def run_script(script_path: Path, params: dict) -> dict[str, Any] | None:
        """Execute a diagnostic/inspect script and parse result."""
        if not script_path.exists():
            return None

        try:
            script_content = script_path.read_text(encoding="utf-8")
        except Exception:
            return None

        params_code = (
            "import builtins\n"
            f"builtins.__PARAMS__ = {repr(params)}\n"
            f"__PARAMS__ = builtins.__PARAMS__\n\n"
        )

        full_code = params_code + script_content
        result = manager._execute(full_code, timeout=60.0)

        if not result.get("success"):
            return None

        # Parse JSON output
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

        # Find JSON result (marked with MCP_RESULT:)
        if "MCP_RESULT:" in output_str:
            json_str = output_str.split("MCP_RESULT:", 1)[1].strip()
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
                return json.loads(json_str)
            except json.JSONDecodeError:
                return None

        return None

    # Process created and modified assets
    for change_list in [changes.get("created", []), changes.get("modified", [])]:
        for change in change_list:
            asset_path = change["path"]
            asset_type = change["asset_type"]

            if asset_type == "Level":
                # Run diagnostic for Level assets
                result = run_script(diagnostic_script, {"asset_path": asset_path})
                if result:
                    change["details"] = {
                        "errors": result.get("errors", 0),
                        "warnings": result.get("warnings", 0),
                        "issues": result.get("issues", []),
                    }
            else:
                # Run lightweight inspect for other assets
                result = run_script(inspect_script, {
                    "asset_path": asset_path
                })
                if result:
                    change["details"] = {
                        "properties": result.get("properties", {}),
                        "screenshot_path": result.get("screenshot_path"),
                    }

    return changes
