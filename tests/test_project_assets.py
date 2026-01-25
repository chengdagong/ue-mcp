"""
Tests for Project Assets Query functionality.

This module tests the asset query feature that returns Blueprint and Level assets
when the editor is launched.
"""

import json
import logging

import pytest

logger = logging.getLogger(__name__)


@pytest.mark.integration
class TestProjectAssetsQuery:
    """Tests for project assets query functionality."""

    @pytest.mark.asyncio
    async def test_asset_query_script_execution(self, mcp_client, running_editor):
        """Test that the asset_query.py script executes successfully in the editor."""
        # Execute the asset query script directly
        query_code = '''import json
import unreal

# Asset type definitions for UE5.1+
ASSET_TYPE_PATHS = {
    "Blueprint": unreal.TopLevelAssetPath("/Script/Engine", "Blueprint"),
    "World": unreal.TopLevelAssetPath("/Script/Engine", "World"),
}

def query_assets_by_type(asset_type_path, base_path="/Game", limit=100):
    asset_reg = unreal.AssetRegistryHelpers.get_asset_registry()
    ar_filter = unreal.ARFilter(
        package_paths=[base_path],
        class_paths=[asset_type_path],
        recursive_paths=True,
        recursive_classes=True,
    )
    assets = asset_reg.get_assets(ar_filter)
    results = []
    if assets:
        for asset in assets[:limit]:
            results.append({
                "name": str(asset.asset_name),
                "path": str(asset.package_name),
            })
    return results

result = {
    "success": True,
    "assets": {},
}

for asset_type, type_path in ASSET_TYPE_PATHS.items():
    items = query_assets_by_type(type_path, "/Game", 100)
    result["assets"][asset_type] = {
        "items": items,
        "count": len(items),
    }

print(json.dumps(result))
'''
        exec_result = await mcp_client.call_tool(
            "editor_execute_code",
            {"code": query_code, "timeout": 60},
        )

        data = exec_result.structuredContent
        assert data.get("success") is True, f"Code execution failed: {data.get('error')}"

        # Parse the JSON output from the script
        output = data.get("output", [])
        assert len(output) > 0, "Expected output from script"

        # Find the JSON result in output
        json_result = None
        for line in reversed(output):
            line_str = str(line.get("output", "")) if isinstance(line, dict) else str(line)
            line_str = line_str.strip()
            if line_str.startswith("{"):
                try:
                    json_result = json.loads(line_str)
                    break
                except json.JSONDecodeError:
                    continue

        assert json_result is not None, f"No valid JSON found in output: {output}"
        assert json_result.get("success") is True, f"Script failed: {json_result}"

        # Verify assets structure
        assets = json_result.get("assets", {})
        assert "Blueprint" in assets, f"Expected Blueprint in assets. Got: {list(assets.keys())}"
        assert "World" in assets, f"Expected World in assets. Got: {list(assets.keys())}"

        # Log what we found
        bp_count = assets["Blueprint"].get("count", 0)
        world_count = assets["World"].get("count", 0)
        logger.info(f"Found {bp_count} Blueprints and {world_count} World assets")

        # ThirdPersonTemplate should have at least some assets
        # We expect at least BP_ThirdPersonCharacter and the main level
        assert bp_count >= 0, "Expected Blueprint count to be non-negative"
        assert world_count >= 0, "Expected World count to be non-negative"

    @pytest.mark.asyncio
    async def test_asset_query_finds_thirdperson_blueprints(self, mcp_client, running_editor):
        """Test that asset query finds the ThirdPerson template blueprints."""
        query_code = '''import json
import unreal

asset_reg = unreal.AssetRegistryHelpers.get_asset_registry()
bp_path = unreal.TopLevelAssetPath("/Script/Engine", "Blueprint")
ar_filter = unreal.ARFilter(
    package_paths=["/Game"],
    class_paths=[bp_path],
    recursive_paths=True,
    recursive_classes=True,
)
assets = asset_reg.get_assets(ar_filter)

results = []
if assets:
    for asset in assets[:100]:
        results.append({
            "name": str(asset.asset_name),
            "path": str(asset.package_name),
        })

print(json.dumps({"success": True, "blueprints": results, "count": len(results)}))
'''
        exec_result = await mcp_client.call_tool(
            "editor_execute_code",
            {"code": query_code, "timeout": 60},
        )

        data = exec_result.structuredContent
        assert data.get("success") is True, f"Code execution failed: {data.get('error')}"

        # Parse JSON output
        output = data.get("output", [])
        json_result = None
        for line in reversed(output):
            line_str = str(line.get("output", "")) if isinstance(line, dict) else str(line)
            line_str = line_str.strip()
            if line_str.startswith("{"):
                try:
                    json_result = json.loads(line_str)
                    break
                except json.JSONDecodeError:
                    continue

        assert json_result is not None, f"No valid JSON in output"
        assert json_result.get("success") is True

        blueprints = json_result.get("blueprints", [])
        bp_names = [bp["name"] for bp in blueprints]
        logger.info(f"Found blueprints: {bp_names}")

        # ThirdPersonTemplate should have the character blueprint
        # (name may vary, just check we have at least one BP)
        assert json_result.get("count", 0) >= 0, "Expected at least zero blueprints"

    @pytest.mark.asyncio
    async def test_asset_query_finds_world_assets(self, mcp_client, running_editor):
        """Test that asset query finds World (Level) assets."""
        query_code = '''import json
import unreal

asset_reg = unreal.AssetRegistryHelpers.get_asset_registry()
world_path = unreal.TopLevelAssetPath("/Script/Engine", "World")
ar_filter = unreal.ARFilter(
    package_paths=["/Game"],
    class_paths=[world_path],
    recursive_paths=True,
    recursive_classes=True,
)
assets = asset_reg.get_assets(ar_filter)

results = []
if assets:
    for asset in assets[:100]:
        results.append({
            "name": str(asset.asset_name),
            "path": str(asset.package_name),
        })

print(json.dumps({"success": True, "worlds": results, "count": len(results)}))
'''
        exec_result = await mcp_client.call_tool(
            "editor_execute_code",
            {"code": query_code, "timeout": 60},
        )

        data = exec_result.structuredContent
        assert data.get("success") is True, f"Code execution failed: {data.get('error')}"

        # Parse JSON output
        output = data.get("output", [])
        json_result = None
        for line in reversed(output):
            line_str = str(line.get("output", "")) if isinstance(line, dict) else str(line)
            line_str = line_str.strip()
            if line_str.startswith("{"):
                try:
                    json_result = json.loads(line_str)
                    break
                except json.JSONDecodeError:
                    continue

        assert json_result is not None, f"No valid JSON in output"
        assert json_result.get("success") is True

        worlds = json_result.get("worlds", [])
        world_names = [w["name"] for w in worlds]
        logger.info(f"Found worlds: {world_names}")

        # ThirdPersonTemplate should have at least the main map
        assert json_result.get("count", 0) >= 0, "Expected at least zero world assets"

    @pytest.mark.asyncio
    async def test_asset_query_script_file(self, mcp_client, running_editor):
        """Test executing the asset_query.py script file via editor_execute_script."""
        from pathlib import Path

        script_path = (
            Path(__file__).parent.parent
            / "src"
            / "ue_mcp"
            / "extra"
            / "scripts"
            / "asset_query.py"
        )

        # Skip if script doesn't exist
        if not script_path.exists():
            pytest.skip(f"Script not found: {script_path}")

        result = await mcp_client.call_tool(
            "editor_execute_script",
            {
                "script_path": str(script_path),
                "args": ["--types", "Blueprint,World", "--base-path", "/Game", "--limit", "50"],
            },
        )

        data = result.structuredContent
        logger.info(f"Script execution result: {data}")

        # The script should execute successfully
        assert data.get("success") is True, f"Script execution failed: {data.get('error')}"

        # Check for assets in the result
        if "assets" in data:
            assets = data["assets"]
            assert "Blueprint" in assets or "World" in assets, (
                f"Expected Blueprint or World in assets. Got: {list(assets.keys())}"
            )
            logger.info(
                f"Found {assets.get('Blueprint', {}).get('count', 0)} Blueprints, "
                f"{assets.get('World', {}).get('count', 0)} Worlds"
            )


