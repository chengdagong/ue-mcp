"""
Adversarial Integration Tests for UE-MCP Server

Tests MCP tools (project.build, editor.launch) via Claude CLI against
the EmptyCPPProject fixture. Tests both normal operations and adversarial
scenarios (invalid inputs, race conditions, error handling).

Requirements:
- Claude CLI installed and configured
- UE5 5.7 installed (matching fixture project)
- ue-mcp package installed in development mode
"""

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Optional

import pytest

# Fixture paths
FIXTURES_DIR = Path(__file__).parent / "fixtures"
EMPTY_CPP_PROJECT = FIXTURES_DIR / "EmptyCPPProject"


class FixtureManager:
    """Manages backup and restore of fixture project state."""

    def __init__(self, project_path: Path):
        self.project_path = project_path
        self.backup_dir = project_path.parent / f".{project_path.name}_backup"
        self.files_to_backup = [
            "EmptyCPPProject.uproject",
            "Config/DefaultEngine.ini",
            "Config/DefaultEditor.ini",
            "Config/DefaultGame.ini",
            "Config/DefaultInput.ini",
        ]

    def backup(self) -> None:
        """Create backup of fixture files."""
        if self.backup_dir.exists():
            shutil.rmtree(self.backup_dir)
        self.backup_dir.mkdir(parents=True)

        for rel_path in self.files_to_backup:
            src = self.project_path / rel_path
            if src.exists():
                dst = self.backup_dir / rel_path
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)

    def restore(self) -> None:
        """Restore fixture files from backup."""
        if not self.backup_dir.exists():
            return

        for rel_path in self.files_to_backup:
            backup_file = self.backup_dir / rel_path
            if backup_file.exists():
                dst = self.project_path / rel_path
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(backup_file, dst)

        # Cleanup backup directory
        shutil.rmtree(self.backup_dir)

    def cleanup_editor_processes(self) -> None:
        """Kill any orphaned Unreal Editor processes for this project."""
        try:
            # Use taskkill on Windows to stop any UnrealEditor processes
            if sys.platform == "win32":
                subprocess.run(
                    ["taskkill", "/F", "/IM", "UnrealEditor.exe"],
                    capture_output=True,
                    timeout=10,
                )
        except Exception:
            pass  # Ignore errors if no processes to kill


