"""
CrashDetector - Unified crash detection for UE5 editor.

This module provides centralized crash detection logic used by:
- HealthMonitor: Detect crashes from process exit and log files
- ExecutionManager: Detect crashes from execution results
"""

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# Crash indicators in UE5 log/output
CRASH_INDICATORS = [
    "[CRASH]",
    "Fatal error:",
    "Access violation",
    "Unhandled Exception",
    "SIGSEGV",
    "Assertion failed",
    "Ensure condition failed",
    "LowLevelFatalError",
    "Out of memory",
    "GPU crash",
    "D3D11/12 crash",
    "Rendering thread exception",
    "Game thread exception",
]


# Windows NTSTATUS crash codes (converted to signed 32-bit integers)
WINDOWS_CRASH_CODES: dict[int, str] = {
    -1073741819: "ACCESS_VIOLATION (0xC0000005)",
    -1073741795: "ILLEGAL_INSTRUCTION (0xC000001D)",
    -1073741571: "STACK_OVERFLOW (0xC00000FD)",
    -1073740791: "HEAP_CORRUPTION (0xC0000374)",
    -1073740940: "STATUS_STACK_BUFFER_OVERRUN (0xC0000409)",
    -1073741676: "INTEGER_DIVIDE_BY_ZERO (0xC0000094)",
    -1073741675: "INTEGER_OVERFLOW (0xC0000095)",
    -1073741674: "PRIVILEGED_INSTRUCTION (0xC0000096)",
    -1073741811: "INVALID_HANDLE (0xC0000008)",
    -1073741801: "INVALID_PARAMETER (0xC000000D)",
    -1073740777: "FATAL_APP_EXIT (0xC0000417)",
}


class CrashDetector:
    """
    Unified crash detection for UE5 editor.
    
    Provides methods to detect crashes from various sources:
    - Process exit codes
    - Log file content
    - Execution output/error messages
    """
    
    @staticmethod
    def analyze_exit_code(exit_code: int) -> dict[str, Any]:
        """
        Analyze process exit code and return detailed exit information.
        
        Args:
            exit_code: The process exit code
            
        Returns:
            Dictionary containing:
            - exit_type: "normal", "error", or "crash"
            - exit_code: The raw exit code
            - description: Human-readable description
            - hex_code: (for crashes) Hex representation of the code
        """
        if exit_code == 0:
            return {
                "exit_type": "normal",
                "exit_code": 0,
                "description": "Editor exited normally",
            }
        elif exit_code > 0:
            return {
                "exit_type": "error",
                "exit_code": exit_code,
                "description": f"Editor exited with error code {exit_code}",
            }
        else:
            # Negative exit codes on Windows are NTSTATUS crash codes
            crash_name = WINDOWS_CRASH_CODES.get(exit_code)
            hex_code = hex(exit_code & 0xFFFFFFFF)
            
            if crash_name:
                description = f"Editor crashed: {crash_name}"
            else:
                description = f"Editor crashed with code {hex_code}"
            
            return {
                "exit_type": "crash",
                "exit_code": exit_code,
                "hex_code": hex_code,
                "description": description,
            }
    
    @staticmethod
    def check_content_for_crash(content: str) -> tuple[bool, str | None]:
        """
        Check text content for crash indicators.
        
        Args:
            content: Text to check (log content, error message, output, etc.)
            
        Returns:
            Tuple of (is_crash, indicator_found)
        """
        for indicator in CRASH_INDICATORS:
            if indicator in content:
                logger.debug(f"Found crash indicator in content: {indicator}")
                return True, indicator
        return False, None
    
    @staticmethod
    def check_log_file(log_path: Path | str, tail_size: int = 100 * 1024) -> bool:
        """
        Check log file for crash indicators.
        
        Args:
            log_path: Path to log file
            tail_size: Number of bytes to read from end of file (default 100KB)
            
        Returns:
            True if log contains crash indicators
        """
        if not isinstance(log_path, Path):
            log_path = Path(log_path)
        
        if not log_path.exists():
            return False
        
        try:
            file_size = log_path.stat().st_size
            read_size = min(tail_size, file_size)
            
            with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
                if read_size < file_size:
                    f.seek(file_size - read_size)
                log_tail = f.read()
            
            is_crash, _ = CrashDetector.check_content_for_crash(log_tail)
            return is_crash
        except (OSError, IOError, UnicodeDecodeError) as e:
            logger.debug(f"Failed to read log file for crash check: {e}")
            return False
    
    @staticmethod
    def check_execution_result(result: dict[str, Any]) -> bool:
        """
        Check execution result for crash indicators.
        
        Args:
            result: Execution result dictionary from remote client
            
        Returns:
            True if result indicates a crash
        """
        # Already marked as crashed
        if result.get("crashed", False):
            return True
        
        # Check error message and output for crash indicators
        if not result.get("success", True):
            error_msg = str(result.get("error", ""))
            output_str = str(result.get("output", ""))
            combined = error_msg + output_str
            
            is_crash, indicator = CrashDetector.check_content_for_crash(combined)
            if is_crash:
                logger.warning(f"Detected crash indicator in execution result: {indicator}")
                return True
        
        return False
    
    @staticmethod
    def analyze_exit_with_log_check(
        exit_code: int,
        log_path: Path | str | None = None
    ) -> dict[str, Any]:
        """
        Analyze exit code with optional log file check.
        
        This is the most comprehensive check, used by HealthMonitor when
        process exits. It handles the Windows crash reporting case where
        exit code is 0 but log shows crash.
        
        Args:
            exit_code: Process exit code
            log_path: Optional path to log file for additional checking
            
        Returns:
            Exit analysis dictionary
        """
        # First check exit code
        exit_info = CrashDetector.analyze_exit_code(exit_code)
        
        # If exit code indicates crash, no need to check log
        if exit_info["exit_type"] == "crash":
            return exit_info
        
        # If exit code is 0, check log file for crash indicators
        # (Windows crash reporting may show "Send Report" dialog and exit with 0)
        if exit_code == 0 and log_path is not None:
            if CrashDetector.check_log_file(log_path):
                return {
                    "exit_type": "crash",
                    "exit_code": 0,
                    "description": "Editor crashed (Windows crash report dialog was shown)",
                    "note": "Exit code was 0 due to Windows crash reporting, but log shows crash",
                }
        
        return exit_info
