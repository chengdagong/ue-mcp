"""Tests for ue_mcp.autoconfig module."""

import json
from pathlib import Path

import pytest

from ue_mcp.autoconfig import (
    check_additional_paths,
    check_python_plugin,
    check_remote_execution,
    run_config_check,
)


class TestCheckPythonPlugin:
    """Tests for check_python_plugin function."""

    def test_detect_missing_plugins(self, temp_uproject: Path):
        """Test detecting missing Python plugins."""
        enabled, modified, msg = check_python_plugin(temp_uproject, auto_fix=False)
        assert enabled is False
        assert modified is False
        # Message should mention missing plugins
        assert "PythonScriptPlugin" in msg or "not in" in msg.lower()

    def test_auto_fix_plugins(self, temp_uproject: Path):
        """Test auto-fixing missing Python plugins."""
        # First call: auto-fix
        enabled, modified, msg = check_python_plugin(temp_uproject, auto_fix=True)
        assert enabled is True
        assert modified is True
        assert "Added" in msg or "Enabled" in msg

        # Second call: should be already configured
        enabled2, modified2, msg2 = check_python_plugin(temp_uproject, auto_fix=True)
        assert enabled2 is True
        assert modified2 is False
        assert "correctly configured" in msg2.lower()

    def test_verify_plugin_content(self, temp_uproject: Path):
        """Test that auto-fix actually adds plugins to file."""
        check_python_plugin(temp_uproject, auto_fix=True)

        with open(temp_uproject, "r", encoding="utf-8") as f:
            config = json.load(f)

        plugins = config.get("Plugins", [])
        plugin_names = [p.get("Name") for p in plugins]

        assert "PythonScriptPlugin" in plugin_names
        assert "PythonAutomationTest" in plugin_names

        # Verify they are enabled
        for plugin in plugins:
            if plugin.get("Name") in ["PythonScriptPlugin", "PythonAutomationTest"]:
                assert plugin.get("Enabled") is True

    def test_handle_invalid_json(self, tmp_path: Path):
        """Test handling of invalid JSON file."""
        invalid_file = tmp_path / "Invalid.uproject"
        invalid_file.write_text("not valid json", encoding="utf-8")

        enabled, modified, msg = check_python_plugin(invalid_file, auto_fix=False)
        assert enabled is False
        assert "JSON" in msg or "Parse" in msg

    def test_handle_missing_file(self, tmp_path: Path):
        """Test handling of missing file."""
        missing_file = tmp_path / "Missing.uproject"

        enabled, modified, msg = check_python_plugin(missing_file, auto_fix=False)
        assert enabled is False
        assert "Failed" in msg


class TestCheckRemoteExecution:
    """Tests for check_remote_execution function."""

    def test_detect_missing_settings(self, temp_engine_ini: Path):
        """Test detecting missing remote execution settings."""
        enabled, modified, messages = check_remote_execution(
            temp_engine_ini, auto_fix=False
        )
        assert enabled is False
        assert modified is False
        # Should report missing settings
        assert len(messages) > 0

    def test_auto_fix_settings(self, temp_engine_ini: Path):
        """Test auto-fixing remote execution settings."""
        enabled, modified, messages = check_remote_execution(
            temp_engine_ini, auto_fix=True
        )
        assert enabled is True
        assert modified is True

        # Verify file content
        content = temp_engine_ini.read_text(encoding="utf-8")
        assert "bRemoteExecution=True" in content
        assert "bDeveloperMode=True" in content
        assert "RemoteExecutionMulticastBindAddress=0.0.0.0" in content

    def test_already_configured(self, temp_engine_ini: Path):
        """Test detection of already configured settings."""
        # First fix
        check_remote_execution(temp_engine_ini, auto_fix=True)

        # Second call should not modify
        enabled, modified, messages = check_remote_execution(
            temp_engine_ini, auto_fix=True
        )
        assert enabled is True
        assert modified is False

    def test_create_missing_ini_file(self, tmp_path: Path):
        """Test creating missing DefaultEngine.ini."""
        ini_path = tmp_path / "Config" / "DefaultEngine.ini"
        assert not ini_path.exists()

        enabled, modified, messages = check_remote_execution(ini_path, auto_fix=True)
        assert enabled is True
        assert modified is True
        assert ini_path.exists()

        content = ini_path.read_text(encoding="utf-8")
        assert "PythonScriptPlugin" in content

    def test_detect_missing_ini_without_fix(self, tmp_path: Path):
        """Test detecting missing INI file without auto-fix."""
        ini_path = tmp_path / "Config" / "DefaultEngine.ini"

        enabled, modified, messages = check_remote_execution(ini_path, auto_fix=False)
        assert enabled is False
        assert modified is False
        assert "does not exist" in messages[0]


