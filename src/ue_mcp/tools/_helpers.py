"""Shared helper functions for MCP tools."""

import json
import logging
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Optional

# Environment variable names for script parameter passing
ENV_VAR_MODE = "UE_MCP_MODE"  # "1" when running via MCP (vs CLI)
ENV_VAR_CALL = "UE_MCP_CALL"  # "<checksum>:<timestamp>:<json_params>" script call info

# Maximum allowed age for injected parameters (in seconds)
# If parameters are older than this, the script should reject them
INJECT_TIME_MAX_AGE = 5

if TYPE_CHECKING:
    from fastmcp import Context

    from ..editor.execution_manager import ExecutionManager

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


def query_project_assets(execution: "ExecutionManager") -> dict[str, Any]:
    """Query Blueprint and World (Level) assets in the project.

    Args:
        execution: ExecutionManager instance (must be connected)

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
            execution,
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


def compute_script_checksum(script_path: str) -> str:
    """Compute a short checksum of the script path for token validation.

    Uses a simple hash to create a short identifier that scripts can verify
    to ensure parameters were intended for them.

    Args:
        script_path: Absolute path to the script file

    Returns:
        8-character hex checksum
    """
    import hashlib
    return hashlib.md5(script_path.encode()).hexdigest()[:8]


def build_env_injection_code(script_path: str, params: dict[str, Any], output_file: str | None = None) -> str:
    """Build code to inject parameters via environment variables.

    This sets the following env vars:
    - UE_MCP_MODE: "1" to indicate MCP mode (vs CLI mode)
    - UE_MCP_CALL: "<checksum>:<timestamp>:<json_params>" script call info

    The call info combines:
    - checksum: 8-char MD5 hash of script path, ensuring params are for this script
    - timestamp: injection time, ensuring params are fresh (< INJECT_TIME_MAX_AGE)
    - json_params: JSON-encoded parameters

    If output_file is provided, sets up stdout/stderr capture to that file using TeeWriter.

    Args:
        script_path: Absolute path to the script file
        params: Parameter dictionary (None values are filtered out)
        output_file: Optional path to file for capturing stdout/stderr output

    Returns:
        Python code string to execute before EXECUTE_FILE
    """
    # Filter out None values
    clean_params = {k: v for k, v in params.items() if v is not None}

    # Compute checksum for the script path
    checksum = compute_script_checksum(str(script_path))

    # JSON-encode parameters (will be part of the payload)
    params_json = json.dumps(clean_params)
    # Escape for f-string embedding:
    # 1. Backslashes must be doubled (\ -> \\) because f-string literals interpret escapes
    # 2. Braces must be doubled ({ -> {{, } -> }}) to avoid f-string format expressions
    escaped_params_json = (
        params_json
        .replace("\\", "\\\\")  # Must come first!
        .replace("{", "{{")
        .replace("}", "}}")
    )

    lines = [
        "import os",
        "import sys",
        "import time",
        # Set MCP mode flag
        f"os.environ[{repr(ENV_VAR_MODE)}] = '1'",
        # Set call info: "<checksum>:<timestamp>:<json_params>"
        f"os.environ[{repr(ENV_VAR_CALL)}] = f'{checksum}:{{time.time()}}:{escaped_params_json}'",
    ]

    # Add output capture setup if output_file is provided
    if output_file:
        # Escape backslashes for Windows paths (don't use raw string prefix)
        escaped_output_file = output_file.replace("\\", "\\\\")
        lines.extend([
            "import builtins",
            "import atexit",
            # Store original streams
            "builtins.__ue_mcp_orig_stdout__ = sys.stdout",
            "builtins.__ue_mcp_orig_stderr__ = sys.stderr",
            # Open output file for writing
            f"builtins.__ue_mcp_output_file__ = open('{escaped_output_file}', 'w', encoding='utf-8')",
            # Create a TeeWriter that writes to both the file and original stream
            "class _UeMcpTeeWriter:",
            "    def __init__(self, file, original):",
            "        self.file = file",
            "        self.original = original",
            "    def write(self, data):",
            "        self.file.write(data)",
            "        self.file.flush()",
            "        self.original.write(data)",
            "    def flush(self):",
            "        self.file.flush()",
            "        self.original.flush()",
            "sys.stdout = _UeMcpTeeWriter(builtins.__ue_mcp_output_file__, builtins.__ue_mcp_orig_stdout__)",
            "sys.stderr = _UeMcpTeeWriter(builtins.__ue_mcp_output_file__, builtins.__ue_mcp_orig_stderr__)",
            # Register cleanup function to restore streams and close file
            "def _ue_mcp_cleanup():",
            "    if hasattr(builtins, '__ue_mcp_orig_stdout__'):",
            "        sys.stdout = builtins.__ue_mcp_orig_stdout__",
            "    if hasattr(builtins, '__ue_mcp_orig_stderr__'):",
            "        sys.stderr = builtins.__ue_mcp_orig_stderr__",
            "    if hasattr(builtins, '__ue_mcp_output_file__'):",
            "        builtins.__ue_mcp_output_file__.close()",
            "atexit.register(_ue_mcp_cleanup)",
        ])

    return "\n".join(lines)


async def run_pie_task(
    ctx: "Context",
    execution: "ExecutionManager",
    project_root: Path,
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
        execution: ExecutionManager instance
        project_root: Path to the project root directory
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
        execution,
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
        project_root=project_root,
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
