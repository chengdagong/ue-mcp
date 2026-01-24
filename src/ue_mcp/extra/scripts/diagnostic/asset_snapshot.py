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
        asset_path: UE asset path (e.g., /Game/Maps/TestLevel)
        project_dir: Project directory path

    Returns:
        Filesystem path to the .uasset or .umap file, or None if not found
    """
    # /Game/xxx -> Content/xxx
    if not asset_path.startswith("/Game/"):
        return None

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
                if fs_path:
                    try:
                        timestamp = os.path.getmtime(fs_path)
                    except OSError:
                        pass

                result["assets"][asset_path] = {
                    "asset_type": asset_type,
                    "timestamp": timestamp,
                }

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
