"""
Asset snapshot script for UE-MCP.

Takes a snapshot of assets in specified directories, including their types and
filesystem timestamps. Runs inside UE5 editor.

MCP mode (__PARAMS__):
    paths: list[str] - Directory paths to scan (e.g., ["/Game/Maps/", "/Game/Blueprints/"])
    project_dir: str - Project directory path for filesystem path conversion
"""
import json
import os
import sys
import time

import unreal


# Asset class to type mapping
_ASSET_TYPE_MAP = {
    "World": "Level",
    "Blueprint": "Blueprint",
    "WidgetBlueprint": "WidgetBlueprint",
    "Material": "Material",
    "MaterialInstance": "MaterialInstance",
    "MaterialInstanceConstant": "MaterialInstance",
    "StaticMesh": "StaticMesh",
    "SkeletalMesh": "SkeletalMesh",
    "Texture2D": "Texture",
    "TextureCube": "Texture",
    "SoundWave": "Sound",
    "SoundCue": "Sound",
    "AnimSequence": "Animation",
    "AnimMontage": "Animation",
    "AnimBlueprint": "AnimBlueprint",
    "ParticleSystem": "ParticleSystem",
    "NiagaraSystem": "NiagaraSystem",
    "DataAsset": "DataAsset",
    "DataTable": "DataTable",
    "CurveTable": "CurveTable",
    "CurveFloat": "Curve",
    "CurveLinearColor": "Curve",
    "CurveVector": "Curve",
}


def get_params() -> dict:
    """Get parameters from MCP server."""
    import builtins
    if hasattr(builtins, "__PARAMS__"):
        return builtins.__PARAMS__
    raise RuntimeError("No __PARAMS__ found - this script must be run via MCP")


def get_asset_type(asset_path: str) -> str:
    """Get the asset type from asset data."""
    try:
        asset_data = unreal.EditorAssetLibrary.find_asset_data(asset_path)
        if asset_data and asset_data.is_valid():
            asset_class = str(asset_data.asset_class_path.asset_name)
            return _ASSET_TYPE_MAP.get(asset_class, asset_class)
    except Exception:
        pass
    return "Unknown"


def asset_to_filesystem_path(asset_path: str, project_dir: str) -> str | None:
    """
    Convert an asset path to filesystem path.

    Args:
        asset_path: UE asset path (e.g., /Game/Maps/TestLevel or
                    /Game/Maps/TestLevel.TestLevel with object name suffix)
        project_dir: Project directory path

    Returns:
        Filesystem path to the .uasset or .umap file, or None if not found
    """
    # /Game/xxx -> Content/xxx
    if not asset_path.startswith("/Game/"):
        return None

    # Strip object name suffix if present
    # e.g., /Game/Tests/MyLevel.MyLevel -> /Game/Tests/MyLevel
    # The object name is after the last dot, but only if it comes after the last slash
    last_slash = asset_path.rfind("/")
    last_dot = asset_path.rfind(".")
    if last_dot > last_slash:
        asset_path = asset_path[:last_dot]

    relative = asset_path.replace("/Game/", "Content/", 1)

    # Try .umap first (for Level assets)
    umap_path = os.path.join(project_dir, relative + ".umap")
    if os.path.exists(umap_path):
        return umap_path

    # Try .uasset
    uasset_path = os.path.join(project_dir, relative + ".uasset")
    if os.path.exists(uasset_path):
        return uasset_path

    return None


def get_external_dir_paths(asset_path: str, project_dir: str) -> tuple[str | None, str | None]:
    """
    Get the __ExternalActors__ and __ExternalObjects__ directory paths for a Level asset.

    For OFPA (One File Per Actor) mode, UE5 stores actor and object data in separate
    directories rather than in the main .umap file.

    Args:
        asset_path: UE asset path (e.g., /Game/ThirdPerson/Lvl_ThirdPerson)
        project_dir: Project directory path

    Returns:
        Tuple of (external_actors_dir, external_objects_dir), either can be None if not found

    Example:
        For /Game/ThirdPerson/Lvl_ThirdPerson:
        - external_actors: Content/__ExternalActors__/ThirdPerson/Lvl_ThirdPerson/
        - external_objects: Content/__ExternalObjects__/ThirdPerson/Lvl_ThirdPerson/
    """
    if not asset_path.startswith("/Game/"):
        return None, None

    # Strip object name suffix if present
    last_slash = asset_path.rfind("/")
    last_dot = asset_path.rfind(".")
    if last_dot > last_slash:
        asset_path = asset_path[:last_dot]

    # /Game/ThirdPerson/Lvl_ThirdPerson -> ThirdPerson/Lvl_ThirdPerson
    relative = asset_path.replace("/Game/", "", 1)

    external_actors_dir = os.path.join(project_dir, "Content", "__ExternalActors__", relative)
    external_objects_dir = os.path.join(project_dir, "Content", "__ExternalObjects__", relative)

    actors_path = external_actors_dir if os.path.isdir(external_actors_dir) else None
    objects_path = external_objects_dir if os.path.isdir(external_objects_dir) else None

    return actors_path, objects_path


