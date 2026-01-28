"""
UE-MCP Server

FastMCP-based MCP server for Unreal Editor interaction.
"""

import json
import logging
import os
import signal
import sys
from pathlib import Path

import mcp.types as mt
from fastmcp import FastMCP
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext
from fastmcp.tools.tool import ToolResult
from mcp.types import ImageContent, TextContent

from .state import server_state
from .tools import register_all_tools
from .core.image_processing import is_claude_ai_client, process_result_for_images

# Configure logging
# Get project root directory (two levels up from current file)
_log_dir = Path(__file__).parent.parent.parent.resolve()
_log_file = _log_dir / "ue-mcp.log"

# Configure basic logging to stderr first
logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stderr)],
)
logger = logging.getLogger(__name__)

# Try to add file handler
try:
    _log_dir.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(_log_file, mode="a", encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(
        logging.Formatter("[%(levelname)s] %(name)s: %(message)s")
    )
    logging.getLogger().addHandler(file_handler)
    logger.info(f"Logging to file: {_log_file}")
except Exception as e:
    logger.error(f"Failed to setup file logging: {e}")
    logger.info(f"Attempted log file path: {_log_file}")


class ClientDetectionMiddleware(Middleware):
    """Detect MCP client type and auto-initialize project."""

    async def on_initialize(
        self,
        context: MiddlewareContext[mt.InitializeRequest],
        call_next: CallNext[mt.InitializeRequest, mt.InitializeResult | None],
    ) -> mt.InitializeResult | None:
        # Extract client name
        client_info = context.message.params.clientInfo
        server_state.client_name = client_info.name if client_info else "unknown"

        # Log client info
        logger.info("=" * 70)
        logger.info(f"UE-MCP SERVER INITIALIZED - Client: {server_state.client_name}")
        logger.info("=" * 70)

        # Call next middleware/handler
        result = await call_next(context)

        # Try to auto-detect project from current working directory
        manager = server_state.initialize_from_cwd()
        if manager:
            logger.info(f"Auto-detected project: {manager.project_name}")
        else:
            logger.info(
                f"No UE5 project detected. Client '{server_state.client_name}' "
                "needs to call project_set_path to set the project path."
            )

        return result

    async def on_list_tools(
        self,
        context: MiddlewareContext[mt.ListToolsRequest],
        call_next: CallNext[mt.ListToolsRequest, mt.InitializeResult | None],
    ) -> mt.InitializeResult | None:
        """Return full tool list - project_set_path is available for all clients."""
        return await call_next(context)

    async def on_call_tool(
        self,
        context: MiddlewareContext[mt.CallToolRequestParams],
        call_next: CallNext[mt.CallToolRequestParams, ToolResult],
    ) -> ToolResult:
        """Intercept tool results and convert images to base64 for Claude AI clients."""
        # Execute the tool first
        result = await call_next(context)

        # Check if we should process images for this client
        if not is_claude_ai_client(server_state.client_name):
            return result

        # Check if disabled via environment variable
        if os.environ.get("UE_MCP_DISABLE_BASE64_IMAGES"):
            return result

        # Process the result content for images
        return self._process_images_in_result(result)

    def _process_images_in_result(self, result: ToolResult) -> ToolResult:
        """Process tool result and add base64 images for Claude AI.

        This method:
        1. Finds text content in the result and parses it as JSON
        2. Scans for image paths in known fields
        3. Converts images to base64 and adds them as ImageContent blocks
        4. Adds an 'images' array to the JSON with metadata
        """
        if not result.content:
            return result

        # Find text content and parse as JSON
        text_content = None
        text_index = -1
        for i, block in enumerate(result.content):
            if isinstance(block, TextContent):
                text_content = block
                text_index = i
                break

        if text_content is None:
            return result

        try:
            data = json.loads(text_content.text)
        except json.JSONDecodeError:
            return result

        if not isinstance(data, dict):
            return result

        # Process for images
        processed_data, images = process_result_for_images(data)

        if not images:
            return result

        logger.info(
            f"Converting {len(images)} image(s) to base64 for Claude AI client"
        )

        # Add images array to the result data (metadata only, not the base64 data)
        processed_data["images"] = [
            {
                "path": img["path"],
                "mime_type": img["mime_type"],
                "size_bytes": img["size_bytes"],
                "source_field": img["source_field"],
            }
            for img in images
        ]

        # Build new content list
        new_content = list(result.content)
        new_content[text_index] = TextContent(
            type="text", text=json.dumps(processed_data)
        )

        # Add ImageContent blocks
        for img in images:
            new_content.append(
                ImageContent(
                    type="image",
                    data=img["data"],
                    mimeType=img["mime_type"],
                )
            )

        return ToolResult(content=new_content)


# Create FastMCP instance
mcp = FastMCP(
    name="ue-mcp",
    middleware=[ClientDetectionMiddleware()],
    instructions="""
UE-MCP is an MCP server for interacting with Unreal Editor.

**Project Initialization:**
- If started from a UE5 project directory, the server auto-detects and launches the editor
- If started from any other directory, use the 'project_set_path' tool to set your UE5 project directory
- The 'project_set_path' tool can be called multiple times - if an editor is running, it will be stopped first

Available tools:
- project_set_path: Set the UE5 project directory (stops running editor if switching projects)
- editor_launch: Start the Unreal Editor for the bound project
- editor_status: Get the current editor status (includes log_file_path)
- editor_read_log: Read the editor log file content
- editor_stop: Stop the running editor
- editor_execute_code: Execute Python code in the editor
- editor_execute_script: Execute a Python script file in the editor
- editor_configure: Check and fix project configuration
- editor_pip_install: Install Python packages in UE5's Python environment
- editor_start_pie: Start a Play-In-Editor (PIE) session
- editor_stop_pie: Stop the current Play-In-Editor (PIE) session
- editor_load_level: Load a level in the editor
- editor_capture_pie: Capture screenshots during Play-In-Editor session
- editor_trace_actors_in_pie: Trace actor transforms during PIE session
- editor_pie_execute_in_tick: Execute code at specific ticks during PIE
- editor_capture_window: Capture editor window screenshots (Windows only)
- editor_level_screenshot: Capture screenshots from custom camera positions looking at a target
- editor_asset_open: Open an asset in its editor (Blueprint Editor, Material Editor, etc.)
- editor_asset_diagnostic: Run diagnostics on a UE5 asset to detect common issues
- editor_asset_inspect: Inspect a UE5 asset and return all its properties
- project_build: Build the UE5 project using UnrealBuildTool (supports Editor, Game, etc.)
- python_api_search: Search UE5 Python APIs in the running editor
""",
)

# Register all tools from the tools package
register_all_tools(mcp, server_state)


def _cleanup_on_shutdown() -> None:
    """Clean up resources when the server is shutting down."""
    logger.info("Server shutdown requested, cleaning up...")
    server_state.cleanup()
    logger.info("Cleanup completed")


def _signal_handler(signum: int, frame) -> None:
    """Handle termination signals (SIGTERM, SIGINT)."""
    sig_name = signal.Signals(signum).name
    logger.info(f"Received signal {sig_name} ({signum})")
    _cleanup_on_shutdown()
    sys.exit(0)


def main():
    """Main entry point for the MCP server."""
    # Register signal handlers for graceful shutdown
    if sys.platform != "win32":
        # Unix-like systems: handle SIGTERM and SIGINT
        signal.signal(signal.SIGTERM, _signal_handler)
        signal.signal(signal.SIGINT, _signal_handler)
    else:
        # Windows: SIGTERM is not supported, only SIGINT (Ctrl+C)
        signal.signal(signal.SIGINT, _signal_handler)
        if hasattr(signal, "SIGBREAK"):
            signal.signal(signal.SIGBREAK, _signal_handler)

    logger.info("Starting UE-MCP server...")

    try:
        mcp.run()
    finally:
        # Fallback cleanup in case signals weren't caught
        _cleanup_on_shutdown()


if __name__ == "__main__":
    main()
