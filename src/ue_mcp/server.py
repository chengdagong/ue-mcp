"""
UE-MCP Server

FastMCP-based MCP server for Unreal Editor interaction.
"""

import asyncio
import json
import logging
import signal
import sys
import uuid
from pathlib import Path
from typing import Annotated, Any, Callable, Optional

import mcp.types as mt
from fastmcp import Context, FastMCP
from pydantic import Field
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext

from .autoconfig import get_bundled_site_packages
from .editor_manager import EditorManager
from .log_watcher import watch_pie_capture_complete
from .script_executor import execute_script_from_path, get_extra_scripts_dir
from .utils import find_uproject_file

# Configure logging
# 获取项目根目录（从当前文件向上两级）
_log_dir = Path(__file__).parent.parent.parent.resolve()
_log_file = _log_dir / "ue-mcp.log"

# 先配置基础日志到stderr，以便能看到日志配置过程中的问题
logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stderr)]
)
logger = logging.getLogger(__name__)

# 尝试添加文件handler
try:
    # 确保日志目录存在
    _log_dir.mkdir(parents=True, exist_ok=True)
    
    # 添加文件handler
    file_handler = logging.FileHandler(_log_file, mode='a', encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(logging.Formatter("[%(levelname)s] %(name)s: %(message)s"))
    logging.getLogger().addHandler(file_handler)
    
    logger.info(f"Logging to file: {_log_file}")
except Exception as e:
    logger.error(f"Failed to setup file logging: {e}")
    logger.info(f"Attempted log file path: {_log_file}")

# Global state
_editor_manager: Optional[EditorManager] = None
_client_name: Optional[str] = None  # 客户端名称
_project_path_set: bool = False  # 跟踪project.set_path是否已调用


def _get_editor_manager() -> EditorManager:
    """Get the global EditorManager instance."""
    if _editor_manager is None:
        raise RuntimeError(
            "EditorManager not initialized. "
            "Please call the 'project_set_path' tool first to set the UE5 project directory."
        )
    return _editor_manager


def _parse_json_result(exec_result: dict[str, Any]) -> dict[str, Any]:
    """
    Parse JSON result from script output.

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


def _query_project_assets(manager: EditorManager) -> dict[str, Any]:
    """
    Query Blueprint and World (Level) assets in the project.

    Args:
        manager: EditorManager instance (must be connected)

    Returns:
        Dict with assets info or error
    """
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

        return _parse_json_result(exec_result)
    except Exception as e:
        logger.warning(f"Failed to query project assets: {e}")
        return {"success": False, "error": str(e)}


def _initialize_server() -> Optional[EditorManager]:
    """
    Initialize the MCP server by detecting and binding to a UE5 project.

    Returns:
        EditorManager instance if successful, None otherwise
    """
    global _editor_manager

    logger.info("Initializing UE-MCP server...")
    logger.info(f"Working directory: {Path.cwd()}")

    # Auto-detect project
    uproject_path = find_uproject_file()

    if uproject_path is None:
        logger.error(
            "No .uproject file found. "
            "Please run this server from a UE5 project directory."
        )
        return None

    logger.info(f"Detected project: {uproject_path}")

    _editor_manager = EditorManager(uproject_path)
    return _editor_manager


class ClientDetectionMiddleware(Middleware):
    """检测MCP客户端类型"""

    async def on_initialize(
        self,
        context: MiddlewareContext[mt.InitializeRequest],
        call_next: CallNext[mt.InitializeRequest, mt.InitializeResult | None],
    ) -> mt.InitializeResult | None:
        global _client_name, _editor_manager

        # 提取客户端名称
        client_info = context.message.params.clientInfo
        _client_name = client_info.name if client_info else "unknown"

        # 打印客户端信息（会同时输出到日志文件和控制台）
        logger.info("=" * 70)
        logger.info(f"UE-MCP SERVER INITIALIZED - Client: {_client_name}")
        logger.info("=" * 70)

        # 调用下一个middleware/handler
        result = await call_next(context)

        # 尝试从当前工作目录自动检测项目
        manager = _initialize_server()
        if manager:
            logger.info(f"自动检测到项目: {manager.project_name}")
        else:
            logger.info(
                f"未检测到UE5项目，客户端 '{_client_name}' 需要调用 project_set_path 设置项目路径"
            )

        return result

    async def on_list_tools(
        self,
        context: MiddlewareContext[mt.ListToolsRequest],
        call_next: CallNext[mt.ListToolsRequest, Any],
    ) -> Any:
        """返回完整工具列表，project_set_path对所有客户端可用"""
        return await call_next(context)


# Note: _initialize_server() is called during initialization for all clients.
# - If a .uproject is found in the working directory, auto-initialize and launch editor
# - If not found, user can call project_set_path to set the project path manually

# Create FastMCP instance
mcp = FastMCP(
    name="ue-mcp",
    middleware=[ClientDetectionMiddleware()],
    instructions="""
UE-MCP is an MCP server for interacting with Unreal Editor.

**Project Initialization:**
- If started from a UE5 project directory, the server auto-detects and launches the editor
- If started from any other directory, use the 'project_set_path' tool to set your UE5 project directory
- The 'project_set_path' tool can only be called once per server session

Available tools:
- project_set_path: Set the UE5 project directory (can be called from any directory)
- editor_launch: Start the Unreal Editor for the bound project
- editor_status: Get the current editor status (includes log_file_path)
- editor_read_log: Read the editor log file content
- editor_stop: Stop the running editor
- editor_execute: Execute Python code in the editor
- editor_configure: Check and fix project configuration
- editor_pip_install: Install Python packages in UE5's Python environment
- editor_start_pie: Start a Play-In-Editor (PIE) session
- editor_stop_pie: Stop the current Play-In-Editor (PIE) session
- editor_capture_orbital: Capture multi-angle screenshots around a target location
- editor_capture_pie: Capture screenshots during Play-In-Editor session
- editor_capture_window: Capture editor window screenshots (Windows only)
- editor_asset_diagnostic: Run diagnostics on a UE5 asset to detect common issues
- editor_asset_inspect: Inspect a UE5 asset and return all its properties
- editor_asset_open: Open an asset in its editor (Blueprint Editor, Material Editor, etc.)
- project_build: Build the UE5 project using UnrealBuildTool (supports Editor, Game, etc.)
- python_api_search: Search UE5 Python APIs in the running editor (list_classes, list_functions, class_info, member_info, search)
""",
)


@mcp.tool(name="project_set_path")
def set_project_path(
    project_path: Annotated[str, Field(description="Absolute path to the directory containing the .uproject file")],
) -> dict[str, Any]:
    """
    Set the UE5 project path for the MCP server.

    This tool can be called from any directory to specify which UE5 project to use.
    It can only be called once during the server's lifetime.

    Args:
        project_path: Absolute path to the directory containing the .uproject file

    Returns:
        Result with success status and detected project information
    """
    global _editor_manager, _project_path_set

    # 检查是否已经调用过
    if _project_path_set:
        return {
            "success": False,
            "error": "project.set_path can only be called once per server lifetime. Project path already set.",
            "current_project": _editor_manager.project_name if _editor_manager else None,
        }

    # 验证路径
    project_dir = Path(project_path)
    if not project_dir.exists():
        return {"success": False, "error": f"Path does not exist: {project_path}"}

    if not project_dir.is_dir():
        return {
            "success": False,
            "error": f"Path is not a directory: {project_path}",
        }

    # 在指定目录中查找.uproject文件
    uproject_path = find_uproject_file(start_dir=project_dir)
    if uproject_path is None:
        return {
            "success": False,
            "error": f"No .uproject file found in: {project_path}",
        }

    # 初始化EditorManager
    logger.info(f"Setting project path: {uproject_path}")
    _editor_manager = EditorManager(uproject_path)
    _project_path_set = True

    return {
        "success": True,
        "project_name": _editor_manager.project_name,
        "project_path": str(_editor_manager.project_root),
        "uproject_file": str(uproject_path),
    }


@mcp.tool(name="editor_launch")
async def launch_editor(
    ctx: Context,
    additional_paths: Annotated[list[str], Field(default=[], description="Optional list of additional Python paths to add to the editor's sys.path")],
    wait: Annotated[bool, Field(default=True, description="Whether to wait for the editor to connect before returning")],
    wait_timeout: Annotated[float, Field(default=120.0, description="Maximum time in seconds to wait for editor connection")],
) -> dict[str, Any]:
    """
    Launch Unreal Editor for the bound project.

    This will:
    1. Check and auto-fix project configuration (Python plugin, remote execution)
    2. Automatically include bundled Python packages (asset_diagnostic, editor_capture)
    3. Start the editor process
    4. By default, wait for the editor to become ready for remote execution.

    Args:
        additional_paths: Optional list of additional Python paths to add to the editor's sys.path
        wait: Whether to wait for the editor to connect before returning (default: True)
        wait_timeout: Maximum time in seconds to wait for editor connection (default: 120)

    Returns:
        Launch result with status information.
    """
    manager = _get_editor_manager()

    # Create notification callback using ctx.log
    async def notify(level: str, message: str) -> None:
        """Send notification to client via MCP log message."""
        await ctx.log(message, level=level)

    # Include bundled site-packages automatically
    all_paths = list(additional_paths) if additional_paths else []
    bundled_path = get_bundled_site_packages()
    if bundled_path.exists():
        bundled_path_str = str(bundled_path.resolve())
        if bundled_path_str not in all_paths:
            all_paths.insert(0, bundled_path_str)
            logger.info(f"Including bundled site-packages: {bundled_path_str}")

    if wait:
        result = await manager.launch(
            notify=notify,
            additional_paths=all_paths if all_paths else None,
            wait_timeout=wait_timeout,
        )
    else:
        result = await manager.launch_async(
            notify=notify,
            additional_paths=all_paths if all_paths else None,
            wait_timeout=wait_timeout,
        )

    # Query project assets if launch was successful
    if result.get("success"):
        assets_result = _query_project_assets(manager)
        if assets_result.get("success"):
            result["project_assets"] = assets_result.get("assets", {})
        else:
            # Include error info but don't fail the launch
            result["project_assets_error"] = assets_result.get("error", "Unknown error")

    return result


@mcp.tool(name="editor_status")
def get_editor_status() -> dict[str, Any]:
    """
    Get the current status of the managed Unreal Editor.

    Returns:
        Status dictionary containing:
        - status: "not_running", "starting", "ready", or "stopped"
        - project_name: Name of the bound project
        - project_path: Path to the .uproject file
        - pid: Process ID (if running)
        - started_at: Timestamp when editor was started (if running)
        - connected: Whether remote execution is connected (if running)
        - log_file_path: Path to the editor log file (if launched)
    """
    manager = _get_editor_manager()
    return manager.get_status()


@mcp.tool(name="editor_read_log")
def read_editor_log(
    tail_lines: Annotated[Optional[int], Field(default=None, description="If specified, only return the last N lines of the log. Useful for large log files.")],
) -> dict[str, Any]:
    """
    Read the Unreal Editor log file content.

    The log file is created when the editor is launched via editor_launch.
    Each launch creates a unique log file with the project name and timestamp.

    Args:
        tail_lines: If specified, only return the last N lines of the log.
                   Useful for large log files. If not specified, returns entire log.

    Returns:
        Result containing:
        - success: Whether read succeeded
        - log_file_path: Path to the log file
        - content: Log file content (or last N lines if tail_lines specified)
        - file_size: Size of the log file in bytes
        - error: Error message (if failed)
    """
    manager = _get_editor_manager()
    return manager.read_log(tail_lines=tail_lines)


@mcp.tool(name="editor_stop")
def stop_editor() -> dict[str, Any]:
    """
    Stop the managed Unreal Editor.

    This will:
    1. Attempt graceful shutdown via unreal.SystemLibrary.quit_editor()
    2. Wait up to 5 seconds for graceful exit
    3. Force terminate if graceful shutdown fails

    Returns:
        Stop result with success status
    """
    manager = _get_editor_manager()
    return manager.stop()


@mcp.tool(name="editor_execute_code")
def execute_code(
    code: Annotated[str, Field(description="Python code to execute")],
    timeout: Annotated[float, Field(default=30.0, description="Execution timeout in seconds")],
) -> dict[str, Any]:
    """
    Execute Python code in the managed Unreal Editor.

    The code is executed in the editor's Python environment with access to
    the 'unreal' module and all editor APIs.

    Args:
        code: Python code to execute
        timeout: Execution timeout in seconds (default: 30)

    Returns:
        Execution result containing:
        - success: Whether execution succeeded
        - result: Return value (if any)
        - output: Console output from the code
        - error: Error message (if failed)

    Example:
        execute_code("import unreal; print(unreal.EditorAssetLibrary.list_assets('/Game/'))")
    """
    manager = _get_editor_manager()
    return manager.execute_with_checks(code, timeout=timeout)


def _build_script_args_injection(script_path: str, args: list[str] | None, kwargs: dict | None) -> str:
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


@mcp.tool(name="editor_execute_script")
def execute_script(
    script_path: Annotated[str, Field(description="Path to the Python script file to execute")],
    timeout: Annotated[float, Field(default=30.0, description="Execution timeout in seconds")],
    args: Annotated[list[str] | None, Field(default=None, description="List of command-line arguments passed to the script via sys.argv[1:]")] = None,
    kwargs: Annotated[dict[str, Any] | None, Field(default=None, description="Dictionary of keyword arguments accessible via __SCRIPT_ARGS__ global variable")] = None,
) -> dict[str, Any]:
    """
    Execute a Python script file in the managed Unreal Editor.

    The script is read from the file system and executed in the editor's Python
    environment with access to the 'unreal' module and all editor APIs.
    Missing modules will be automatically installed.

    Args:
        script_path: Path to the Python script file to execute
        timeout: Execution timeout in seconds (default: 30)
        args: List of command-line arguments to pass to the script via sys.argv[1:]
        kwargs: Dictionary of keyword arguments accessible via __SCRIPT_ARGS__ global variable

    Returns:
        Execution result containing:
        - success: Whether execution succeeded
        - result: Return value (if any)
        - output: Console output from the script
        - error: Error message (if failed)
        - auto_installed: List of packages that were auto-installed (if any)

    Example:
        execute_script("/path/to/my_script.py")

        # With command-line arguments (accessible via sys.argv or argparse):
        execute_script("/path/to/my_script.py", args=["--level", "/Game/Maps/Test", "--verbose"])

        # With keyword arguments (accessible via __SCRIPT_ARGS__):
        execute_script("/path/to/my_script.py", kwargs={"level": "/Game/Maps/Test", "actors": ["A", "B"]})
    """
    from pathlib import Path

    path = Path(script_path)
    if not path.exists():
        return {
            "success": False,
            "error": f"Script file not found: {script_path}",
        }

    if not path.is_file():
        return {
            "success": False,
            "error": f"Path is not a file: {script_path}",
        }

    try:
        code = path.read_text(encoding="utf-8")
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to read script file: {e}",
        }

    # Inject arguments before script content
    injection_code = _build_script_args_injection(script_path, args, kwargs)
    full_code = injection_code + code

    manager = _get_editor_manager()
    return manager.execute_with_checks(full_code, timeout=timeout)


@mcp.tool(name="editor_configure")
def configure_project(
    auto_fix: Annotated[bool, Field(default=True, description="Whether to automatically fix issues")],
    additional_paths: Annotated[list[str], Field(default=[], description="Optional list of additional Python paths to configure")],
) -> dict[str, Any]:
    """
    Check and optionally fix project configuration for Python remote execution.

    This checks:
    1. Python plugin enabled in .uproject
    2. Remote execution settings in DefaultEngine.ini
    3. Additional Python paths (bundled packages are automatically included)

    Bundled packages (asset_diagnostic, editor_capture) are automatically added
    to the editor's Python path.

    Args:
        auto_fix: Whether to automatically fix issues (default: True)
        additional_paths: Optional list of additional Python paths to configure

    Returns:
        Configuration check result with status and details for each check
    """
    from .autoconfig import run_config_check

    manager = _get_editor_manager()
    return run_config_check(
        manager.project_root,
        auto_fix=auto_fix,
        additional_paths=additional_paths if additional_paths else None,
        include_bundled_packages=True,
    )


@mcp.tool(name="project_build")
async def build_project(
    ctx: Context,
    target: Annotated[str, Field(default="Editor", description="Build target type: 'Editor', 'Game', 'Client', or 'Server'")],
    configuration: Annotated[str, Field(default="Development", description="Build configuration: 'Debug', 'DebugGame', 'Development', 'Shipping', or 'Test'")],
    platform: Annotated[str, Field(default="Win64", description="Target platform: 'Win64', 'Mac', 'Linux', etc.")],
    clean: Annotated[bool, Field(default=False, description="Whether to perform a clean build (rebuilds everything)")],
    wait: Annotated[bool, Field(default=True, description="Whether to wait for build to complete")],
    verbose: Annotated[bool, Field(default=False, description="Whether to stream all build logs via notifications")],
    timeout: Annotated[float, Field(default=1800.0, description="Build timeout in seconds (default: 30 minutes)")],
) -> dict[str, Any]:
    """
    Build the UE5 project using UnrealBuildTool.

    This tool compiles the project's C++ code. By default, it waits for the build
    to complete (synchronous) and reports real-time progress.

    Args:
        target: Build target type - one of:
            - "Editor": Build for editor (ProjectNameEditor) [default]
            - "Game": Build standalone game (ProjectName)
            - "Client": Build client target (ProjectNameClient)
            - "Server": Build dedicated server (ProjectNameServer)
        configuration: Build configuration - one of:
            - "Debug": Full debugging, no optimizations
            - "DebugGame": Game debugging, engine optimized
            - "Development": Development build with optimizations [default]
            - "Shipping": Final shipping build, fully optimized
            - "Test": Testing configuration
        platform: Target platform - "Win64" [default], "Mac", "Linux", etc.
        clean: Whether to perform a clean build (rebuilds everything) (default: False)
        wait: Whether to wait for build to complete (default: True)
        verbose: Whether to stream all build logs via notifications (default: False)
        timeout: Build timeout in seconds (default: 1800 = 30 minutes)

    Returns:
        If wait=True (default):
            - success: Whether build succeeded
            - output: Full build output/log
            - return_code: Process return code
            - error: Error message (if failed)

        If wait=False:
            - success: True if build started
            - message: Status message
            - target/platform/configuration: Build parameters

    Example:
        # Build project (waits for completion by default)
        build_project(target="Editor", configuration="Development")

        # Start build in background (returns immediately)
        build_project(target="Game", configuration="Shipping", wait=False)
    """
    manager = _get_editor_manager()

    async def notify(level: str, message: str) -> None:
        await ctx.log(message, level=level)

    async def progress_callback(current: int, total: int) -> None:
        await ctx.report_progress(progress=current, total=total)

    if wait:
        # Synchronous build - wait for completion
        return await manager.build(
            notify=notify,
            progress=progress_callback,
            target=target,
            configuration=configuration,
            platform=platform,
            clean=clean,
            timeout=timeout,
            verbose=verbose,
        )
    else:
        # Asynchronous build - return immediately
        return await manager.build_async(
            notify=notify,
            progress=progress_callback,
            target=target,
            configuration=configuration,
            platform=platform,
            clean=clean,
            timeout=timeout,
            verbose=verbose,
        )


@mcp.tool(name="editor_pip_install")
def pip_install_packages(
    packages: Annotated[list[str], Field(description="List of package names to install (e.g., ['Pillow', 'numpy'])")],
    upgrade: Annotated[bool, Field(default=False, description="Whether to upgrade packages if already installed")],
) -> dict[str, Any]:
    """
    Install Python packages in UE5's embedded Python environment.

    This tool uses UE5's bundled Python interpreter to install packages via pip.
    Installed packages will be available for use in editor.execute() calls.

    Args:
        packages: List of package names to install (e.g., ["Pillow", "numpy"])
        upgrade: Whether to upgrade packages if already installed (default: False)

    Returns:
        Installation result containing:
        - success: Whether installation succeeded
        - packages: List of packages that were installed
        - output: pip output
        - python_path: Path to UE5's Python interpreter used

    Example:
        pip_install_packages(["Pillow", "numpy"])
    """
    manager = _get_editor_manager()
    return manager.pip_install_packages(packages, upgrade=upgrade)


# =============================================================================
# Capture Tools
# =============================================================================


async def _run_pie_task(
    ctx: Context,
    script_name: str,
    params: dict[str, Any],
    duration_seconds: float,
    task_description: str,
    output_key: str,
    output_value: str,
    result_processor: Optional[Callable[[dict[str, Any]], dict[str, Any]]] = None,
) -> dict[str, Any]:
    """
    Execute a PIE task with common logic for capture and trace tools.
    
    This function encapsulates the shared pattern between editor_capture_pie
    and editor_trace_actors_in_pie tools:
    - Generate unique task_id
    - Execute script via script_executor
    - Monitor completion via watch_pie_capture_complete
    - Handle timeout and result processing
    
    Args:
        ctx: MCP Context for logging
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
    manager = _get_editor_manager()
    
    from .script_executor import execute_script
    
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
        return _parse_json_result(result)
    
    # Notify that task has started
    await ctx.log(f"{task_description} started (task_id={task_id}), monitoring for completion...", level="info")
    
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


@mcp.tool(name="editor_start_pie")
def start_pie() -> dict[str, Any]:
    """
    Start a Play-In-Editor (PIE) session.

    This will request the editor to begin playing the current level in PIE mode.
    If PIE is already running, it will return a warning.

    Returns:
        Result containing:
        - success: Whether PIE start was requested successfully
        - message: Status message
        - error: Error message (if failed)
    """
    manager = _get_editor_manager()

    from .script_executor import execute_script_from_path
    script_path = Path(__file__).parent / "extra" / "scripts" / "pie_control.py"

    result = execute_script_from_path(
        manager,
        script_path,
        params={"command": "start"},
        timeout=10.0,
    )

    return _parse_json_result(result)


@mcp.tool(name="editor_stop_pie")
def stop_pie() -> dict[str, Any]:
    """
    Stop the current Play-In-Editor (PIE) session.

    This will request the editor to stop the current PIE session.
    If PIE is not running, it will return a warning.

    Returns:
        Result containing:
        - success: Whether PIE stop was requested successfully
        - message: Status message
        - error: Error message (if failed)
    """
    manager = _get_editor_manager()

    from .script_executor import execute_script_from_path
    script_path = Path(__file__).parent / "extra" / "scripts" / "pie_control.py"

    result = execute_script_from_path(
        manager,
        script_path,
        params={"command": "stop"},
        timeout=10.0,
    )

    return _parse_json_result(result)


@mcp.tool(name="editor_load_level")
def load_level(
    level_path: Annotated[str, Field(description="Path to the level to load (e.g., /Game/Maps/MyLevel)")],
) -> dict[str, Any]:
    """
    Load a level in the editor.

    This uses LevelEditorSubsystem.load_level() to open a level in the editor.

    Args:
        level_path: Path to the level to load (must start with /Game/)

    Returns:
        Result containing:
        - success: Whether level was loaded successfully
        - message: Status message
        - level_path: The level path that was loaded
        - error: Error message (if failed)
    """
    manager = _get_editor_manager()

    from .script_executor import execute_script_from_path
    script_path = Path(__file__).parent / "extra" / "scripts" / "level_load.py"

    result = execute_script_from_path(
        manager,
        script_path,
        params={"level_path": level_path},
        timeout=30.0,
    )

    return _parse_json_result(result)


@mcp.tool(name="editor_capture_orbital")
def capture_orbital(
    level: Annotated[str, Field(description="Path to the level to load (e.g. /Game/Maps/MyLevel)")],
    target_x: Annotated[float, Field(description="Target X coordinate in world space")],
    target_y: Annotated[float, Field(description="Target Y coordinate in world space")],
    target_z: Annotated[float, Field(description="Target Z coordinate in world space")],
    distance: Annotated[float, Field(default=500.0, description="Camera distance from target in UE units")],
    preset: Annotated[str, Field(default="orthographic", description="View preset: 'all', 'perspective', 'orthographic', 'birdseye', 'horizontal', or 'technical'")],
    output_dir: Annotated[Optional[str], Field(default=None, description="Output directory for screenshots (default: auto-generated in project)")],
    resolution_width: Annotated[int, Field(default=800, description="Screenshot width in pixels")],
    resolution_height: Annotated[int, Field(default=600, description="Screenshot height in pixels")],
) -> dict[str, Any]:
    """
    Capture multi-angle screenshots around a target location using SceneCapture2D.

    Creates multiple screenshots from different camera angles orbiting around
    the specified target point in the editor world.

    Args:
        level: Path to the level to load (e.g. /Game/Maps/MyLevel)
        target_x: Target X coordinate in world space
        target_y: Target Y coordinate in world space
        target_z: Target Z coordinate in world space
        distance: Camera distance from target in UE units (default: 500)
        preset: View preset - one of:
            - "all": All views (perspective + orthographic + birdseye)
            - "perspective": 4 horizontal views (front, back, left, right)
            - "orthographic": 6 views (front, back, left, right, top, bottom) [default]
            - "birdseye": 4 elevated 45-degree angle views
            - "horizontal": perspective + birdseye views
            - "technical": Same as orthographic
        output_dir: Output directory for screenshots (default: auto-generated in project)
        resolution_width: Screenshot width in pixels (default: 800)
        resolution_height: Screenshot height in pixels (default: 600)

    Returns:
        Result containing:
        - success: Whether capture succeeded
        - files: Dictionary mapping view types to lists of file paths
        - output: Console output from capture
    """
    manager = _get_editor_manager()

    from .script_executor import execute_script

    result = execute_script(
        manager,
        "capture_orbital",
        params={
            "level": level,
            "target_x": target_x,
            "target_y": target_y,
            "target_z": target_z,
            "distance": distance,
            "preset": preset,
            "output_dir": output_dir,
            "resolution_width": resolution_width,
            "resolution_height": resolution_height,
        },
        timeout=120.0,
    )
    return _parse_json_result(result)


@mcp.tool(name="editor_capture_pie")
async def capture_pie(
    ctx: Context,
    output_dir: Annotated[str, Field(description="Output directory for screenshots")],
    level: Annotated[str, Field(description="Path to the level to load")],
    duration_seconds: Annotated[float, Field(default=10.0, description="How long to capture in seconds")],
    interval_seconds: Annotated[float, Field(default=1.0, description="Time between captures in seconds")],
    resolution_width: Annotated[int, Field(default=1920, description="Screenshot width in pixels")],
    resolution_height: Annotated[int, Field(default=1080, description="Screenshot height in pixels")],
    multi_angle: Annotated[bool, Field(default=True, description="Enable multi-angle capture around player")],
    camera_distance: Annotated[float, Field(default=300.0, description="Camera distance from player for multi-angle")],
    target_height: Annotated[float, Field(default=90.0, description="Target height offset for camera")],
    target_actor: Annotated[Optional[str], Field(default=None, description="Name of the actor to capture (actor label or object name). If not specified, captures around player character.")],
) -> dict[str, Any]:
    """
    Capture screenshots during Play-In-Editor (PIE) session.

    Automatically starts PIE, captures screenshots at regular intervals for
    the specified duration, then stops PIE and returns. This is a synchronous
    operation that blocks until capture completes.

    Args:
        output_dir: Output directory for screenshots (required)
        level: Path to the level to load (required)
        duration_seconds: How long to capture in seconds (default: 10)
        interval_seconds: Time between captures in seconds (default: 1.0)
        resolution_width: Screenshot width in pixels (default: 1920)
        resolution_height: Screenshot height in pixels (default: 1080)
        multi_angle: Enable multi-angle capture around player (default: True)
        camera_distance: Camera distance from player for multi-angle (default: 300)
        target_height: Target height offset for camera (default: 90)
        target_actor: Name of the actor to capture (actor label or object name).
                      If not specified, captures around player character.
                      If specified but not found, returns error with available actors.

    Returns:
        Result containing:
        - success: Whether capture succeeded
        - output_dir: Directory containing captured screenshots
        - duration: Actual capture duration
        - available_actors: (on error) List of actors in level with label, name, type
    """
    def process_capture_result(capture_result: dict[str, Any]) -> dict[str, Any]:
        """Process capture result and extract relevant fields."""
        result = {
            "success": capture_result.get("success", False),
            "output_dir": capture_result.get("output_dir", output_dir),
            "duration": capture_result.get("duration", 0),
            "interval": capture_result.get("interval", interval_seconds),
            "screenshot_count": capture_result.get("screenshot_count", 0),
        }
        # Pass through error info if capture failed
        if not result["success"]:
            if "error" in capture_result:
                result["error"] = capture_result["error"]
            if "available_actors" in capture_result:
                result["available_actors"] = capture_result["available_actors"]
            if "matched_actors" in capture_result:
                result["matched_actors"] = capture_result["matched_actors"]
        return result

    return await _run_pie_task(
        ctx=ctx,
        script_name="capture_pie",
        params={
            "output_dir": output_dir,
            "level": level,
            "duration_seconds": duration_seconds,
            "interval_seconds": interval_seconds,
            "resolution_width": resolution_width,
            "resolution_height": resolution_height,
            "multi_angle": multi_angle,
            "camera_distance": camera_distance,
            "target_height": target_height,
            "target_actor": target_actor,
        },
        duration_seconds=duration_seconds,
        task_description="PIE capture",
        output_key="output_dir",
        output_value=output_dir,
        result_processor=process_capture_result,
    )


@mcp.tool(name="editor_trace_actors_in_pie")
async def trace_actors_in_pie(
    ctx: Context,
    output_dir: Annotated[str, Field(description="Output directory for trace data and screenshots")],
    level: Annotated[str, Field(description="Path to the level to load")],
    actor_names: Annotated[list[str], Field(description="List of actor names to track")],
    duration_seconds: Annotated[float, Field(default=10.0, description="How long to trace in seconds")],
    interval_seconds: Annotated[float, Field(default=0.1, description="Time between samples in seconds")],
    capture_screenshots: Annotated[bool, Field(default=False, description="Whether to capture screenshots of actors")],
    camera_distance: Annotated[float, Field(default=300, description="Camera distance from actor for screenshots")],
    target_height: Annotated[float, Field(default=90, description="Target height offset from actor origin")],
    resolution_width: Annotated[int, Field(default=800, description="Screenshot width in pixels")],
    resolution_height: Annotated[int, Field(default=600, description="Screenshot height in pixels")],
    multi_angle: Annotated[bool, Field(default=True, description="Whether to capture multiple angles per actor")],
) -> dict[str, Any]:
    """
    Trace actor transforms during Play-In-Editor (PIE) session.

    Automatically starts PIE, periodically samples specified actors'
    positions, rotations, and velocities, then stops PIE and returns
    a JSON report.

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

    Args:
        output_dir: Output directory for trace data (required)
        level: Path to the level to load (required)
        actor_names: List of actor names to track (required)
        duration_seconds: How long to trace in seconds (default: 10)
        interval_seconds: Time between samples in seconds (default: 0.1)
        capture_screenshots: Whether to capture screenshots of actors (default: False)
        camera_distance: Camera distance from actor for screenshots (default: 300)
        target_height: Target height offset from actor origin (default: 90)
        resolution_width: Screenshot width in pixels (default: 800)
        resolution_height: Screenshot height in pixels (default: 600)
        multi_angle: Whether to capture multiple angles per actor (default: True)

    Returns:
        Result containing:
        - success: Whether tracing succeeded
        - output_dir: Path to output directory
        - duration: Actual trace duration
        - interval: Sampling interval used
        - sample_count: Number of samples collected
        - actor_count: Number of actors successfully tracked
        - actors_not_found: List of actor names that weren't found
    """
    def process_trace_result(trace_result: dict[str, Any]) -> dict[str, Any]:
        """Process trace result and extract relevant fields."""
        return {
            "success": trace_result.get("success", False),
            "output_dir": trace_result.get("output_dir", output_dir),
            "duration": trace_result.get("duration", 0),
            "interval": trace_result.get("interval", interval_seconds),
            "sample_count": trace_result.get("sample_count", 0),
            "actor_count": trace_result.get("actor_count", 0),
            "actors_not_found": trace_result.get("actors_not_found", []),
        }

    return await _run_pie_task(
        ctx=ctx,
        script_name="trace_actors_pie",
        params={
            "output_dir": output_dir,
            "level": level,
            "actor_names": actor_names,
            "duration_seconds": duration_seconds,
            "interval_seconds": interval_seconds,
            "capture_screenshots": capture_screenshots,
            "camera_distance": camera_distance,
            "target_height": target_height,
            "resolution_width": resolution_width,
            "resolution_height": resolution_height,
            "multi_angle": multi_angle,
        },
        duration_seconds=duration_seconds,
        task_description="PIE actor tracing" + (" with screenshots" if capture_screenshots else ""),
        output_key="output_dir",
        output_value=output_dir,
        result_processor=process_trace_result,
    )


@mcp.tool(name="editor_pie_execute_in_tick")
async def pie_execute_in_tick(
    ctx: Context,
    level: Annotated[str, Field(description="Path to the level to load")],
    total_ticks: Annotated[int, Field(description="Total number of ticks to run PIE")],
    code_snippets: Annotated[list[dict[str, Any]], Field(description="List of code snippet configurations. Each snippet has: code (str), start_tick (int), execution_count (int, default: 1)")],
) -> dict[str, Any]:
    """
    Execute Python code snippets at specific ticks during PIE session.

    Automatically starts PIE, executes code snippets at specified ticks,
    then stops PIE and returns execution results.

    Args:
        level: Path to the level to load (required)
        total_ticks: Total number of ticks to run PIE (required)
        code_snippets: List of code snippet configurations (required)
            Each snippet is a dict with:
            - code: Python code string to execute
            - start_tick: Tick number to start execution (0-indexed)
            - execution_count: Number of consecutive ticks to execute (default: 1)

    Returns:
        Result containing:
        - success: Whether all executions succeeded
        - total_ticks: Total ticks configured
        - executed_ticks: Actual ticks executed
        - execution_count: Number of code executions performed
        - executions: List of execution results (snippet_index, tick, success, output)
        - errors: List of any errors encountered
    """
    def process_executor_result(exec_result: dict[str, Any]) -> dict[str, Any]:
        """Process executor result and extract relevant fields."""
        return {
            "success": exec_result.get("success", False),
            "total_ticks": exec_result.get("total_ticks", total_ticks),
            "executed_ticks": exec_result.get("executed_ticks", 0),
            "execution_count": exec_result.get("execution_count", 0),
            "executions": exec_result.get("executions", []),
            "errors": exec_result.get("errors", []),
        }

    # Estimate duration based on ticks (assume ~60 FPS, add buffer)
    estimated_duration = (total_ticks / 60.0) + 10.0

    return await _run_pie_task(
        ctx=ctx,
        script_name="execute_in_tick",
        params={
            "level": level,
            "total_ticks": total_ticks,
            "code_snippets": code_snippets,
        },
        duration_seconds=estimated_duration,
        task_description="PIE tick execution",
        output_key="total_ticks",
        output_value=str(total_ticks),
        result_processor=process_executor_result,
    )


@mcp.tool(name="editor_capture_window")
def capture_window(
    level: Annotated[str, Field(description="Path to the level to load")],
    output_file: Annotated[Optional[str], Field(default=None, description="Output file path (required for 'window' and 'asset' modes)")],
    mode: Annotated[str, Field(default="window", description="Capture mode: 'window', 'asset', or 'batch'")],
    asset_path: Annotated[Optional[str], Field(default=None, description="Asset path to open (required for 'asset' mode)")],
    asset_list: Annotated[Optional[list[str]], Field(default=None, description="List of asset paths (required for 'batch' mode)")],
    output_dir: Annotated[Optional[str], Field(default=None, description="Output directory (required for 'batch' mode)")],
    tab: Annotated[Optional[int], Field(default=None, description="Tab number to switch to (1-9)")],
) -> dict[str, Any]:
    """
    Capture UE5 editor window screenshot using Windows API.

    NOTE: This tool is Windows-only and uses Windows API for window capture.

    Args:
        level: Path to the level to load (required)
        output_file: Output file path (required for "window" and "asset" modes)
        mode: Capture mode - one of:
            - "window": Capture the main UE5 editor window [default]
            - "asset": Open an asset editor and capture it
            - "batch": Capture multiple assets to a directory
        asset_path: Asset path to open (required for "asset" mode)
        asset_list: List of asset paths (required for "batch" mode)
        output_dir: Output directory (required for "batch" mode)
        tab: Tab number to switch to (1-9, optional)

    Returns:
        Result containing:
        - success: Whether capture succeeded
        - file/files: Path(s) to captured screenshot(s)
    """
    manager = _get_editor_manager()

    from .script_executor import execute_script

    params = {
        "level": level,
        "mode": mode,
        "tab": tab,
    }

    if output_file:
        params["output_file"] = output_file
    
    if mode == "window":
        if not output_file:
            return {"success": False, "error": "output_file is required for 'window' mode"}
        # params["output_file"] is set above

    elif mode == "asset":
        if not output_file:
            return {"success": False, "error": "output_file is required for 'asset' mode"}
        if not asset_path:
             return {"success": False, "error": "asset_path is required for 'asset' mode"}
        params["asset_path"] = asset_path
    
    elif mode == "batch":
        if not asset_list or not output_dir:
            return {
                "success": False,
                "error": "asset_list and output_dir are required for 'batch' mode",
            }
        params["asset_list"] = asset_list
        params["output_dir"] = output_dir

    result = execute_script(
        manager,
        "capture_window",
        params=params,
        timeout=120.0,
    )
    return _parse_json_result(result)


# =============================================================================
# Diagnostic Tools
# =============================================================================


@mcp.tool(name="editor_asset_open")
def open_asset(
    asset_path: Annotated[str, Field(description="Path to the asset to open (e.g., /Game/Blueprints/BP_Character)")],
    tab_id: Annotated[str | None, Field(default=None, description="Optional tab ID to open/focus after the editor opens (e.g., 'Inspector', 'SCSViewport', 'GraphEditor')")],
) -> dict[str, Any]:
    """
    Open an asset in its editor within Unreal Editor.

    This tool loads the specified asset and opens its appropriate editor
    (e.g., Blueprint Editor for Blueprints, Material Editor for Materials).

    Args:
        asset_path: Path to the asset to open (e.g., /Game/Blueprints/BP_Character)
        tab_id: Optional tab ID to open/focus after the editor opens.
                Common Blueprint Editor tab IDs:
                - "Inspector" (Details panel)
                - "SCSViewport" (Viewport/Components view)
                - "GraphEditor" (Event Graph - only available in Graph mode)
                - "MyBlueprint" (My Blueprint panel)
                - "PaletteList" (Palette)
                - "CompilerResults" (Compiler Results)
                - "FindResults" (Find Results)
                - "ConstructionScriptEditor" (Construction Script)
                Note: Some tabs may not be available depending on the editor mode/layout.

    Returns:
        Result containing:
        - success: Whether the asset was opened successfully
        - asset_path: Path of the opened asset
        - asset_name: Name of the asset
        - tab_id: The requested tab ID (if provided)
        - tab_switched: Whether tab switching succeeded (if tab_id provided)
        - tab_error: Error message if tab switching failed (if applicable)
        - error: Error message (if failed)
    """
    manager = _get_editor_manager()

    from .script_executor import execute_script_from_path
    script_path = Path(__file__).parent / "extra" / "scripts" / "asset_open.py"

    result = execute_script_from_path(
        manager,
        script_path,
        params={"asset_path": asset_path, "tab_id": tab_id},
        timeout=30.0,
    )

    return _parse_json_result(result)


@mcp.tool(name="editor_asset_diagnostic")
def diagnose_asset(
    asset_path: Annotated[str, Field(description="Path to the asset to diagnose (e.g., /Game/Maps/TestLevel)")],
) -> dict[str, Any]:
    """
    Run diagnostics on a UE5 asset to detect common issues.

    The tool automatically detects the asset type and runs appropriate
    diagnostics. Supported types include: Level, Blueprint, Material,
    StaticMesh, SkeletalMesh, Texture, and more.

    Args:
        asset_path: Path to the asset to diagnose (e.g., /Game/Maps/TestLevel)

    Returns:
        Diagnostic result containing:
        - success: Whether diagnostic ran successfully
        - asset_path: Path of diagnosed asset
        - asset_type: Detected asset type (Level, Blueprint, etc.)
        - asset_name: Name of the asset
        - errors: Number of errors found
        - warnings: Number of warnings found
        - issues: List of issues, each with severity, category, message, actor, details, suggestion
        - summary: Optional summary message
        - metadata: Additional asset metadata
    """
    manager = _get_editor_manager()

    from .script_executor import execute_script_from_path, get_diagnostic_scripts_dir

    scripts_dir = get_diagnostic_scripts_dir()
    script_path = scripts_dir / "diagnostic_runner.py"

    result = execute_script_from_path(
        manager,
        script_path,
        params={"asset_path": asset_path},
        timeout=120.0,
    )

    return _parse_json_result(result)


@mcp.tool(name="editor_asset_inspect")
def inspect_asset(
    asset_path: Annotated[str, Field(description="Path to the asset to inspect (e.g., /Game/Meshes/MyStaticMesh)")],
    component_name: Annotated[str | None, Field(default=None, description="Optional name of a specific component to inspect (only valid for Blueprint assets)")],
) -> dict[str, Any]:
    """
    Inspect a UE5 asset and return all its properties.

    This tool loads an asset and extracts all accessible properties,
    metadata, and reference information.

    For Blueprint assets, you can optionally specify a component to inspect.
    When no component is specified for Blueprints, the response includes a list
    of available components with their names, class types, and hierarchy.

    For Blueprint and Level assets, a viewport screenshot is automatically captured
    and saved to the system temp directory.

    Args:
        asset_path: Path to the asset (e.g., /Game/Meshes/MyStaticMesh)
        component_name: Optional name of a specific component to inspect
                       (only valid for Blueprint assets)

    Returns:
        Inspection result containing:
        - success: Whether inspection succeeded
        - asset_path: Path of inspected asset
        - asset_type: Detected asset type (Level, Blueprint, StaticMesh, etc.)
        - asset_name: Name of the asset
        - asset_class: UE5 class name of the asset
        - properties: Dictionary of all accessible properties with their values
        - property_count: Number of properties found
        - components: (For Blueprints) List of available components with hierarchy
        - component_info: (When component_name specified) Details of the component
        - metadata: Asset registry metadata (package info, etc.)
        - references: Dependencies and referencers
        - screenshot_path: (For Blueprint/Level) Path to viewport screenshot
        - screenshot_error: (For Blueprint/Level) Error message if screenshot failed
    """
    manager = _get_editor_manager()

    from .script_executor import execute_script_from_path, get_diagnostic_scripts_dir

    scripts_dir = get_diagnostic_scripts_dir()
    script_path = scripts_dir / "inspect_runner.py"

    params = {"asset_path": asset_path}
    if component_name is not None:
        params["component_name"] = component_name

    result = execute_script_from_path(
        manager,
        script_path,
        params=params,
        timeout=120.0,
    )

    return _parse_json_result(result)


# =============================================================================
# Python API Search Tools
# =============================================================================


@mcp.tool(name="python_api_search")
def python_api_search(
    mode: Annotated[str, Field(description="Query mode: 'list_classes', 'list_functions', 'class_info', 'member_info', 'search'")],
    query: Annotated[str | None, Field(default=None, description="Class name, member path (Class.member), search term, or wildcard pattern (e.g., '*Actor*')")],
    include_inherited: Annotated[bool, Field(default=True, description="For class_info: include inherited members")],
    include_private: Annotated[bool, Field(default=False, description="Include private members (_underscore)")],
    limit: Annotated[int, Field(default=100, description="Maximum results to return")],
) -> dict[str, Any]:
    """
    Query UE5 Python APIs from the running editor using runtime introspection.

    This tool introspects the live 'unreal' module in the running editor,
    providing accurate API information for the current UE5 version.

    Args:
        mode: Query mode - one of:
            - "list_classes": List all classes (supports wildcard pattern in query)
            - "list_functions": List functions/methods (supports multiple formats, see below)
            - "class_info": Get class details with all members (requires query)
            - "member_info": Get specific member details (requires query)
            - "search": Fuzzy search across all names (requires query)
        query: Depends on mode:
            - list_classes: Optional wildcard pattern (e.g., "*Actor*", "Static*")
            - list_functions: Multiple formats supported:
                - None or no ".": Module-level functions (e.g., "*asset*")
                - "ClassName.*": All methods of a class (e.g., "Actor.*")
                - "ClassName.*pattern*": Methods matching pattern (e.g., "Actor.*location*")
                - "*.*pattern*": Search methods across all classes (e.g., "*.*spawn*")
            - class_info: Class name (e.g., "Actor")
            - member_info: Member path (e.g., "Actor.get_actor_location")
            - search: Search term (e.g., "spawn")
        include_inherited: For class_info: include inherited members (default: True)
        include_private: Include private members starting with underscore (default: False)
        limit: Maximum number of results to return (default: 100)

    Returns:
        Result containing:
        - success: Whether query succeeded
        - mode: The query mode used
        - results: (for list/search modes) List of matching items
        - pattern: (for list modes with query) The wildcard pattern used
        - class_name/member_name: (for info modes) The queried item
        - properties/methods: (for class_info) Lists of class members
        - signature/docstring: (for member_info) Member details
        - error: Error message (if failed)

    Examples:
        # List all classes
        python_api_search(mode="list_classes", limit=10)

        # List classes matching wildcard pattern
        python_api_search(mode="list_classes", query="*Actor*")
        python_api_search(mode="list_classes", query="Static*")

        # List module-level functions
        python_api_search(mode="list_functions")
        python_api_search(mode="list_functions", query="*asset*")

        # List all methods of a class
        python_api_search(mode="list_functions", query="Actor.*")

        # List methods matching pattern in a class
        python_api_search(mode="list_functions", query="Actor.*location*")

        # Search methods across all classes
        python_api_search(mode="list_functions", query="*.*spawn*")

        # Get Actor class info
        python_api_search(mode="class_info", query="Actor")

        # Get specific method info
        python_api_search(mode="member_info", query="Actor.get_actor_location")

        # Search for spawn-related APIs
        python_api_search(mode="search", query="spawn")
    """
    from .script_executor import get_extra_scripts_dir, execute_script_from_path

    manager = _get_editor_manager()

    # Validate mode
    valid_modes = ["list_classes", "list_functions", "class_info", "member_info", "search"]
    if mode not in valid_modes:
        return {"success": False, "error": f"Invalid mode '{mode}'. Must be one of: {valid_modes}"}

    # Validate query required for certain modes
    if mode in ["class_info", "member_info", "search"] and not query:
        return {"success": False, "error": f"query parameter required for mode '{mode}'"}

    # Execute api_search script
    script_path = get_extra_scripts_dir() / "api_search.py"
    params = {
        "mode": mode,
        "query": query,
        "include_inherited": include_inherited,
        "include_private": include_private,
        "limit": limit,
    }

    result = execute_script_from_path(manager, script_path, params, timeout=30.0)

    # Parse result
    return _parse_json_result(result)


def _cleanup_on_shutdown() -> None:
    """
    Clean up resources when the server is shutting down.

    This function is called by signal handlers and ensures proper cleanup
    of the EditorManager and any running UE5 editor instances.
    """
    global _editor_manager
    logger.info("Server shutdown requested, cleaning up...")

    if _editor_manager is not None:
        try:
            _editor_manager._cleanup()
            logger.info("EditorManager cleanup completed")
        except Exception as e:
            logger.error(f"Error during EditorManager cleanup: {e}")

    logger.info("Cleanup completed")


def _signal_handler(signum: int, frame) -> None:
    """
    Handle termination signals (SIGTERM, SIGINT).

    This ensures proper cleanup when the MCP server is stopped by:
    - mcp-pytest's stdio_client closing the connection
    - User pressing Ctrl+C
    - System sending SIGTERM
    """
    sig_name = signal.Signals(signum).name
    logger.info(f"Received signal {sig_name} ({signum})")
    _cleanup_on_shutdown()
    sys.exit(0)


def main():
    """Main entry point for the MCP server."""
    # Register signal handlers for graceful shutdown
    # This ensures cleanup happens even when atexit is not triggered
    if sys.platform != "win32":
        # Unix-like systems: handle SIGTERM and SIGINT
        signal.signal(signal.SIGTERM, _signal_handler)
        signal.signal(signal.SIGINT, _signal_handler)
    else:
        # Windows: SIGTERM is not supported, only SIGINT (Ctrl+C)
        # For Windows, we also use SIGBREAK for Ctrl+Break
        signal.signal(signal.SIGINT, _signal_handler)
        if hasattr(signal, "SIGBREAK"):
            signal.signal(signal.SIGBREAK, _signal_handler)

    # Note: For claude-ai/Automatic-Testing clients, _editor_manager is initialized
    # via project.set_path tool, not at startup. For other clients, it's initialized
    # automatically in ClientDetectionMiddleware.on_initialize().
    logger.info("Starting UE-MCP server...")

    try:
        mcp.run()
    finally:
        # Fallback cleanup in case signals weren't caught
        _cleanup_on_shutdown()


if __name__ == "__main__":
    main()
