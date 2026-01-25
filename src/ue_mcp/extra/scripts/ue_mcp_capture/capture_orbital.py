"""
Orbital capture script for UE Editor.

Can be run directly in UE or via MCP server.

Usage (CLI):
    python capture_orbital.py --level=/Game/Maps/TestLevel --target-x=0 --target-y=0 --target-z=100

    Optional arguments:
        --distance=500        Camera distance from target (default: 500)
        --preset=orthographic View preset: all, perspective, orthographic, birdseye, horizontal, technical
        --output-dir=path     Output directory (default: auto-generated)
        --resolution-width=800   Screenshot width (default: 800)
        --resolution-height=600  Screenshot height (default: 600)

MCP mode (environment variables):
    level: str - Level path to load
    target_x, target_y, target_z: float - Target location
    distance: float - Camera distance
    preset: str - View preset
    output_dir: str | None - Output directory
    resolution_width, resolution_height: int - Resolution
"""

import argparse
import gc
import unreal
import editor_capture


from ue_mcp_capture.utils import bootstrap_from_env, ensure_level_loaded, output_result

# Default parameter values for CLI mode (kept as reference)
# DEFAULTS = {
#     "distance": 500.0,
#     "preset": "orthographic",
#     "output_dir": None,
#     "resolution_width": 800,
#     "resolution_height": 600,
# }

# Required parameters (kept as reference)
# REQUIRED = ["level", "target_x", "target_y", "target_z"]


def main():
    # Bootstrap from environment variables (must be before argparse)
    bootstrap_from_env()

    parser = argparse.ArgumentParser(
        description="Orbital capture script for UE Editor",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    # Required parameters
    parser.add_argument("--level", type=str, required=True, help="Level path to load (e.g., /Game/Maps/TestLevel)")
    parser.add_argument("--target-x", type=float, required=True, dest="target_x", help="Target X coordinate in world space")
    parser.add_argument("--target-y", type=float, required=True, dest="target_y", help="Target Y coordinate in world space")
    parser.add_argument("--target-z", type=float, required=True, dest="target_z", help="Target Z coordinate in world space")

    # Optional parameters
    parser.add_argument("--distance", type=float, default=500.0, help="Camera distance from target in UE units (default: 500)")
    parser.add_argument("--preset", type=str, default="orthographic",
                       choices=["all", "perspective", "orthographic", "birdseye", "horizontal", "technical"],
                       help="View preset (default: orthographic)")
    parser.add_argument("--output-dir", type=str, default=None, dest="output_dir", help="Output directory (default: auto-generated)")
    parser.add_argument("--resolution-width", type=int, default=800, dest="resolution_width", help="Screenshot width in pixels (default: 800)")
    parser.add_argument("--resolution-height", type=int, default=600, dest="resolution_height", help="Screenshot height in pixels (default: 600)")

    args = parser.parse_args()
    params = vars(args)

    # Ensure correct level is loaded
    ensure_level_loaded(params["level"])

    # Get editor world using UnrealEditorSubsystem (modern API)
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    if not world:
        raise RuntimeError("Could not get editor world")

    # Execute capture
    results = editor_capture.take_orbital_screenshots_with_preset(
        loaded_world=world,
        preset=params["preset"],
        target_location=unreal.Vector(params["target_x"], params["target_y"], params["target_z"]),
        distance=params["distance"],
        output_dir=params.get("output_dir"),
        resolution_width=params["resolution_width"],
        resolution_height=params["resolution_height"],
    )

    # CRITICAL: Release UE object reference before function returns
    # This prevents memory leaks when the level is changed later
    del world
    gc.collect()

    # Output result
    files = {k: list(v) if v else [] for k, v in results.items()}
    total = sum(len(v) for v in files.values())
    output_result({
        "success": True,
        "files": files,
        "total_captures": total
    })


if __name__ == "__main__":
    main()
