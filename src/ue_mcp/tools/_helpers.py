"""Shared helper functions for MCP tools."""

import json
import logging
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Optional

if TYPE_CHECKING:
    from fastmcp import Context

    from ..editor_manager import EditorManager

logger = logging.getLogger(__name__)


def parse_json_result(exec_result: dict[str, Any]) -> dict[str, Any]:
    """Parse JSON result from script output.

    Extracts the last valid JSON object from output list.
    This is the standard way to parse results from all standalone scripts.

    Args:
        exec_result: Execution result from script

    Returns:
        Parsed JSON result or error dict
    """
    if not exec_result.get("success"):
        return {
            "success": False,
            "error": exec_result.get("error", "Execution failed"),
        }

    output = exec_result.get("output", [])
    if not output:
        return {"success": False, "error": "No output from script"}

    # Find last valid JSON in output
    for line in reversed(output):
        line_str = str(line.get("output", "")) if isinstance(line, dict) else str(line)
        line_str = line_str.strip()
        if line_str.startswith("{") or line_str.startswith("["):
            try:
                return json.loads(line_str)
            except json.JSONDecodeError:
                continue

    return {"success": False, "error": "No valid JSON found in output"}


def query_project_assets(manager: "EditorManager") -> dict[str, Any]:
    """Query Blueprint and World (Level) assets in the project.

    Args:
        manager: EditorManager instance (must be connected)

    Returns:
        Dict with assets info or error
    """
    from ..script_executor import execute_script_from_path, get_extra_scripts_dir

    try:
        script_path = get_extra_scripts_dir() / "asset_query.py"
        if not script_path.exists():
            logger.warning(f"Asset query script not found: {script_path}")
            return {"success": False, "error": "Asset query script not found"}

        # Query Blueprint and World assets
        exec_result = execute_script_from_path(
            manager,
            script_path,
            {"types": "Blueprint,World", "base_path": "/Game", "limit": 100},
            timeout=30.0,
        )

        return parse_json_result(exec_result)
    except Exception as e:
        logger.warning(f"Failed to query project assets: {e}")
        return {"success": False, "error": str(e)}


def build_script_args_injection(
    script_path: str, args: list[str] | None, kwargs: dict | None
) -> str:
    """Build code to inject arguments before script execution.

    Args:
        script_path: Path to the script file (used as sys.argv[0])
        args: List of command-line arguments (becomes sys.argv[1:])
        kwargs: Dictionary of keyword arguments (becomes __SCRIPT_ARGS__)

    Returns:
        Python code string to prepend to the script
    """
    lines = ["import sys"]

    # Always set sys.argv[0] to script path for standard Python behavior
    if args:
        argv_list = [script_path] + [str(a) for a in args]
        lines.append(f"sys.argv = {repr(argv_list)}")
    else:
        lines.append(f"sys.argv = [{repr(script_path)}]")

    if kwargs:
        lines.append("import builtins")
        lines.append(f"builtins.__SCRIPT_ARGS__ = {repr(kwargs)}")
        lines.append("__SCRIPT_ARGS__ = builtins.__SCRIPT_ARGS__")

    return "\n".join(lines) + "\n\n"


async def run_pie_task(
    ctx: "Context",
    manager: "EditorManager",
    script_name: str,
    params: dict[str, Any],
    duration_seconds: float,
    task_description: str,
    output_key: str,
    output_value: str,
    result_processor: Optional[Callable[[dict[str, Any]], dict[str, Any]]] = None,
) -> dict[str, Any]:
    """Execute a PIE task with common logic for capture and trace tools.

    This function encapsulates the shared pattern between editor_capture_pie
    and editor_trace_actors_in_pie tools:
    - Generate unique task_id
    - Execute script via script_executor
    - Monitor completion via watch_pie_capture_complete
    - Handle timeout and result processing

    Args:
        ctx: MCP Context for logging
        manager: EditorManager instance
        script_name: Name of the script to execute
        params: Script parameters (task_id will be added automatically)
        duration_seconds: Duration for the task
        task_description: Human-readable description for logging
        output_key: Key name for output file/directory in error response
        output_value: Value for output file/directory in error response
        result_processor: Optional function to process the final result dict

    Returns:
        Result dict from the PIE task execution
    """
    from ..log_watcher import watch_pie_capture_complete
    from ..script_executor import execute_script

    # Generate unique task_id for this task
    task_id = str(uuid.uuid4())[:8]

    # Add task_id to params
    params_with_id = {"task_id": task_id, **params}

    # Start task (returns immediately, runs via tick callbacks)
    result = execute_script(
        manager,
        script_name,
        params=params_with_id,
        timeout=30.0,  # Short timeout since script returns immediately
    )

    if not result.get("success", False):
        return parse_json_result(result)

    # Notify that task has started
    await ctx.log(
        f"{task_description} started (task_id={task_id}), monitoring for completion...",
        level="info",
    )

    # Watch for completion file
    # Timeout = duration + buffer for PIE startup/shutdown
    watch_timeout = duration_seconds + 60.0

    async def on_complete(task_result: dict[str, Any]) -> None:
        """Called when task completes."""
        await ctx.log(f"{task_description} completed", level="info")

    task_result = await watch_pie_capture_complete(
        project_root=manager.project_root,
        task_id=task_id,
        callback=on_complete,
        timeout=watch_timeout,
    )

    if task_result is None:
        return {
            "success": False,
            "error": f"Timeout waiting for {task_description.lower()} completion after {watch_timeout}s",
            output_key: output_value,
        }

    # Apply result processor if provided
    if result_processor is not None:
        return result_processor(task_result)

    return task_result
