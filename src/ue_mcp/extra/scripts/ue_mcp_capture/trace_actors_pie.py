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

MCP mode (__PARAMS__):
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
import editor_capture
from ue_mcp_capture.utils import get_params, ensure_level_loaded, output_result

# Default parameter values for CLI mode
DEFAULTS = {
    "task_id": None,
    "duration_seconds": 10.0,
    "interval_seconds": 0.1,
    "capture_screenshots": False,
    "camera_distance": 300,
    "target_height": 90,
    "resolution_width": 800,
    "resolution_height": 600,
    "multi_angle": True,
}

# Required parameters
REQUIRED = ["output_dir", "level", "actor_names"]


def main():
    params = get_params(defaults=DEFAULTS, required=REQUIRED)

    # Ensure correct level is loaded
    ensure_level_loaded(params["level"])

    # Build resolution tuple
    resolution = (params["resolution_width"], params["resolution_height"])

    # Start PIE tracer with duration (will auto-stop via tick callback)
    # Returns immediately - tracing runs asynchronously
    tracer = editor_capture.start_pie_tracer(
        output_dir=params["output_dir"],
        actor_names=params["actor_names"],
        interval_seconds=params["interval_seconds"],
        auto_start_pie=True,
        duration=params["duration_seconds"],
        auto_stop_pie=True,
        task_id=params.get("task_id"),
        # Screenshot capture options
        capture_screenshots=params["capture_screenshots"],
        camera_distance=params["camera_distance"],
        target_height=params["target_height"],
        resolution=resolution,
        multi_angle=params["multi_angle"],
    )

    # Build result
    result = {
        "status": "started",
        "output_dir": params["output_dir"],
        "duration": params["duration_seconds"],
        "interval": params["interval_seconds"],
        "actor_count": len(params["actor_names"]),
        "capture_screenshots": params["capture_screenshots"],
    }

    # Return immediately with started status
    output_result(result)


if __name__ == "__main__":
    main()
