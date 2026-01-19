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
""",
)


@mcp.tool(name="editor.launch")
async def launch_editor(
    ctx: Context,
    additional_paths: list[str] = [],
    wait_timeout: float = 120.0,
) -> dict[str, Any]:
    """
    Launch Unreal Editor for the bound project.

    This will:
    1. Check and auto-fix project configuration (Python plugin, remote execution)
    2. Automatically include bundled Python packages (asset_diagnostic, editor_capture)
    3. Start the editor process
    4. Return immediately while waiting for connection in background
    5. Send a notification when connection is established

    The tool returns immediately after the editor process starts. You will receive
    a notification when the editor is fully connected and ready for remote execution.
    Use editor.status to check the current connection status.

    Args:
        additional_paths: Optional list of additional Python paths to add to the editor's sys.path
        wait_timeout: Maximum time in seconds to wait for editor connection (default: 120)

    Returns:
        Launch result with status information (editor process started)
    """
    manager = _get_editor_manager()

    # Create notification callback using ctx.log
    async def notify(level: str, message: str) -> None:
        """Send notification to client via MCP log message."""
        await ctx.log(level, message)

    # Include bundled site-packages automatically
    all_paths = list(additional_paths) if additional_paths else []
    bundled_path = get_bundled_site_packages()
    if bundled_path.exists():
        bundled_path_str = str(bundled_path.resolve())
        if bundled_path_str not in all_paths:
            all_paths.insert(0, bundled_path_str)
            logger.info(f"Including bundled site-packages: {bundled_path_str}")

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

    output_dir_repr = repr(output_dir) if output_dir else "None"

    code = f'''
import editor_capture
import unreal
import json

world = unreal.EditorLevelLibrary.get_editor_world()
if not world:
    raise RuntimeError("Could not get editor world")

results = editor_capture.take_orbital_screenshots_with_preset(
    loaded_world=world,
    preset="{preset}",
    target_location=unreal.Vector({target_x}, {target_y}, {target_z}),
    distance={distance},
    output_dir={output_dir_repr},
    resolution_width={resolution_width},
    resolution_height={resolution_height},
)

# Convert to JSON-serializable format
files = {{k: list(v) if v else [] for k, v in results.items()}}
total = sum(len(v) for v in files.values())
print("__CAPTURE_RESULT__" + json.dumps({{"files": files, "total_captures": total}}))
'''

    result = manager.execute_with_auto_install(code, timeout=120.0)
    return _parse_capture_result(result)


@mcp.tool(name="editor.capture.pie")
def capture_pie(
    output_dir: str,
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

    code = f'''
import editor_capture
import time
import json

# Start PIE capture with auto-start
capturer = editor_capture.start_pie_capture(
    output_dir="{output_dir}",
    interval_seconds={interval_seconds},
    resolution=({resolution_width}, {resolution_height}),
    auto_start_pie=True,
    multi_angle={multi_angle},
    camera_distance={camera_distance},
    target_height={target_height},
)

# Wait for specified duration
start_time = time.time()
time.sleep({duration_seconds})
elapsed = time.time() - start_time

# Stop PIE capture
editor_capture.stop_pie_capture()

print("__CAPTURE_RESULT__" + json.dumps({{
    "output_dir": "{output_dir}",
    "duration": elapsed,
    "interval": {interval_seconds},
}}))
'''

    # Timeout = duration + buffer for startup/shutdown
    timeout = duration_seconds + 60.0
    result = manager.execute_with_auto_install(code, timeout=timeout)
    return _parse_capture_result(result)


@mcp.tool(name="editor.capture.window")
def capture_window(
    output_file: str,
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

    if mode == "window":
        tab_code = ""
        if tab is not None:
            tab_code = f'''
hwnd = editor_capture.find_ue5_window()
if hwnd:
    editor_capture.switch_to_tab({tab}, hwnd)
    time.sleep(0.5)
'''
        code = f'''
import editor_capture
import time
import json

{tab_code}
success = editor_capture.capture_ue5_window("{output_file}")
print("__CAPTURE_RESULT__" + json.dumps({{"file": "{output_file}", "captured": success}}))
'''

    elif mode == "asset":
        if not asset_path:
            return {"success": False, "error": "asset_path is required for 'asset' mode"}

        tab_arg = f", tab_number={tab}" if tab is not None else ""
        code = f'''
import editor_capture
import json

result = editor_capture.open_asset_and_screenshot(
    asset_path="{asset_path}",
    output_path="{output_file}",
    delay=3.0{tab_arg}
)
print("__CAPTURE_RESULT__" + json.dumps({{
    "file": "{output_file}",
    "opened": result["opened"],
    "captured": result["screenshot"],
}}))
'''

    elif mode == "batch":
        if not asset_list or not output_dir:
            return {
                "success": False,
                "error": "asset_list and output_dir are required for 'batch' mode",
            }

        asset_list_repr = repr(asset_list)
        code = f'''
import editor_capture
import json

results = editor_capture.batch_asset_screenshots(
    asset_paths={asset_list_repr},
    output_dir="{output_dir}",
    delay=3.0,
    close_after=True,
)

files = [r.get("screenshot_path") for r in results if r.get("screenshot")]
success_count = len(files)
total_count = len({asset_list_repr})
print("__CAPTURE_RESULT__" + json.dumps({{
    "files": files,
    "success_count": success_count,
    "total_count": total_count,
}}))
'''
    else:
        return {"success": False, "error": f"Unknown mode: {mode}"}

    result = manager.execute_with_auto_install(code, timeout=120.0)
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
