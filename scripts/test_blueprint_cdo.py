#!/usr/bin/env python3
"""
Test script for Blueprint CDO property inspection.

Uses Automatic-Testing client identity to access project_set_path tool.

Usage:
    uv run python scripts/test_blueprint_cdo.py
"""

import asyncio
import json
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import Implementation


async def run_test():
    """Run the Blueprint CDO inspection test."""
    project_root = Path(__file__).parent.parent
    project_path = project_root / "tests" / "fixtures" / "ThirdPersonTemplate"

    print(f"Project root: {project_root}")
    print(f"Test project: {project_path}")

    # Server parameters
    server_params = StdioServerParameters(
        command="uv",
        args=["run", "--project", str(project_root), "ue-mcp"],
    )

    print("\nStarting MCP server with Automatic-Testing identity...")

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(
            read, write,
            client_info=Implementation(name="Automatic-Testing", version="1.0.0")
        ) as session:
            # Initialize the session
            await session.initialize()
            print("Session initialized")

            # List available tools
            tools_result = await session.list_tools()
            tool_names = [tool.name for tool in tools_result.tools]
            print(f"Available tools: {sorted(tool_names)}")

            # Check if project_set_path is available
            if "project_set_path" not in tool_names:
                print("ERROR: project_set_path tool not found!")
                print("Make sure MCP_CLIENT_NAME is set to 'Automatic-Testing'")
                return

            # Set project path
            print(f"\n[Step 1] Setting project path to: {project_path}")
            set_path_result = await session.call_tool(
                "project_set_path",
                {"project_path": str(project_path)},
            )
            set_path_text = set_path_result.content[0].text if set_path_result.content else ""
            print(f"Result: {set_path_text}")

            # Launch editor
            print("\n[Step 2] Launching editor (this may take a few minutes)...")
            launch_result = await session.call_tool(
                "editor_launch",
                {"wait": True, "wait_timeout": 300},
            )
            launch_text = launch_result.content[0].text if launch_result.content else ""
            try:
                launch_data = json.loads(launch_text)
                if launch_data.get("success"):
                    print("Editor launched successfully!")
                else:
                    print(f"Editor launch result: {launch_data}")
                    if "already" not in str(launch_data.get("error", "")).lower():
                        return
            except json.JSONDecodeError:
                print(f"Launch response: {launch_text}")

            try:
                # Test 1: Inspect a non-Blueprint asset (StaticMesh)
                print("\n" + "=" * 60)
                print("[Test 1] Inspecting non-Blueprint: /Engine/BasicShapes/Cube")
                print("=" * 60)
                cube_result = await session.call_tool(
                    "editor_asset_inspect",
                    {"asset_path": "/Engine/BasicShapes/Cube"},
                )
                cube_text = cube_result.content[0].text if cube_result.content else ""
                try:
                    cube_data = json.loads(cube_text)
                    if cube_data.get("success"):
                        print(f"  Asset type: {cube_data.get('asset_type')}")
                        print(f"  Asset class: {cube_data.get('asset_class')}")
                        print(f"  Is Blueprint: {cube_data.get('is_blueprint')}")
                        print(f"  Property count: {cube_data.get('property_count')}")
                    else:
                        print(f"  Error: {cube_data.get('error')}")
                except json.JSONDecodeError:
                    print(f"  Response: {cube_text}")

                # Test 2: Inspect BP_ThirdPersonCharacter
                print("\n" + "=" * 60)
                print("[Test 2] Inspecting Blueprint: BP_ThirdPersonCharacter")
                print("=" * 60)
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
                        print(f"  Blueprint property count: {bp_data.get('blueprint_property_count', 'N/A')}")
                        print(f"  CDO property count: {bp_data.get('cdo_property_count', 'N/A')}")

                        if bp_data.get("cdo_error"):
                            print(f"  CDO Error: {bp_data.get('cdo_error')}")

                        # Show CDO properties sample
                        cdo_props = bp_data.get("cdo_properties", {})
                        if cdo_props:
                            print(f"\n  CDO properties sample (first 15):")
                            for key, value in list(cdo_props.items())[:15]:
                                value_str = str(value)[:60] + "..." if len(str(value)) > 60 else str(value)
                                print(f"    {key}: {value_str}")

                        # Show Blueprint properties sample
                        bp_props = bp_data.get("blueprint_properties", {})
                        if bp_props:
                            print(f"\n  Blueprint properties sample (first 5):")
                            for key, value in list(bp_props.items())[:5]:
                                value_str = str(value)[:60] + "..." if len(str(value)) > 60 else str(value)
                                print(f"    {key}: {value_str}")
                    else:
                        print(f"  Error: {bp_data.get('error')}")
                except json.JSONDecodeError:
                    print(f"  Response: {bp_text}")

                # Test 3: Inspect BP_ThirdPersonGameMode
                print("\n" + "=" * 60)
                print("[Test 3] Inspecting Blueprint: BP_ThirdPersonGameMode")
                print("=" * 60)
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
                        print(f"  CDO property count: {gm_data.get('cdo_property_count', 'N/A')}")

                        # Show some GameMode-specific CDO properties
                        cdo_props = gm_data.get("cdo_properties", {})
                        if cdo_props:
                            print(f"\n  CDO properties sample:")
                            # Look for GameMode-specific properties
                            gm_keys = ["default_pawn_class", "player_controller_class",
                                       "game_state_class", "hud_class", "spectator_class"]
                            for key in gm_keys:
                                if key in cdo_props:
                                    print(f"    {key}: {cdo_props[key]}")
                    else:
                        print(f"  Error: {gm_data.get('error')}")
                except json.JSONDecodeError:
                    print(f"  Response: {gm_text}")

            finally:
                # Stop the editor
                print("\n[Cleanup] Stopping editor...")
                await session.call_tool("editor_stop", {})
                print("Editor stopped")

    print("\n" + "=" * 60)
    print("Blueprint CDO test completed!")
    print("=" * 60)


def main():
    """Main entry point."""
    asyncio.run(run_test())


if __name__ == "__main__":
    main()
