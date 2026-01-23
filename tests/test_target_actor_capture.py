"""
Test script for PIE capture with target_actor parameter.

Tests the new target_actor functionality using URF project.
"""
import asyncio
import sys
import os
from pathlib import Path

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ue_mcp.editor_manager import EditorManager


async def test_pie_capture_with_target_actor():
    """Test PIE capture targeting a specific actor."""

    project_path = Path(r"C:\Users\cheng\Documents\Unreal Projects\URF")
    level = "/Game/punchingbaglevel"
    target_actor = "BP_RobotBase"
    output_dir = str(project_path / "Screenshots" / "TargetActorTest")

    print(f"Project: {project_path}")
    print(f"Level: {level}")
    print(f"Target Actor: {target_actor}")
    print(f"Output Dir: {output_dir}")
    print("-" * 60)

    # Create editor manager
    manager = EditorManager(project_path)

    # Check editor status
    status = manager.get_status()
    print(f"Editor status: {status['status']}")

    if status["status"] != "ready":
        print("Launching editor...")
        launch_result = await manager.launch(wait_timeout=180)
        if not launch_result.get("success"):
            print(f"Failed to launch editor: {launch_result}")
            return
        print("Editor launched successfully")

    # Import execute_script
    from ue_mcp.script_executor import execute_script
    import uuid

    # Generate task_id
    task_id = str(uuid.uuid4())[:8]
    print(f"\nStarting PIE capture with task_id: {task_id}")

    # Test 1: Capture with valid target actor
    print("\n" + "=" * 60)
    print("TEST 1: Capture with valid target actor (BP_RobotBase)")
    print("=" * 60)

    result = execute_script(
        manager,
        "capture_pie",
        params={
            "task_id": task_id,
            "output_dir": output_dir,
            "level": level,
            "duration_seconds": 5.0,
            "interval_seconds": 1.0,
            "resolution_width": 1280,
            "resolution_height": 720,
            "multi_angle": True,
            "camera_distance": 500.0,
            "target_height": 100.0,
            "target_actor": target_actor,
        },
        timeout=30.0,
    )

    print(f"Script result: {result}")

    if result.get("success"):
        # Wait for completion
        from ue_mcp.log_watcher import watch_pie_capture_complete

        print("\nWaiting for capture completion...")
        capture_result = await watch_pie_capture_complete(
            project_root=project_path,
            task_id=task_id,
            timeout=60.0,
        )

        print(f"\nCapture result: {capture_result}")

        if capture_result and capture_result.get("success"):
            print(f"\n[SUCCESS] Captured {capture_result.get('screenshot_count', 0)} screenshots")
            print(f"Output directory: {capture_result.get('output_dir')}")
        else:
            print(f"\n[FAILED] Capture failed: {capture_result}")
    else:
        print(f"\n[FAILED] Script execution failed: {result}")

    # Test 2: Capture with invalid target actor (should return error with available actors)
    print("\n" + "=" * 60)
    print("TEST 2: Capture with INVALID target actor (NonExistentActor)")
    print("=" * 60)

    task_id2 = str(uuid.uuid4())[:8]

    result2 = execute_script(
        manager,
        "capture_pie",
        params={
            "task_id": task_id2,
            "output_dir": output_dir,
            "level": level,
            "duration_seconds": 5.0,
            "interval_seconds": 1.0,
            "resolution_width": 1280,
            "resolution_height": 720,
            "multi_angle": True,
            "camera_distance": 500.0,
            "target_height": 100.0,
            "target_actor": "NonExistentActor",
        },
        timeout=30.0,
    )

    print(f"Script result: {result2}")

    if result2.get("success"):
        # Wait for completion (should fail with available actors)
        from ue_mcp.log_watcher import watch_pie_capture_complete

        print("\nWaiting for capture completion (expecting error)...")
        capture_result2 = await watch_pie_capture_complete(
            project_root=project_path,
            task_id=task_id2,
            timeout=60.0,
        )

        print(f"\nCapture result: {capture_result2}")

        if capture_result2:
            if not capture_result2.get("success"):
                print(f"\n[EXPECTED] Capture failed as expected: {capture_result2.get('error')}")
                if "available_actors" in capture_result2:
                    print(f"\nAvailable actors ({len(capture_result2['available_actors'])} total):")
                    for i, actor in enumerate(capture_result2["available_actors"][:20]):
                        print(f"  {i+1}. {actor['label']} ({actor['type']})")
                    if len(capture_result2["available_actors"]) > 20:
                        print(f"  ... and {len(capture_result2['available_actors']) - 20} more")
            else:
                print(f"\n[UNEXPECTED] Capture succeeded when it should have failed")
    else:
        print(f"\n[FAILED] Script execution failed: {result2}")

    print("\n" + "=" * 60)
    print("Tests completed!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_pie_capture_with_target_actor())
