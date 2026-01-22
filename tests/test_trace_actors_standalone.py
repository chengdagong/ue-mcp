#!/usr/bin/env python3
"""
Standalone test script for editor_trace_actors_in_pie MCP tool.

This script tests the actor transform tracing functionality without pytest.
It connects to the MCP server, runs PIE, traces actors, and validates output.

Usage:
    python tests/test_trace_actors_standalone.py

Requirements:
    - UE-MCP package installed (uv run ue-mcp)
    - ThirdPersonTemplate project in tests/fixtures/
"""

import asyncio
import json
import os
import sys
import tempfile
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
TEST_LEVEL = "/Game/ThirdPerson/Maps/ThirdPersonMap"

# Actor names to test (ThirdPersonTemplate defaults)
TEST_ACTORS = {
    "player": "BP_ThirdPersonCharacter",  # Player character (has velocity)
    "static": "Floor",                     # Static mesh (no velocity)
    "nonexistent": "NonExistentActor_12345",  # Should not be found
}


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
    print(f"\n>>> Calling: {name}")
    if args:
        # Print args but truncate long values
        display_args = {}
        for k, v in args.items():
            if isinstance(v, str) and len(v) > 60:
                display_args[k] = v[:60] + "..."
            else:
                display_args[k] = v
        print(f"    Args: {display_args}")

    try:
        result = await asyncio.wait_for(
            session.call_tool(name, args),
            timeout=timeout
        )
        data = parse_result(result)
        # Truncate output for display
        display = json.dumps(data, indent=2, default=str)
        if len(display) > 800:
            display = display[:800] + "\n    ... (truncated)"
        print(f"<<< Result: {display}")
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


async def test_tool_registered(session: ClientSession) -> bool:
    """Test 1: Verify editor_trace_actors_in_pie tool is registered."""
    print("\n" + "=" * 60)
    print("TEST 1: Verify Tool Registration")
    print("=" * 60)

    tools = await session.list_tools()
    tool_names = [t.name for t in tools.tools]

    if "editor_trace_actors_in_pie" in tool_names:
        print("PASS: editor_trace_actors_in_pie is registered")
        return True
    else:
        print(f"FAIL: Tool not found in: {tool_names}")
        return False


async def test_trace_single_actor(session: ClientSession) -> bool:
    """Test 2: Trace a single actor (player character)."""
    print("\n" + "=" * 60)
    print("TEST 2: Trace Single Actor (Player Character)")
    print("=" * 60)

    # Create temp output file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        output_file = f.name

    try:
        data = await call_tool(
            session,
            "editor_trace_actors_in_pie",
            {
                "output_file": output_file,
                "level": TEST_LEVEL,
                "actor_names": [TEST_ACTORS["player"]],
                "duration_seconds": 3.0,
                "interval_seconds": 0.1,
            },
            timeout=120
        )

        # Check result
        if not data.get("success"):
            print(f"FAIL: Trace failed: {data.get('error', data)}")
            return False

        sample_count = data.get("sample_count", 0)
        actor_count = data.get("actor_count", 0)
        duration = data.get("duration", 0)

        print(f"\n  Results:")
        print(f"    - Samples: {sample_count}")
        print(f"    - Actors tracked: {actor_count}")
        print(f"    - Duration: {duration:.2f}s")

        # Validate sample count (should be approximately duration / interval)
        # Note: Actual rate is limited by editor frame rate and PIE startup time
        expected_samples = 3.0 / 0.1  # 30 samples
        if sample_count < expected_samples * 0.5:  # Allow 50% tolerance for frame rate variations
            print(f"FAIL: Too few samples ({sample_count} < {expected_samples * 0.5})")
            return False

        if actor_count < 1:
            print("FAIL: No actors tracked")
            return False

        # Verify output file exists and has valid JSON
        if not os.path.exists(output_file):
            print(f"FAIL: Output file not created: {output_file}")
            return False

        with open(output_file, 'r', encoding='utf-8') as f:
            trace_data = json.load(f)

        # Validate structure
        if "actors" not in trace_data:
            print("FAIL: Missing 'actors' key in output")
            return False

        if "metadata" not in trace_data:
            print("FAIL: Missing 'metadata' key in output")
            return False

        # Check actor data
        actor_name = TEST_ACTORS["player"]
        if actor_name not in trace_data["actors"]:
            # Try partial match (actor name might be slightly different)
            found_actor = None
            for name in trace_data["actors"].keys():
                if TEST_ACTORS["player"].lower() in name.lower():
                    found_actor = name
                    break
            if not found_actor:
                print(f"FAIL: Actor '{actor_name}' not in output data")
                print(f"  Found actors: {list(trace_data['actors'].keys())}")
                return False
            actor_name = found_actor

        samples = trace_data["actors"][actor_name]
        if len(samples) == 0:
            print("FAIL: No samples in actor data")
            return False

        # Validate sample structure
        sample = samples[0]
        required_fields = ["timestamp", "location", "rotation"]
        for field in required_fields:
            if field not in sample:
                print(f"FAIL: Missing '{field}' in sample")
                return False

        # Validate location structure
        loc = sample["location"]
        if not all(k in loc for k in ["x", "y", "z"]):
            print("FAIL: Invalid location structure")
            return False

        # Validate rotation structure
        rot = sample["rotation"]
        if not all(k in rot for k in ["pitch", "yaw", "roll"]):
            print("FAIL: Invalid rotation structure")
            return False

        print("\n  Sample data (first sample):")
        print(f"    - Location: ({loc['x']:.1f}, {loc['y']:.1f}, {loc['z']:.1f})")
        print(f"    - Rotation: (pitch={rot['pitch']:.1f}, yaw={rot['yaw']:.1f}, roll={rot['roll']:.1f})")
        if sample.get("velocity"):
            vel = sample["velocity"]
            print(f"    - Velocity: ({vel['x']:.1f}, {vel['y']:.1f}, {vel['z']:.1f})")
        else:
            print("    - Velocity: None")

        print("\nPASS: Single actor trace successful")
        return True

    finally:
        # Cleanup
        if os.path.exists(output_file):
            os.remove(output_file)


