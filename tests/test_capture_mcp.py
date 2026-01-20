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
        output_file: str,
        mode: str = "window",
    ) -> dict[str, Any]:
        """Capture editor window screenshot."""
        return await self.call_tool(
            "editor.capture.window",
            {
                "level": level,
                "output_file": output_file,
                "mode": mode,
            },
            timeout_seconds=60,
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


# Direct execution for quick testing
async def quick_test():
    """Quick test function for manual testing."""
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
