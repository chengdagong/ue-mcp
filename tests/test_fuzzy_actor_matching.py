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

import json
from pathlib import Path

import pytest

# Import test level path from conftest
from .conftest import TEST_LEVEL_PATH


class TestFuzzyActorMatching:
    """Test fuzzy actor matching in PIE capture."""

    @pytest.mark.asyncio
    async def test_exact_label_match(
        self, running_editor, test_level_path: str, test_output_dir: Path
    ):
        """Test exact match on actor label."""
        output_dir = test_output_dir / "fuzzy_exact_label"
        output_dir.mkdir(exist_ok=True)

        # Execute PIE capture with exact label match
        # Use PlayerStart which exists in the test level
        result = await running_editor.call(
            "editor_capture_pie",
            {
                "level": test_level_path,
                "duration_seconds": 5.0,
                "interval_seconds": 1.0,
                "multi_angle": True,
                "camera_distance": 400.0,
                "target_height": 90.0,
                "resolution_width": 1280,
                "resolution_height": 720,
                "target_actor": "PlayerStart",  # Exact label match
                "output_dir": str(output_dir),
            },
            timeout=90,
        )

        result_text = result.text_content or ""
        print(f"[DEBUG] Exact label match result: {result_text}")

        # Parse JSON result
        result_data = json.loads(result_text)
        assert result_data["success"], f"Capture failed: {result_data.get('error')}"
        assert result_data.get("screenshot_count", 0) > 0, "No screenshots captured"
        print(f"[OK] Exact label match: captured {result_data['screenshot_count']} screenshots")

    @pytest.mark.asyncio
    async def test_partial_label_match(
        self, running_editor, test_level_path: str, test_output_dir: Path
    ):
        """Test partial match on actor label (fuzzy matching)."""
        output_dir = test_output_dir / "fuzzy_partial_label"
        output_dir.mkdir(exist_ok=True)

        result = await running_editor.call(
            "editor_capture_pie",
            {
                "level": test_level_path,
                "duration_seconds": 5.0,
                "interval_seconds": 1.0,
                "multi_angle": True,
                "camera_distance": 400.0,
                "target_height": 90.0,
                "resolution_width": 1280,
                "resolution_height": 720,
                "target_actor": "Start",  # Partial label match -> PlayerStart
                "output_dir": str(output_dir),
            },
            timeout=90,
        )

        result_text = result.text_content or ""
        print(f"[DEBUG] Partial label match result: {result_text}")

        result_data = json.loads(result_text)
        assert result_data["success"], f"Capture failed: {result_data.get('error')}"
        assert result_data.get("screenshot_count", 0) > 0, "No screenshots captured"
        print(
            f"[OK] Partial label match 'Start': captured {result_data['screenshot_count']} screenshots"
        )

    @pytest.mark.asyncio
    async def test_multiple_match_error(
        self, running_editor, test_level_path: str, test_output_dir: Path
    ):
        """Test that multiple matches return error with matched_actors list."""
        output_dir = test_output_dir / "fuzzy_multiple_match"
        output_dir.mkdir(exist_ok=True)

        result = await running_editor.call(
            "editor_capture_pie",
            {
                "level": test_level_path,
                "duration_seconds": 5.0,
                "interval_seconds": 1.0,
                "multi_angle": True,
                "camera_distance": 400.0,
                "target_height": 90.0,
                "resolution_width": 1280,
                "resolution_height": 720,
                "target_actor": "StaticMeshActor",  # Should match multiple static meshes
                "output_dir": str(output_dir),
            },
            timeout=90,
        )

        result_text = result.text_content or ""
        print(f"[DEBUG] Multiple match result: {result_text}")

        result_data = json.loads(result_text)
        assert not result_data["success"], "Expected failure for multiple matches"
        assert "error" in result_data, "Expected error message"
        assert "Multiple actors" in result_data["error"], (
            f"Expected multiple match error, got: {result_data['error']}"
        )
        assert "matched_actors" in result_data, "Expected matched_actors list in error response"
        assert len(result_data["matched_actors"]) >= 2, (
            f"Expected at least 2 matched actors, got: {result_data['matched_actors']}"
        )

        print(f"[OK] Multiple match error: {result_data['error']}")
        print(f"  Matched actors: {json.dumps(result_data['matched_actors'], indent=2)}")

    @pytest.mark.asyncio
    async def test_no_match_error(
        self, running_editor, test_level_path: str, test_output_dir: Path
    ):
        """Test that no match returns error with available_actors list."""
        output_dir = test_output_dir / "fuzzy_no_match"
        output_dir.mkdir(exist_ok=True)

        result = await running_editor.call(
            "editor_capture_pie",
            {
                "level": test_level_path,
                "duration_seconds": 5.0,
                "interval_seconds": 1.0,
                "multi_angle": True,
                "camera_distance": 400.0,
                "target_height": 90.0,
                "resolution_width": 1280,
                "resolution_height": 720,
                "target_actor": "NonExistentActor12345XYZ",  # Should not match anything
                "output_dir": str(output_dir),
            },
            timeout=90,
        )

        result_text = result.text_content or ""
        print(f"[DEBUG] No match result: {result_text}")

        result_data = json.loads(result_text)
        print(f"[DEBUG] Full result for no_match: {json.dumps(result_data, indent=2)}")
        assert not result_data["success"], "Expected failure for no match"
        assert "error" in result_data, "Expected error message"
        assert "not found" in result_data["error"], (
            f"Expected 'not found' error, got: {result_data['error']}"
        )
        assert "available_actors" in result_data, "Expected available_actors list in error response"

        print(f"[OK] No match error: {result_data['error']}")
        print(f"  Available actors count: {len(result_data['available_actors'])}")

    @pytest.mark.asyncio
    async def test_class_match_multiple_error(
        self, running_editor, test_level_path: str, test_output_dir: Path
    ):
        """Test that class match with multiple actors returns error."""
        output_dir = test_output_dir / "fuzzy_class_match"
        output_dir.mkdir(exist_ok=True)

        result = await running_editor.call(
            "editor_capture_pie",
            {
                "level": test_level_path,
                "duration_seconds": 5.0,
                "interval_seconds": 1.0,
                "multi_angle": True,
                "camera_distance": 400.0,
                "target_height": 90.0,
                "resolution_width": 1280,
                "resolution_height": 720,
                "target_actor": "BP_ThirdPersonCharacter",  # Should match multiple characters
                "output_dir": str(output_dir),
            },
            timeout=90,
        )

        result_text = result.text_content or ""
        print(f"[DEBUG] Class match result: {result_text}")

        result_data = json.loads(result_text)
        assert not result_data["success"], "Expected failure for multiple class matches"
        assert "error" in result_data, "Expected error message"
        assert "Multiple actors" in result_data["error"], (
            f"Expected multiple match error, got: {result_data['error']}"
        )
        assert "matched_actors" in result_data, "Expected matched_actors list"

        print(f"[OK] Class match multiple error: {result_data['error']}")
        print(f"  Matched actors count: {len(result_data['matched_actors'])}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
