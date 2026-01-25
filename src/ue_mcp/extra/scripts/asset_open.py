"""
Asset opening script with optional tab switching.

Opens a UE5 asset in its appropriate editor and optionally switches to a specific tab.

Usage:
    # Via MCP (parameters auto-injected via environment variables):
    MCP tool calls this script automatically

    # Via UE Python console:
    import sys
    sys.argv = ['asset_open.py', '--asset-path', '/Game/BP_Test', '--tab-id', 'Inspector']
    exec(open(r'C:\\path\\to\\asset_open.py').read())

Parameters:
    asset_path: Path to the asset to open (required)
    tab_id: Optional tab ID to switch to after opening (optional)

Common Blueprint Editor Tab IDs:
    - Inspector: Details panel
    - SCSViewport: Viewport/Components view
    - GraphEditor: Event Graph
    - MyBlueprint: My Blueprint panel
    - PaletteList: Palette
    - CompilerResults: Compiler Results
    - FindResults: Find Results
    - ConstructionScriptEditor: Construction Script
"""

import argparse
import json
import sys

import unreal

# Defaults: {"tab_id": None}
# Required: ["asset_path"]


def main():
    """Main entry point."""
    # Bootstrap from environment variables (must be before argparse)
    from ue_mcp_capture.utils import bootstrap_from_env
    bootstrap_from_env()

    parser = argparse.ArgumentParser(
        description="Open a UE5 asset in its appropriate editor and optionally switch to a specific tab."
    )
    parser.add_argument(
        "--asset-path",
        required=True,
        help="Path to the asset to open (e.g., /Game/BP_Test)",
    )
    parser.add_argument(
        "--tab-id",
        default=None,
        help="Optional tab ID to switch to after opening (e.g., Inspector, SCSViewport, GraphEditor)",
    )
    args = parser.parse_args()
    asset_path = args.asset_path
    tab_id = args.tab_id

    # Load the asset
    asset = unreal.load_asset(asset_path)
    if asset is None:
        result = {
            "success": False,
            "asset_path": asset_path,
            "error": f"Asset not found: {asset_path}",
        }
        print(json.dumps(result))
        return

    # Open the asset editor
    subsystem = unreal.get_editor_subsystem(unreal.AssetEditorSubsystem)
    subsystem.open_editor_for_assets([asset])

    asset_name = asset.get_name()

    # Build base result
    result = {
        "success": True,
        "asset_path": asset_path,
        "asset_name": asset_name,
    }

    # If tab_id specified, try to switch to it
    if tab_id:
        result["tab_id"] = tab_id
        try:
            tab_result = unreal.ExSlateTabLibrary.invoke_asset_editor_tab(
                asset, unreal.Name(tab_id)
            )
            if tab_result:
                result["tab_switched"] = True
            else:
                result["tab_switched"] = False
                result["tab_error"] = (
                    f"Tab '{tab_id}' could not be opened. "
                    "It may not be available in the current editor mode/layout."
                )
        except AttributeError:
            result["tab_switched"] = False
            result["tab_error"] = (
                "ExSlateTabLibrary not available. "
                "Ensure ExtraPythonAPIs plugin is installed and the project is rebuilt."
            )
        except Exception as e:
            result["tab_switched"] = False
            result["tab_error"] = str(e)

    # Output result as pure JSON
    print(json.dumps(result))


if __name__ == "__main__":
    main()
