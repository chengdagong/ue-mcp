"""
UE-MCP Code Inspector Module

Inspects Python code before remote execution to detect patterns that could
cause issues in the Unreal Editor environment, such as blocking the main thread.

This module is designed to be easily extensible - add new checkers by:
1. Subclass BaseChecker
2. Implement name, description, and check() method
3. Register with CodeInspector.register_checker()
"""

import ast
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class IssueSeverity(Enum):
    """Severity levels for code inspection issues."""

    ERROR = "ERROR"  # Blocks execution
    WARNING = "WARNING"  # Warns but allows execution


@dataclass
class InspectionIssue:
    """Represents a single code inspection issue found."""

    severity: IssueSeverity
    checker: str  # Name of the checker that found this issue
    message: str  # Description of the issue
    line_number: Optional[int] = None  # Line number where issue was found
    suggestion: Optional[str] = None  # How to fix or avoid the issue

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "severity": self.severity.value,
            "checker": self.checker,
            "message": self.message,
            "line_number": self.line_number,
            "suggestion": self.suggestion,
        }


@dataclass
class InspectionResult:
    """Result of code inspection."""

    allowed: bool  # Whether execution is allowed
    issues: List[InspectionIssue] = field(default_factory=list)

    @property
    def error_count(self) -> int:
        """Count of ERROR severity issues."""
        return sum(1 for i in self.issues if i.severity == IssueSeverity.ERROR)

    @property
    def warning_count(self) -> int:
        """Count of WARNING severity issues."""
        return sum(1 for i in self.issues if i.severity == IssueSeverity.WARNING)

    @property
    def has_errors(self) -> bool:
        """Whether there are any ERROR severity issues."""
        return self.error_count > 0

    def format_error(self) -> str:
        """
        Format issues as a human-readable error message.

        Returns:
            Formatted error string for display to user
        """
        lines = ["Code inspection failed:", ""]

        for issue in self.issues:
            # Header with severity and checker
            if issue.line_number:
                lines.append(
                    f"[{issue.severity.value}] {issue.checker} (line {issue.line_number}):"
                )
            else:
                lines.append(f"[{issue.severity.value}] {issue.checker}:")

            # Message
            lines.append(f"  {issue.message}")

            # Suggestion
            if issue.suggestion:
                lines.append("")
                lines.append(f"  Suggestion: {issue.suggestion}")

            lines.append("")

        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "allowed": self.allowed,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "issues": [i.to_dict() for i in self.issues],
        }


class BaseChecker(ABC):
    """
    Base class for all code checkers.

    Subclasses must implement:
    - name: Property returning the checker name
    - description: Property returning what this checker detects
    - check(): Method that analyzes code and returns issues found
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the name of this checker."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Return a description of what this checker detects."""
        pass

    @abstractmethod
    def check(self, tree: ast.AST, code: str) -> List[InspectionIssue]:
        """
        Analyze code and return issues found.

        Args:
            tree: Parsed AST of the code
            code: Original source code string

        Returns:
            List of InspectionIssue objects for issues found
        """
        pass


