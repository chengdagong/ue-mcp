"""
Asset query script for querying project assets by type.

Queries Blueprint and World (Level) assets in the project's /Game directory.

Usage:
    # Via MCP (parameters auto-injected):
    MCP tool calls this script automatically

    # Via UE Python console:
    import sys
    sys.argv = ['asset_query.py', '--types', 'Blueprint,World', '--base-path', '/Game']
    exec(open(r'D:\\path\\to\\asset_query.py').read())

Parameters:
    types: Comma-separated list of asset types to query (default: Blueprint,World)
    base_path: Base path to search in (default: /Game)
    limit: Maximum number of assets per type (default: 100)
"""

import argparse
import json

import unreal


# Asset type definitions for UE5.1+
ASSET_TYPE_PATHS = {
    "Blueprint": unreal.TopLevelAssetPath("/Script/Engine", "Blueprint"),
    "World": unreal.TopLevelAssetPath("/Script/Engine", "World"),
    "StaticMesh": unreal.TopLevelAssetPath("/Script/Engine", "StaticMesh"),
    "SkeletalMesh": unreal.TopLevelAssetPath("/Script/Engine", "SkeletalMesh"),
    "Material": unreal.TopLevelAssetPath("/Script/Engine", "Material"),
    "Texture2D": unreal.TopLevelAssetPath("/Script/Engine", "Texture2D"),
}


def query_assets_by_type(asset_type_path, base_path="/Game", limit=100):
    """
    Query assets of a specific type.

    Args:
        asset_type_path: TopLevelAssetPath for the asset type
        base_path: Base path to search in
        limit: Maximum number of assets to return

    Returns:
        List of asset info dicts
    """
    asset_reg = unreal.AssetRegistryHelpers.get_asset_registry()

    ar_filter = unreal.ARFilter(
        package_paths=[base_path],
        class_paths=[asset_type_path],
        recursive_paths=True,
        recursive_classes=True,
    )

    assets = asset_reg.get_assets(ar_filter)

    results = []
    if assets:
        for asset in assets[:limit]:
            results.append({
                "name": str(asset.asset_name),
                "path": str(asset.package_name),
            })

    return results


def main():
    """Main entry point."""
    # Bootstrap from environment variables (must be before argparse)
    from ue_mcp_capture.utils import bootstrap_from_env
    bootstrap_from_env()

    parser = argparse.ArgumentParser(
        description="Query project assets by type."
    )
    parser.add_argument(
        "--types",
        default="Blueprint,World",
        help="Comma-separated list of asset types to query (default: Blueprint,World)",
    )
    parser.add_argument(
        "--base-path",
        default="/Game",
        help="Base path to search in (default: /Game)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Maximum number of assets per type (default: 100)",
    )
    args = parser.parse_args()

    types_to_query = [t.strip() for t in args.types.split(",")]
    base_path = args.base_path
    limit = args.limit

    result = {
        "success": True,
        "base_path": base_path,
        "assets": {},
    }

    for asset_type in types_to_query:
        if asset_type not in ASSET_TYPE_PATHS:
            result["assets"][asset_type] = {
                "error": f"Unknown asset type: {asset_type}",
                "items": [],
                "count": 0,
            }
            continue

        type_path = ASSET_TYPE_PATHS[asset_type]
        items = query_assets_by_type(type_path, base_path, limit)

        result["assets"][asset_type] = {
            "items": items,
            "count": len(items),
            "truncated": len(items) >= limit,
        }

    # Output result as pure JSON
    print(json.dumps(result))


if __name__ == "__main__":
    main()
