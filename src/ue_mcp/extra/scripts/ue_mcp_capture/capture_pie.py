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

MCP mode (environment variables):
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
import argparse
import editor_capture
from ue_mcp_capture.utils import bootstrap_from_env, ensure_level_loaded, output_result

# Default parameter values for CLI mode (kept as reference)
# DEFAULTS = {
#     "task_id": None,
#     "duration_seconds": 10.0,
#     "interval_seconds": 1.0,
#     "resolution_width": 1920,
#     "resolution_height": 1080,
#     "multi_angle": True,
#     "camera_distance": 300.0,
#     "target_height": 90.0,
#     "target_actor": None,
# }

# Required parameters (kept as reference)
# REQUIRED = ["output_dir", "level"]


def main():
    # Bootstrap from environment variables (must be before argparse)
    bootstrap_from_env()

    parser = argparse.ArgumentParser(
        description="PIE (Play-In-Editor) capture script for UE Editor",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    # Required parameters
    parser.add_argument("--output-dir", type=str, required=True, dest="output_dir", help="Output directory for screenshots")
    parser.add_argument("--level", type=str, required=True, help="Level path to load (e.g., /Game/Maps/TestLevel)")

    # Optional parameters
    parser.add_argument("--task-id", type=str, default=None, dest="task_id", help="Task ID for completion file (optional)")
    parser.add_argument("--duration-seconds", type=float, default=10.0, dest="duration_seconds", help="Capture duration in seconds (default: 10)")
    parser.add_argument("--interval-seconds", type=float, default=1.0, dest="interval_seconds", help="Interval between captures in seconds (default: 1.0)")
    parser.add_argument("--resolution-width", type=int, default=1920, dest="resolution_width", help="Screenshot width in pixels (default: 1920)")
    parser.add_argument("--resolution-height", type=int, default=1080, dest="resolution_height", help="Screenshot height in pixels (default: 1080)")
    parser.add_argument("--multi-angle", action="store_true", default=True, dest="multi_angle", help="Enable multi-angle capture (default: true)")
    parser.add_argument("--no-multi-angle", action="store_false", dest="multi_angle", help="Disable multi-angle capture")
    parser.add_argument("--camera-distance", type=float, default=300.0, dest="camera_distance", help="Camera distance for multi-angle (default: 300)")
    parser.add_argument("--target-height", type=float, default=90.0, dest="target_height", help="Target height offset (default: 90)")
    parser.add_argument("--target-actor", type=str, default=None, dest="target_actor", help="Name of actor to capture (optional, defaults to player)")

    args = parser.parse_args()
    params = vars(args)

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
