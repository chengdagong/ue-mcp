#!/usr/bin/env python3
"""
Standalone test script for ExSlateTabLibrary API.

This script tests the Slate UI tab switching functionality without pytest.
It connects to the MCP server and runs a series of tests.

Usage:
    python tests/test_slate_tab_api_standalone.py

Requirements:
    - UE-MCP package installed (uv run ue-mcp)
    - ThirdPersonTemplate project in tests/fixtures/
"""

import asyncio
import json
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import Implementation


# =============================================================================
# Configuration
# =============================================================================

THIRDPERSON_PROJECT_PATH = Path(__file__).parent / "fixtures" / "ThirdPersonTemplate"
BLUEPRINT_PATH = "/Game/ThirdPerson/Blueprints/BP_ThirdPersonCharacter"


# =============================================================================
# Helper Functions
# =============================================================================


def parse_result(result) -> dict:
    """Parse MCP tool result."""
    if result.content and len(result.content) > 0:
        text = result.content[0].text
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"raw_text": text}
    return {"error": "No content"}


async def call_tool(session: ClientSession, name: str, args: dict = None, timeout: int = 120) -> dict:
    """Call an MCP tool and return parsed result."""
    args = args or {}
    print(f"\n>>> Calling: {name}({args})")

    try:
        result = await asyncio.wait_for(
            session.call_tool(name, args),
            timeout=timeout
        )
        data = parse_result(result)
        print(f"<<< Result: {json.dumps(data, indent=2, default=str)[:500]}")
        return data
    except asyncio.TimeoutError:
        print(f"<<< TIMEOUT after {timeout}s")
        return {"error": "timeout"}
    except Exception as e:
        print(f"<<< ERROR: {e}")
        return {"error": str(e)}


# =============================================================================
# Test Functions
# =============================================================================


async def test_check_library_available(session: ClientSession) -> bool:
    """Test 1: Check if ExSlateTabLibrary is available."""
    print("\n" + "=" * 60)
    print("TEST 1: Check ExSlateTabLibrary availability")
    print("=" * 60)

    code = """
import unreal

try:
    lib = unreal.ExSlateTabLibrary
    methods = [m for m in dir(lib) if not m.startswith('_')]
    print(f"ExSlateTabLibrary available with methods: {methods}")
    result = {"available": True, "methods": methods}
except AttributeError as e:
    print(f"ExSlateTabLibrary NOT available: {e}")
    result = {"available": False, "error": str(e)}

print(f"RESULT_JSON: {result}")
"""
    data = await call_tool(session, "editor_execute_code", {"code": code})

    output = data.get("output", [])
    output_text = "\n".join(output) if isinstance(output, list) else str(output)

    if "ExSlateTabLibrary available" in output_text:
        print("PASS: ExSlateTabLibrary is available")
        return True
    else:
        print("FAIL: ExSlateTabLibrary not available")
        print(f"Output: {output_text}")
        return False


async def test_get_tab_ids(session: ClientSession) -> bool:
    """Test 2: Get Blueprint Editor tab IDs."""
    print("\n" + "=" * 60)
    print("TEST 2: Get Blueprint Editor Tab IDs")
    print("=" * 60)

    code = """
import unreal

tab_ids = unreal.ExSlateTabLibrary.get_blueprint_editor_tab_ids()
tabs_list = [str(t) for t in tab_ids]
print(f"Found {len(tabs_list)} tabs: {tabs_list}")

expected = ["SCSViewport", "GraphEditor", "Inspector", "MyBlueprint"]
found = [e for e in expected if e in tabs_list]
print(f"Expected tabs found: {found}")
"""
    data = await call_tool(session, "editor_execute_code", {"code": code})

    output = data.get("output", [])
    output_text = "\n".join(output) if isinstance(output, list) else str(output)

    if "SCSViewport" in output_text and "GraphEditor" in output_text:
        print("PASS: Got expected tab IDs")
        return True
    else:
        print("FAIL: Missing expected tab IDs")
        return False


async def test_open_blueprint_editor(session: ClientSession) -> bool:
    """Test 3: Open Blueprint in editor."""
    print("\n" + "=" * 60)
    print("TEST 3: Open Blueprint Editor")
    print("=" * 60)

    code = f"""
import unreal

blueprint = unreal.load_asset("{BLUEPRINT_PATH}")
if blueprint:
    print(f"Loaded: {{blueprint.get_name()}}")

    # Get the AssetEditorSubsystem
    subsystem = unreal.get_editor_subsystem(unreal.AssetEditorSubsystem)
    if subsystem:
        subsystem.open_editor_for_asset(blueprint)
        print("Opened Blueprint editor")
        result = True
    else:
        print("Failed to get AssetEditorSubsystem")
        result = False
else:
    print("Failed to load Blueprint")
    result = False

print(f"SUCCESS: {{result}}")
"""
    data = await call_tool(session, "editor_execute_code", {"code": code})

    output = data.get("output", [])
    output_text = "\n".join(output) if isinstance(output, list) else str(output)

    if "Opened Blueprint editor" in output_text:
        print("PASS: Blueprint editor opened")
        return True
    else:
        print("FAIL: Could not open Blueprint editor")
        return False


