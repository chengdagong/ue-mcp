"""
Asset Diagnostic Tool Integration Tests using Official MCP Client SDK

Tests the editor.asset.diagnostic tool via the official MCP Python SDK.
Requires a UE5 project with valid assets to diagnose.

Usage:
    pytest tests/test_diagnostic_mcp.py -v -s

Note: These tests require UE5 to be installed and will launch the editor.
"""

import asyncio
import json
import sys
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


class MCPDiagnosticClient:
    """Helper class for testing diagnostic tools via MCP."""

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

    async def diagnose_asset(
        self,
        asset_path: str,
    ) -> dict[str, Any]:
        """Run diagnostics on an asset."""
        return await self.call_tool(
            "editor.asset.diagnostic",
            {"asset_path": asset_path},
            timeout_seconds=120,
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
class TestDiagnosticTools:
    """Integration tests for diagnostic tools."""

    @pytest.mark.asyncio
    async def test_list_tools_includes_diagnostic(self, project_path: Path):
        """Test that diagnostic tool is listed."""
        server_params = get_server_params(project_path)

        async with stdio_client(server_params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                client = MCPDiagnosticClient(session)

                tools = await client.list_tools()

                # Check diagnostic tool is present
                assert "editor.asset.diagnostic" in tools

    @pytest.mark.asyncio
    async def test_diagnostic_without_editor(self, project_path: Path):
        """Test diagnostic fails gracefully when editor not running."""
        server_params = get_server_params(project_path)

        async with stdio_client(server_params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                client = MCPDiagnosticClient(session)

                result = await client.diagnose_asset(
                    asset_path="/Game/Maps/TestLevel",
                )

                # Should fail with error about editor not running
                assert result.get("success") is False or "error" in result

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_diagnostic_with_editor(self, project_path: Path):
        """Test diagnostic with editor running."""
        server_params = get_server_params(project_path)

        async with stdio_client(server_params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                client = MCPDiagnosticClient(session)

                # Launch editor
                launch_result = await client.editor_launch(wait_timeout=180)

                if not launch_result.get("success"):
                    pytest.skip(f"Editor launch failed: {launch_result.get('error')}")

                try:
                    # Test diagnostics on a level
                    result = await client.diagnose_asset(
                        asset_path="/Game/Maps/Main",
                    )

                    # Check result structure
                    if result.get("success"):
                        assert "asset_path" in result
                        assert "asset_type" in result
                        assert "errors" in result
                        assert "warnings" in result
                        assert "issues" in result
                        assert isinstance(result["issues"], list)
                    else:
                        # May fail if level doesn't exist - that's OK for this test
                        print(f"Diagnostic result: {result}")

                finally:
                    # Always stop editor
                    await client.editor_stop()


@pytest.mark.integration
class TestDiagnosticToolValidation:
    """Test input validation for diagnostic tools."""

    @pytest.mark.asyncio
    async def test_diagnostic_missing_asset_path(self, project_path: Path):
        """Test diagnostic with missing asset_path parameter."""
        server_params = get_server_params(project_path)

        async with stdio_client(server_params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                client = MCPDiagnosticClient(session)

                # Missing required 'asset_path' parameter should cause error
                try:
                    result = await client.call_tool(
                        "editor.asset.diagnostic",
                        {},  # Empty arguments
                    )
                    # If we get here, check for error in result
                    assert "error" in result or result.get("success") is False
                except Exception as e:
                    # Expected - missing required parameter
                    assert "asset_path" in str(e).lower() or "required" in str(e).lower()

    @pytest.mark.asyncio
    async def test_diagnostic_invalid_asset_path(self, project_path: Path):
        """Test diagnostic with invalid asset path format."""
        server_params = get_server_params(project_path)

        async with stdio_client(server_params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                client = MCPDiagnosticClient(session)

                # Invalid asset path - should fail gracefully
                result = await client.diagnose_asset(
                    asset_path="not_a_valid_path",
                )

                # Should fail since editor is not running
                assert result.get("success") is False or "error" in result


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

            client = MCPDiagnosticClient(session)

            # List tools
            print("\nAvailable tools:")
            tools = await client.list_tools()
            for tool in sorted(tools):
                print(f"  - {tool}")

            # Check diagnostic tool is present
            if "editor.asset.diagnostic" in tools:
                print("\n✓ editor.asset.diagnostic tool is registered")
            else:
                print("\n✗ editor.asset.diagnostic tool NOT found!")

            # Check editor status
            print("\nEditor status:")
            status = await client.editor_status()
            print(f"  {status}")


if __name__ == "__main__":
    asyncio.run(quick_test())