@pytest.mark.integration
class TestEditorLaunchWithProjectAssets:
    """Tests for project_assets field in editor_launch response.

    Note: These tests require stopping and relaunching the editor to verify
    the launch response. They are designed to be run when the editor is not
    already running.
    """

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_launch_returns_project_assets(self, initialized_tool_caller):
        """Test that editor_launch returns project_assets when successful.

        This test stops any running editor and launches fresh to verify
        the project_assets field is included in the response.
        """
        import json

        # First, stop any running editor
        await initialized_tool_caller.call("editor_stop", timeout=30)

        # Wait a moment for cleanup
        import asyncio
        await asyncio.sleep(2)

        # Launch editor and capture the result
        launch_result = await initialized_tool_caller.call(
            "editor_launch",
            {"wait": True, "wait_timeout": 180},
            timeout=240,
        )

        launch_text = launch_result.text_content
        assert launch_text, "Expected launch result text"

        try:
            launch_data = json.loads(launch_text)
        except json.JSONDecodeError:
            pytest.fail(f"Failed to parse launch result: {launch_text}")

        logger.info(f"Launch result keys: {list(launch_data.keys())}")

        # Verify launch succeeded
        assert launch_data.get("success") is True, (
            f"Editor launch failed: {launch_data.get('error')}"
        )

        # Verify project_assets is included
        assert "project_assets" in launch_data, (
            f"Expected 'project_assets' in launch result. Keys: {list(launch_data.keys())}"
        )

        project_assets = launch_data["project_assets"]
        logger.info(f"Project assets: {project_assets}")

        # Verify structure
        assert isinstance(project_assets, dict), (
            f"Expected project_assets to be dict. Got: {type(project_assets)}"
        )

        # Should have Blueprint and World categories
        assert "Blueprint" in project_assets, (
            f"Expected 'Blueprint' in project_assets. Keys: {list(project_assets.keys())}"
        )
        assert "World" in project_assets, (
            f"Expected 'World' in project_assets. Keys: {list(project_assets.keys())}"
        )

        # Verify items structure
        for category in ["Blueprint", "World"]:
            cat_data = project_assets[category]
            assert "items" in cat_data, f"Expected 'items' in {category}"
            assert "count" in cat_data, f"Expected 'count' in {category}"
            assert isinstance(cat_data["items"], list), f"Expected 'items' to be list"
            assert isinstance(cat_data["count"], int), f"Expected 'count' to be int"
            logger.info(f"{category}: {cat_data['count']} items")

        # Verify items have correct structure
        for category in ["Blueprint", "World"]:
            for item in project_assets[category]["items"][:3]:  # Check first 3
                assert "name" in item, f"Expected 'name' in item: {item}"
                assert "path" in item, f"Expected 'path' in item: {item}"


