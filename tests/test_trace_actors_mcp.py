"""
Tests for editor_trace_actors_in_pie MCP tool.

Run with:
    pytest tests/test_trace_actors_mcp.py -v

For tests requiring editor:
    pytest tests/test_trace_actors_mcp.py -v -k "WithEditor"
"""

import json
import logging
import os
import shutil
from pathlib import Path
from typing import Any

import pytest
from mcp_pytest import ToolCaller, ToolCallResult

# Configure logging for tests
logger = logging.getLogger(__name__)

# Test project fixture path
FIXTURE_PROJECT = Path(__file__).parent / "fixtures" / "ThirdPersonTemplate"


def parse_tool_result(result: ToolCallResult) -> dict[str, Any]:
    """Parse tool result text content as JSON."""
    text = result.text_content
    if not text:
        return {"is_error": result.is_error, "content": str(result.result.content)}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"raw_text": text}


@pytest.mark.integration
class TestTraceActorsToolsBasic:
    """Basic tests that don't require a running editor."""

    @pytest.mark.asyncio
    async def test_list_tools_includes_trace_actors(self, tool_caller: ToolCaller):
        """Verify trace actors tool is registered."""
        tools = await tool_caller.list_tools()

        assert "editor_trace_actors_in_pie" in tools, \
            f"editor_trace_actors_in_pie not found in tools: {list(tools.keys())}"

