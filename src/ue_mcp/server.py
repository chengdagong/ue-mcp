"""
UE-MCP Server

FastMCP-based MCP server for Unreal Editor interaction.
"""

import asyncio
import logging
import sys
import uuid
from pathlib import Path
from typing import Any, Optional

import mcp.types as mt
from fastmcp import Context, FastMCP
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext

from .autoconfig import get_bundled_site_packages
from .editor_manager import EditorManager
from .log_watcher import watch_pie_capture_complete
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
- project_build: Build the UE5 project using UnrealBuildTool (supports Editor, Game, etc.)
""",
)


@mcp.tool(name="project_set_path")
def set_project_path(project_path: str) -> dict[str, Any]:
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
    additional_paths: list[str] = [],
    wait: bool = True,
    wait_timeout: float = 120.0,
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
        return await manager.launch(
            notify=notify,
            additional_paths=all_paths if all_paths else None,
            wait_timeout=wait_timeout,
        )
    else:
        return await manager.launch_async(
            notify=notify,
            additional_paths=all_paths if all_paths else None,
            wait_timeout=wait_timeout,
        )


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
def read_editor_log(tail_lines: Optional[int] = None) -> dict[str, Any]:
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
def execute_code(code: str, timeout: float = 30.0) -> dict[str, Any]:
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
    return manager.execute_with_auto_install(code, timeout=timeout)


@mcp.tool(name="editor_execute_script")
def execute_script(script_path: str, timeout: float = 30.0) -> dict[str, Any]:
    """
    Execute a Python script file in the managed Unreal Editor.

    The script is read from the file system and executed in the editor's Python
    environment with access to the 'unreal' module and all editor APIs.
    Missing modules will be automatically installed.

    Args:
        script_path: Path to the Python script file to execute
        timeout: Execution timeout in seconds (default: 30)

    Returns:
        Execution result containing:
        - success: Whether execution succeeded
        - result: Return value (if any)
        - output: Console output from the script
        - error: Error message (if failed)
        - auto_installed: List of packages that were auto-installed (if any)

    Example:
        execute_script("/path/to/my_script.py")
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

    manager = _get_editor_manager()
    return manager.execute_with_auto_install(code, timeout=timeout)


