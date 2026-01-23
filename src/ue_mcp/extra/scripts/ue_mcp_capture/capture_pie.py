"""
PIE (Play-In-Editor) capture script for UE Editor.

Can be run directly in UE or via MCP server.

This script starts PIE capture and returns immediately. The capture runs
asynchronously via tick callbacks and auto-stops when duration is reached.

Usage (CLI):
    python capture_pie.py --output-dir=/path/to/output --level=/Game/Maps/TestLevel

    Optional arguments:
        --duration-seconds=10     Capture duration in seconds (default: 10)
        --interval-seconds=1.0    Interval between captures (default: 1.0)
        --resolution-width=1920   Screenshot width (default: 1920)
        --resolution-height=1080  Screenshot height (default: 1080)
        --multi-angle             Enable multi-angle capture (default: true)
        --camera-distance=300     Camera distance for multi-angle (default: 300)
        --target-height=90        Target height offset (default: 90)
        --task-id=<id>            Task ID for completion file (optional)

MCP mode (__PARAMS__):
    task_id: str - Unique task identifier for completion file
    output_dir: str - Output directory
    level: str - Level path to load
    duration_seconds: float - Capture duration (auto-stops when reached)
    interval_seconds: float - Capture interval
    resolution_width, resolution_height: int - Resolution
    multi_angle: bool - Enable multi-angle capture
    camera_distance: float - Camera distance
    target_height: float - Target height
    target_actor: str - Name of actor to capture (optional, defaults to player)
"""
import editor_capture
from ue_mcp_capture.utils import get_params, ensure_level_loaded, output_result

# Default parameter values for CLI mode
DEFAULTS = {
    "task_id": None,
    "duration_seconds": 10.0,
    "interval_seconds": 1.0,
    "resolution_width": 1920,
    "resolution_height": 1080,
    "multi_angle": True,
    "camera_distance": 300.0,
    "target_height": 90.0,
    "target_actor": None,
}

# Required parameters
REQUIRED = ["output_dir", "level"]


def main():
    params = get_params(defaults=DEFAULTS, required=REQUIRED)

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
        target_actor=params.get("target_actor"),
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
