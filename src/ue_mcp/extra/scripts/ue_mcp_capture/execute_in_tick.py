"""
PIE (Play-In-Editor) tick-based code execution script for UE Editor.

Can be run directly in UE or via MCP server.

This script starts PIE tick executor and returns immediately. The execution runs
asynchronously via tick callbacks and auto-stops when total_ticks is reached.

Usage (CLI):
    python execute_in_tick.py --level=/Game/Maps/TestLevel --total-ticks=100 --code-snippets='[{"code":"print(1)","start_tick":0,"execution_count":1}]'

    Optional arguments:
        --task-id=<id>            Task ID for completion file (optional)

MCP mode (__PARAMS__):
    task_id: str - Unique task identifier for completion file
    level: str - Level path to load
    total_ticks: int - Total number of ticks to run PIE
    code_snippets: list[dict] - List of code snippet configurations
        Each snippet has: code, start_tick, execution_count (default: 1)
"""
import editor_capture
from ue_mcp_capture.utils import get_params, ensure_level_loaded, output_result

# Default parameter values for CLI mode
DEFAULTS = {
    "task_id": None,
    "total_ticks": 100,
    "code_snippets": [],
}

# Required parameters
REQUIRED = ["level", "total_ticks", "code_snippets"]


def main():
    params = get_params(defaults=DEFAULTS, required=REQUIRED)

    # Ensure correct level is loaded
    ensure_level_loaded(params["level"])

    # Start PIE tick executor (will auto-stop via tick callback)
    # Returns immediately - execution runs asynchronously
    executor = editor_capture.start_pie_tick_executor(
        total_ticks=params["total_ticks"],
        code_snippets=params["code_snippets"],
        auto_start_pie=True,
        auto_stop_pie=True,
        task_id=params.get("task_id"),
    )

    # Return immediately with started status
    output_result({
        "status": "started",
        "total_ticks": params["total_ticks"],
        "snippet_count": len(params["code_snippets"]),
    })


if __name__ == "__main__":
    main()