class BlockingCallChecker(BaseChecker):
    """
    Detects blocking calls that would freeze the Unreal Editor main thread.

    Currently detects:
    - time.sleep() calls
    """

    # Blocking functions to detect: (module, function)
    BLOCKING_CALLS = {
        ("time", "sleep"),
    }

    @property
    def name(self) -> str:
        return "BlockingCallChecker"

    @property
    def description(self) -> str:
        return "Detects blocking calls like time.sleep() that freeze the main thread"

    def check(self, tree: ast.AST, code: str) -> List[InspectionIssue]:
        """Check for blocking function calls."""
        issues: List[InspectionIssue] = []

        # Track import aliases
        # e.g., "import time as t" -> {"t": "time"}
        # e.g., "from time import sleep" -> direct call tracking
        module_aliases: Dict[str, str] = {}
        direct_imports: Set[tuple] = set()  # (module, function)

        # First pass: collect import information
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    # import time / import time as t
                    name = alias.asname if alias.asname else alias.name
                    module_aliases[name] = alias.name

            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    for alias in node.names:
                        # from time import sleep / from time import sleep as s
                        func_name = alias.asname if alias.asname else alias.name
                        direct_imports.add((node.module, alias.name, func_name))

        # Second pass: find blocking calls
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                blocking_call = self._is_blocking_call(node, module_aliases, direct_imports)
                if blocking_call:
                    module, func = blocking_call
                    issues.append(
                        InspectionIssue(
                            severity=IssueSeverity.WARNING,
                            checker=self.name,
                            message=f"Detected '{module}.{func}()' call which blocks the Unreal Engine main thread.",
                            line_number=node.lineno,
                            suggestion=(
                                "For async operations, use tick callbacks instead:\n"
                                "    - unreal.register_slate_post_tick_callback(callback)\n"
                                "    - unreal.unregister_slate_post_tick_callback(handle)"
                            ),
                        )
                    )

        return issues

    def _is_blocking_call(
        self,
        node: ast.Call,
        module_aliases: Dict[str, str],
        direct_imports: Set[tuple],
    ) -> Optional[tuple]:
        """
        Check if a Call node is a blocking call.

        Args:
            node: AST Call node
            module_aliases: Mapping of alias -> module name
            direct_imports: Set of (module, orig_name, alias) for from imports

        Returns:
            (module, function) tuple if blocking, None otherwise
        """
        # Case 1: module.func() - e.g., time.sleep() or t.sleep()
        if isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name):
                alias = node.func.value.id
                func = node.func.attr

                # Resolve alias to actual module
                module = module_aliases.get(alias, alias)

                if (module, func) in self.BLOCKING_CALLS:
                    return (module, func)

        # Case 2: direct call - e.g., sleep() after "from time import sleep"
        elif isinstance(node.func, ast.Name):
            func_alias = node.func.id

            for module, orig_name, imported_alias in direct_imports:
                if func_alias == imported_alias:
                    if (module, orig_name) in self.BLOCKING_CALLS:
                        return (module, orig_name)

        return None


class UnrealAPIChecker(BaseChecker):
    """
    Detects calls to unreal module APIs and validates their existence.

    This checker validates:
    - Direct API calls: unreal.SomeAPI
    - Chained API calls: unreal.SomeClass.some_method
    - From imports: from unreal import Something

    Note: This checker requires the unreal module to be available.
    If unreal is not importable, the checker will be skipped.
    """

    @property
    def name(self) -> str:
        return "UnrealAPIChecker"

    @property
    def description(self) -> str:
        return "Validates that unreal module API calls reference existing APIs"

    def check(self, tree: ast.AST, code: str) -> List[InspectionIssue]:
        """Check for invalid unreal API calls."""
        issues: List[InspectionIssue] = []

        # Try to import unreal module
        try:
            import unreal
        except ImportError:
            # unreal module not available, skip this check
            logger.debug("unreal module not available, skipping UnrealAPIChecker")
            return issues

        # Track unreal module aliases and direct imports
        # unreal_aliases: names that refer to the unreal module (e.g., "unreal" or "u")
        # direct_imports: names imported from unreal (e.g., from unreal import EditorAssetLibrary)
        unreal_aliases: Set[str] = set()
        direct_imports: Dict[str, str] = {}  # alias -> original_name

        # First pass: collect import information
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "unreal":
                        name = alias.asname if alias.asname else alias.name
                        unreal_aliases.add(name)

            elif isinstance(node, ast.ImportFrom):
                if node.module == "unreal":
                    for alias in node.names:
                        # from unreal import Something / from unreal import Something as S
                        imported_name = alias.asname if alias.asname else alias.name
                        direct_imports[imported_name] = alias.name

                        # Validate that the imported name exists
                        if not hasattr(unreal, alias.name):
                            issues.append(
                                InspectionIssue(
                                    severity=IssueSeverity.ERROR,
                                    checker=self.name,
                                    message=f"Cannot import '{alias.name}' from unreal module (does not exist)",
                                    line_number=node.lineno,
                                    suggestion="Check the API name spelling or refer to UE5 Python API documentation",
                                )
                            )

        # Second pass: find unreal API attribute accesses and validate them
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                # Extract the API path if this is an unreal API call
                api_path = self._extract_api_path(node, unreal_aliases)
                if api_path:
                    # Validate the API path
                    valid, invalid_attr, _ = self._validate_api_path(
                        api_path, unreal
                    )
                    if not valid:
                        # Build the full path string for error message
                        full_path = "unreal." + ".".join(api_path)
                        # Find where it breaks
                        valid_path = "unreal." + ".".join(
                            api_path[: api_path.index(invalid_attr)]
                        )

                        issues.append(
                            InspectionIssue(
                                severity=IssueSeverity.ERROR,
                                checker=self.name,
                                message=f"API '{full_path}' does not exist ('{invalid_attr}' not found in {valid_path})",
                                line_number=node.lineno,
                                suggestion="Check the API name spelling or refer to UE5 Python API documentation",
                            )
                        )

            # Also check direct use of imported names
            elif isinstance(node, ast.Name):
                if node.id in direct_imports:
                    # The name itself is valid (we checked it during import),
                    # but we could add additional checks here if needed
                    pass

        return issues

    def _extract_api_path(
        self, node: ast.Attribute, unreal_aliases: Set[str]
    ) -> Optional[List[str]]:
        """
        Extract the API path from an attribute access node.

        For example:
        - unreal.EditorAssetLibrary -> ['EditorAssetLibrary']
        - unreal.EditorAssetLibrary.list_assets -> ['EditorAssetLibrary', 'list_assets']

        Args:
            node: An ast.Attribute node
            unreal_aliases: Set of names that refer to the unreal module

        Returns:
            List of attribute names if this is an unreal API call, None otherwise
        """
        path = []
        current = node

        # Walk up the attribute chain
        while isinstance(current, ast.Attribute):
            path.insert(0, current.attr)
            current = current.value

        # Check if the base is the unreal module
        if isinstance(current, ast.Name) and current.id in unreal_aliases:
            return path

        return None

    def _validate_api_path(
        self, path: List[str], unreal_module
    ) -> tuple[bool, Optional[str], Any]:
        """
        Validate that an API path exists in the unreal module.

        Args:
            path: List of attribute names, e.g., ['EditorAssetLibrary', 'list_assets']
            unreal_module: The imported unreal module

        Returns:
            Tuple of (valid, invalid_attr, last_valid_obj):
            - valid: True if the entire path exists
            - invalid_attr: The first attribute that doesn't exist (None if all valid)
            - last_valid_obj: The last valid object in the path
        """
        current = unreal_module
        for attr in path:
            if not hasattr(current, attr):
                return False, attr, current
            current = getattr(current, attr)

        return True, None, current


