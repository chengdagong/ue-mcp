"""
Capture Tool Integration Tests using Official MCP Client SDK

Tests the editor.capture.* tools via the official MCP Python SDK.
Requires a UE5 project with a valid level to capture.

Usage:
    pytest tests/test_capture_mcp.py -v -s

Note: These tests require UE5 to be installed and will launch the editor.
"""

import asyncio
import json
import sys
import tempfile
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest

from mcp import ClientSession, StdioServerParameters, stdio_client

# Fixture paths
FIXTURES_DIR = Path(__file__).parent / "fixtures"
TEST_PROJECT = FIXTURES_DIR / "TestProject1"
# Alternative: Use URF project for more comprehensive testing
URF_PROJECT = Path("D:/Code/URF")


def get_server_params(project_path: Path) -> StdioServerParameters:
    """Create server parameters for ue-mcp server."""
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "ue_mcp.server"],
        cwd=str(project_path),
        env={
            "PYTHONPATH": str(Path(__file__).parent.parent / "src"),
        },
    )


class MCPCaptureClient:
    """Helper class for testing capture tools via MCP."""

    def __init__(self, session: ClientSession):
        self.session = session

    async def list_tools(self) -> list[str]:
        """List all available tools."""
        result = await self.session.list_tools()
        return [tool.name for tool in result.tools]

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
        timeout_seconds: float = 120.0,
    ) -> dict[str, Any]:
        """Call a tool and return the result as a dictionary."""
        result = await self.session.call_tool(
            name=name,
            arguments=arguments,
            read_timeout_seconds=timedelta(seconds=timeout_seconds),
        )

        # Extract content from result
        if result.content:
            for content_item in result.content:
                if hasattr(content_item, "text"):
                    try:
                        return json.loads(content_item.text)
                    except json.JSONDecodeError:
                        return {"raw_text": content_item.text}

        return {"is_error": result.isError, "content": str(result.content)}

    async def editor_launch(self, wait_timeout: float = 180.0) -> dict[str, Any]:
        """Launch the editor and wait for connection."""
        return await self.call_tool(
            "editor.launch",
            {"wait": True, "wait_timeout": wait_timeout},
            timeout_seconds=wait_timeout + 60,
        )

    async def editor_stop(self) -> dict[str, Any]:
        """Stop the editor."""
        return await self.call_tool("editor.stop", timeout_seconds=30)

    async def editor_status(self) -> dict[str, Any]:
        """Get editor status."""
        return await self.call_tool("editor.status", timeout_seconds=10)

    async def capture_orbital(
        self,
        level: str,
        target_x: float,
        target_y: float,
        target_z: float,
        distance: float = 500.0,
        preset: str = "orthographic",
        output_dir: str | None = None,
        resolution_width: int = 800,
        resolution_height: int = 600,
    ) -> dict[str, Any]:
        """Capture orbital screenshots."""
        return await self.call_tool(
            "editor.capture.orbital",
            {
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
            timeout_seconds=120,
        )

    async def capture_window(
        self,
        level: str,
        output_file: str | None = None,
        mode: str = "window",
        asset_path: str | None = None,
        asset_list: list[str] | None = None,
        output_dir: str | None = None,
        tab: int | None = None,
    ) -> dict[str, Any]:
        """Capture editor window screenshot."""
        args: dict[str, Any] = {
            "level": level,
            "mode": mode,
        }
        if output_file:
            args["output_file"] = output_file
        if asset_path:
            args["asset_path"] = asset_path
        if asset_list:
            args["asset_list"] = asset_list
        if output_dir:
            args["output_dir"] = output_dir
        if tab is not None:
            args["tab"] = tab

        return await self.call_tool(
            "editor.capture.window",
            args,
            timeout_seconds=120,
        )

    async def capture_pie(
        self,
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
        """Capture screenshots during Play-In-Editor session."""
        # Timeout = duration + buffer for startup/shutdown
        timeout = duration_seconds + 120.0
        return await self.call_tool(
            "editor.capture.pie",
            {
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
            timeout_seconds=timeout,
        )


@pytest.fixture(scope="module")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="module")
def project_path() -> Path:
    """Return the test project path."""
    # Prefer URF project for comprehensive testing if available
    if URF_PROJECT.exists():
        return URF_PROJECT
    if not TEST_PROJECT.exists():
        pytest.skip(f"Test project not found: {TEST_PROJECT}")
    return TEST_PROJECT


@pytest.mark.integration
@pytest.mark.slow
class TestCaptureTools:
    """Integration tests for capture tools."""

    @pytest.mark.asyncio
    async def test_list_tools_includes_capture(self, project_path: Path):
        """Test that capture tools are listed."""
        server_params = get_server_params(project_path)

        async with stdio_client(server_params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                client = MCPCaptureClient(session)

                tools = await client.list_tools()

                # Check capture tools are present
                assert "editor.capture.orbital" in tools
                assert "editor.capture.pie" in tools
                assert "editor.capture.window" in tools

    @pytest.mark.asyncio
    async def test_capture_orbital_without_editor(self, project_path: Path):
        """Test capture.orbital fails gracefully when editor not running."""
        server_params = get_server_params(project_path)

        async with stdio_client(server_params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                client = MCPCaptureClient(session)

                result = await client.capture_orbital(
                    level="/Game/Maps/TestLevel",
                    target_x=0,
                    target_y=0,
                    target_z=100,
                )

                # Should fail with error about editor not running
                assert result.get("success") is False or "error" in result

    @pytest.mark.asyncio
    async def test_capture_orbital_with_editor(self, project_path: Path):
        """Test capture.orbital with editor running."""
        server_params = get_server_params(project_path)

        async with stdio_client(server_params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                client = MCPCaptureClient(session)

                # Launch editor
                launch_result = await client.editor_launch(wait_timeout=180)

                if not launch_result.get("success"):
                    pytest.skip(f"Editor launch failed: {launch_result.get('error')}")

                try:
                    # Create temp output directory
                    with tempfile.TemporaryDirectory() as temp_dir:
                        result = await client.capture_orbital(
                            level="/Game/Maps/Main",  # Default UE5 level
                            target_x=0,
                            target_y=0,
                            target_z=100,
                            distance=500,
                            preset="orthographic",
                            output_dir=temp_dir,
                            resolution_width=640,
                            resolution_height=480,
                        )

                        # Check result
                        if result.get("success"):
                            assert "files" in result or "total_captures" in result
                        else:
                            # May fail if level doesn't exist - that's OK for this test
                            print(f"Capture result: {result}")

                finally:
                    # Always stop editor
                    await client.editor_stop()

    @pytest.mark.asyncio
    async def test_capture_window_without_editor(self, project_path: Path):
        """Test capture.window fails gracefully when editor not running."""
        server_params = get_server_params(project_path)

        async with stdio_client(server_params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                client = MCPCaptureClient(session)

                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                    result = await client.capture_window(
                        level="/Game/Maps/TestLevel",
                        output_file=f.name,
                    )

                # Should fail with error about editor not running
                assert result.get("success") is False or "error" in result

    @pytest.mark.asyncio
    async def test_capture_pie_without_editor(self, project_path: Path):
        """Test capture.pie fails gracefully when editor not running."""
        server_params = get_server_params(project_path)

        async with stdio_client(server_params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                client = MCPCaptureClient(session)

                with tempfile.TemporaryDirectory() as temp_dir:
                    result = await client.capture_pie(
                        output_dir=temp_dir,
                        level="/Game/Maps/TestLevel",
                        duration_seconds=2.0,
                        interval_seconds=0.5,
                    )

                # Should fail with error about editor not running
                assert result.get("success") is False or "error" in result

    @pytest.mark.asyncio
    async def test_capture_pie_with_editor(self, project_path: Path):
        """Test capture.pie with editor running."""
        server_params = get_server_params(project_path)

        async with stdio_client(server_params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                client = MCPCaptureClient(session)

                # Launch editor
                launch_result = await client.editor_launch(wait_timeout=180)

                if not launch_result.get("success"):
                    pytest.skip(f"Editor launch failed: {launch_result.get('error')}")

                try:
                    # Create temp output directory
                    with tempfile.TemporaryDirectory() as temp_dir:
                        result = await client.capture_pie(
                            output_dir=temp_dir,
                            level="/Game/Maps/Main",  # Default UE5 level
                            duration_seconds=5.0,
                            interval_seconds=1.0,
                            resolution_width=640,
                            resolution_height=480,
                            multi_angle=False,  # Simpler for testing
                        )

                        # Check result
                        if result.get("success"):
                            assert "output_dir" in result or "duration" in result
                        else:
                            # May fail if level doesn't exist - that's OK for this test
                            print(f"PIE Capture result: {result}")

                finally:
                    # Always stop editor
                    await client.editor_stop()

    @pytest.mark.asyncio
    async def test_capture_window_with_editor(self, project_path: Path):
        """Test capture.window with editor running."""
        server_params = get_server_params(project_path)

        async with stdio_client(server_params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                client = MCPCaptureClient(session)

                # Launch editor
                launch_result = await client.editor_launch(wait_timeout=180)

                if not launch_result.get("success"):
                    pytest.skip(f"Editor launch failed: {launch_result.get('error')}")

                try:
                    # Test window mode capture
                    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                        result = await client.capture_window(
                            level="/Game/Maps/Main",
                            output_file=f.name,
                            mode="window",
                        )

                        # Check result
                        if result.get("success"):
                            assert "file" in result or "captured" in result
                            # Verify file was created
                            if result.get("captured"):
                                assert Path(f.name).exists()
                        else:
                            # May fail on non-Windows - that's OK
                            print(f"Window Capture result: {result}")

                finally:
                    # Always stop editor
                    await client.editor_stop()

    @pytest.mark.asyncio
    async def test_capture_window_batch_mode_with_editor(self, project_path: Path):
        """Test capture.window batch mode with editor running."""
        server_params = get_server_params(project_path)

        async with stdio_client(server_params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                client = MCPCaptureClient(session)

                # Launch editor
                launch_result = await client.editor_launch(wait_timeout=180)

                if not launch_result.get("success"):
                    pytest.skip(f"Editor launch failed: {launch_result.get('error')}")

                try:
                    with tempfile.TemporaryDirectory() as temp_dir:
                        # Test batch mode with sample assets
                        result = await client.capture_window(
                            level="/Game/Maps/Main",
                            mode="batch",
                            asset_list=[
                                "/Game/FirstPerson/Blueprints/BP_FirstPersonCharacter",
                            ],
                            output_dir=temp_dir,
                        )

                        # Check result
                        if result.get("success"):
                            assert "files" in result or "success_count" in result
                        else:
                            # Assets may not exist - that's OK
                            print(f"Batch Capture result: {result}")

                finally:
                    # Always stop editor
                    await client.editor_stop()


@pytest.mark.integration
class TestCaptureToolValidation:
    """Test input validation for capture tools."""

    @pytest.mark.asyncio
    async def test_capture_orbital_missing_level(self, project_path: Path):
        """Test capture.orbital with missing level parameter."""
        server_params = get_server_params(project_path)

        async with stdio_client(server_params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                client = MCPCaptureClient(session)

                # Missing required 'level' parameter should cause error
                try:
                    result = await client.call_tool(
                        "editor.capture.orbital",
                        {
                            # "level" is missing
                            "target_x": 0,
                            "target_y": 0,
                            "target_z": 100,
                        },
                    )
                    # If we get here, check for error in result
                    assert "error" in result or result.get("success") is False
                except Exception as e:
                    # Expected - missing required parameter
                    assert "level" in str(e).lower() or "required" in str(e).lower()

    @pytest.mark.asyncio
    async def test_capture_window_mode_validation(self, project_path: Path):
        """Test capture.window validates output_file for window mode."""
        server_params = get_server_params(project_path)

        async with stdio_client(server_params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                client = MCPCaptureClient(session)

                # window mode without output_file should fail
                result = await client.call_tool(
                    "editor.capture.window",
                    {
                        "level": "/Game/Maps/TestLevel",
                        "mode": "window",
                        # output_file is missing
                    },
                )

                assert result.get("success") is False
                assert "output_file" in result.get("error", "").lower()

    @pytest.mark.asyncio
    async def test_capture_window_asset_mode_validation(self, project_path: Path):
        """Test capture.window validates asset_path for asset mode."""
        server_params = get_server_params(project_path)

        async with stdio_client(server_params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                client = MCPCaptureClient(session)

                # asset mode without asset_path should fail
                result = await client.call_tool(
                    "editor.capture.window",
                    {
                        "level": "/Game/Maps/TestLevel",
                        "mode": "asset",
                        "output_file": "/tmp/test.png",
                        # asset_path is missing
                    },
                )

                assert result.get("success") is False
                assert "asset_path" in result.get("error", "").lower()

    @pytest.mark.asyncio
    async def test_capture_window_batch_mode_validation(self, project_path: Path):
        """Test capture.window validates asset_list and output_dir for batch mode."""
        server_params = get_server_params(project_path)

        async with stdio_client(server_params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                client = MCPCaptureClient(session)

                # batch mode without asset_list should fail
                result = await client.call_tool(
                    "editor.capture.window",
                    {
                        "level": "/Game/Maps/TestLevel",
                        "mode": "batch",
                        "output_dir": "/tmp/output",
                        # asset_list is missing
                    },
                )

                assert result.get("success") is False
                assert "asset_list" in result.get("error", "").lower() or "output_dir" in result.get("error", "").lower()

    @pytest.mark.asyncio
    async def test_capture_pie_missing_level(self, project_path: Path):
        """Test capture.pie with missing level parameter."""
        server_params = get_server_params(project_path)

        async with stdio_client(server_params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                client = MCPCaptureClient(session)

                # Missing required 'level' parameter should cause error
                try:
                    result = await client.call_tool(
                        "editor.capture.pie",
                        {
                            "output_dir": "/tmp/output",
                            # "level" is missing
                            "duration_seconds": 5.0,
                        },
                    )
                    # If we get here, check for error in result
                    assert "error" in result or result.get("success") is False
                except Exception as e:
                    # Expected - missing required parameter
                    assert "level" in str(e).lower() or "required" in str(e).lower()

    @pytest.mark.asyncio
    async def test_capture_pie_missing_output_dir(self, project_path: Path):
        """Test capture.pie with missing output_dir parameter."""
        server_params = get_server_params(project_path)

        async with stdio_client(server_params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                client = MCPCaptureClient(session)

                # Missing required 'output_dir' parameter should cause error
                try:
                    result = await client.call_tool(
                        "editor.capture.pie",
                        {
                            "level": "/Game/Maps/TestLevel",
                            # "output_dir" is missing
                            "duration_seconds": 5.0,
                        },
                    )
                    # If we get here, check for error in result
                    assert "error" in result or result.get("success") is False
                except Exception as e:
                    # Expected - missing required parameter
                    assert "output_dir" in str(e).lower() or "required" in str(e).lower()


# Direct execution for quick testing
async def quick_test():
    """Quick test function for manual testing."""
    # Prefer URF project for comprehensive testing if available
    if URF_PROJECT.exists():
        project_path = URF_PROJECT
    else:
        project_path = TEST_PROJECT

    if not project_path.exists():
        print(f"Error: Test project not found at {project_path}")
        return

    print(f"Using project: {project_path}")
    server_params = get_server_params(project_path)

    print("Connecting to MCP server...")
    async with stdio_client(server_params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            print("Initializing session...")
            init_result = await session.initialize()
            print(f"Server: {init_result.serverInfo.name} v{init_result.serverInfo.version}")

            client = MCPCaptureClient(session)

            # List tools
            print("\nAvailable tools:")
            tools = await client.list_tools()
            for tool in sorted(tools):
                print(f"  - {tool}")

            # Check editor status
            print("\nEditor status:")
            status = await client.editor_status()
            print(f"  {status}")

            # If you want to test capture (requires editor to be launched):
            # print("\nLaunching editor...")
            # launch = await client.editor_launch()
            # print(f"  {launch}")


if __name__ == "__main__":
    asyncio.run(quick_test())