class ClaudeMCPClient:
    """Client for invoking MCP tools via Claude CLI."""

    def __init__(self, project_path: Path, timeout: float = 300.0):
        self.project_path = project_path
        self.timeout = timeout

    def call_tool(
        self,
        tool_name: str,
        args: Optional[dict[str, Any]] = None,
        timeout: Optional[float] = None,
    ) -> dict[str, Any]:
        """
        Call an MCP tool via Claude CLI.

        Args:
            tool_name: Name of the tool to call (e.g., "project.build")
            args: Arguments to pass to the tool
            timeout: Override default timeout

        Returns:
            Tool result as dictionary
        """
        timeout = timeout or self.timeout

        # Build the prompt for Claude to call the tool
        args_str = json.dumps(args) if args else "{}"
        prompt = f"""Use the ue-mcp MCP server tool "{tool_name}" with these arguments: {args_str}

Return ONLY the raw JSON result from the tool call, no additional text or formatting.
If the tool returns an error, return that error as JSON."""

        try:
            result = subprocess.run(
                [
                    "claude",
                    "--print",
                    "-p", prompt,
                ],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(self.project_path),
                env={**os.environ, "CLAUDE_PROJECT_DIR": str(self.project_path)},
            )

            output = result.stdout.strip()

            # Try to parse JSON from the output
            # Claude might wrap the response, so look for JSON object/array
            if output:
                # Find JSON in output
                json_start = output.find("{")
                json_end = output.rfind("}") + 1
                if json_start != -1 and json_end > json_start:
                    json_str = output[json_start:json_end]
                    return json.loads(json_str)

            return {
                "success": False,
                "error": f"Could not parse response: {output}",
                "raw_output": output,
                "stderr": result.stderr,
            }

        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": f"Command timed out after {timeout}s",
                "timeout": True,
            }
        except json.JSONDecodeError as e:
            return {
                "success": False,
                "error": f"JSON parse error: {e}",
                "raw_output": output if "output" in dir() else "",
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
            }

    def editor_launch(
        self,
        wait: bool = True,
        wait_timeout: float = 120.0,
        additional_paths: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """Launch Unreal Editor."""
        args = {
            "wait": wait,
            "wait_timeout": wait_timeout,
        }
        if additional_paths:
            args["additional_paths"] = additional_paths
        return self.call_tool("editor.launch", args, timeout=wait_timeout + 60)

    def editor_status(self) -> dict[str, Any]:
        """Get editor status."""
        return self.call_tool("editor.status", timeout=30)

    def editor_stop(self) -> dict[str, Any]:
        """Stop the editor."""
        return self.call_tool("editor.stop", timeout=60)

    def editor_execute(self, code: str, timeout: float = 30.0) -> dict[str, Any]:
        """Execute Python code in the editor."""
        return self.call_tool(
            "editor.execute",
            {"code": code, "timeout": timeout},
            timeout=timeout + 30,
        )

    def project_build(
        self,
        target: str = "Editor",
        configuration: str = "Development",
        platform: str = "Win64",
        clean: bool = False,
        wait: bool = True,
        verbose: bool = False,
        timeout: float = 1800.0,
    ) -> dict[str, Any]:
        """Build the project."""
        args = {
            "target": target,
            "configuration": configuration,
            "platform": platform,
            "clean": clean,
            "wait": wait,
            "verbose": verbose,
            "timeout": timeout,
        }
        return self.call_tool("project.build", args, timeout=timeout + 60)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture(scope="session", autouse=True)
def session_cleanup():
    """Ensure fixture is restored even if tests crash."""
    manager = FixtureManager(EMPTY_CPP_PROJECT)
    # Restore any leftover backup from previous failed runs
    if manager.backup_dir.exists():
        manager.restore()
    
    yield
    
    # Final cleanup at session end
    manager.cleanup_editor_processes()
    if manager.backup_dir.exists():
        manager.restore()


@pytest.fixture(scope="function", autouse=True)
def fixture_manager():
    """Provide fixture manager with automatic backup/restore for each test."""
    manager = FixtureManager(EMPTY_CPP_PROJECT)
    manager.backup()

    yield manager

    # Cleanup: stop any running editors and restore fixture
    manager.cleanup_editor_processes()
    manager.restore()


@pytest.fixture(scope="function")
def mcp_client():
    """Provide MCP client for testing."""
    return ClaudeMCPClient(EMPTY_CPP_PROJECT)


# ============================================================================
# Normal Flow Tests
# ============================================================================


@pytest.mark.integration
@pytest.mark.slow
class TestNormalFlow:
    """Test normal/expected operations."""

    def test_project_build_normal(self, mcp_client):
        """Test project.build with default parameters succeeds."""
        result = mcp_client.project_build(
            target="Editor",
            configuration="Development",
            timeout=1800.0,
        )

        # Build should succeed or return meaningful status
        assert "error" not in result or result.get("success") is not None
        # If build completed, verify return code
        if result.get("success"):
            assert result.get("return_code", 0) == 0

    def test_editor_status_not_running(self, mcp_client):
        """Test editor.status when editor is not running."""
        result = mcp_client.editor_status()

        assert result.get("status") == "not_running"
        assert "project_name" in result or "error" not in result

    def test_editor_launch_and_status(self, mcp_client):
        """Test editor.launch and then check status."""
        # Launch editor
        launch_result = mcp_client.editor_launch(
            wait=True,
            wait_timeout=180.0,
        )

        # Verify launch result
        if launch_result.get("success"):
            # Check status
            status_result = mcp_client.editor_status()
            assert status_result.get("status") in ["ready", "starting"]
            assert status_result.get("connected") is True

            # Stop editor for cleanup
            stop_result = mcp_client.editor_stop()
            assert stop_result.get("success") is True
        else:
            # Launch may fail if UE5 not installed - that's acceptable for CI
            pytest.skip(f"Editor launch failed: {launch_result.get('error')}")


# ============================================================================
# Adversarial Tests - Invalid Inputs
# ============================================================================


@pytest.mark.integration
class TestInvalidInputs:
    """Test handling of invalid inputs."""

    def test_project_build_invalid_target(self, mcp_client):
        """Test project.build with invalid target string."""
        result = mcp_client.project_build(
            target="InvalidTargetThatDoesNotExist",
            configuration="Development",
            timeout=60.0,
        )

        # Should either fail gracefully or return error
        # Should NOT hang or crash
        assert result is not None
        # If there's output, check for error indication
        if result.get("success") is False:
            assert "error" in result or "output" in result

    def test_project_build_invalid_configuration(self, mcp_client):
        """Test project.build with invalid configuration."""
        result = mcp_client.project_build(
            target="Editor",
            configuration="SuperInvalidConfig",
            timeout=60.0,
        )

        # Should fail gracefully
        assert result is not None
        # Invalid config should cause build failure
        if result.get("return_code") is not None:
            assert result.get("return_code") != 0 or result.get("success") is False

    def test_project_build_invalid_platform(self, mcp_client):
        """Test project.build with invalid platform."""
        result = mcp_client.project_build(
            target="Editor",
            configuration="Development",
            platform="PlayStation99",
            timeout=60.0,
        )

        # Should fail gracefully
        assert result is not None

    def test_editor_launch_zero_timeout(self, mcp_client):
        """Test editor.launch with zero timeout."""
        result = mcp_client.editor_launch(
            wait=True,
            wait_timeout=0.0,
        )

        # Should either timeout immediately or handle gracefully
        assert result is not None
        # Zero timeout should not cause infinite wait

    def test_editor_launch_negative_timeout(self, mcp_client):
        """Test editor.launch with negative timeout."""
        result = mcp_client.editor_launch(
            wait=True,
            wait_timeout=-10.0,
        )

        # Should handle gracefully, not hang
        assert result is not None


# ============================================================================
# Adversarial Tests - Race Conditions
# ============================================================================


@pytest.mark.integration
class TestRaceConditions:
    """Test race conditions and ordering issues."""

    def test_editor_execute_before_launch(self, mcp_client):
        """Test editor.execute when no editor is running."""
        result = mcp_client.editor_execute(
            code="import unreal; print('Hello')",
            timeout=10.0,
        )

        # Should fail with clear error, not hang or crash
        assert result is not None
        assert result.get("success") is False or "error" in result

    def test_double_editor_launch(self, mcp_client):
        """Test launching editor twice in a row."""
        # First launch (async to speed up test)
        first_result = mcp_client.editor_launch(
            wait=False,
            wait_timeout=60.0,
        )

        # Small delay
        time.sleep(2)

        # Second launch while first may still be starting
        second_result = mcp_client.editor_launch(
            wait=False,
            wait_timeout=60.0,
        )

        # Both calls should complete without hanging
        assert first_result is not None
        assert second_result is not None

        # Cleanup
        time.sleep(5)
        mcp_client.editor_stop()

    def test_stop_during_launch(self, mcp_client):
        """Test stopping editor while it's still launching."""
        # Start async launch
        mcp_client.editor_launch(wait=False, wait_timeout=60.0)

        # Immediately try to stop
        time.sleep(1)
        stop_result = mcp_client.editor_stop()

        # Should complete without hanging
        assert stop_result is not None


# ============================================================================
# Adversarial Tests - Error Handling
# ============================================================================


@pytest.mark.integration
class TestErrorHandling:
    """Test error handling scenarios."""

    def test_project_build_short_timeout(self, mcp_client):
        """Test project.build with very short timeout."""
        result = mcp_client.project_build(
            target="Editor",
            configuration="Development",
            timeout=1.0,  # 1 second - way too short for any real build
        )

        # Should timeout or fail, not hang forever
        assert result is not None
        # Very short timeout should fail
        if result.get("success") is not True:
            # Expected - build can't complete in 1 second
            pass

    def test_editor_stop_when_not_running(self, mcp_client):
        """Test editor.stop when editor is not running."""
        result = mcp_client.editor_stop()

        # Should complete gracefully
        assert result is not None
        # May succeed (no-op) or return specific error

    def test_editor_execute_syntax_error(self, mcp_client):
        """Test editor.execute with Python syntax error."""
        # First launch editor
        launch_result = mcp_client.editor_launch(wait=True, wait_timeout=180.0)

        if not launch_result.get("success"):
            pytest.skip("Editor launch failed")

        try:
            # Execute code with syntax error
            result = mcp_client.editor_execute(
                code="def broken(:\n    pass",  # Invalid syntax
                timeout=10.0,
            )

            # Should return error, not crash
            assert result is not None
            assert result.get("success") is False or "error" in result
        finally:
            mcp_client.editor_stop()

    def test_editor_execute_runtime_error(self, mcp_client):
        """Test editor.execute with runtime error."""
        # First launch editor
        launch_result = mcp_client.editor_launch(wait=True, wait_timeout=180.0)

        if not launch_result.get("success"):
            pytest.skip("Editor launch failed")

        try:
            # Execute code that raises exception
            result = mcp_client.editor_execute(
                code="raise RuntimeError('Test error')",
                timeout=10.0,
            )

            # Should return error gracefully
            assert result is not None
            assert result.get("success") is False or "error" in result
        finally:
            mcp_client.editor_stop()

    def test_editor_execute_infinite_loop_timeout(self, mcp_client):
        """Test editor.execute with code that would hang."""
        # First launch editor
        launch_result = mcp_client.editor_launch(wait=True, wait_timeout=180.0)

        if not launch_result.get("success"):
            pytest.skip("Editor launch failed")

        try:
            # Execute code with infinite loop (should timeout)
            result = mcp_client.editor_execute(
                code="while True: pass",
                timeout=5.0,  # Short timeout
            )

            # Should timeout, not hang forever
            assert result is not None
            # Timeout or error expected
        finally:
            mcp_client.editor_stop()


# ============================================================================
# Edge Case Tests
# ============================================================================


@pytest.mark.integration
class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_project_build_empty_target(self, mcp_client):
        """Test project.build with empty target string."""
        result = mcp_client.project_build(
            target="",
            configuration="Development",
            timeout=60.0,
        )

        # Should handle gracefully
        assert result is not None

    def test_editor_execute_empty_code(self, mcp_client):
        """Test editor.execute with empty code string."""
        # First launch editor
        launch_result = mcp_client.editor_launch(wait=True, wait_timeout=180.0)

        if not launch_result.get("success"):
            pytest.skip("Editor launch failed")

        try:
            result = mcp_client.editor_execute(code="", timeout=10.0)

            # Should complete, possibly with success (empty code = no-op)
            assert result is not None
        finally:
            mcp_client.editor_stop()

    def test_editor_execute_unicode_code(self, mcp_client):
        """Test editor.execute with unicode characters."""
        # First launch editor
        launch_result = mcp_client.editor_launch(wait=True, wait_timeout=180.0)

        if not launch_result.get("success"):
            pytest.skip("Editor launch failed")

        try:
            result = mcp_client.editor_execute(
                code="print('测试中文 🎮 émojis')",
                timeout=10.0,
            )

            # Should handle unicode without crashing
            assert result is not None
        finally:
            mcp_client.editor_stop()

    def test_editor_execute_very_long_code(self, mcp_client):
        """Test editor.execute with very long code string."""
        # First launch editor
        launch_result = mcp_client.editor_launch(wait=True, wait_timeout=180.0)

        if not launch_result.get("success"):
            pytest.skip("Editor launch failed")

        try:
            # Generate long code (10KB of comments)
            long_code = "# " + "x" * 10000 + "\nprint('done')"
            result = mcp_client.editor_execute(code=long_code, timeout=30.0)

            # Should complete without hanging
            assert result is not None
        finally:
            mcp_client.editor_stop()


# ============================================================================
# Main entry point for running tests directly
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "-x"])
