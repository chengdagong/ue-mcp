"""
UE-MCP Server

FastMCP-based MCP server for Unreal Editor interaction.
"""

import logging
import sys
from pathlib import Path
from typing import Any, Optional

from fastmcp import Context, FastMCP

from .autoconfig import get_bundled_site_packages
from .editor_manager import EditorManager
from .utils import find_uproject_file

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Global state
_editor_manager: Optional[EditorManager] = None


def _get_editor_manager() -> EditorManager:
    """Get the global EditorManager instance."""
    if _editor_manager is None:
        raise RuntimeError(
            "EditorManager not initialized. "
            "MCP server must be started from a directory containing a UE5 project."
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


# Initialize server on module load
_initialize_server()

# Create FastMCP instance
mcp = FastMCP(
    name="ue-mcp",
    instructions="""
UE-MCP is an MCP server for interacting with Unreal Editor.

This server is bound to a specific UE5 project (detected from the working directory).
All tools operate on the bound project's editor instance.

Available tools:
- editor.launch: Start the Unreal Editor for the bound project
- editor.status: Get the current editor status
- editor.stop: Stop the running editor
- editor.execute: Execute Python code in the editor
- editor.configure: Check and fix project configuration
- editor.pip_install: Install Python packages in UE5's Python environment
- editor.capture.orbital: Capture multi-angle screenshots around a target location
- editor.capture.pie: Capture screenshots during Play-In-Editor session
- editor.capture.window: Capture editor window screenshots (Windows only)
- project.build: Build the UE5 project using UnrealBuildTool (supports Editor, Game, etc.)
""",
)


@mcp.tool(name="editor.launch")
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


@mcp.tool(name="editor.status")
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
    """
    manager = _get_editor_manager()
    return manager.get_status()


@mcp.tool(name="editor.stop")
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


@mcp.tool(name="editor.execute")
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
    return manager.execute(code, timeout=timeout)


@mcp.tool(name="editor.configure")
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


@mcp.tool(name="project.build")
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


@mcp.tool(name="editor.pip_install")
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
        return {
            "success": False,
            "error": exec_result.get("error", "Execution failed"),
            "output": exec_result.get("output", ""),
        }

    output = exec_result.get("output", "")
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

    return {"success": True, "output": output}


@mcp.tool(name="editor.capture.orbital")
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


@mcp.tool(name="editor.capture.pie")
def capture_pie(
    output_dir: str,
    level: str,
    duration_seconds: float = 10.0,
    interval_seconds: float = 1.0,
    resolution_width: int = 1920,
    resolution_height: int = 1080,
    multi_angle: bool = True,
    camera_distance: float = 300.0,
    target_height: float = 90.0,
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

    Returns:
        Result containing:
        - success: Whether capture succeeded
        - output_dir: Directory containing captured screenshots
        - duration: Actual capture duration
    """
    manager = _get_editor_manager()

    from .script_executor import execute_script

    # Timeout = duration + buffer for startup/shutdown
    timeout = duration_seconds + 60.0
    
    result = execute_script(
        manager,
        "capture_pie",
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
        },
        timeout=timeout,
    )
    return _parse_capture_result(result)


@mcp.tool(name="editor.capture.window")
def capture_window(
    output_file: str,
    level: str,
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
        output_file: Output file path for screenshot (required for window/asset modes)
        level: Path to the level to load (required)
        mode: Capture mode - one of:
            - "window": Capture the main UE5 editor window [default]
            - "asset": Open an asset editor and capture it
            - "batch": Capture multiple assets to a directory
        asset_path: Asset path to open (required for "asset" mode)
        asset_list: List of asset paths (required for "batch" mode)
        output_dir: Output directory (required for "batch" mode, overrides output_file)
        tab: Tab number to switch to before capture (1-9, optional)

    Returns:
        Result containing:
        - success: Whether capture succeeded
        - file/files: Path(s) to captured screenshot(s)
    """
    manager = _get_editor_manager()

    from .script_executor import execute_script

    params = {
        "output_file": output_file,
        "level": level,
        "mode": mode,
        "tab": tab,
    }
    
    if mode == "asset":
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


def main():
    """Main entry point for the MCP server."""
    if _editor_manager is None:
        logger.error("Failed to initialize server. Exiting.")
        sys.exit(1)

    logger.info(f"Starting UE-MCP server for project: {_editor_manager.project_name}")
    mcp.run()


if __name__ == "__main__":
    main()
