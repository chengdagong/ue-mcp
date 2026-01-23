"""
Unit tests for code_inspector module.
"""

import pytest

from ue_mcp.code_inspector import (
    BaseChecker,
    BlockingCallChecker,
    CodeInspector,
    InspectionIssue,
    InspectionResult,
    IssueSeverity,
    inspect_code,
)


class TestBlockingCallChecker:
    """Tests for BlockingCallChecker."""

    def test_detects_time_sleep_direct(self):
        """Detects time.sleep() direct call as WARNING."""
        code = """
import time
time.sleep(1)
"""
        result = inspect_code(code)
        assert result.allowed  # WARNING allows execution
        assert result.warning_count == 1
        assert result.error_count == 0
        assert "time.sleep" in result.issues[0].message

    def test_detects_time_sleep_with_alias(self):
        """Detects time.sleep() when time is imported with alias as WARNING."""
        code = """
import time as t
t.sleep(1)
"""
        result = inspect_code(code)
        assert result.allowed  # WARNING allows execution
        assert result.warning_count == 1
        assert result.error_count == 0
        assert "time.sleep" in result.issues[0].message

    def test_detects_from_import_sleep(self):
        """Detects sleep() when imported directly from time module as WARNING."""
        code = """
from time import sleep
sleep(1)
"""
        result = inspect_code(code)
        assert result.allowed  # WARNING allows execution
        assert result.warning_count == 1
        assert result.error_count == 0
        assert "time.sleep" in result.issues[0].message

    def test_detects_from_import_sleep_with_alias(self):
        """Detects sleep() when imported with alias from time module as WARNING."""
        code = """
from time import sleep as s
s(1)
"""
        result = inspect_code(code)
        assert result.allowed  # WARNING allows execution
        assert result.warning_count == 1
        assert result.error_count == 0
        assert "time.sleep" in result.issues[0].message

    def test_allows_other_time_functions(self):
        """Allows other time module functions like time.time()."""
        code = """
import time
t = time.time()
"""
        result = inspect_code(code)
        assert result.allowed
        assert result.error_count == 0

    def test_allows_code_without_time_module(self):
        """Allows code that doesn't use time module."""
        code = """
import unreal
unreal.log("Hello")
"""
        result = inspect_code(code)
        assert result.allowed
        assert result.error_count == 0

    def test_detects_multiple_sleep_calls(self):
        """Detects multiple time.sleep() calls as WARNINGs."""
        code = """
import time
time.sleep(1)
time.sleep(2)
"""
        result = inspect_code(code)
        assert result.allowed  # WARNING allows execution
        assert result.warning_count == 2
        assert result.error_count == 0

    def test_line_number_tracking(self):
        """Correctly tracks line numbers of blocking calls."""
        code = """import time
# comment
time.sleep(1)
"""
        result = inspect_code(code)
        assert result.allowed  # WARNING allows execution
        assert result.warning_count == 1
        assert result.issues[0].line_number == 3

    def test_suggestion_provided(self):
        """Provides suggestion for how to fix the issue."""
        code = """
import time
time.sleep(1)
"""
        result = inspect_code(code)
        assert result.issues[0].suggestion is not None
        assert "tick" in result.issues[0].suggestion.lower()


class TestCodeInspector:
    """Tests for CodeInspector class."""

    def test_custom_checker_registration(self):
        """Can register custom checkers."""
        import ast
        from typing import List

        class CustomChecker(BaseChecker):
            @property
            def name(self) -> str:
                return "CustomChecker"

            @property
            def description(self) -> str:
                return "Custom test checker"

            def check(self, tree: ast.AST, code: str) -> List[InspectionIssue]:
                if "forbidden" in code:
                    return [
                        InspectionIssue(
                            severity=IssueSeverity.ERROR,
                            checker=self.name,
                            message="Found forbidden keyword",
                        )
                    ]
                return []

        inspector = CodeInspector()
        inspector.register_checker(CustomChecker())

        # Test with forbidden code
        result = inspector.inspect("x = 'forbidden'")
        assert not result.allowed
        assert any("forbidden" in i.message for i in result.issues)

        # Test with allowed code
        result = inspector.inspect("x = 'allowed'")
        # Note: BlockingCallChecker is also registered by default
        assert result.allowed or not any("forbidden" in i.message for i in result.issues)

    def test_handles_syntax_errors_gracefully(self):
        """Handles syntax errors gracefully."""
        code = "def broken("
        result = inspect_code(code)
        # Syntax errors are handled by extract_import_statements, not code_inspector
        # So code_inspector should return allowed=True for unparseable code
        assert result.allowed

    def test_empty_code(self):
        """Handles empty code."""
        result = inspect_code("")
        assert result.allowed
        assert len(result.issues) == 0


class TestInspectionResult:
    """Tests for InspectionResult class."""

    def test_format_error(self):
        """format_error() produces readable output."""
        result = InspectionResult(
            allowed=False,
            issues=[
                InspectionIssue(
                    severity=IssueSeverity.ERROR,
                    checker="TestChecker",
                    message="Test error message",
                    line_number=5,
                    suggestion="Fix it this way",
                )
            ],
        )
        error_text = result.format_error()
        assert "TestChecker" in error_text
        assert "line 5" in error_text
        assert "Test error message" in error_text
        assert "Fix it this way" in error_text

    def test_to_dict(self):
        """to_dict() produces correct dictionary."""
        result = InspectionResult(
            allowed=False,
            issues=[
                InspectionIssue(
                    severity=IssueSeverity.ERROR,
                    checker="TestChecker",
                    message="Test message",
                )
            ],
        )
        d = result.to_dict()
        assert d["allowed"] is False
        assert d["error_count"] == 1
        assert len(d["issues"]) == 1
        assert d["issues"][0]["severity"] == "ERROR"

    def test_warning_count(self):
        """Correctly counts warnings."""
        result = InspectionResult(
            allowed=True,
            issues=[
                InspectionIssue(
                    severity=IssueSeverity.WARNING,
                    checker="TestChecker",
                    message="Warning 1",
                ),
                InspectionIssue(
                    severity=IssueSeverity.WARNING,
                    checker="TestChecker",
                    message="Warning 2",
                ),
            ],
        )
        assert result.warning_count == 2
        assert result.error_count == 0