async def test_switch_to_viewport(session: ClientSession) -> bool:
    """Test 4: Switch to Viewport mode."""
    print("\n" + "=" * 60)
    print("TEST 4: Switch to Viewport Mode")
    print("=" * 60)

    # Wait for editor to fully open
    await asyncio.sleep(2)

    code = f"""
import unreal

blueprint = unreal.load_asset("{BLUEPRINT_PATH}")
if blueprint:
    success = unreal.ExSlateTabLibrary.switch_to_viewport_mode(blueprint)
    print(f"Switch to Viewport: {{success}}")
else:
    print("Blueprint not loaded")
    success = False
"""
    data = await call_tool(session, "editor_execute_code", {"code": code})

    output = data.get("output", [])
    output_text = "\n".join(output) if isinstance(output, list) else str(output)

    if "Switch to Viewport: True" in output_text:
        print("PASS: Switched to Viewport mode")
        return True
    else:
        print("FAIL: Could not switch to Viewport mode")
        return False


async def test_switch_to_graph(session: ClientSession) -> bool:
    """Test 5: Switch to Graph mode."""
    print("\n" + "=" * 60)
    print("TEST 5: Switch to Graph Mode")
    print("=" * 60)

    await asyncio.sleep(1)

    code = f"""
import unreal

blueprint = unreal.load_asset("{BLUEPRINT_PATH}")
if blueprint:
    success = unreal.ExSlateTabLibrary.switch_to_graph_mode(blueprint)
    print(f"Switch to Graph: {{success}}")
else:
    print("Blueprint not loaded")
    success = False
"""
    data = await call_tool(session, "editor_execute_code", {"code": code})

    output = data.get("output", [])
    output_text = "\n".join(output) if isinstance(output, list) else str(output)

    if "Switch to Graph: True" in output_text:
        print("PASS: Switched to Graph mode")
        return True
    else:
        print("FAIL: Could not switch to Graph mode")
        return False


async def test_focus_panels(session: ClientSession) -> bool:
    """Test 6: Focus Details and MyBlueprint panels."""
    print("\n" + "=" * 60)
    print("TEST 6: Focus Panels")
    print("=" * 60)

    await asyncio.sleep(1)

    code = f"""
import unreal

blueprint = unreal.load_asset("{BLUEPRINT_PATH}")
if blueprint:
    details = unreal.ExSlateTabLibrary.focus_details_panel(blueprint)
    print(f"Focus Details: {{details}}")

    myblueprint = unreal.ExSlateTabLibrary.focus_my_blueprint_panel(blueprint)
    print(f"Focus MyBlueprint: {{myblueprint}}")
else:
    print("Blueprint not loaded")
"""
    data = await call_tool(session, "editor_execute_code", {"code": code})

    output = data.get("output", [])
    output_text = "\n".join(output) if isinstance(output, list) else str(output)

    if "True" in output_text:
        print("PASS: At least one panel focused")
        return True
    else:
        print("FAIL: Could not focus panels")
        return False


async def test_is_editor_open(session: ClientSession) -> bool:
    """Test 7: Check if editor is open."""
    print("\n" + "=" * 60)
    print("TEST 7: Check Editor Open Status")
    print("=" * 60)

    code = f"""
import unreal

blueprint = unreal.load_asset("{BLUEPRINT_PATH}")
if blueprint:
    is_open = unreal.ExSlateTabLibrary.is_asset_editor_open(blueprint)
    print(f"Editor is open: {{is_open}}")
else:
    print("Blueprint not loaded")
    is_open = False
"""
    data = await call_tool(session, "editor_execute_code", {"code": code})

    output = data.get("output", [])
    output_text = "\n".join(output) if isinstance(output, list) else str(output)

    if "Editor is open: True" in output_text:
        print("PASS: Editor reported as open")
        return True
    else:
        print("FAIL: Editor not reported as open")
        return False