def get_dir_stats(dir_path: str) -> tuple[float, int]:
    """
    Get stats for all .uasset files in a directory tree.

    Args:
        dir_path: Directory path to scan

    Returns:
        Tuple of (max_timestamp, file_count)
    """
    max_ts = 0.0
    file_count = 0
    try:
        for root, dirs, files in os.walk(dir_path):
            for filename in files:
                if filename.endswith(".uasset"):
                    file_count += 1
                    file_path = os.path.join(root, filename)
                    try:
                        ts = os.path.getmtime(file_path)
                        if ts > max_ts:
                            max_ts = ts
                    except OSError:
                        pass
    except OSError:
        pass
    return max_ts, file_count


def get_level_stats_with_externals(
    asset_path: str, project_dir: str, main_file_path: str | None
) -> tuple[float, int]:
    """
    Get the effective timestamp and external file count for a Level asset.

    For Level assets with OFPA enabled, this considers:
    - The main .umap file timestamp
    - All files in __ExternalActors__/[level_path]/
    - All files in __ExternalObjects__/[level_path]/

    Args:
        asset_path: UE asset path
        project_dir: Project directory path
        main_file_path: Filesystem path to the main .umap file (can be None)

    Returns:
        Tuple of (max_timestamp, total_external_file_count)
        - max_timestamp: Maximum timestamp among main file and all external files
        - total_external_file_count: Total number of files in external directories
    """
    max_ts = 0.0
    total_file_count = 0

    # Get main file timestamp
    if main_file_path:
        try:
            max_ts = os.path.getmtime(main_file_path)
        except OSError:
            pass

    # Get external directories
    external_actors_dir, external_objects_dir = get_external_dir_paths(asset_path, project_dir)

    # Check external actors
    if external_actors_dir:
        actors_ts, actors_count = get_dir_stats(external_actors_dir)
        if actors_ts > max_ts:
            max_ts = actors_ts
        total_file_count += actors_count

    # Check external objects
    if external_objects_dir:
        objects_ts, objects_count = get_dir_stats(external_objects_dir)
        if objects_ts > max_ts:
            max_ts = objects_ts
        total_file_count += objects_count

    return max_ts, total_file_count


def take_snapshot(paths: list[str], project_dir: str) -> dict:
    """
    Take a snapshot of assets in the specified directories.

    Args:
        paths: List of directory paths to scan
        project_dir: Project directory for filesystem path conversion

    Returns:
        Snapshot dictionary:
        {
            "timestamp": float,
            "scanned_paths": [...],
            "assets": {
                "/Game/Maps/TestLevel": {
                    "asset_type": "Level",
                    "timestamp": 1234567890.123
                },
                ...
            }
        }
    """
    result = {
        "timestamp": time.time(),
        "scanned_paths": paths,
        "assets": {},
    }

    for scan_path in paths:
        try:
            # List all assets in this path (recursive)
            assets = unreal.EditorAssetLibrary.list_assets(
                scan_path.rstrip("/"),
                recursive=True,
                include_folder=False
            )

            if not assets:
                continue

            for asset_path in assets:
                asset_path = str(asset_path)

                # Skip if already processed
                if asset_path in result["assets"]:
                    continue

                # Get asset type
                asset_type = get_asset_type(asset_path)

                # Get filesystem timestamp
                fs_path = asset_to_filesystem_path(asset_path, project_dir)
                timestamp = 0.0
                external_file_count = None  # Only set for Level assets

                # For Level assets, also check __ExternalActors__ and __ExternalObjects__
                # directories (OFPA mode stores actor/object data separately)
                if asset_type == "Level":
                    timestamp, external_file_count = get_level_stats_with_externals(
                        asset_path, project_dir, fs_path
                    )
                elif fs_path:
                    try:
                        timestamp = os.path.getmtime(fs_path)
                    except OSError:
                        pass

                asset_data = {
                    "asset_type": asset_type,
                    "timestamp": timestamp,
                }
                # Add external file count for Level assets (used to detect file additions/deletions)
                if external_file_count is not None:
                    asset_data["external_file_count"] = external_file_count

                result["assets"][asset_path] = asset_data

        except Exception as e:
            # Log but continue with other paths
            print(f"Warning: Failed to scan {scan_path}: {e}")

    return result


def main():
    """Main entry point."""
    params = get_params()

    paths = params.get("paths", [])
    project_dir = params.get("project_dir", "")

    if not paths:
        print("SNAPSHOT_RESULT:" + json.dumps({
            "error": "No paths specified",
            "timestamp": time.time(),
            "scanned_paths": [],
            "assets": {},
        }))
        return

    if not project_dir:
        print("SNAPSHOT_RESULT:" + json.dumps({
            "error": "No project_dir specified",
            "timestamp": time.time(),
            "scanned_paths": paths,
            "assets": {},
        }))
        return

    snapshot = take_snapshot(paths, project_dir)
    print("SNAPSHOT_RESULT:" + json.dumps(snapshot))


# Execute main
main()
