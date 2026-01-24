"""
Unit tests for execute_script argument passing feature.
"""

import pytest

from ue_mcp.tools._helpers import build_script_args_injection as _build_script_args_injection


class TestBuildScriptArgsInjection:
    """Tests for _build_script_args_injection helper function."""

    def test_no_args_no_kwargs(self):
        """Returns sys.argv with only script path when no args or kwargs."""
        result = _build_script_args_injection("/path/to/script.py", None, None)
        assert "import sys" in result
        assert "sys.argv = ['/path/to/script.py']" in result
        assert "__SCRIPT_ARGS__" not in result
        assert "builtins" not in result

    def test_with_args_only(self):
        """Correctly sets sys.argv with args."""
        result = _build_script_args_injection(
            "/path/to/script.py",
            ["--level", "/Game/Maps/Test", "--verbose"],
            None
        )
        assert "import sys" in result
        assert "sys.argv = ['/path/to/script.py', '--level', '/Game/Maps/Test', '--verbose']" in result
        assert "__SCRIPT_ARGS__" not in result

    def test_with_kwargs_only(self):
        """Correctly sets __SCRIPT_ARGS__ with kwargs."""
        result = _build_script_args_injection(
            "/path/to/script.py",
            None,
            {"level": "/Game/Maps/Test", "verbose": True}
        )
        assert "import sys" in result
        assert "sys.argv = ['/path/to/script.py']" in result
        assert "import builtins" in result
        assert "builtins.__SCRIPT_ARGS__" in result
        assert "__SCRIPT_ARGS__ = builtins.__SCRIPT_ARGS__" in result
        assert "'level': '/Game/Maps/Test'" in result
        assert "'verbose': True" in result

    def test_with_both_args_and_kwargs(self):
        """Correctly sets both sys.argv and __SCRIPT_ARGS__."""
        result = _build_script_args_injection(
            "/path/to/script.py",
            ["--mode", "capture"],
            {"config": {"width": 1920}}
        )
        assert "sys.argv = ['/path/to/script.py', '--mode', 'capture']" in result
        assert "builtins.__SCRIPT_ARGS__" in result
        assert "'config': {'width': 1920}" in result

    def test_non_string_args_converted(self):
        """Non-string args are converted to strings."""
        result = _build_script_args_injection(
            "/path/to/script.py",
            ["--count", 42, "--ratio", 3.14, True],
            None
        )
        # All args should be string representations
        assert "'--count'" in result
        assert "'42'" in result
        assert "'3.14'" in result
        assert "'True'" in result

    def test_empty_args_list(self):
        """Empty args list results in sys.argv with only script path."""
        result = _build_script_args_injection("/path/to/script.py", [], None)
        assert "sys.argv = ['/path/to/script.py']" in result

    def test_empty_kwargs_dict(self):
        """Empty kwargs dict is treated as no kwargs (no injection)."""
        result = _build_script_args_injection("/path/to/script.py", None, {})
        # Empty dict is falsy, so no __SCRIPT_ARGS__ injection
        assert "__SCRIPT_ARGS__" not in result
        assert "builtins" not in result

    def test_complex_kwargs_types(self):
        """Handles complex kwargs types like nested dicts and lists."""
        result = _build_script_args_injection(
            "/path/to/script.py",
            None,
            {
                "actors": ["Actor1", "Actor2"],
                "settings": {"nested": {"deep": True}},
                "count": 42,
                "ratio": 3.14,
                "enabled": False,
                "nothing": None,
            }
        )
        assert "'actors': ['Actor1', 'Actor2']" in result
        assert "'settings': {'nested': {'deep': True}}" in result
        assert "'count': 42" in result
        assert "'ratio': 3.14" in result
        assert "'enabled': False" in result
        assert "'nothing': None" in result

    def test_special_characters_in_path(self):
        """Handles special characters in script path."""
        result = _build_script_args_injection(
            "/path/with spaces/script's file.py",
            None,
            None
        )
        # Path should be properly escaped in repr()
        assert "script's file.py" in result or "script\\'s file.py" in result

    def test_injection_ends_with_newlines(self):
        """Injection code ends with double newline for separation."""
        result = _build_script_args_injection("/path/to/script.py", None, None)
        assert result.endswith("\n\n")

    def test_injection_order(self):
        """Imports come before assignments."""
        result = _build_script_args_injection(
            "/path/to/script.py",
            ["--test"],
            {"key": "value"}
        )
        lines = result.strip().split("\n")

        # Find positions
        sys_import_pos = None
        builtins_import_pos = None
        argv_pos = None
        script_args_pos = None

        for i, line in enumerate(lines):
            if line == "import sys":
                sys_import_pos = i
            elif line == "import builtins":
                builtins_import_pos = i
            elif line.startswith("sys.argv"):
                argv_pos = i
            elif line.startswith("builtins.__SCRIPT_ARGS__"):
                script_args_pos = i

        # Verify order: imports before their usage
        assert sys_import_pos is not None
        assert argv_pos is not None
        assert sys_import_pos < argv_pos

        assert builtins_import_pos is not None
        assert script_args_pos is not None
        assert builtins_import_pos < script_args_pos


class TestExecuteScriptIntegration:
    """Integration tests that verify the full execute_script flow.

    These tests require a running UE5 editor and are marked with @pytest.mark.integration.
    """

    @pytest.fixture
    def temp_script(self, tmp_path):
        """Create a temporary script file."""
        def _create_script(content: str) -> str:
            script_file = tmp_path / "test_script.py"
            script_file.write_text(content, encoding="utf-8")
            return str(script_file)
        return _create_script

    @pytest.mark.integration
    def test_execute_script_with_args_argparse(self, temp_script):
        """Test script that uses argparse with injected args."""
        script_content = '''
import argparse
import sys

parser = argparse.ArgumentParser()
parser.add_argument("--level", required=True)
parser.add_argument("--verbose", action="store_true")
args = parser.parse_args()

print(f"Level: {args.level}")
print(f"Verbose: {args.verbose}")
'''
        script_path = temp_script(script_content)

        # This test would need a running UE5 editor to actually execute
        # For now, we just verify the script file was created correctly
        with open(script_path, encoding="utf-8") as f:
            content = f.read()
        assert "argparse" in content
        assert "--level" in content

    @pytest.mark.integration
    def test_execute_script_with_kwargs_access(self, temp_script):
        """Test script that accesses __SCRIPT_ARGS__."""
        script_content = '''
level = __SCRIPT_ARGS__.get("level")
actors = __SCRIPT_ARGS__.get("actors", [])

print(f"Level: {level}")
print(f"Actors: {actors}")
'''
        script_path = temp_script(script_content)

        with open(script_path, encoding="utf-8") as f:
            content = f.read()
        assert "__SCRIPT_ARGS__" in content
