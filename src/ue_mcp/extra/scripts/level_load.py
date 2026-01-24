"""
Level loading script.

Loads a level in the editor using LevelEditorSubsystem.

Usage:
    # Via MCP (parameters auto-injected):
    MCP tool calls this script automatically

    # Via UE Python console:
    import sys
    sys.argv = ['level_load.py', '--level-path', '/Game/Maps/MyLevel']
    # exec(open(r'D:\\path\\to\\level_load.py').read())

Parameters:
    level_path: Path to the level to load (e.g., /Game/Maps/MyLevel)
"""

import argparse
import json

import unreal


def level_exists(level_path: str) -> bool:
    """Check if a level asset exists in the asset registry."""
    registry = unreal.AssetRegistryHelpers.get_asset_registry()

    # Use get_assets_by_package_name which takes a simple package path
    # e.g., /Game/Maps/MyLevel
    assets = registry.get_assets_by_package_name(level_path)
    if assets is not None and len(assets) > 0:
        return True

    return False


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Load a level in the editor.")
    parser.add_argument(
        "--level-path",
        required=True,
        help="Path to the level to load (e.g., /Game/Maps/MyLevel)",
    )
    args = parser.parse_args()
    level_path = args.level_path

    # Validate level path format
    if not level_path.startswith("/Game/"):
        result = {
            "success": False,
            "error": f"Invalid level path: {level_path}. Must start with /Game/",
        }
        print(json.dumps(result))
        return

    # Check if level exists before attempting to load
    if not level_exists(level_path):
        result = {
            "success": False,
            "error": f"Level not found: {level_path}",
            "level_path": level_path,
        }
        print(json.dumps(result))
        return

    # Get LevelEditorSubsystem
    level_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    if not level_subsystem:
        result = {
            "success": False,
            "error": "Failed to get LevelEditorSubsystem",
        }
        print(json.dumps(result))
        return

    # Load the level
    try:
        level_subsystem.load_level(level_path)

        # Verify the level was actually loaded by checking current level
        editor_subsystem = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
        world = editor_subsystem.get_editor_world()
        current_level = ""
        if world:
            outer = world.get_outer()
            if outer:
                current_level = outer.get_path_name()

        # Check if current level matches the requested level
        # Handle both /Game/Maps/MyLevel and /Game/Maps/MyLevel.MyLevel formats
        level_name = level_path.rsplit("/", 1)[-1]
        if level_name in current_level:
            result = {
                "success": True,
                "message": f"Level loaded: {level_path}",
                "level_path": level_path,
                "current_level": current_level,
            }
        else:
            result = {
                "success": False,
                "error": f"Level load failed: current level is {current_level}",
                "level_path": level_path,
                "current_level": current_level,
            }
    except Exception as e:
        result = {
            "success": False,
            "error": f"Exception loading level: {str(e)}",
            "level_path": level_path,
        }

    # Output result as pure JSON
    print(json.dumps(result))


if __name__ == "__main__":
    main()
