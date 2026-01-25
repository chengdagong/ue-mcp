"""
PIE (Play-In-Editor) tick-based code execution script for UE Editor.

Can be run directly in UE or via MCP server.

This script starts PIE tick executor and returns immediately. The execution runs
asynchronously via tick callbacks and auto-stops when total_ticks is reached.

Usage (CLI):
    python execute_in_tick.py --level=/Game/Maps/TestLevel --total-ticks=100 --code-snippets='[{"code":"print(1)","start_tick":0,"execution_count":1}]'

    Optional arguments:
        --task-id=<id>            Task ID for completion file (optional)

MCP mode (sys.argv):
    task_id: str - Unique task identifier for completion file
    level: str - Level path to load
    total_ticks: int - Total number of ticks to run PIE
    code_snippets: list[dict] - List of code snippet configurations
        Each snippet has: code, start_tick, execution_count (default: 1)
"""
import argparse
import json
import editor_capture
from ue_mcp_capture.utils import bootstrap_from_env, ensure_level_loaded, output_result

# Default parameter values (for reference)
# DEFAULTS = {
#     "task_id": None,
#     "total_ticks": 100,
#     "code_snippets": [],
# }

# Required parameters (for reference)
# REQUIRED = ["level", "total_ticks", "code_snippets"]


def parse_args():
    """Parse command-line arguments."""
    # Bootstrap from environment variables (must be before argparse)
    bootstrap_from_env()

    parser = argparse.ArgumentParser(
        description="PIE tick-based code execution script for UE Editor",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Required arguments
    parser.add_argument(
        "--level",
        type=str,
        required=True,
        help="Level path to load (e.g., /Game/Maps/TestLevel)"
    )
    parser.add_argument(
        "--total-ticks",
        type=int,
        required=True,
        help="Total number of ticks to run PIE"
    )
    parser.add_argument(
        "--code-snippets",
        type=str,
        required=True,
        help='List of code snippet configurations (JSON array string, e.g., \'[{"code":"print(1)","start_tick":0,"execution_count":1}]\')'
    )

    # Optional arguments
    parser.add_argument(
        "--task-id",
        type=str,
        default=None,
        help="Unique task identifier for completion file (optional)"
    )

    args = parser.parse_args()

    # Parse code_snippets from JSON string
    try:
        args.code_snippets = json.loads(args.code_snippets)
        if not isinstance(args.code_snippets, list):
            parser.error("--code-snippets must be a JSON array")
        # Validate each snippet has required fields
        for i, snippet in enumerate(args.code_snippets):
            if not isinstance(snippet, dict):
                parser.error(f"--code-snippets[{i}] must be a JSON object")
            if "code" not in snippet:
                parser.error(f"--code-snippets[{i}] must have a 'code' field")
            if "start_tick" not in snippet:
                parser.error(f"--code-snippets[{i}] must have a 'start_tick' field")
    except json.JSONDecodeError as e:
        parser.error(f"--code-snippets must be valid JSON: {e}")

    return args


def main():
    args = parse_args()

    # Ensure correct level is loaded
    ensure_level_loaded(args.level)

    # Start PIE tick executor (will auto-stop via tick callback)
    # Returns immediately - execution runs asynchronously
    executor = editor_capture.start_pie_tick_executor(
        total_ticks=args.total_ticks,
        code_snippets=args.code_snippets,
        auto_start_pie=True,
        auto_stop_pie=True,
        task_id=args.task_id,
    )

    # Return immediately with started status
    output_result({
        "status": "started",
        "total_ticks": args.total_ticks,
        "snippet_count": len(args.code_snippets),
    })


if __name__ == "__main__":
    main()
