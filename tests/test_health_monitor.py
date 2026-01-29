"""
Health Monitor Tests for UE-MCP.

Tests the HealthMonitor's exit detection and notification behavior.
"""

import pytest

from ue_mcp.editor.crash_detector import WINDOWS_CRASH_CODES
from ue_mcp.editor.health_monitor import HealthMonitor


class TestExitAnalysis:
    """Test the analyze_exit function for different exit codes."""

    @pytest.fixture
    def health_monitor(self):
        """Create a HealthMonitor instance without context for unit testing."""
        # Create a mock context
        class MockContext:
            _monitor_task = None
            _notify_callback = None
            _intentional_stop = False
            editor = None

        return HealthMonitor(MockContext())

    def test_normal_exit_code_zero(self, health_monitor):
        """Exit code 0 should be classified as normal exit."""
        result = health_monitor.analyze_exit(0)

        assert result["exit_type"] == "normal"
        assert result["exit_code"] == 0
        assert "normally" in result["description"].lower()

    def test_error_exit_positive_code(self, health_monitor):
        """Positive exit codes should be classified as errors."""
        result = health_monitor.analyze_exit(1)

        assert result["exit_type"] == "error"
        assert result["exit_code"] == 1
        assert "error" in result["description"].lower()

    def test_error_exit_various_positive_codes(self, health_monitor):
        """Various positive exit codes should all be classified as errors."""
        for code in [1, 2, 127, 255]:
            result = health_monitor.analyze_exit(code)
            assert result["exit_type"] == "error"
            assert result["exit_code"] == code

    def test_crash_exit_access_violation(self, health_monitor):
        """Access violation (0xC0000005) should be classified as crash."""
        exit_code = -1073741819  # 0xC0000005

        result = health_monitor.analyze_exit(exit_code)

        assert result["exit_type"] == "crash"
        assert result["exit_code"] == exit_code
        assert "hex_code" in result
        assert result["hex_code"] == "0xc0000005"
        assert "ACCESS_VIOLATION" in result["description"]

    def test_crash_exit_stack_overflow(self, health_monitor):
        """Stack overflow (0xC00000FD) should be classified as crash."""
        exit_code = -1073741571  # 0xC00000FD

        result = health_monitor.analyze_exit(exit_code)

        assert result["exit_type"] == "crash"
        assert "STACK_OVERFLOW" in result["description"]

    def test_crash_exit_heap_corruption(self, health_monitor):
        """Heap corruption (0xC0000374) should be classified as crash."""
        exit_code = -1073740791  # 0xC0000374

        result = health_monitor.analyze_exit(exit_code)

        assert result["exit_type"] == "crash"
        assert "HEAP_CORRUPTION" in result["description"]

    def test_crash_exit_unknown_code(self, health_monitor):
        """Unknown negative exit codes should still be classified as crash."""
        exit_code = -12345  # Unknown code

        result = health_monitor.analyze_exit(exit_code)

        assert result["exit_type"] == "crash"
        assert result["exit_code"] == exit_code
        assert "hex_code" in result
        assert "crashed" in result["description"].lower()

    def test_all_known_crash_codes(self, health_monitor):
        """All known Windows crash codes should be recognized."""
        for exit_code, expected_name in WINDOWS_CRASH_CODES.items():
            result = health_monitor.analyze_exit(exit_code)

            assert result["exit_type"] == "crash", f"Failed for {expected_name}"
            # The description should contain the crash name
            crash_type = expected_name.split(" ")[0]  # e.g., "ACCESS_VIOLATION"
            assert crash_type in result["description"], f"Failed for {expected_name}"


class TestBuildCrashResponse:
    """Test the _build_crash_response function used during execution."""

    def test_crash_response_with_exit_code(self):
        """Crash response should include detailed exit info when available."""
        from unittest.mock import MagicMock

        from ue_mcp.editor.execution_manager import _build_crash_response

        # Create mock context with a crashed process
        mock_ctx = MagicMock()
        mock_ctx.editor.process.poll.return_value = -1073741819  # ACCESS_VIOLATION

        result = _build_crash_response(mock_ctx, {"error": "connection lost"})

        assert result["success"] is False
        assert "ACCESS_VIOLATION" in result["error"]
        assert result["exit_type"] == "crash"
        assert result["exit_code"] == -1073741819
        assert result["hex_code"] == "0xc0000005"

    def test_crash_response_normal_exit(self):
        """Crash response should handle normal exit code."""
        from unittest.mock import MagicMock

        from ue_mcp.editor.execution_manager import _build_crash_response

        mock_ctx = MagicMock()
        mock_ctx.editor.process.poll.return_value = 0

        result = _build_crash_response(mock_ctx, {"error": "connection lost"})

        assert result["success"] is False
        assert "normally" in result["error"]
        assert result["exit_type"] == "normal"
        assert result["exit_code"] == 0

    def test_crash_response_no_exit_code(self):
        """Crash response should handle case where process hasn't exited yet."""
        from unittest.mock import MagicMock

        from ue_mcp.editor.execution_manager import _build_crash_response

        mock_ctx = MagicMock()
        mock_ctx.editor.process.poll.return_value = None  # Still running

        result = _build_crash_response(mock_ctx, {"error": "connection lost"})

        assert result["success"] is False
        assert "connection lost" in result["error"]
        assert "exit_type" not in result  # No exit info available


class TestWindowsCrashCodes:
    """Test the WINDOWS_CRASH_CODES dictionary."""

    def test_access_violation_code(self):
        """Access violation code should be correct."""
        assert -1073741819 in WINDOWS_CRASH_CODES
        assert "ACCESS_VIOLATION" in WINDOWS_CRASH_CODES[-1073741819]

    def test_stack_overflow_code(self):
        """Stack overflow code should be correct."""
        assert -1073741571 in WINDOWS_CRASH_CODES
        assert "STACK_OVERFLOW" in WINDOWS_CRASH_CODES[-1073741571]

    def test_heap_corruption_code(self):
        """Heap corruption code should be correct."""
        assert -1073740791 in WINDOWS_CRASH_CODES
        assert "HEAP_CORRUPTION" in WINDOWS_CRASH_CODES[-1073740791]

    def test_all_codes_are_negative(self):
        """All crash codes should be negative integers."""
        for code in WINDOWS_CRASH_CODES.keys():
            assert code < 0, f"Code {code} should be negative"

    def test_all_codes_have_hex_in_description(self):
        """All crash code descriptions should include hex representation."""
        for code, description in WINDOWS_CRASH_CODES.items():
            assert "0x" in description.lower(), f"Missing hex in: {description}"