async def test_trace_actor_not_found(session: ClientSession) -> bool:
    """Test 3: Verify handling of non-existent actor."""
    print("\n" + "=" * 60)
    print("TEST 3: Trace Non-Existent Actor")
    print("=" * 60)

    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        output_file = f.name

    try:
        data = await call_tool(
            session,
            "editor_trace_actors_in_pie",
            {
                "output_file": output_file,
                "level": TEST_LEVEL,
                "actor_names": [TEST_ACTORS["nonexistent"]],
                "duration_seconds": 2.0,
                "interval_seconds": 0.1,
            },
            timeout=120
        )

        # Should report actor not found
        actors_not_found = data.get("actors_not_found", [])

        if TEST_ACTORS["nonexistent"] in actors_not_found:
            print(f"  actors_not_found: {actors_not_found}")
            print("\nPASS: Non-existent actor reported correctly")
            return True
        else:
            print(f"FAIL: Expected actor in actors_not_found")
            print(f"  Got: {data}")
            return False

    finally:
        if os.path.exists(output_file):
            os.remove(output_file)


async def test_trace_multiple_actors(session: ClientSession) -> bool:
    """Test 4: Trace multiple actors (mix of existing and non-existing)."""
    print("\n" + "=" * 60)
    print("TEST 4: Trace Multiple Actors")
    print("=" * 60)

    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        output_file = f.name

    try:
        data = await call_tool(
            session,
            "editor_trace_actors_in_pie",
            {
                "output_file": output_file,
                "level": TEST_LEVEL,
                "actor_names": [
                    TEST_ACTORS["player"],      # Should exist
                    TEST_ACTORS["nonexistent"],  # Should not exist
                ],
                "duration_seconds": 2.0,
                "interval_seconds": 0.2,
            },
            timeout=120
        )

        actor_count = data.get("actor_count", 0)
        actors_not_found = data.get("actors_not_found", [])
        sample_count = data.get("sample_count", 0)

        print(f"\n  Results:")
        print(f"    - Actors tracked: {actor_count}")
        print(f"    - Actors not found: {actors_not_found}")
        print(f"    - Samples: {sample_count}")

        # At least one actor should be tracked
        if actor_count < 1:
            print("FAIL: No actors tracked")
            return False

        # Non-existent actor should be reported
        if TEST_ACTORS["nonexistent"] not in actors_not_found:
            print(f"FAIL: Non-existent actor not in actors_not_found")
            return False

        print("\nPASS: Multiple actor trace handled correctly")
        return True

    finally:
        if os.path.exists(output_file):
            os.remove(output_file)


async def test_trace_high_frequency(session: ClientSession) -> bool:
    """Test 5: High frequency sampling (limited by editor frame rate)."""
    print("\n" + "=" * 60)
    print("TEST 5: High Frequency Sampling (Frame-Rate Limited)")
    print("=" * 60)

    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        output_file = f.name

    try:
        # Use 0.05s (20 Hz) which is achievable at typical editor frame rates
        data = await call_tool(
            session,
            "editor_trace_actors_in_pie",
            {
                "output_file": output_file,
                "level": TEST_LEVEL,
                "actor_names": [TEST_ACTORS["player"]],
                "duration_seconds": 2.0,
                "interval_seconds": 0.05,  # 20 Hz target
            },
            timeout=120
        )

        if not data.get("success"):
            print(f"FAIL: Trace failed: {data.get('error', data)}")
            return False

        sample_count = data.get("sample_count", 0)
        duration = data.get("duration", 0)

        # Expected: 2.0 / 0.05 = 40 samples
        # Note: Actual rate limited by editor frame rate (typically 30-60 FPS)
        expected_samples = 2.0 / 0.05
        actual_rate = sample_count / duration if duration > 0 else 0

        print(f"\n  Results:")
        print(f"    - Samples: {sample_count}")
        print(f"    - Duration: {duration:.2f}s")
        print(f"    - Expected: ~{expected_samples:.0f} samples (at 20Hz)")
        print(f"    - Actual rate: {actual_rate:.1f} Hz")

        # Allow significant tolerance - frame rate and startup overhead affect results
        # Just verify we get a reasonable number of samples (at least 10)
        if sample_count < 10:
            print(f"FAIL: Too few samples ({sample_count} < 10)")
            return False

        print("\nPASS: High frequency sampling works")
        return True

    finally:
        if os.path.exists(output_file):
            os.remove(output_file)