@pytest.mark.integration
class TestTraceActorsWithEditor:
    """Tests that require a running editor.

    Uses the session-scoped running_editor fixture to share editor instance
    across all tests in the test session.
    """

    @pytest.mark.asyncio
    async def test_trace_single_actor(self, running_editor: ToolCaller, test_level_path: str, test_output_dir: Path):
        """Test tracing a single actor (player character)."""
        # Use test output directory
        output_dir = test_output_dir / "test_trace_single_actor"
        if output_dir.exists():
            shutil.rmtree(output_dir)

        try:
            result = await running_editor.call(
                "editor_trace_actors_in_pie",
                {
                    "output_dir": str(output_dir),
                    "level": test_level_path,
                    "actor_names": ["BP_ThirdPersonCharacter_0"],
                    "duration_seconds": 3.0,
                    "interval_seconds": 0.1,
                },
                timeout=120,
            )

            data = parse_tool_result(result)

            # Check result
            assert data.get("success") is True, f"Trace failed: {data}"
            assert data.get("sample_count", 0) > 0, "No samples collected"
            assert data.get("actor_count", 0) >= 1, "No actors tracked"

            # Verify output directory structure
            assert output_dir.exists(), f"Output directory not created: {output_dir}"

            # Verify metadata.json exists
            metadata_file = output_dir / "metadata.json"
            assert metadata_file.exists(), f"metadata.json not created: {metadata_file}"

            with open(metadata_file, 'r', encoding='utf-8') as f:
                metadata = json.load(f)

            # Verify metadata structure
            assert metadata["sample_count"] > 0, "No samples in metadata"
            assert len(metadata["actors"]) > 0, "No actors in metadata"

            # Verify actor subdirectories exist with sample directories
            actor_dirs = [d for d in output_dir.iterdir() if d.is_dir()]
            assert len(actor_dirs) > 0, "No actor subdirectories created"

            # Check at least one sample directory exists
            sample_dirs = list(actor_dirs[0].glob("sample_at_tick_*"))
            assert len(sample_dirs) > 0, "No sample directories created"

            # Verify transform.json exists in sample directory
            transform_file = sample_dirs[0] / "transform.json"
            assert transform_file.exists(), f"transform.json not found: {transform_file}"

            with open(transform_file, 'r', encoding='utf-8') as f:
                transform_data = json.load(f)

            assert "tick" in transform_data, "Missing 'tick' in transform.json"
            assert "timestamp" in transform_data, "Missing 'timestamp' in transform.json"
            assert "location" in transform_data, "Missing 'location' in transform.json"
            assert "rotation" in transform_data, "Missing 'rotation' in transform.json"

            logger.info("[OK] Trace completed:")
            logger.info(f"  - Samples: {data.get('sample_count')}")
            logger.info(f"  - Actors: {data.get('actor_count')}")
            logger.info(f"  - Duration: {data.get('duration'):.2f}s")
            logger.info(f"  - Output dir: {output_dir}")
            logger.info(f"  - Sample dirs: {len(sample_dirs)}")

            # Log all generated files
            logger.info("Generated files:")
            for actor_dir in actor_dirs:
                logger.info(f"  Actor: {actor_dir.name}")
                for sample_dir in sorted(actor_dir.glob("sample_at_tick_*")):
                    logger.info(f"    {sample_dir.name}/")
                    for file in sorted(sample_dir.rglob("*")):
                        if file.is_file():
                            rel_path = file.relative_to(sample_dir)
                            logger.info(f"      - {rel_path}")

        finally:
            # Preserve all outputs for inspection
            pass

    @pytest.mark.asyncio
    async def test_trace_actor_not_found(self, running_editor: ToolCaller, test_level_path: str, test_output_dir: Path):
        """Test tracing with non-existent actor name."""
        # Use test output directory
        output_dir = test_output_dir / "test_trace_actor_not_found"
        if output_dir.exists():
            shutil.rmtree(output_dir)

        try:
            result = await running_editor.call(
                "editor_trace_actors_in_pie",
                {
                    "output_dir": str(output_dir),
                    "level": test_level_path,
                    "actor_names": ["NonExistentActor_12345"],
                    "duration_seconds": 2.0,
                    "interval_seconds": 0.1,
                },
                timeout=120,
            )

            data = parse_tool_result(result)

            # Should complete but report actor not found
            assert "actors_not_found" in data, "Should report not found actors"
            assert "NonExistentActor_12345" in data.get("actors_not_found", []), \
                "Should list the not-found actor"

            logger.info("[OK] Actor not found test passed:")
            logger.info(f"  - actors_not_found: {data.get('actors_not_found')}")

        finally:
            # Preserve all outputs for inspection
            pass

    @pytest.mark.asyncio
    async def test_trace_multiple_actors(self, running_editor: ToolCaller, test_level_path: str, test_output_dir: Path):
        """Test tracing multiple actors."""
        # Use test output directory
        output_dir = test_output_dir / "test_trace_multiple_actors"
        if output_dir.exists():
            shutil.rmtree(output_dir)

        try:
            result = await running_editor.call(
                "editor_trace_actors_in_pie",
                {
                    "output_dir": str(output_dir),
                    "level": test_level_path,
                    "actor_names": [
                        "BP_ThirdPersonCharacter_0",  # Should exist
                        "Floor",                       # Should exist (static mesh)
                        "NonExistent_Actor",           # Should not exist
                    ],
                    "duration_seconds": 2.0,
                    "interval_seconds": 0.2,
                },
                timeout=120,
            )

            data = parse_tool_result(result)

            logger.info("[INFO] Multiple actors trace result:")
            logger.info(f"  - actor_count: {data.get('actor_count')}")
            logger.info(f"  - actors_not_found: {data.get('actors_not_found')}")
            logger.info(f"  - sample_count: {data.get('sample_count')}")

            # At least one actor should be found
            assert data.get("actor_count", 0) >= 1, "At least one actor should be tracked"

            # Verify multiple actor subdirectories exist
            actor_dirs = [d for d in output_dir.iterdir() if d.is_dir()]
            logger.info(f"  - Actor directories: {[d.name for d in actor_dirs]}")
            logger.info(f"  - Output dir: {output_dir}")

        finally:
            # Preserve all outputs for inspection
            pass

    @pytest.mark.asyncio
    async def test_trace_with_screenshots(self, running_editor: ToolCaller, test_level_path: str, test_output_dir: Path):
        """Test tracing with screenshot capture enabled."""
        # Use test output directory
        output_dir = test_output_dir / "test_trace_with_screenshots"
        if output_dir.exists():
            shutil.rmtree(output_dir)

        try:
            result = await running_editor.call(
                "editor_trace_actors_in_pie",
                {
                    "output_dir": str(output_dir),
                    "level": test_level_path,
                    "actor_names": ["BP_ThirdPersonCharacter_0"],
                    "duration_seconds": 3.0,
                    "interval_seconds": 1.0,  # Longer interval to reduce screenshot count
                    "capture_screenshots": True,
                    "camera_distance": 300,
                    "target_height": 90,
                    "resolution_width": 640,
                    "resolution_height": 480,
                    "multi_angle": True,
                },
                timeout=180,  # Longer timeout for screenshots
            )

            data = parse_tool_result(result)

            # Check result
            assert data.get("success") is True, f"Trace with screenshots failed: {data}"
            assert data.get("sample_count", 0) > 0, "No samples collected"
            assert data.get("actor_count", 0) >= 1, "No actors tracked"

            # Verify output directory structure
            assert output_dir.exists(), f"Output directory not created: {output_dir}"

            # Verify metadata.json
            metadata_file = output_dir / "metadata.json"
            assert metadata_file.exists(), "metadata.json not created"

            with open(metadata_file, 'r', encoding='utf-8') as f:
                metadata = json.load(f)

            assert metadata.get("capture_screenshots") is True, \
                "Metadata should indicate screenshots were captured"

            # Verify actor subdirectories with screenshots
            actor_dirs = [d for d in output_dir.iterdir() if d.is_dir()]
            assert len(actor_dirs) > 0, "No actor subdirectories created"

            # Check sample directories have screenshots subdirectory
            sample_dirs = list(actor_dirs[0].glob("sample_at_tick_*"))
            assert len(sample_dirs) > 0, "No sample directories created"

            # Verify screenshots directory and files
            screenshots_dir = sample_dirs[0] / "screenshots"
            assert screenshots_dir.exists(), f"Screenshots directory not created: {screenshots_dir}"

            screenshots = list(screenshots_dir.glob("*.png"))
            assert len(screenshots) > 0, f"No screenshots found in {screenshots_dir}"

            # Verify transform.json contains screenshot references
            transform_file = sample_dirs[0] / "transform.json"
            with open(transform_file, 'r', encoding='utf-8') as f:
                transform_data = json.load(f)

            assert "screenshots" in transform_data, "Missing 'screenshots' in transform.json"
            assert len(transform_data["screenshots"]) > 0, "Empty screenshots list in transform.json"

            # Count total screenshots across all samples
            total_screenshots = len(list(output_dir.glob("**/screenshots/*.png")))

            logger.info("[OK] Trace with screenshots completed:")
            logger.info(f"  - Samples: {data.get('sample_count')}")
            logger.info(f"  - Actors: {data.get('actor_count')}")
            logger.info(f"  - Duration: {data.get('duration'):.2f}s")
            logger.info(f"  - Output dir: {output_dir}")
            logger.info(f"  - Total screenshots: {total_screenshots}")
            logger.info(f"  - Screenshots per sample: {[f.name for f in screenshots]}")

            # Log all generated screenshot files
            logger.info("Generated screenshot files:")
            for actor_dir in actor_dirs:
                logger.info(f"  Actor: {actor_dir.name}")
                for sample_dir in sorted(actor_dir.glob("sample_at_tick_*")):
                    screenshots_in_sample = list((sample_dir / "screenshots").glob("*.png"))
                    if screenshots_in_sample:
                        logger.info(f"    {sample_dir.name}/screenshots/")
                        for screenshot in sorted(screenshots_in_sample):
                            logger.info(f"      - {screenshot.name}: {screenshot}")

        finally:
            # Preserve all outputs for inspection
            pass

    @pytest.mark.asyncio
    async def test_trace_with_screenshots_single_angle(self, running_editor: ToolCaller, test_level_path: str, test_output_dir: Path):
        """Test tracing with single-angle screenshot capture."""
        # Use test output directory
        output_dir = test_output_dir / "test_trace_with_screenshots_single_angle"
        if output_dir.exists():
            shutil.rmtree(output_dir)

        try:
            result = await running_editor.call(
                "editor_trace_actors_in_pie",
                {
                    "output_dir": str(output_dir),
                    "level": test_level_path,
                    "actor_names": ["BP_ThirdPersonCharacter_0"],
                    "duration_seconds": 2.0,
                    "interval_seconds": 1.0,
                    "capture_screenshots": True,
                    "multi_angle": False,  # Single angle only
                    "resolution_width": 640,
                    "resolution_height": 480,
                },
                timeout=120,
            )

            data = parse_tool_result(result)

            assert data.get("success") is True, f"Single-angle trace failed: {data}"

            # Verify output structure
            assert output_dir.exists(), "Output directory not created"

            # Count total screenshots (single angle = 1 per sample per actor)
            total_screenshots = len(list(output_dir.glob("**/screenshots/*.png")))

            # With single angle, should have fewer screenshots than multi-angle
            # (1 per sample per actor instead of 4)
            logger.info("[OK] Single-angle trace completed:")
            logger.info(f"  - Total screenshots: {total_screenshots}")
            logger.info(f"  - Sample count: {data.get('sample_count')}")
            logger.info(f"  - Output dir: {output_dir}")

            # Log all generated files
            all_files = list(output_dir.rglob("*"))
            all_files = [f for f in all_files if f.is_file()]
            logger.info(f"All generated files ({len(all_files)} total):")
            for file_path in sorted(all_files):
                rel_path = file_path.relative_to(output_dir)
                logger.info(f"  - {rel_path}")

        finally:
            # Preserve all outputs for inspection
            pass


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
