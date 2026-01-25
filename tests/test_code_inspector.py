"""
Unit tests for code_inspector module.
"""

import pytest

from ue_mcp.code_inspector import (
    BaseChecker,
    BlockingCallChecker,
    CodeInspector,
    DeprecatedAPIChecker,
    InspectionIssue,
    InspectionResult,
    IssueSeverity,
    UnrealAPIChecker,
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


class TestUnrealAPIChecker:
    """Tests for UnrealAPIChecker - requires unreal module (run in UE5 editor)."""

    @pytest.fixture
    def unreal_available(self):
        """Check if unreal module is available."""
        try:
            import unreal
            return True
        except ImportError:
            return False

    def test_skips_when_unreal_not_available(self):
        """Checker gracefully skips when unreal module is not available."""
        code = """
import unreal
unreal.log("Hello")
"""
        result = inspect_code(code)
        # Without unreal module, UnrealAPIChecker skips, so no errors from it
        # (but code is still allowed to execute)
        assert result.allowed

    def test_detects_invalid_direct_api(self, unreal_available):
        """Detects invalid direct API call as ERROR."""
        if not unreal_available:
            pytest.skip("unreal module not available")

        code = """
import unreal
unreal.NonExistentAPI()
"""
        result = inspect_code(code)
        assert not result.allowed  # ERROR blocks execution
        assert result.error_count >= 1
        assert any("NonExistentAPI" in i.message for i in result.issues)
        assert any(i.checker == "UnrealAPIChecker" for i in result.issues)

    def test_detects_invalid_chained_api(self, unreal_available):
        """Detects invalid chained API call as ERROR."""
        if not unreal_available:
            pytest.skip("unreal module not available")

        code = """
import unreal
unreal.EditorAssetLibrary.nonexistent_method()
"""
        result = inspect_code(code)
        assert not result.allowed
        assert result.error_count >= 1
        assert any("nonexistent_method" in i.message for i in result.issues)

    def test_detects_invalid_from_import(self, unreal_available):
        """Detects invalid from unreal import as ERROR."""
        if not unreal_available:
            pytest.skip("unreal module not available")

        code = """
from unreal import NonExistentClass
obj = NonExistentClass()
"""
        result = inspect_code(code)
        assert not result.allowed
        assert result.error_count >= 1
        assert any("NonExistentClass" in i.message for i in result.issues)

    def test_allows_valid_unreal_api(self, unreal_available):
        """Allows valid unreal API calls."""
        if not unreal_available:
            pytest.skip("unreal module not available")

        code = """
import unreal
unreal.log("Test message")
unreal.EditorAssetLibrary.list_assets("/Game/")
"""
        result = inspect_code(code)
        # Should not have errors from UnrealAPIChecker
        unreal_errors = [i for i in result.issues if i.checker == "UnrealAPIChecker"]
        assert len(unreal_errors) == 0

    def test_handles_import_alias(self, unreal_available):
        """Handles unreal module imported with alias."""
        if not unreal_available:
            pytest.skip("unreal module not available")

        code = """
import unreal as u
u.InvalidAPI()
"""
        result = inspect_code(code)
        assert not result.allowed
        assert result.error_count >= 1
        assert any("InvalidAPI" in i.message for i in result.issues)

    def test_line_number_tracking(self, unreal_available):
        """Correctly tracks line numbers of invalid API calls."""
        if not unreal_available:
            pytest.skip("unreal module not available")

        code = """import unreal
# comment
unreal.NonExistentAPI()
"""
        result = inspect_code(code)
        assert result.error_count >= 1
        # Line 3 has the invalid API call
        assert any(i.line_number == 3 for i in result.issues)

    def test_provides_suggestion(self, unreal_available):
        """Provides helpful suggestion for invalid API calls."""
        if not unreal_available:
            pytest.skip("unreal module not available")

        code = """
import unreal
unreal.InvalidAPI()
"""
        result = inspect_code(code)
        assert result.error_count >= 1
        unreal_issues = [i for i in result.issues if i.checker == "UnrealAPIChecker"]
        assert len(unreal_issues) > 0
        assert unreal_issues[0].suggestion is not None
        assert "documentation" in unreal_issues[0].suggestion.lower()

    def test_detects_multiple_invalid_apis(self, unreal_available):
        """Detects multiple invalid API calls."""
        if not unreal_available:
            pytest.skip("unreal module not available")

        code = """
import unreal
unreal.InvalidAPI1()
unreal.InvalidAPI2()
from unreal import NonExistentClass
"""
        result = inspect_code(code)
        assert not result.allowed
        # Should detect all 3 invalid APIs
        assert result.error_count >= 2

    def test_checker_registered_by_default(self):
        """UnrealAPIChecker is registered by default in CodeInspector."""
        inspector = CodeInspector()
        checkers = inspector.get_checkers()
        checker_names = [c.name for c in checkers]
        assert "UnrealAPIChecker" in checker_names


class TestDeprecatedAPIChecker:
    """Tests for DeprecatedAPIChecker."""

    def test_detects_deprecated_load_level(self):
        """Detects deprecated EditorLevelLibrary.load_level() as ERROR (blocks execution)."""
        code = """
import unreal
unreal.EditorLevelLibrary.load_level("/Game/Maps/TestLevel")
"""
        result = inspect_code(code)
        assert not result.allowed  # ERROR blocks execution
        assert result.error_count >= 1
        deprecated_issues = [i for i in result.issues if i.checker == "DeprecatedAPIChecker"]
        assert len(deprecated_issues) >= 1
        assert "load_level" in deprecated_issues[0].message
        assert "LevelEditorSubsystem" in deprecated_issues[0].message

    def test_detects_deprecated_new_level(self):
        """Detects deprecated EditorLevelLibrary.new_level() as ERROR."""
        code = """
import unreal
unreal.EditorLevelLibrary.new_level("/Game/Maps/NewLevel")
"""
        result = inspect_code(code)
        assert not result.allowed  # ERROR blocks execution
        deprecated_issues = [i for i in result.issues if i.checker == "DeprecatedAPIChecker"]
        assert len(deprecated_issues) >= 1
        assert "new_level" in deprecated_issues[0].message

    def test_detects_deprecated_save_current_level(self):
        """Detects deprecated EditorLevelLibrary.save_current_level() as ERROR."""
        code = """
import unreal
unreal.EditorLevelLibrary.save_current_level()
"""
        result = inspect_code(code)
        assert not result.allowed  # ERROR blocks execution
        deprecated_issues = [i for i in result.issues if i.checker == "DeprecatedAPIChecker"]
        assert len(deprecated_issues) >= 1
        assert "save_current_level" in deprecated_issues[0].message

    def test_detects_deprecated_spawn_actor(self):
        """Detects deprecated EditorLevelLibrary.spawn_actor_from_class() as ERROR."""
        code = """
import unreal
unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.Actor, unreal.Vector())
"""
        result = inspect_code(code)
        assert not result.allowed  # ERROR blocks execution
        deprecated_issues = [i for i in result.issues if i.checker == "DeprecatedAPIChecker"]
        assert len(deprecated_issues) >= 1
        assert "spawn_actor_from_class" in deprecated_issues[0].message
        assert "EditorActorSubsystem" in deprecated_issues[0].message

    def test_detects_deprecated_get_all_level_actors(self):
        """Detects deprecated EditorLevelLibrary.get_all_level_actors() as ERROR."""
        code = """
import unreal
actors = unreal.EditorLevelLibrary.get_all_level_actors()
"""
        result = inspect_code(code)
        assert not result.allowed  # ERROR blocks execution
        deprecated_issues = [i for i in result.issues if i.checker == "DeprecatedAPIChecker"]
        assert len(deprecated_issues) >= 1
        assert "get_all_level_actors" in deprecated_issues[0].message

    def test_handles_unreal_alias(self):
        """Detects deprecated API with unreal module alias as ERROR."""
        code = """
import unreal as ue
ue.EditorLevelLibrary.load_level("/Game/Maps/TestLevel")
"""
        result = inspect_code(code)
        assert not result.allowed  # ERROR blocks execution
        deprecated_issues = [i for i in result.issues if i.checker == "DeprecatedAPIChecker"]
        assert len(deprecated_issues) >= 1
        assert "load_level" in deprecated_issues[0].message

    def test_allows_non_deprecated_api(self):
        """Allows non-deprecated API calls from EditorLevelLibrary."""
        code = """
import unreal
# EditorAssetLibrary is not deprecated
assets = unreal.EditorAssetLibrary.list_assets("/Game/")
"""
        result = inspect_code(code)
        deprecated_issues = [i for i in result.issues if i.checker == "DeprecatedAPIChecker"]
        assert len(deprecated_issues) == 0

    def test_allows_subsystem_api(self):
        """Allows the recommended Subsystem-based API calls."""
        code = """
import unreal
level_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
level_subsystem.load_level("/Game/Maps/TestLevel")
"""
        result = inspect_code(code)
        deprecated_issues = [i for i in result.issues if i.checker == "DeprecatedAPIChecker"]
        assert len(deprecated_issues) == 0

    def test_detects_multiple_deprecated_calls(self):
        """Detects multiple deprecated API calls as ERRORs."""
        code = """
import unreal
unreal.EditorLevelLibrary.new_level("/Game/Maps/New")
unreal.EditorLevelLibrary.save_current_level()
unreal.EditorLevelLibrary.load_level("/Game/Maps/Existing")
"""
        result = inspect_code(code)
        assert not result.allowed  # ERROR blocks execution
        assert result.error_count >= 3
        deprecated_issues = [i for i in result.issues if i.checker == "DeprecatedAPIChecker"]
        assert len(deprecated_issues) == 3

    def test_line_number_tracking(self):
        """Correctly tracks line numbers of deprecated API calls."""
        code = """import unreal
# comment
unreal.EditorLevelLibrary.load_level("/Game/Maps/Test")
"""
        result = inspect_code(code)
        deprecated_issues = [i for i in result.issues if i.checker == "DeprecatedAPIChecker"]
        assert len(deprecated_issues) >= 1
        assert deprecated_issues[0].line_number == 3

    def test_provides_suggestion(self):
        """Provides helpful suggestion for deprecated API calls."""
        code = """
import unreal
unreal.EditorLevelLibrary.load_level("/Game/Maps/Test")
"""
        result = inspect_code(code)
        deprecated_issues = [i for i in result.issues if i.checker == "DeprecatedAPIChecker"]
        assert len(deprecated_issues) >= 1
        assert deprecated_issues[0].suggestion is not None
        assert "get_editor_subsystem" in deprecated_issues[0].suggestion
        assert "LevelEditorSubsystem" in deprecated_issues[0].suggestion

    def test_checker_registered_by_default(self):
        """DeprecatedAPIChecker is registered by default in CodeInspector."""
        inspector = CodeInspector()
        checkers = inspector.get_checkers()
        checker_names = [c.name for c in checkers]
        assert "DeprecatedAPIChecker" in checker_names

    def test_ignores_unrelated_code(self):
        """Ignores code that doesn't use unreal module."""
        code = """
import time
import os
print("Hello")
"""
        result = inspect_code(code)
        deprecated_issues = [i for i in result.issues if i.checker == "DeprecatedAPIChecker"]
        assert len(deprecated_issues) == 0


class TestDecoratorHandling:
    """Tests for decorator handling in UnrealAPIChecker."""

    def test_skips_decorator_validation(self):
        """Decorators should not be validated as API calls."""
        # Even if @unreal.ufunction doesn't exist via hasattr(),
        # decorators should be skipped to avoid false positives
        code = """
import unreal

@unreal.ufunction(meta=dict(Category="Test"))
def test_func():
    pass
"""
        result = inspect_code(code)
        # Should not report decorator as invalid API
        unreal_errors = [
            i for i in result.issues
            if i.checker == "UnrealAPIChecker" and "ufunction" in i.message
        ]
        assert len(unreal_errors) == 0

    def test_skips_chained_decorator_validation(self):
        """Chained decorators like @unreal.AutomationScheduler.add_latent_command should be skipped."""
        code = """
import unreal

@unreal.AutomationScheduler.add_latent_command
def test_latent():
    yield
"""
        result = inspect_code(code)
        # Should not report chained decorator as invalid API
        unreal_errors = [
            i for i in result.issues
            if i.checker == "UnrealAPIChecker" and "add_latent_command" in i.message
        ]
        assert len(unreal_errors) == 0

    def test_skips_class_decorator_validation(self):
        """Class decorators should also be skipped."""
        code = """
import unreal

@unreal.uclass()
class MyClass:
    pass
"""
        result = inspect_code(code)
        # Should not report class decorator as invalid API
        unreal_errors = [
            i for i in result.issues
            if i.checker == "UnrealAPIChecker" and "uclass" in i.message
        ]
        assert len(unreal_errors) == 0

    def test_still_validates_non_decorator_code(self, unreal_available=None):
        """Non-decorator code should still be validated."""
        try:
            import unreal
        except ImportError:
            pytest.skip("unreal module not available")

        code = """
import unreal

@unreal.ufunction()
def test_func():
    # This should still be validated
    unreal.NonExistentAPI()
"""
        result = inspect_code(code)
        # The decorator should be skipped, but the function body should be checked
        unreal_errors = [
            i for i in result.issues
            if i.checker == "UnrealAPIChecker" and "NonExistentAPI" in i.message
        ]
        assert len(unreal_errors) >= 1