async def test_output_file_structure(session: ClientSession) -> bool:
    """Test 6: Validate complete output file structure."""
    print("\n" + "=" * 60)
    print("TEST 6: Validate Output File Structure")
    print("=" * 60)

    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        output_file = f.name

    try:
        data = await call_tool(
            session,
            "editor_trace_actors_in_pie",
            {
                "output_file": output_file,
                "level": TEST_LEVEL,
                "actor_names": [TEST_ACTORS["player"]],
                "duration_seconds": 1.5,
                "interval_seconds": 0.1,
            },
            timeout=120
        )

        if not data.get("success"):
            print(f"FAIL: Trace failed: {data.get('error', data)}")
            return False

        # Read and validate output file
        with open(output_file, 'r', encoding='utf-8') as f:
            trace_data = json.load(f)

        # Validate top-level structure
        required_keys = ["actors", "metadata"]
        for key in required_keys:
            if key not in trace_data:
                print(f"FAIL: Missing top-level key '{key}'")
                return False

        # Validate metadata structure
        metadata = trace_data["metadata"]
        metadata_keys = ["level", "start_time", "end_time", "duration", "interval", "sample_count"]
        for key in metadata_keys:
            if key not in metadata:
                print(f"FAIL: Missing metadata key '{key}'")
                return False

        print(f"\n  Metadata:")
        print(f"    - Level: {metadata['level']}")
        print(f"    - Start: {metadata['start_time']}")
        print(f"    - End: {metadata['end_time']}")
        print(f"    - Duration: {metadata['duration']:.2f}s")
        print(f"    - Interval: {metadata['interval']}s")
        print(f"    - Samples: {metadata['sample_count']}")

        # Validate actors data
        actors = trace_data["actors"]
        if len(actors) == 0:
            print("FAIL: No actors in output")
            return False

        print(f"\n  Actors tracked: {list(actors.keys())}")

        # Validate sample timestamps are increasing
        for actor_name, samples in actors.items():
            if len(samples) < 2:
                continue
            for i in range(1, len(samples)):
                if samples[i]["timestamp"] <= samples[i-1]["timestamp"]:
                    print(f"FAIL: Non-increasing timestamps in {actor_name}")
                    return False

        print("\nPASS: Output file structure valid")
        return True

    finally:
        if os.path.exists(output_file):
            os.remove(output_file)


# =============================================================================
# Main
# =============================================================================


async def run_tests():
    """Run all tests."""
    print("=" * 60)
    print("editor_trace_actors_in_pie Test Suite")
    print("=" * 60)
    print(f"Project: {THIRDPERSON_PROJECT_PATH}")
    print(f"Level: {TEST_LEVEL}")

    # Check project exists
    if not THIRDPERSON_PROJECT_PATH.exists():
        print(f"ERROR: Project not found at {THIRDPERSON_PROJECT_PATH}")
        return 1

    uproject_files = list(THIRDPERSON_PROJECT_PATH.glob("*.uproject"))
    if not uproject_files:
        print(f"ERROR: No .uproject found in {THIRDPERSON_PROJECT_PATH}")
        return 1

    print(f"UProject: {uproject_files[0].name}")

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

            # Test 1: Tool registration (doesn't need editor)
            try:
                passed = await test_tool_registered(session)
                results.append(("Tool Registration", passed))
            except Exception as e:
                print(f"ERROR: {e}")
                results.append(("Tool Registration", False))

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

            # Launch editor
            print("\n>>> Launching editor (this may take a few minutes)...")
            data = await call_tool(
                session,
                "editor_launch",
                {"wait": True, "wait_timeout": 300},
                timeout=360
            )

            # Check if build is required
            if not data.get("success") and data.get("requires_build"):
                print("\n>>> Plugin requires build, building project first...")
                build_data = await call_tool(
                    session,
                    "project_build",
                    {"target": "Editor", "wait": True},
                    timeout=600
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

            # Run tests that require editor
            tests = [
                ("Trace Single Actor", test_trace_single_actor),
                ("Trace Actor Not Found", test_trace_actor_not_found),
                ("Trace Multiple Actors", test_trace_multiple_actors),
                ("High Frequency Sampling", test_trace_high_frequency),
                ("Output File Structure", test_output_file_structure),
            ]

            for name, test_func in tests:
                try:
                    passed = await test_func(session)
                    results.append((name, passed))
                except Exception as e:
                    print(f"ERROR in {name}: {e}")
                    import traceback
                    traceback.print_exc()
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