class CodeInspector:
    """
    Main code inspector that runs all registered checkers.

    Usage:
        inspector = CodeInspector()
        result = inspector.inspect(code)
        if not result.allowed:
            print(result.format_error())
    """

    def __init__(self):
        self._checkers: List[BaseChecker] = []
        self._register_default_checkers()

    def _register_default_checkers(self):
        """Register the default set of checkers."""
        self.register_checker(BlockingCallChecker())
        self.register_checker(UnrealAPIChecker())

    def register_checker(self, checker: BaseChecker):
        """
        Register a new checker.

        Args:
            checker: BaseChecker instance to register
        """
        self._checkers.append(checker)
        logger.debug(f"Registered checker: {checker.name}")

    def get_checkers(self) -> List[BaseChecker]:
        """Return list of registered checkers."""
        return list(self._checkers)

    def inspect(self, code: str) -> InspectionResult:
        """
        Inspect code using all registered checkers.

        Args:
            code: Python source code to inspect

        Returns:
            InspectionResult with all issues found
        """
        issues: List[InspectionIssue] = []

        # Parse code into AST
        try:
            tree = ast.parse(code)
        except SyntaxError:
            # Syntax errors are handled elsewhere (extract_import_statements)
            # Just return empty result here
            return InspectionResult(allowed=True, issues=[])

        # Run all checkers
        for checker in self._checkers:
            try:
                checker_issues = checker.check(tree, code)
                issues.extend(checker_issues)
            except Exception as e:
                logger.warning(f"Checker {checker.name} failed: {e}")

        # Determine if execution is allowed (no ERROR severity issues)
        has_errors = any(i.severity == IssueSeverity.ERROR for i in issues)

        return InspectionResult(allowed=not has_errors, issues=issues)


# Global inspector instance
_inspector: Optional[CodeInspector] = None


def get_inspector() -> CodeInspector:
    """
    Get the global CodeInspector instance.

    Returns:
        CodeInspector singleton instance
    """
    global _inspector
    if _inspector is None:
        _inspector = CodeInspector()
    return _inspector


def inspect_code(code: str) -> InspectionResult:
    """
    Convenience function to inspect code using the global inspector.

    Args:
        code: Python source code to inspect

    Returns:
        InspectionResult with all issues found

    Example:
        result = inspect_code("import time; time.sleep(1)")
        if not result.allowed:
            print(result.format_error())
    """
    return get_inspector().inspect(code)