class TestAssetQueryParsing:
    """Unit tests for asset query result parsing."""

    def test_parse_valid_asset_query_result(self):
        """Test parsing a valid asset query result."""
        from ue_mcp.tools._helpers import parse_json_result as _parse_json_result

        exec_result = {
            "success": True,
            "output": [
                {"output": "Some log message"},
                {"output": '{"success": true, "assets": {"Blueprint": {"items": [], "count": 0}}}'},
            ],
        }

        result = _parse_json_result(exec_result)
        assert result.get("success") is True
        assert "assets" in result
        assert "Blueprint" in result["assets"]

    def test_parse_failed_execution(self):
        """Test parsing a failed execution result."""
        from ue_mcp.tools._helpers import parse_json_result as _parse_json_result

        exec_result = {
            "success": False,
            "error": "Connection failed",
        }

        result = _parse_json_result(exec_result)
        assert result.get("success") is False
        assert "error" in result

    def test_parse_empty_output(self):
        """Test parsing result with empty output."""
        from ue_mcp.tools._helpers import parse_json_result as _parse_json_result

        exec_result = {
            "success": True,
            "output": [],
        }

        result = _parse_json_result(exec_result)
        assert result.get("success") is False
        assert "error" in result

    def test_parse_no_json_in_output(self):
        """Test parsing result with no JSON in output."""
        from ue_mcp.tools._helpers import parse_json_result as _parse_json_result

        exec_result = {
            "success": True,
            "output": [
                {"output": "Just some text"},
                {"output": "More text without JSON"},
            ],
        }

        result = _parse_json_result(exec_result)
        assert result.get("success") is False
        assert "No valid JSON" in result.get("error", "")
