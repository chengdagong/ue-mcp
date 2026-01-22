"""
PIE (Play-In-Editor) capture script for UE Editor.

Can be run directly in UE or via MCP server.

This script starts PIE capture and returns immediately. The capture runs
asynchronously via tick callbacks and auto-stops when duration is reached.

Expected __PARAMS__:
    task_id: str - Unique task identifier for completion file
    output_dir: str - Output directory
    level: str - Level path to load
    duration_seconds: float - Capture duration (auto-stops when reached)
    interval_seconds: float - Capture interval
    resolution_width, resolution_height: int - Resolution
    multi_angle: bool - Enable multi-angle capture
    camera_distance: float - Camera distance
    target_height: float - Target height
"""
import editor_capture

from ue_mcp_capture.utils import get_params, ensure_level_loaded, output_result


def main():
    params = get_params()

    # Ensure correct level is loaded
    ensure_level_loaded(params["level"])

    # Start PIE capture with duration (will auto-stop via tick callback)
    # Returns immediately - capture runs asynchronously
    capturer = editor_capture.start_pie_capture(
        output_dir=params["output_dir"],
        interval_seconds=params["interval_seconds"],
        resolution=(params["resolution_width"], params["resolution_height"]),
        auto_start_pie=True,
        multi_angle=params["multi_angle"],
        camera_distance=params["camera_distance"],
        target_height=params["target_height"],
        duration=params["duration_seconds"],
        auto_stop_pie=True,
        task_id=params.get("task_id"),
    )

    # Return immediately with started status
    output_result({
        "status": "started",
        "output_dir": params["output_dir"],
        "duration": params["duration_seconds"],
        "interval": params["interval_seconds"],
        "multi_angle": capturer.multi_angle,  # May be changed to False if camera failed
    })


if __name__ == "__main__":
    main()
