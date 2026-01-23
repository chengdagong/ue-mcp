"""
Fuzzy Actor Matching Tests for PIE Capture.

Tests the fuzzy matching functionality for target_actor parameter in editor_capture_pie.

Matching priority:
1. Exact match on object name
2. Exact match on label
3. Exact match on class name
4. Partial match on object name (contains)
5. Partial match on label (contains)
6. Partial match on class name (contains)

When multiple actors match, an error is returned with matched_actors list.

Usage:
    pytest tests/test_fuzzy_actor_matching.py -v -s
"""

import asyncio
import json
import os
import uuid
from pathlib import Path

import pytest

from ue_mcp import EditorManager
from ue_mcp.log_watcher import watch_pie_capture_complete
from ue_mcp.script_executor import execute_script


@pytest.fixture(scope="module")
def project_path() -> Path:
    """Return path to the ThirdPersonTemplate test project."""
    path = Path(__file__).parent / "fixtures" / "ThirdPersonTemplate" / "thirdperson_template.uproject"
    if not path.exists():
        pytest.skip(f"Test project not found: {path}")
    return path


@pytest.fixture(scope="module")
def event_loop():
    """Create event loop for module-scoped async fixtures."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="module")
async def manager(project_path: Path):
    """Create and launch EditorManager for the test project."""
    mgr = EditorManager(project_path)

    # Launch editor and wait for connection (longer timeout for initial launch)
    result = await mgr.launch(wait_timeout=300)
    assert result.get("success"), f"Failed to launch editor: {result}"

    # Verify connection with a simple test
    status = mgr.get_status()
    print(f"\n[INFO] Editor launched - PID: {status.get('pid')}, Connected: {status.get('connected')}")

    yield mgr

    # Cleanup
    mgr.stop()


class TestFuzzyActorMatching:
    """Test fuzzy actor matching in PIE capture."""

    @pytest.mark.asyncio
    async def test_exact_label_match(self, manager: EditorManager, tmp_path: Path):
        """Test exact match on actor label."""
        output_dir = str(tmp_path / "exact_label")
        task_id = str(uuid.uuid4())[:8]

        # Execute PIE capture script with exact label match
        # Use PlayerStart which exists in ThirdPersonTemplate
        script_params = {
            "task_id": task_id,
            "output_dir": output_dir,
            "level": "/Game/ThirdPerson/DefaultAutomaticTestLevel",
            "duration_seconds": 5.0,
            "interval_seconds": 1.0,
            "multi_angle": True,
            "camera_distance": 400.0,
            "target_height": 90.0,
            "resolution_width": 1280,
            "resolution_height": 720,
            "target_actor": "PlayerStart",  # Exact label match
        }

        result = await self._run_pie_capture(manager, script_params, task_id)

        assert result["success"], f"Capture failed: {result.get('error')}"
        assert result.get("screenshot_count", 0) > 0, "No screenshots captured"
        print(f"[OK] Exact label match: captured {result['screenshot_count']} screenshots")

    @pytest.mark.asyncio
    async def test_partial_label_match(self, manager: EditorManager, tmp_path: Path):
        """Test partial match on actor label (fuzzy matching)."""
        output_dir = str(tmp_path / "partial_label")
        task_id = str(uuid.uuid4())[:8]

        script_params = {
            "task_id": task_id,
            "output_dir": output_dir,
            "level": "/Game/ThirdPerson/DefaultAutomaticTestLevel",
            "duration_seconds": 5.0,
            "interval_seconds": 1.0,
            "multi_angle": True,
            "camera_distance": 400.0,
            "target_height": 90.0,
            "resolution_width": 1280,
            "resolution_height": 720,
            "target_actor": "Start",  # Partial label match -> PlayerStart
        }

        result = await self._run_pie_capture(manager, script_params, task_id)

        assert result["success"], f"Capture failed: {result.get('error')}"
        assert result.get("screenshot_count", 0) > 0, "No screenshots captured"
        print(f"[OK] Partial label match 'Start': captured {result['screenshot_count']} screenshots")

    @pytest.mark.asyncio
    async def test_multiple_match_error(self, manager: EditorManager, tmp_path: Path):
        """Test that multiple matches return error with matched_actors list."""
        output_dir = str(tmp_path / "multiple_match")
        task_id = str(uuid.uuid4())[:8]

        script_params = {
            "task_id": task_id,
            "output_dir": output_dir,
            "level": "/Game/ThirdPerson/DefaultAutomaticTestLevel",
            "duration_seconds": 5.0,
            "interval_seconds": 1.0,
            "multi_angle": True,
            "camera_distance": 400.0,
            "target_height": 90.0,
            "resolution_width": 1280,
            "resolution_height": 720,
            "target_actor": "StaticMeshActor",  # Should match multiple static meshes
        }

        result = await self._run_pie_capture(manager, script_params, task_id)

        assert not result["success"], "Expected failure for multiple matches"
        assert "error" in result, "Expected error message"
        assert "Multiple actors" in result["error"], f"Expected multiple match error, got: {result['error']}"
        assert "matched_actors" in result, "Expected matched_actors list in error response"
        assert len(result["matched_actors"]) >= 2, f"Expected at least 2 matched actors, got: {result['matched_actors']}"

        print(f"[OK] Multiple match error: {result['error']}")
        print(f"  Matched actors: {json.dumps(result['matched_actors'], indent=2)}")

    @pytest.mark.asyncio
    async def test_no_match_error(self, manager: EditorManager, tmp_path: Path):
        """Test that no match returns error with available_actors list."""
        output_dir = str(tmp_path / "no_match")
        task_id = str(uuid.uuid4())[:8]

        script_params = {
            "task_id": task_id,
            "output_dir": output_dir,
            "level": "/Game/ThirdPerson/DefaultAutomaticTestLevel",
            "duration_seconds": 5.0,
            "interval_seconds": 1.0,
            "multi_angle": True,
            "camera_distance": 400.0,
            "target_height": 90.0,
            "resolution_width": 1280,
            "resolution_height": 720,
            "target_actor": "NonExistentActor12345XYZ",  # Should not match anything
        }

        result = await self._run_pie_capture(manager, script_params, task_id)

        print(f"[DEBUG] Full result for no_match: {json.dumps(result, indent=2)}")
        assert not result["success"], "Expected failure for no match"
        assert "error" in result, "Expected error message"
        assert "not found" in result["error"], f"Expected 'not found' error, got: {result['error']}"
        assert "available_actors" in result, "Expected available_actors list in error response"

        print(f"[OK] No match error: {result['error']}")
        print(f"  Available actors count: {len(result['available_actors'])}")

    @pytest.mark.asyncio
    async def test_class_match_multiple_error(self, manager: EditorManager, tmp_path: Path):
        """Test that class match with multiple actors returns error."""
        output_dir = str(tmp_path / "class_match")
        task_id = str(uuid.uuid4())[:8]

        script_params = {
            "task_id": task_id,
            "output_dir": output_dir,
            "level": "/Game/ThirdPerson/DefaultAutomaticTestLevel",
            "duration_seconds": 5.0,
            "interval_seconds": 1.0,
            "multi_angle": True,
            "camera_distance": 400.0,
            "target_height": 90.0,
            "resolution_width": 1280,
            "resolution_height": 720,
            "target_actor": "PointLight",  # Should match multiple point lights
        }

        result = await self._run_pie_capture(manager, script_params, task_id)

        assert not result["success"], "Expected failure for multiple class matches"
        assert "error" in result, "Expected error message"
        assert "Multiple actors" in result["error"], f"Expected multiple match error, got: {result['error']}"
        assert "matched_actors" in result, "Expected matched_actors list"

        print(f"[OK] Class match multiple error: {result['error']}")
        print(f"  Matched actors count: {len(result['matched_actors'])}")

    async def _run_pie_capture(self, manager: EditorManager, params: dict, task_id: str) -> dict:
        """
        Run PIE capture and wait for completion.

        Args:
            manager: EditorManager instance
            params: Capture parameters (using script_executor param names)
            task_id: Unique task ID for completion tracking

        Returns:
            Capture result dictionary
        """
        # Execute capture script using script_executor (synchronous, run in executor)
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: execute_script(manager, "capture_pie", params=params, timeout=30.0)
        )

        print(f"[DEBUG] execute_script result: {result}")

        if not result.get("success"):
            return {"success": False, "error": f"Script execution failed: {result.get('error')}", "details": result}

        # Wait for completion
        capture_result = await watch_pie_capture_complete(
            project_root=manager.project_root,
            task_id=task_id,
            timeout=params["duration_seconds"] + 60,
        )

        if capture_result is None:
            return {"success": False, "error": "Timeout waiting for capture completion"}

        return capture_result


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