@mcp.tool(name="editor_configure")
def configure_project(
    auto_fix: bool = True,
    additional_paths: list[str] = [],
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
    target: str = "Editor",
    configuration: str = "Development",
    platform: str = "Win64",
    clean: bool = False,
    wait: bool = True,
    verbose: bool = False,
    timeout: float = 1800.0,
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
    packages: list[str],
    upgrade: bool = False,
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


def _parse_capture_result(exec_result: dict[str, Any]) -> dict[str, Any]:
    """Parse capture result from execution output."""
    if not exec_result.get("success"):
        # Check 'result' for proper exception details from UE
        error_msg = exec_result.get("error", "Execution failed")
        ue_result = exec_result.get("result")
        if ue_result:
             # If successful execution but returned False, result often contains the error/traceback
             error_msg = f"{error_msg}. Details: {ue_result}"

        return {
            "success": False,
            "error": error_msg,
            "output": exec_result.get("output", ""),
        }

    output = exec_result.get("output", "")
    if isinstance(output, list):
        # Handle list of strings or list of dicts (if UE returns structured log)
        processed_lines = []
        for line in output:
            if isinstance(line, dict):
                processed_lines.append(str(line.get("output", "")))
            else:
                processed_lines.append(str(line))
        output = "\n".join(processed_lines)
    marker = "__CAPTURE_RESULT__"

    if marker in output:
        import json

        try:
            json_str = output.split(marker)[1].strip().split("\n")[0]
            result_data = json.loads(json_str)
            return {"success": True, **result_data}
        except (json.JSONDecodeError, IndexError) as e:
            return {
                "success": True,
                "warning": f"Could not parse result: {e}",
                "output": output,
            }

    return {
        "success": False,
        "error": "No capture result returned from editor script", 
        "output": output
    }


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

    code = """
import editor_capture.pie_capture as pie_capture

result = pie_capture.start_pie_session()
if result:
    print("__PIE_RESULT__SUCCESS")
else:
    # Check if already running
    if pie_capture.is_pie_running():
        print("__PIE_RESULT__ALREADY_RUNNING")
    else:
        print("__PIE_RESULT__FAILED")
"""
    exec_result = manager.execute_with_auto_install(code, timeout=10.0)

    if not exec_result.get("success"):
        return {
            "success": False,
            "error": exec_result.get("error", "Failed to execute PIE start command"),
        }

    output = exec_result.get("output", "")
    if isinstance(output, list):
        output = "\n".join(str(line) for line in output)

    if "__PIE_RESULT__SUCCESS" in output:
        return {"success": True, "message": "PIE session started"}
    elif "__PIE_RESULT__ALREADY_RUNNING" in output:
        return {"success": False, "message": "PIE is already running"}
    else:
        return {"success": False, "error": "Failed to start PIE session"}


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

    code = """
import editor_capture.pie_capture as pie_capture

result = pie_capture.stop_pie_session()
if result:
    print("__PIE_RESULT__SUCCESS")
else:
    # Check if not running
    if not pie_capture.is_pie_running():
        print("__PIE_RESULT__NOT_RUNNING")
    else:
        print("__PIE_RESULT__FAILED")
"""
    exec_result = manager.execute_with_auto_install(code, timeout=10.0)

    if not exec_result.get("success"):
        return {
            "success": False,
            "error": exec_result.get("error", "Failed to execute PIE stop command"),
        }

    output = exec_result.get("output", "")
    if isinstance(output, list):
        output = "\n".join(str(line) for line in output)

    if "__PIE_RESULT__SUCCESS" in output:
        return {"success": True, "message": "PIE session stopped"}
    elif "__PIE_RESULT__NOT_RUNNING" in output:
        return {"success": False, "message": "PIE is not running"}
    else:
        return {"success": False, "error": "Failed to stop PIE session"}


@mcp.tool(name="editor_capture_orbital")
def capture_orbital(
    level: str,
    target_x: float,
    target_y: float,
    target_z: float,
    distance: float = 500.0,
    preset: str = "orthographic",
    output_dir: Optional[str] = None,
    resolution_width: int = 800,
    resolution_height: int = 600,
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
    return _parse_capture_result(result)


@mcp.tool(name="editor_capture_pie")
async def capture_pie(
    ctx: Context,
    output_dir: str,
    level: str,
    duration_seconds: float = 10.0,
    interval_seconds: float = 1.0,
    resolution_width: int = 1920,
    resolution_height: int = 1080,
    multi_angle: bool = True,
    camera_distance: float = 300.0,
    target_height: float = 90.0,
    target_actor: Optional[str] = None,
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
    manager = _get_editor_manager()

    from .script_executor import execute_script

    # Generate unique task_id for this capture
    task_id = str(uuid.uuid4())[:8]

    # Start capture (returns immediately, capture runs via tick callbacks)
    result = execute_script(
        manager,
        "capture_pie",
        params={
            "task_id": task_id,
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
        timeout=30.0,  # Short timeout since script returns immediately
    )

    if not result.get("success", False):
        return _parse_capture_result(result)

    # Notify that capture has started
    await ctx.log(f"PIE capture started (task_id={task_id}), monitoring for completion...", level="info")

    # Watch for completion file
    # Timeout = duration + buffer for PIE startup/shutdown
    watch_timeout = duration_seconds + 60.0

    async def on_complete(capture_result: dict[str, Any]) -> None:
        """Called when capture completes."""
        await ctx.log(
            f"PIE capture completed: {capture_result.get('screenshot_count', 0)} screenshots",
            level="info",
        )

    capture_result = await watch_pie_capture_complete(
        project_root=manager.project_root,
        task_id=task_id,
        callback=on_complete,
        timeout=watch_timeout,
    )

    if capture_result is None:
        return {
            "success": False,
            "error": f"Timeout waiting for PIE capture completion after {watch_timeout}s",
            "output_dir": output_dir,
        }

    result = {
        "success": capture_result.get("success", False),
        "output_dir": capture_result.get("output_dir", output_dir),
        "duration": capture_result.get("duration", 0),
        "interval": capture_result.get("interval", interval_seconds),
        "screenshot_count": capture_result.get("screenshot_count", 0),
    }

    # Pass through error info if capture failed (e.g., target_actor not found or multiple matches)
    if not result["success"]:
        if "error" in capture_result:
            result["error"] = capture_result["error"]
        if "available_actors" in capture_result:
            result["available_actors"] = capture_result["available_actors"]
        if "matched_actors" in capture_result:
            result["matched_actors"] = capture_result["matched_actors"]

    return result


@mcp.tool(name="editor_trace_actors_in_pie")
async def trace_actors_in_pie(
    ctx: Context,
    output_file: str,
    level: str,
    actor_names: list[str],
    duration_seconds: float = 10.0,
    interval_seconds: float = 0.1,
) -> dict[str, Any]:
    """
    Trace actor transforms during Play-In-Editor (PIE) session.

    Automatically starts PIE, periodically samples specified actors'
    positions, rotations, and velocities, then stops PIE and returns
    a JSON report.

    Args:
        output_file: Output JSON file path (required)
        level: Path to the level to load (required)
        actor_names: List of actor names to track (required)
        duration_seconds: How long to trace in seconds (default: 10)
        interval_seconds: Time between samples in seconds (default: 0.1)

    Returns:
        Result containing:
        - success: Whether tracing succeeded
        - output_file: Path to JSON trace file
        - duration: Actual trace duration
        - interval: Sampling interval used
        - sample_count: Number of samples collected
        - actor_count: Number of actors successfully tracked
        - actors_not_found: List of actor names that weren't found
    """
    manager = _get_editor_manager()

    from .script_executor import execute_script

    # Generate unique task_id for this trace
    task_id = str(uuid.uuid4())[:8]

    # Start tracer (returns immediately, tracing runs via tick callbacks)
    result = execute_script(
        manager,
        "trace_actors_pie",
        params={
            "task_id": task_id,
            "output_file": output_file,
            "level": level,
            "actor_names": actor_names,
            "duration_seconds": duration_seconds,
            "interval_seconds": interval_seconds,
        },
        timeout=30.0,  # Short timeout since script returns immediately
    )

    if not result.get("success", False):
        return _parse_capture_result(result)

    # Notify that tracing has started
    await ctx.log(f"PIE actor tracing started (task_id={task_id}), monitoring for completion...", level="info")

    # Watch for completion file
    # Timeout = duration + buffer for PIE startup/shutdown
    watch_timeout = duration_seconds + 60.0

    async def on_complete(trace_result: dict[str, Any]) -> None:
        """Called when tracing completes."""
        await ctx.log(
            f"PIE tracing completed: {trace_result.get('sample_count', 0)} samples "
            f"for {trace_result.get('actor_count', 0)} actors",
            level="info",
        )

    trace_result = await watch_pie_capture_complete(
        project_root=manager.project_root,
        task_id=task_id,
        callback=on_complete,
        timeout=watch_timeout,
    )

    if trace_result is None:
        return {
            "success": False,
            "error": f"Timeout waiting for PIE tracing completion after {watch_timeout}s",
            "output_file": output_file,
        }

    return {
        "success": trace_result.get("success", False),
        "output_file": trace_result.get("output_file", output_file),
        "duration": trace_result.get("duration", 0),
        "interval": trace_result.get("interval", interval_seconds),
        "sample_count": trace_result.get("sample_count", 0),
        "actor_count": trace_result.get("actor_count", 0),
        "actors_not_found": trace_result.get("actors_not_found", []),
    }


@mcp.tool(name="editor_capture_window")
def capture_window(
    level: str,
    output_file: Optional[str] = None,
    mode: str = "window",
    asset_path: Optional[str] = None,
    asset_list: Optional[list[str]] = None,
    output_dir: Optional[str] = None,
    tab: Optional[int] = None,
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
    return _parse_capture_result(result)


# =============================================================================
# Diagnostic Tools
# =============================================================================


def _parse_diagnostic_result(exec_result: dict[str, Any]) -> dict[str, Any]:
    """Parse diagnostic result from execution output."""
    if not exec_result.get("success"):
        error_msg = exec_result.get("error", "Execution failed")
        ue_result = exec_result.get("result")
        if ue_result:
            error_msg = f"{error_msg}. Details: {ue_result}"
        return {
            "success": False,
            "error": error_msg,
            "output": exec_result.get("output", ""),
        }

    output = exec_result.get("output", "")
    if isinstance(output, list):
        processed_lines = []
        for line in output:
            if isinstance(line, dict):
                processed_lines.append(str(line.get("output", "")))
            else:
                processed_lines.append(str(line))
        output = "\n".join(processed_lines)

    marker = "__DIAGNOSTIC_RESULT__"
    if marker in output:
        import json
        try:
            json_str = output.split(marker)[1].strip().split("\n")[0]
            result_data = json.loads(json_str)
            return result_data
        except (json.JSONDecodeError, IndexError) as e:
            return {
                "success": True,
                "warning": f"Could not parse result: {e}",
                "output": output,
            }

    return {
        "success": False,
        "error": "No diagnostic result returned from editor script",
        "output": output,
    }


@mcp.tool(name="editor_asset_diagnostic")
def diagnose_asset(asset_path: str) -> dict[str, Any]:
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

    from .script_executor import get_diagnostic_scripts_dir

    scripts_dir = get_diagnostic_scripts_dir()
    script_path = scripts_dir / "diagnostic_runner.py"

    if not script_path.exists():
        return {"success": False, "error": f"Script not found: {script_path}"}

    try:
        script_content = script_path.read_text(encoding="utf-8")
    except Exception as e:
        return {"success": False, "error": f"Failed to read script: {e}"}

    # Inject parameters
    params = {"asset_path": asset_path}
    params_code = (
        "import builtins\n"
        f"builtins.__PARAMS__ = {repr(params)}\n"
        f"__PARAMS__ = builtins.__PARAMS__\n\n"
    )

    full_code = params_code + script_content
    result = manager.execute_with_auto_install(full_code, timeout=120.0)

    return _parse_diagnostic_result(result)


@mcp.tool(name="editor_asset_inspect")
def inspect_asset(asset_path: str, component_name: str | None = None) -> dict[str, Any]:
    """
    Inspect a UE5 asset and return all its properties.

    This tool loads an asset and extracts all accessible properties,
    metadata, and reference information.

    For Blueprint assets, you can optionally specify a component to inspect.
    When no component is specified for Blueprints, the response includes a list
    of available components with their names, class types, and hierarchy.

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
    """
    manager = _get_editor_manager()

    from .script_executor import get_diagnostic_scripts_dir

    scripts_dir = get_diagnostic_scripts_dir()
    script_path = scripts_dir / "inspect_runner.py"

    if not script_path.exists():
        return {"success": False, "error": f"Script not found: {script_path}"}

    try:
        script_content = script_path.read_text(encoding="utf-8")
    except Exception as e:
        return {"success": False, "error": f"Failed to read script: {e}"}

    # Inject parameters
    params = {"asset_path": asset_path}
    if component_name is not None:
        params["component_name"] = component_name
    params_code = (
        "import builtins\n"
        f"builtins.__PARAMS__ = {repr(params)}\n"
        f"__PARAMS__ = builtins.__PARAMS__\n\n"
    )

    full_code = params_code + script_content
    result = manager.execute_with_auto_install(full_code, timeout=120.0)

    return _parse_diagnostic_result(result)


def main():
    """Main entry point for the MCP server."""
    # Note: For claude-ai/Automatic-Testing clients, _editor_manager is initialized
    # via project.set_path tool, not at startup. For other clients, it's initialized
    # automatically in ClientDetectionMiddleware.on_initialize().
    logger.info("Starting UE-MCP server...")
    mcp.run()


if __name__ == "__main__":
    main()
