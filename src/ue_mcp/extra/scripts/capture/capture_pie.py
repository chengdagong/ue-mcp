"""
PIE (Play-In-Editor) capture script for UE Editor.

Can be run directly in UE or via MCP server.

Expected __PARAMS__:
    output_dir: str - Output directory
    level: str - Level path to load
    duration_seconds: float - Capture duration
    interval_seconds: float - Capture interval
    resolution_width, resolution_height: int - Resolution
    multi_angle: bool - Enable multi-angle capture
    camera_distance: float - Camera distance
    target_height: float - Target height
"""
import time
import editor_capture

from capture.utils import get_params, ensure_level_loaded, output_result, error_handler


def main():
    params = get_params()

    # Ensure correct level is loaded
    ensure_level_loaded(params["level"])

    # Start PIE capture with auto-start
    # Note: start_pie_capture returns a capturer object, but we don't need to keep a reference
    # as the module manages the active session
    editor_capture.start_pie_capture(
        output_dir=params["output_dir"],
        interval_seconds=params["interval_seconds"],
        resolution=(params["resolution_width"], params["resolution_height"]),
        auto_start_pie=True,
        multi_angle=params["multi_angle"],
        camera_distance=params["camera_distance"],
        target_height=params["target_height"],
    )

    # Wait for specified duration
    start_time = time.time()
    time.sleep(params["duration_seconds"])
    elapsed = time.time() - start_time

    # Stop PIE capture
    editor_capture.stop_pie_capture()

    output_result({
        "output_dir": params["output_dir"],
        "duration": elapsed,
        "interval": params["interval_seconds"],
    })


if __name__ == "__main__":
    main()
