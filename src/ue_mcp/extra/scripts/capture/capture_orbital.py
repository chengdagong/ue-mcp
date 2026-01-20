"""
Orbital capture script for UE Editor.

Can be run directly in UE or via MCP server.

Expected __PARAMS__:
    level: str - Level path to load
    target_x, target_y, target_z: float - Target location
    distance: float - Camera distance
    preset: str - View preset
    output_dir: str | None - Output directory
    resolution_width, resolution_height: int - Resolution
"""
import unreal
import editor_capture

from capture.utils import get_params, ensure_level_loaded, output_result, error_handler


def main():
    params = get_params()

    # Ensure correct level is loaded
    ensure_level_loaded(params["level"])

    # Get editor world
    # Get editor world using UnrealEditorSubsystem (modern API)
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    if not world:
        raise RuntimeError("Could not get editor world")

    # Execute capture
    results = editor_capture.take_orbital_screenshots_with_preset(
        loaded_world=world,
        preset=params["preset"],
        target_location=unreal.Vector(
            params["target_x"],
            params["target_y"],
            params["target_z"]
        ),
        distance=params["distance"],
        output_dir=params.get("output_dir"),
        resolution_width=params["resolution_width"],
        resolution_height=params["resolution_height"],
    )

    # Output result
    files = {k: list(v) if v else [] for k, v in results.items()}
    total = sum(len(v) for v in files.values())
    output_result({"files": files, "total_captures": total})


if __name__ == "__main__":
    main()
