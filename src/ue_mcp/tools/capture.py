"""Screenshot capture and actor tracing tools."""

from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any, Optional

from fastmcp import Context
from pydantic import Field

if TYPE_CHECKING:
    from fastmcp import FastMCP

    from ..state import ServerState


def register_tools(mcp: "FastMCP", state: "ServerState") -> None:
    """Register capture and tracing tools."""

    from ..script_executor import execute_script, execute_script_from_path

    from ._helpers import parse_json_result, run_pie_task

    @mcp.tool(name="editor_capture_orbital")
    def capture_orbital(
        level: Annotated[
            str,
            Field(description="Path to the level to load (e.g. /Game/Maps/MyLevel)"),
        ],
        target_x: Annotated[
            float, Field(description="Target X coordinate in world space")
        ],
        target_y: Annotated[
            float, Field(description="Target Y coordinate in world space")
        ],
        target_z: Annotated[
            float, Field(description="Target Z coordinate in world space")
        ],
        distance: Annotated[
            float,
            Field(default=500.0, description="Camera distance from target in UE units"),
        ],
        preset: Annotated[
            str,
            Field(
                default="orthographic",
                description="View preset: 'all', 'perspective', 'orthographic', 'birdseye', 'horizontal', or 'technical'",
            ),
        ],
        output_dir: Annotated[
            Optional[str],
            Field(
                default=None,
                description="Output directory for screenshots (default: auto-generated in project)",
            ),
        ],
        resolution_width: Annotated[
            int, Field(default=800, description="Screenshot width in pixels")
        ],
        resolution_height: Annotated[
            int, Field(default=600, description="Screenshot height in pixels")
        ],
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
        execution = state.get_execution_subsystem()

        result = execute_script(
            execution,
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
        return parse_json_result(result)

    @mcp.tool(name="editor_capture_pie")
    async def capture_pie(
        ctx: Context,
        output_dir: Annotated[
            str, Field(description="Output directory for screenshots")
        ],
        level: Annotated[str, Field(description="Path to the level to load")],
        duration_seconds: Annotated[
            float,
            Field(default=10.0, description="How long to capture in seconds"),
        ],
        interval_seconds: Annotated[
            float,
            Field(default=1.0, description="Time between captures in seconds"),
        ],
        resolution_width: Annotated[
            int, Field(default=1920, description="Screenshot width in pixels")
        ],
        resolution_height: Annotated[
            int, Field(default=1080, description="Screenshot height in pixels")
        ],
        multi_angle: Annotated[
            bool,
            Field(default=True, description="Enable multi-angle capture around player"),
        ],
        camera_distance: Annotated[
            float,
            Field(
                default=300.0,
                description="Camera distance from player for multi-angle",
            ),
        ],
        target_height: Annotated[
            float,
            Field(default=90.0, description="Target height offset for camera"),
        ],
        target_actor: Annotated[
            Optional[str],
            Field(
                default=None,
                description="Name of the actor to capture (actor label or object name). If not specified, captures around player character.",
            ),
        ],
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
        execution = state.get_execution_subsystem()
        context = state.get_context()

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

        return await run_pie_task(
            ctx=ctx,
            execution=execution,
            project_root=context.project_root,
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
        output_dir: Annotated[
            str, Field(description="Output directory for trace data and screenshots")
        ],
        level: Annotated[str, Field(description="Path to the level to load")],
        actor_names: Annotated[
            list[str], Field(description="List of actor names to track")
        ],
        duration_seconds: Annotated[
            float, Field(default=10.0, description="How long to trace in seconds")
        ],
        interval_seconds: Annotated[
            float,
            Field(default=0.1, description="Time between samples in seconds"),
        ],
        capture_screenshots: Annotated[
            bool,
            Field(
                default=False, description="Whether to capture screenshots of actors"
            ),
        ],
        camera_distance: Annotated[
            float,
            Field(
                default=300, description="Camera distance from actor for screenshots"
            ),
        ],
        target_height: Annotated[
            float,
            Field(default=90, description="Target height offset from actor origin"),
        ],
        resolution_width: Annotated[
            int, Field(default=800, description="Screenshot width in pixels")
        ],
        resolution_height: Annotated[
            int, Field(default=600, description="Screenshot height in pixels")
        ],
        multi_angle: Annotated[
            bool,
            Field(
                default=True,
                description="Whether to capture multiple angles per actor",
            ),
        ],
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
        execution = state.get_execution_subsystem()
        context = state.get_context()

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

        return await run_pie_task(
            ctx=ctx,
            execution=execution,
            project_root=context.project_root,
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
            task_description="PIE actor tracing"
            + (" with screenshots" if capture_screenshots else ""),
            output_key="output_dir",
            output_value=output_dir,
            result_processor=process_trace_result,
        )

    @mcp.tool(name="editor_pie_execute_in_tick")
    async def pie_execute_in_tick(
        ctx: Context,
        level: Annotated[str, Field(description="Path to the level to load")],
        total_ticks: Annotated[
            int, Field(description="Total number of ticks to run PIE")
        ],
        code_snippets: Annotated[
            list[dict[str, Any]],
            Field(
                description="List of code snippet configurations. Each snippet has: code (str), start_tick (int), execution_count (int, default: 1)"
            ),
        ],
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
        execution = state.get_execution_subsystem()
        context = state.get_context()

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

        return await run_pie_task(
            ctx=ctx,
            execution=execution,
            project_root=context.project_root,
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
        output_file: Annotated[
            Optional[str],
            Field(
                default=None,
                description="Output file path (required for 'window' and 'asset' modes)",
            ),
        ],
        mode: Annotated[
            str,
            Field(
                default="window",
                description="Capture mode: 'window', 'asset', or 'batch'",
            ),
        ],
        asset_path: Annotated[
            Optional[str],
            Field(
                default=None,
                description="Asset path to open (required for 'asset' mode)",
            ),
        ],
        asset_list: Annotated[
            Optional[list[str]],
            Field(
                default=None,
                description="List of asset paths (required for 'batch' mode)",
            ),
        ],
        output_dir: Annotated[
            Optional[str],
            Field(
                default=None,
                description="Output directory (required for 'batch' mode)",
            ),
        ],
        tab: Annotated[
            Optional[int],
            Field(default=None, description="Tab number to switch to (1-9)"),
        ],
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
        execution = state.get_execution_subsystem()

        params: dict[str, Any] = {
            "level": level,
            "mode": mode,
            "tab": tab,
        }

        if output_file:
            params["output_file"] = output_file

        if mode == "window":
            if not output_file:
                return {
                    "success": False,
                    "error": "output_file is required for 'window' mode",
                }

        elif mode == "asset":
            if not output_file:
                return {
                    "success": False,
                    "error": "output_file is required for 'asset' mode",
                }
            if not asset_path:
                return {
                    "success": False,
                    "error": "asset_path is required for 'asset' mode",
                }
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
            execution,
            "capture_window",
            params=params,
            timeout=120.0,
        )
        return parse_json_result(result)

    @mcp.tool(name="editor_level_screenshot")
    def level_screenshot(
        cameras: Annotated[
            Optional[list[str]],
            Field(
                default=None,
                description="List of camera specs in format 'name@x,y,z' (e.g., ['front@500,0,500', 'back@-500,0,500']). If not provided, uses default camera at (800,0,800).",
            ),
        ],
        target: Annotated[
            str,
            Field(
                default="0,0,0",
                description="Target point that all cameras look at, format: 'x,y,z'",
            ),
        ],
        resolution: Annotated[
            str,
            Field(
                default="1280x720",
                description="Screenshot resolution, format: 'WIDTHxHEIGHT'",
            ),
        ],
        output_dir: Annotated[
            Optional[str],
            Field(
                default=None,
                description="Output directory for screenshots. If not provided, uses project's Saved/Screenshots.",
            ),
        ],
        level: Annotated[
            Optional[str],
            Field(
                default=None,
                description="Level path to load before taking screenshots (e.g., /Game/Maps/MyLevel). If not provided, uses the currently open level.",
            ),
        ],
    ) -> dict[str, Any]:
        """
        Capture screenshots from custom camera positions looking at a target point.

        Creates temporary CameraActors at specified positions, takes high-resolution
        screenshots from each camera, then automatically cleans up the cameras.

        This is useful for capturing level screenshots from specific angles without
        manually placing cameras in the editor.

        Args:
            cameras: List of camera specs in format 'name@x,y,z'. Each camera will be
                     positioned at the specified coordinates and oriented to look at
                     the target point. If not provided, uses a single default camera
                     at position (800, 0, 800).
            target: Target point that all cameras will look at, format: 'x,y,z'.
                    Default is origin (0,0,0).
            resolution: Screenshot resolution in format 'WIDTHxHEIGHT'.
                        Default is '1280x720'.
            output_dir: Directory to save screenshots. If not provided, screenshots
                        are saved to the project's Saved/Screenshots folder.
            level: Level path to load before taking screenshots (e.g., /Game/Maps/MyLevel).
                   If not provided, uses the currently open level.

        Returns:
            Result containing:
            - success: Whether all screenshots were captured successfully
            - screenshot_count: Number of screenshots taken
            - screenshots: List of screenshot results with camera name and filename
            - output_dir: Directory where screenshots were saved
            - resolution: Resolution used for screenshots

        Example:
            # Single camera at default position
            editor_level_screenshot()

            # Multiple cameras around a point
            editor_level_screenshot(
                cameras=["front@500,0,300", "back@-500,0,300", "top@0,0,800"],
                target="0,0,100"
            )

            # High resolution with custom output
            editor_level_screenshot(
                cameras=["hero@1000,500,400"],
                resolution="1920x1080",
                output_dir="D:/screenshots"
            )

            # Load a specific level and take screenshots
            editor_level_screenshot(
                level="/Game/Maps/TestLevel",
                cameras=["front@500,0,500", "back@-500,0,500"],
                target="0,0,100"
            )
        """
        execution = state.get_execution_subsystem()

        # Build parameters for the script
        params: dict[str, Any] = {
            "target": target,
            "resolution": resolution,
        }

        if cameras:
            params["cameras"] = cameras

        if output_dir:
            params["out_dir"] = output_dir

        if level:
            params["level"] = level

        # Execute the take_screenshots.py script
        script_path = Path(__file__).parent.parent / "extra" / "scripts" / "take_screenshots.py"

        result = execute_script_from_path(
            execution,
            script_path,
            params=params,
            timeout=120.0,
            wait_for_latent=True,
            latent_timeout=60.0,
        )

        return parse_json_result(result)
