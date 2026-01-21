#!/usr/bin/env python3
"""
Test script for Blueprint component inspection feature.

Tests the enhanced editor_asset_inspect MCP tool with component_name parameter.

Usage:
    # From project root, with ThirdPersonTemplate project:
    uv run python scripts/test_component_inspect.py tests/fixtures/ThirdPersonTemplate
"""

import asyncio
import json
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def run_test(project_path: str | None = None):
    """Run the component inspect test."""
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
            print("Testing Blueprint Component Inspection")
            print("=" * 60)

            # Launch editor
            print("\n[Setup] Launching editor...")
            launch_result = await session.call_tool(
                "editor_launch",
                {"wait": True, "wait_timeout": 300},
            )
            launch_text = launch_result.content[0].text if launch_result.content else ""
            try:
                launch_data = json.loads(launch_text)
                if launch_data.get("success"):
                    print("Editor launched successfully!")
                elif "already running" in launch_data.get("error", "").lower():
                    print("Editor already starting, waiting...")
                    for i in range(60):
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
                # Test 1: Inspect Blueprint without component_name (should list components)
                print("\n" + "-" * 60)
                print("[Test 1] Inspect BP_ThirdPersonCharacter (list components)")
                print("-" * 60)

                result = await session.call_tool(
                    "editor_asset_inspect",
                    {"asset_path": "/Game/ThirdPerson/Blueprints/BP_ThirdPersonCharacter"},
                )
                result_text = result.content[0].text if result.content else ""
                try:
                    data = json.loads(result_text)
                    if data.get("success"):
                        print(f"  Asset type: {data.get('asset_type')}")
                        print(f"  Asset class: {data.get('asset_class')}")

                        components = data.get("components", [])
                        print(f"\n  Components found: {len(components)}")
                        for comp in components:
                            parent = comp.get("parent", "None")
                            children = comp.get("children", [])
                            print(f"    - {comp['name']} ({comp['class']})")
                            print(f"      Parent: {parent}, Children: {children}")
                    else:
                        print(f"  ERROR: {data.get('error')}")
                except json.JSONDecodeError:
                    print(f"  Response: {result_text}")

                # Test 2: Inspect a specific component
                print("\n" + "-" * 60)
                print("[Test 2] Inspect specific component (CapsuleComponent)")
                print("-" * 60)

                # First get the component list to find the exact name
                component_name = None
                if data.get("success") and data.get("components"):
                    # Find a CapsuleComponent
                    for comp in data["components"]:
                        if "Capsule" in comp.get("class", ""):
                            component_name = comp["name"]
                            break

                    # Fallback: use first component
                    if not component_name and data["components"]:
                        component_name = data["components"][0]["name"]

                if component_name:
                    print(f"  Inspecting component: {component_name}")
                    result2 = await session.call_tool(
                        "editor_asset_inspect",
                        {
                            "asset_path": "/Game/ThirdPerson/Blueprints/BP_ThirdPersonCharacter",
                            "component_name": component_name,
                        },
                    )
                    result2_text = result2.content[0].text if result2.content else ""
                    try:
                        data2 = json.loads(result2_text)
                        if data2.get("success"):
                            comp_info = data2.get("component_info", {})
                            print(f"  Component name: {comp_info.get('name')}")
                            print(f"  Component class: {comp_info.get('class')}")
                            print(f"  Parent: {comp_info.get('parent')}")
                            print(f"  Children: {comp_info.get('children')}")
                            print(f"  Property count: {comp_info.get('property_count')}")

                            props = comp_info.get("properties", {})
                            print(f"\n  Sample properties (first 10):")
                            for i, (key, value) in enumerate(list(props.items())[:10]):
                                print(f"    {key}: {value}")
                        else:
                            print(f"  ERROR: {data2.get('error')}")
                            if "available_components" in data2:
                                print(f"  Available: {data2['available_components']}")
                    except json.JSONDecodeError:
                        print(f"  Response: {result2_text}")
                else:
                    print("  SKIP: No component name found")

                # Test 3: Test invalid component name
                print("\n" + "-" * 60)
                print("[Test 3] Test invalid component name (should show available)")
                print("-" * 60)

                result3 = await session.call_tool(
                    "editor_asset_inspect",
                    {
                        "asset_path": "/Game/ThirdPerson/Blueprints/BP_ThirdPersonCharacter",
                        "component_name": "InvalidComponentName123",
                    },
                )
                result3_text = result3.content[0].text if result3.content else ""
                try:
                    data3 = json.loads(result3_text)
                    if data3.get("success"):
                        print("  UNEXPECTED: Should have failed")
                    else:
                        print(f"  Expected error: {data3.get('error')}")
                        if "available_components" in data3:
                            print(f"  Available components: {data3['available_components'][:5]}...")
                except json.JSONDecodeError:
                    print(f"  Response: {result3_text}")

                # Test 4: Test non-Blueprint asset (should work as before)
                print("\n" + "-" * 60)
                print("[Test 4] Test non-Blueprint asset (StaticMesh)")
                print("-" * 60)

                result4 = await session.call_tool(
                    "editor_asset_inspect",
                    {"asset_path": "/Engine/BasicShapes/Cube"},
                )
                result4_text = result4.content[0].text if result4.content else ""
                try:
                    data4 = json.loads(result4_text)
                    if data4.get("success"):
                        print(f"  Asset type: {data4.get('asset_type')}")
                        print(f"  Asset class: {data4.get('asset_class')}")
                        print(f"  Property count: {data4.get('property_count')}")
                        print(f"  Has 'components' key: {'components' in data4}")
                        print(f"  Has 'properties' key: {'properties' in data4}")
                    else:
                        print(f"  ERROR: {data4.get('error')}")
                except json.JSONDecodeError:
                    print(f"  Response: {result4_text}")

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