async def test_invoke_tab_by_id(session: ClientSession) -> bool:
    """Test 8: Invoke specific tabs by ID."""
    print("\n" + "=" * 60)
    print("TEST 8: Invoke Tabs by ID")
    print("=" * 60)

    code = f"""
import unreal

blueprint = unreal.load_asset("{BLUEPRINT_PATH}")
if blueprint:
    # Test invoking various tabs
    tabs_to_test = ["Inspector", "SCSViewport", "GraphEditor", "MyBlueprint"]
    results = {{}}

    for tab_id in tabs_to_test:
        success = unreal.ExSlateTabLibrary.invoke_blueprint_editor_tab(
            blueprint, unreal.Name(tab_id)
        )
        results[tab_id] = success
        print(f"Invoke {{tab_id}}: {{success}}")

    print(f"Results: {{results}}")
else:
    print("Blueprint not loaded")
"""
    data = await call_tool(session, "editor_execute_code", {"code": code})

    output = data.get("output", [])
    output_text = "\n".join(output) if isinstance(output, list) else str(output)

    # Count successes
    success_count = output_text.count(": True")

    if success_count >= 2:
        print(f"PASS: {success_count} tabs invoked successfully")
        return True
    else:
        print(f"FAIL: Only {success_count} tabs invoked")
        return False


# =============================================================================
# Main
# =============================================================================


async def run_tests():
    """Run all tests."""
    print("=" * 60)
    print("ExSlateTabLibrary API Test Suite")
    print("=" * 60)
    print(f"Project: {THIRDPERSON_PROJECT_PATH}")
    print(f"Blueprint: {BLUEPRINT_PATH}")

    # Check project exists
    if not THIRDPERSON_PROJECT_PATH.exists():
        print(f"ERROR: Project not found at {THIRDPERSON_PROJECT_PATH}")
        return 1

    uproject = THIRDPERSON_PROJECT_PATH / "thirdperson_template.uproject"
    if not uproject.exists():
        print(f"ERROR: .uproject not found at {uproject}")
        return 1

    # Setup MCP server parameters
    server_params = StdioServerParameters(
        command="uv",
        args=["run", "--project", str(PROJECT_ROOT), "ue-mcp"],
        cwd=str(THIRDPERSON_PROJECT_PATH),
    )

    results = []

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(
            read, write,
            client_info=Implementation(name="Automatic-Testing", version="1.0.0")
        ) as session:
            await session.initialize()
            print("\nMCP session initialized")

            # Set project path
            print("\n>>> Setting project path...")
            data = await call_tool(
                session,
                "project_set_path",
                {"project_path": str(THIRDPERSON_PROJECT_PATH)},
                timeout=30
            )
            if not data.get("success"):
                print(f"ERROR: Failed to set project path: {data}")
                return 1

            # Launch editor (may require build if plugin was just installed)
            print("\n>>> Launching editor (this may take a few minutes)...")
            data = await call_tool(
                session,
                "editor_launch",
                {"wait": True, "wait_timeout": 300},
                timeout=360
            )

            # Check if build is required (ExtraPythonAPIs plugin was installed)
            if not data.get("success") and data.get("requires_build"):
                print("\n>>> ExtraPythonAPIs plugin installed, building project first...")
                build_data = await call_tool(
                    session,
                    "project_build",
                    {"target": "Editor", "wait": True},
                    timeout=600  # Build can take a while
                )
                if not build_data.get("success"):
                    print(f"ERROR: Failed to build project: {build_data}")
                    return 1

                print("Build completed, launching editor again...")
                data = await call_tool(
                    session,
                    "editor_launch",
                    {"wait": True, "wait_timeout": 300},
                    timeout=360
                )

            if not data.get("success"):
                print(f"ERROR: Failed to launch editor: {data}")
                return 1

            print("\nEditor launched successfully!")
            await asyncio.sleep(5)  # Wait for editor to fully initialize

            # Run tests
            tests = [
                ("Check Library Available", test_check_library_available),
                ("Get Tab IDs", test_get_tab_ids),
                ("Open Blueprint Editor", test_open_blueprint_editor),
                ("Switch to Viewport", test_switch_to_viewport),
                ("Switch to Graph", test_switch_to_graph),
                ("Focus Panels", test_focus_panels),
                ("Is Editor Open", test_is_editor_open),
                ("Invoke Tab by ID", test_invoke_tab_by_id),
            ]

            for name, test_func in tests:
                try:
                    passed = await test_func(session)
                    results.append((name, passed))
                except Exception as e:
                    print(f"ERROR in {name}: {e}")
                    results.append((name, False))

            # Stop editor
            print("\n>>> Stopping editor...")
            await call_tool(session, "editor_stop", {}, timeout=60)

    # Print summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    passed = sum(1 for _, p in results if p)
    total = len(results)

    for name, result in results:
        status = "PASS" if result else "FAIL"
        print(f"  [{status}] {name}")

    print(f"\nTotal: {passed}/{total} tests passed")

    return 0 if passed == total else 1


if __name__ == "__main__":
    exit_code = asyncio.run(run_tests())
    sys.exit(exit_code)
