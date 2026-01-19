"""
End-to-end tests for autoconfig module.

These tests verify the complete configuration workflow from initial state
to fully configured project, using real file operations on copies of
the EmptyProjectTemplate fixture.
"""

import json
from pathlib import Path

import pytest

from ue_mcp.autoconfig import run_config_check


class TestEndToEndAutoconfig:
    """
    End-to-end tests for the complete configuration workflow.

    Each test uses an independent copy of the project fixture,
    ensuring test isolation.
    """

    def test_full_config_workflow(self, temp_project: Path):
        """Test complete config detection and fix workflow."""
        # 1. Initial state detection (no fix)
        result = run_config_check(temp_project, auto_fix=False)
        assert result["status"] == "needs_fix"
        assert result["python_plugin"]["enabled"] is False
        assert result["remote_execution"]["enabled"] is False

        # 2. Auto-fix
        result = run_config_check(temp_project, auto_fix=True)
        assert result["status"] in ("ok", "fixed")
        assert result["python_plugin"]["enabled"] is True
        assert result["remote_execution"]["enabled"] is True
        assert result["restart_needed"] is True

        # 3. Verify fix persisted
        result = run_config_check(temp_project, auto_fix=False)
        assert result["status"] == "ok"
        assert result["python_plugin"]["enabled"] is True
        assert result["remote_execution"]["enabled"] is True

    def test_config_with_additional_paths(self, temp_project: Path):
        """Test configuration with additional Python paths."""
        paths = ["D:/MyScripts", "D:/SharedLib", "E:/CustomTools"]
        result = run_config_check(temp_project, auto_fix=True, additional_paths=paths)

        assert result["additional_paths"]["configured"] is True
        assert result["additional_paths"]["paths"] == paths

        # Verify INI file content
        ini_path = temp_project / "Config" / "DefaultEngine.ini"
        content = ini_path.read_text(encoding="utf-8")

        for path in paths:
            assert f'+AdditionalPaths=(Path="{path}")' in content

    def test_idempotent_config(self, temp_project: Path):
        """Test that configuration is idempotent (multiple runs produce same result)."""
        # Run 3 times
        for i in range(3):
            result = run_config_check(temp_project, auto_fix=True)
            assert result["python_plugin"]["enabled"] is True
            assert result["remote_execution"]["enabled"] is True

        # Last run should not modify anything
        assert result["python_plugin"]["modified"] is False
        assert result["remote_execution"]["modified"] is False
        assert result["status"] == "ok"

    def test_verify_uproject_structure(self, temp_project: Path):
        """Test that .uproject file maintains valid structure after fix."""
        run_config_check(temp_project, auto_fix=True)

        uproject_path = temp_project / "EmptyProjectTemplate.uproject"
        with open(uproject_path, "r", encoding="utf-8") as f:
            config = json.load(f)

        # Verify required fields exist
        assert "FileVersion" in config
        assert "Plugins" in config

        # Verify plugins array structure
        plugins = config["Plugins"]
        assert isinstance(plugins, list)

        # Find Python plugins
        python_plugins = [
            p for p in plugins
            if p.get("Name") in ["PythonScriptPlugin", "PythonAutomationTest"]
        ]
        assert len(python_plugins) == 2

        for plugin in python_plugins:
            assert plugin.get("Enabled") is True

    def test_verify_ini_structure(self, temp_project: Path):
        """Test that DefaultEngine.ini maintains valid structure after fix."""
        run_config_check(temp_project, auto_fix=True)

        ini_path = temp_project / "Config" / "DefaultEngine.ini"
        content = ini_path.read_text(encoding="utf-8")

        # Verify section exists
        assert "[/Script/PythonScriptPlugin.PythonScriptPluginSettings]" in content

        # Verify required settings
        assert "bRemoteExecution=True" in content
        assert "bDeveloperMode=True" in content
        assert "RemoteExecutionMulticastBindAddress=0.0.0.0" in content

    def test_partial_config_detection(self, temp_project: Path):
        """Test detection of partially configured project."""
        # First, fully configure
        run_config_check(temp_project, auto_fix=True)

        # Manually break one setting by modifying INI - remove the setting entirely
        ini_path = temp_project / "Config" / "DefaultEngine.ini"
        content = ini_path.read_text(encoding="utf-8")
        # Remove the bRemoteExecution line entirely to simulate missing config
        lines = [line for line in content.splitlines() if "bRemoteExecution" not in line]
        ini_path.write_text("\n".join(lines), encoding="utf-8")

        # Check should detect the issue
        result = run_config_check(temp_project, auto_fix=False)
        # Python plugin should still be OK
        assert result["python_plugin"]["enabled"] is True
        # Remote execution should need fix (status should be needs_fix)
        assert result["status"] == "needs_fix"

    def test_additional_paths_incremental(self, temp_project: Path):
        """Test adding additional paths incrementally."""
        # First batch
        paths1 = ["D:/Scripts1"]
        result1 = run_config_check(temp_project, auto_fix=True, additional_paths=paths1)
        assert result1["additional_paths"]["configured"] is True

        # Second batch (should add new paths without removing old ones)
        paths2 = ["D:/Scripts2", "D:/Scripts3"]
        result2 = run_config_check(temp_project, auto_fix=True, additional_paths=paths2)
        assert result2["additional_paths"]["configured"] is True

        # Verify all paths exist
        ini_path = temp_project / "Config" / "DefaultEngine.ini"
        content = ini_path.read_text(encoding="utf-8")

        for path in paths1 + paths2:
            assert f'+AdditionalPaths=(Path="{path}")' in content

    def test_config_preserves_existing_plugins(self, temp_project: Path):
        """Test that autoconfig preserves existing plugins."""
        uproject_path = temp_project / "EmptyProjectTemplate.uproject"

        # Load original config
        with open(uproject_path, "r", encoding="utf-8") as f:
            original_config = json.load(f)

        original_plugins = original_config.get("Plugins", [])
        original_plugin_names = {p.get("Name") for p in original_plugins}

        # Run autoconfig
        run_config_check(temp_project, auto_fix=True)

        # Load updated config
        with open(uproject_path, "r", encoding="utf-8") as f:
            updated_config = json.load(f)

        updated_plugins = updated_config.get("Plugins", [])
        updated_plugin_names = {p.get("Name") for p in updated_plugins}

        # Original plugins should still exist
        assert original_plugin_names.issubset(updated_plugin_names)

        # Python plugins should be added
        assert "PythonScriptPlugin" in updated_plugin_names
        assert "PythonAutomationTest" in updated_plugin_names

    def test_config_preserves_existing_ini_sections(self, temp_project: Path):
        """Test that autoconfig preserves existing INI sections."""
        ini_path = temp_project / "Config" / "DefaultEngine.ini"

        # Read original content
        original_content = ini_path.read_text(encoding="utf-8")
        original_sections = [
            line.strip()
            for line in original_content.splitlines()
            if line.strip().startswith("[")
        ]

        # Run autoconfig
        run_config_check(temp_project, auto_fix=True)

        # Read updated content
        updated_content = ini_path.read_text(encoding="utf-8")

        # Original sections should still exist
        for section in original_sections:
            assert section in updated_content


class TestEndToEndEdgeCases:
    """End-to-end tests for edge cases."""

    def test_empty_config_directory(self, temp_project: Path):
        """Test with missing Config directory."""
        config_dir = temp_project / "Config"

        # Remove all INI files
        for ini_file in config_dir.glob("*.ini"):
            ini_file.unlink()

        # Remove Config directory
        config_dir.rmdir()

        # Run config check - should create Config dir and files
        result = run_config_check(temp_project, auto_fix=True)
        assert result["python_plugin"]["enabled"] is True
        assert result["remote_execution"]["enabled"] is True

        # Verify Config directory was created
        assert config_dir.exists()
        assert (config_dir / "DefaultEngine.ini").exists()

    def test_unicode_paths(self, temp_project: Path):
        """Test with unicode characters in additional paths."""
        paths = ["D:/スクリプト", "D:/脚本", "D:/Scripts 目录"]
        result = run_config_check(temp_project, auto_fix=True, additional_paths=paths)

        assert result["additional_paths"]["configured"] is True

        ini_path = temp_project / "Config" / "DefaultEngine.ini"
        content = ini_path.read_text(encoding="utf-8")

        for path in paths:
            assert path in content