class TestCheckAdditionalPaths:
    """Tests for check_additional_paths function."""

    def test_add_paths(self, temp_engine_ini: Path):
        """Test adding additional Python paths."""
        # First ensure remote execution is configured (creates section)
        check_remote_execution(temp_engine_ini, auto_fix=True)

        paths = ["D:/Scripts", "D:/MyLib"]
        configured, modified, messages = check_additional_paths(
            temp_engine_ini, paths, auto_fix=True
        )
        assert configured is True
        assert modified is True

        content = temp_engine_ini.read_text(encoding="utf-8")
        assert '+AdditionalPaths=(Path="D:/Scripts")' in content
        assert '+AdditionalPaths=(Path="D:/MyLib")' in content

    def test_already_configured_paths(self, temp_engine_ini: Path):
        """Test detecting already configured paths."""
        check_remote_execution(temp_engine_ini, auto_fix=True)

        paths = ["D:/Scripts"]
        # First add
        check_additional_paths(temp_engine_ini, paths, auto_fix=True)

        # Second call should not modify
        configured, modified, messages = check_additional_paths(
            temp_engine_ini, paths, auto_fix=True
        )
        assert configured is True
        assert modified is False

    def test_empty_paths_list(self, temp_engine_ini: Path):
        """Test with empty paths list."""
        configured, modified, messages = check_additional_paths(
            temp_engine_ini, [], auto_fix=True
        )
        assert configured is True
        assert modified is False
        assert "No additional paths" in messages[0]

    def test_missing_section(self, temp_engine_ini: Path):
        """Test when section doesn't exist."""
        # Don't configure remote execution first
        paths = ["D:/Scripts"]
        configured, modified, messages = check_additional_paths(
            temp_engine_ini, paths, auto_fix=True
        )
        assert configured is False
        assert "Section missing" in messages[0]


class TestRunConfigCheck:
    """Tests for run_config_check function."""

    def test_full_config_check_detect_only(self, temp_project: Path):
        """Test full config check without auto-fix."""
        result = run_config_check(temp_project, auto_fix=False)

        assert result["status"] == "needs_fix"
        assert result["python_plugin"]["enabled"] is False
        assert result["remote_execution"]["enabled"] is False

    def test_full_config_check_auto_fix(self, temp_project: Path):
        """Test full config check with auto-fix."""
        result = run_config_check(temp_project, auto_fix=True)

        assert result["status"] in ("ok", "fixed")
        assert result["python_plugin"]["enabled"] is True
        assert result["remote_execution"]["enabled"] is True
        assert result["restart_needed"] is True

    def test_config_with_additional_paths(self, temp_project: Path):
        """Test config check with additional paths."""
        paths = ["D:/MyScripts", "D:/SharedLib"]
        result = run_config_check(temp_project, auto_fix=True, additional_paths=paths)

        assert result["additional_paths"]["configured"] is True
        assert result["additional_paths"]["paths"] == paths

        # Verify INI file
        ini_path = temp_project / "Config" / "DefaultEngine.ini"
        content = ini_path.read_text(encoding="utf-8")
        for path in paths:
            assert f'+AdditionalPaths=(Path="{path}")' in content

    def test_idempotent_config(self, temp_project: Path):
        """Test that config check is idempotent."""
        # Run 3 times
        for _ in range(3):
            result = run_config_check(temp_project, auto_fix=True)
            assert result["python_plugin"]["enabled"] is True
            assert result["remote_execution"]["enabled"] is True

        # Last run should not modify anything
        assert result["python_plugin"]["modified"] is False
        assert result["remote_execution"]["modified"] is False

    def test_missing_uproject(self, tmp_path: Path):
        """Test with missing .uproject file."""
        result = run_config_check(tmp_path, auto_fix=True)

        assert result["status"] == "error"
        assert "No .uproject" in result["summary"]

    def test_summary_messages(self, temp_project: Path):
        """Test summary message generation."""
        # First run: should fix issues
        result = run_config_check(temp_project, auto_fix=True)
        assert "Fixed" in result["summary"]

        # Second run: should be ok
        result = run_config_check(temp_project, auto_fix=True)
        assert "correct" in result["summary"].lower()
