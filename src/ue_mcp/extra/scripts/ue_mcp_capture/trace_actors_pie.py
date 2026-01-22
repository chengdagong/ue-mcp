"""
PIE (Play-In-Editor) actor tracing script for UE Editor.

Can be run directly in UE or via MCP server.

This script starts PIE actor tracing and returns immediately. The tracing runs
asynchronously via tick callbacks and auto-stops when duration is reached.

Usage (CLI):
    python trace_actors_pie.py --output-file=/path/to/trace.json --level=/Game/Maps/TestLevel --actor-names=["Actor1","Actor2"]

    Optional arguments:
        --duration-seconds=10     Trace duration in seconds (default: 10)
        --interval-seconds=0.1    Interval between samples (default: 0.1)
        --task-id=<id>            Task ID for completion file (optional)

MCP mode (__PARAMS__):
    task_id: str - Unique task identifier for completion file
    output_file: str - Output JSON file path
    level: str - Level path to load
    actor_names: list[str] - List of actor names to track
    duration_seconds: float - Trace duration (auto-stops when reached)
    interval_seconds: float - Sampling interval
"""
import editor_capture
from ue_mcp_capture.utils import get_params, ensure_level_loaded, output_result

# Default parameter values for CLI mode
DEFAULTS = {
    "task_id": None,
    "duration_seconds": 10.0,
    "interval_seconds": 0.1,
}

# Required parameters
REQUIRED = ["output_file", "level", "actor_names"]


def main():
    params = get_params(defaults=DEFAULTS, required=REQUIRED)

    # Ensure correct level is loaded
    ensure_level_loaded(params["level"])

    # Start PIE tracer with duration (will auto-stop via tick callback)
    # Returns immediately - tracing runs asynchronously
    tracer = editor_capture.start_pie_tracer(
        output_file=params["output_file"],
        actor_names=params["actor_names"],
        interval_seconds=params["interval_seconds"],
        auto_start_pie=True,
        duration=params["duration_seconds"],
        auto_stop_pie=True,
        task_id=params.get("task_id"),
    )

    # Return immediately with started status
    output_result({
        "status": "started",
        "output_file": params["output_file"],
        "duration": params["duration_seconds"],
        "interval": params["interval_seconds"],
        "actor_count": len(params["actor_names"]),
    })


if __name__ == "__main__":
    main()
