#!/usr/bin/env python3
"""
Simple standalone script to test the editor_asset_inspect MCP tool.

Uses the MCP SDK's ClientSession to connect to the UE-MCP server directly.

Usage:
    # From project root, with UE5 project in current directory:
    uv run python scripts/test_asset_inspect.py

    # Or specify a UE5 project path:
    uv run python scripts/test_asset_inspect.py D:/Code/MyProject

Requirements:
    - UE5 installed
    - A valid UE5 project
    - The ue-mcp package installed
"""

import asyncio
import json
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def run_test(project_path: str | None = None):
    """Run the asset inspect test."""
    # Determine working directory
    if project_path:
        cwd = Path(project_path)
    else:
        cwd = Path.cwd()

    print(f"Working directory: {cwd}")

    # Server parameters - launch ue-mcp via uv
    project_root = Path(__file__).parent.parent
    server_params = StdioServerParameters(
        command="uv",
        args=["run", "--project", str(project_root), "ue-mcp"],
        cwd=str(cwd),
    )

    print("Starting MCP server...")

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            # Initialize the session
            await session.initialize()
            print("Session initialized")

            # List available tools
            tools_result = await session.list_tools()
            tool_names = [tool.name for tool in tools_result.tools]
            print(f"Available tools: {sorted(tool_names)}")

            # Check if our tool is available
            if "editor_asset_inspect" not in tool_names:
                print("ERROR: editor_asset_inspect tool not found!")
                return

            print("\n" + "=" * 60)
            print("Testing editor_asset_inspect tool")
            print("=" * 60)

            # Test 1: Check editor status first
            print("\n[Test 1] Checking editor status...")
            status_result = await session.call_tool("editor_status", {})
            status_text = status_result.content[0].text if status_result.content else ""
            try:
                status_data = json.loads(status_text)
                print(f"Editor status: {status_data.get('status', 'unknown')}")
            except json.JSONDecodeError:
                print(f"Status response: {status_text}")

            # Test 2: Launch editor if not running
            print("\n[Test 2] Launching editor (this may take a few minutes)...")
            launch_result = await session.call_tool(
                "editor_launch",
                {"wait": True, "wait_timeout": 300},  # 5 minutes timeout
            )
            launch_text = launch_result.content[0].text if launch_result.content else ""
            try:
                launch_data = json.loads(launch_text)
                if launch_data.get("success"):
                    print("Editor launched successfully!")
                elif "already running" in launch_data.get("error", "").lower():
                    # Wait a bit for the editor to connect
                    print("Editor already starting, waiting for it to be ready...")
                    import asyncio
                    for i in range(60):  # Wait up to 60 seconds
                        await asyncio.sleep(2)
                        status_result = await session.call_tool("editor_status", {})
                        status_text = status_result.content[0].text if status_result.content else ""
                        try:
                            status_data = json.loads(status_text)
                            if status_data.get("status") == "ready":
                                print("Editor is ready!")
                                break
                            print(f"  Status: {status_data.get('status', 'unknown')} ({i*2}s)")
                        except json.JSONDecodeError:
                            pass
                    else:
                        print("Warning: Editor may not be fully ready")
                else:
                    print(f"Editor launch failed: {launch_data.get('error')}")
                    return
            except json.JSONDecodeError:
                print(f"Launch response: {launch_text}")
                return

            try:
                # Test 3: Inspect a built-in engine asset
                print("\n[Test 3] Inspecting /Engine/BasicShapes/Cube...")
                inspect_result = await session.call_tool(
                    "editor_asset_inspect",
                    {"asset_path": "/Engine/BasicShapes/Cube"},
                )
                inspect_text = inspect_result.content[0].text if inspect_result.content else ""
                try:
                    data = json.loads(inspect_text)
                    if data.get("success"):
                        print(f"  Asset path: {data.get('asset_path')}")
                        print(f"  Asset type: {data.get('asset_type')}")
                        print(f"  Asset class: {data.get('asset_class')}")
                        print(f"  Property count: {data.get('property_count')}")
                        print(f"  Metadata: {json.dumps(data.get('metadata', {}), indent=4)}")

                        # Print first few properties
                        props = data.get("properties", {})
                        print(f"\n  Sample properties (first 10):")
                        for i, (key, value) in enumerate(list(props.items())[:10]):
                            print(f"    {key}: {value}")
                    else:
                        print(f"  Inspect failed: {data.get('error')}")
                except json.JSONDecodeError:
                    print(f"  Response: {inspect_text}")

                # Test 4: Try to inspect a Blueprint asset (BP_ThirdPersonCharacter)
                print("\n[Test 4] Inspecting Blueprint: /Game/ThirdPerson/Blueprints/BP_ThirdPersonCharacter...")
                bp_result = await session.call_tool(
                    "editor_asset_inspect",
                    {"asset_path": "/Game/ThirdPerson/Blueprints/BP_ThirdPersonCharacter"},
                )
                bp_text = bp_result.content[0].text if bp_result.content else ""
                try:
                    bp_data = json.loads(bp_text)
                    if bp_data.get("success"):
                        print(f"  Asset type: {bp_data.get('asset_type')}")
                        print(f"  Asset class: {bp_data.get('asset_class')}")
                        print(f"  Is Blueprint: {bp_data.get('is_blueprint')}")
                        print(f"  Generated class: {bp_data.get('generated_class_name')}")
                        print(f"  CDO class: {bp_data.get('cdo_class')}")
                        print(f"  Blueprint property count: {bp_data.get('blueprint_property_count', 0)}")
                        print(f"  CDO property count: {bp_data.get('cdo_property_count', 0)}")

                        # Show CDO error if any
                        if bp_data.get("cdo_error"):
                            print(f"  CDO Error: {bp_data.get('cdo_error')}")

                        # Print first few CDO properties
                        cdo_props = bp_data.get("cdo_properties", {})
                        if cdo_props:
                            print(f"\n  Sample CDO properties (first 10):")
                            for i, (key, value) in enumerate(list(cdo_props.items())[:10]):
                                print(f"    {key}: {value}")
                        else:
                            print("\n  No CDO properties available")

                        # Print first few Blueprint properties
                        bp_props = bp_data.get("blueprint_properties", {})
                        if bp_props:
                            print(f"\n  Sample Blueprint properties (first 5):")
                            for i, (key, value) in enumerate(list(bp_props.items())[:5]):
                                print(f"    {key}: {value}")
                    else:
                        print(f"  Result: {bp_data.get('error', 'Asset may not exist')}")
                except json.JSONDecodeError:
                    print(f"  Response: {bp_text}")

                # Test 5: Try to inspect another Blueprint (GameMode)
                print("\n[Test 5] Inspecting Blueprint: /Game/ThirdPerson/Blueprints/BP_ThirdPersonGameMode...")
                gm_result = await session.call_tool(
                    "editor_asset_inspect",
                    {"asset_path": "/Game/ThirdPerson/Blueprints/BP_ThirdPersonGameMode"},
                )
                gm_text = gm_result.content[0].text if gm_result.content else ""
                try:
                    gm_data = json.loads(gm_text)
                    if gm_data.get("success"):
                        print(f"  Is Blueprint: {gm_data.get('is_blueprint')}")
                        print(f"  Generated class: {gm_data.get('generated_class_name')}")
                        print(f"  CDO class: {gm_data.get('cdo_class')}")
                        print(f"  CDO property count: {gm_data.get('cdo_property_count', 0)}")
                    else:
                        print(f"  Result: {gm_data.get('error', 'Asset may not exist')}")
                except json.JSONDecodeError:
                    print(f"  Response: {gm_text}")

            finally:
                # Always stop the editor
                print("\n[Cleanup] Stopping editor...")
                await session.call_tool("editor_stop", {})
                print("Editor stopped")

    print("\n" + "=" * 60)
    print("Test completed!")
    print("=" * 60)


def main():
    """Main entry point."""
    project_path = sys.argv[1] if len(sys.argv) > 1 else None
    asyncio.run(run_test(project_path))


if __name__ == "__main__":
    main()
