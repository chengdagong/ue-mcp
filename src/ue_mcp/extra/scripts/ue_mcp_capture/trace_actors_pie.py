"""
PIE (Play-In-Editor) actor tracing script for UE Editor.

Can be run directly in UE or via MCP server.

This script starts PIE actor tracing and returns immediately. The tracing runs
asynchronously via tick callbacks and auto-stops when duration is reached.

Optionally captures screenshots of tracked actors at each sample interval.

Output directory structure:
    output_dir/
    ├── metadata.json                 # Global metadata
    ├── ActorLabel/                   # Actor subdirectory (using actor label/name)
    │   ├── sample_at_tick_6/         # Sample directory (using actual tick number)
    │   │   ├── transform.json        # Transform/velocity data for this sample
    │   │   └── screenshots/          # Screenshots (if enabled)
    │   │       ├── front.png
    │   │       ├── side.png
    │   │       ├── back.png
    │   │       └── perspective.png
    │   └── sample_at_tick_12/
    │       └── ...
    └── ...

Usage (CLI):
    python trace_actors_pie.py --output-dir=/path/to/output --level=/Game/Maps/TestLevel --actor-names=["Actor1","Actor2"]

    Optional arguments:
        --duration-seconds=10     Trace duration in seconds (default: 10)
        --interval-seconds=0.1    Interval between samples (default: 0.1)
        --task-id=<id>            Task ID for completion file (optional)
        --capture-screenshots     Enable screenshot capture (default: False)
        --camera-distance=300     Camera distance from actor (default: 300)
        --target-height=90        Target height offset (default: 90)
        --resolution-width=800    Screenshot width (default: 800)
        --resolution-height=600   Screenshot height (default: 600)
        --multi-angle             Enable multi-angle capture (default: True)

MCP mode (sys.argv):
    task_id: str - Unique task identifier for completion file
    output_dir: str - Output directory for trace data
    level: str - Level path to load
    actor_names: list[str] - List of actor names to track
    duration_seconds: float - Trace duration (auto-stops when reached)
    interval_seconds: float - Sampling interval
    capture_screenshots: bool - Whether to capture screenshots (default: False)
    camera_distance: float - Camera distance from actor (default: 300)
    target_height: float - Target height offset (default: 90)
    resolution_width: int - Screenshot width (default: 800)
    resolution_height: int - Screenshot height (default: 600)
    multi_angle: bool - Enable multi-angle capture (default: True)
"""
import argparse
import json
import editor_capture
from ue_mcp_capture.utils import bootstrap_from_env, ensure_level_loaded, output_result

# Default parameter values (for reference)
# DEFAULTS = {
#     "task_id": None,
#     "duration_seconds": 10.0,
#     "interval_seconds": 0.1,
#     "capture_screenshots": False,
#     "camera_distance": 300,
#     "target_height": 90,
#     "resolution_width": 800,
#     "resolution_height": 600,
#     "multi_angle": True,
# }

# Required parameters (for reference)
# REQUIRED = ["output_dir", "level", "actor_names"]


def parse_args():
    """Parse command-line arguments."""
    # Bootstrap from environment variables (must be before argparse)
    bootstrap_from_env()

    parser = argparse.ArgumentParser(
        description="PIE actor tracing script for UE Editor",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Required arguments
    parser.add_argument(
        "--output-dir",
        type=str,
        required=True,
        help="Output directory for trace data"
    )
    parser.add_argument(
        "--level",
        type=str,
        required=True,
        help="Level path to load (e.g., /Game/Maps/TestLevel)"
    )
    parser.add_argument(
        "--actor-names",
        type=str,
        required=True,
        help="List of actor names to track (JSON array string, e.g., '[\"Actor1\",\"Actor2\"]')"
    )

    # Optional arguments
    parser.add_argument(
        "--task-id",
        type=str,
        default=None,
        help="Unique task identifier for completion file (optional)"
    )
    parser.add_argument(
        "--duration-seconds",
        type=float,
        default=10.0,
        help="Trace duration in seconds (default: 10.0)"
    )
    parser.add_argument(
        "--interval-seconds",
        type=float,
        default=0.1,
        help="Sampling interval in seconds (default: 0.1)"
    )
    parser.add_argument(
        "--capture-screenshots",
        action="store_true",
        default=False,
        help="Enable screenshot capture (default: False)"
    )
    parser.add_argument(
        "--camera-distance",
        type=float,
        default=300,
        help="Camera distance from actor in UE units (default: 300)"
    )
    parser.add_argument(
        "--target-height",
        type=float,
        default=90,
        help="Target height offset from actor origin (default: 90)"
    )
    parser.add_argument(
        "--resolution-width",
        type=int,
        default=800,
        help="Screenshot width in pixels (default: 800)"
    )
    parser.add_argument(
        "--resolution-height",
        type=int,
        default=600,
        help="Screenshot height in pixels (default: 600)"
    )
    parser.add_argument(
        "--multi-angle",
        action="store_true",
        default=True,
        help="Enable multi-angle capture (default: True)"
    )
    parser.add_argument(
        "--no-multi-angle",
        action="store_false",
        dest="multi_angle",
        help="Disable multi-angle capture"
    )

    args = parser.parse_args()

    # Parse actor_names from JSON string
    try:
        args.actor_names = json.loads(args.actor_names)
        if not isinstance(args.actor_names, list):
            parser.error("--actor-names must be a JSON array")
    except json.JSONDecodeError as e:
        parser.error(f"--actor-names must be valid JSON: {e}")

    return args


def main():
    args = parse_args()

    # Ensure correct level is loaded
    ensure_level_loaded(args.level)

    # Build resolution tuple
    resolution = (args.resolution_width, args.resolution_height)

    # Start PIE tracer with duration (will auto-stop via tick callback)
    # Returns immediately - tracing runs asynchronously
    tracer = editor_capture.start_pie_tracer(
        output_dir=args.output_dir,
        actor_names=args.actor_names,
        interval_seconds=args.interval_seconds,
        auto_start_pie=True,
        duration=args.duration_seconds,
        auto_stop_pie=True,
        task_id=args.task_id,
        # Screenshot capture options
        capture_screenshots=args.capture_screenshots,
        camera_distance=args.camera_distance,
        target_height=args.target_height,
        resolution=resolution,
        multi_angle=args.multi_angle,
    )

    # Build result
    result = {
        "status": "started",
        "output_dir": args.output_dir,
        "duration": args.duration_seconds,
        "interval": args.interval_seconds,
        "actor_count": len(args.actor_names),
        "capture_screenshots": args.capture_screenshots,
    }

    # Return immediately with started status
    output_result(result)


if __name__ == "__main__":
    main()
