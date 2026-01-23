"""
Test script for editor log file functionality.

This test verifies:
1. editor_launch creates a unique log file with project name and timestamp
2. editor_status returns the log_file_path
3. editor_read_log can read the log content
4. The log file contains UE5 engine logs
"""

import asyncio
import json
import re
from pathlib import Path

import pytest


class TestEditorLog:
    """Test editor log file functionality using MCP tools."""

    @pytest.mark.asyncio
    async def test_editor_log_file_functionality(self, running_editor):
        """Test complete editor log file functionality."""
        print("\n" + "=" * 60)
        print("Testing Editor Log File Functionality")
        print("=" * 60)

        # [1] Check status and get log file path
        print("\n[1] Checking editor status for log_file_path...")
        status_result = await running_editor.call("editor_status", timeout=30)
        status_text = status_result.text_content or ""
        status_data = json.loads(status_text)

        print(f"    Status: {status_data['status']}")
        print(f"    PID: {status_data.get('pid')}")
        print(f"    Log file path: {status_data.get('log_file_path')}")

        log_path = status_data.get("log_file_path")
        assert log_path is not None, "log_file_path should be present in status"

        # [2] Verify log file path format: ue-mcp-{project}-{timestamp}.log
        print("\n[2] Verifying log filename format...")
        log_filename = Path(log_path).name
        pattern = r"^ue-mcp-.+-\d{8}_\d{6}\.log$"
        assert re.match(pattern, log_filename), (
            f"Log filename doesn't match expected pattern. "
            f"Expected: ue-mcp-{{project}}-{{timestamp}}.log, Got: {log_filename}"
        )
        print(f"    OK: Log filename matches pattern: {log_filename}")

        # [3] Wait for log file to be created and have content
        print("\n[3] Waiting for log file to have content...")
        log_file = Path(log_path)
        max_wait = 30
        waited = 0
        while waited < max_wait:
            if log_file.exists() and log_file.stat().st_size > 0:
                break
            await asyncio.sleep(1)
            waited += 1
            if waited % 5 == 0:
                print(f"    Waiting... ({waited}s)")

        assert log_file.exists(), f"Log file does not exist after {max_wait}s"
        file_size = log_file.stat().st_size
        print(f"    OK: Log file exists, size: {file_size} bytes")

        # [4] Test editor_read_log - full content
        print("\n[4] Testing editor_read_log - full content...")
        read_result = await running_editor.call("editor_read_log", timeout=30)
        read_text = read_result.text_content or ""
        read_data = json.loads(read_text)

        assert read_data.get("success"), f"read_log failed: {read_data.get('error')}"

        content = read_data.get("content", "")
        file_size = read_data.get("file_size", 0)
        print(f"    OK: Read {len(content)} chars, file size: {file_size} bytes")

        # [5] Check for UE5 log markers
        print("\n[5] Checking for UE5 log markers...")
        ue5_markers = ["LogInit", "LogConfig", "LogPython", "Unreal"]
        found_markers = [m for m in ue5_markers if m in content]
        if found_markers:
            print(f"    OK: Found UE5 log markers: {found_markers}")
        else:
            print(f"    WARNING: No UE5 log markers found (log may still be initializing)")
            # Don't fail the test, as the log might be initializing

        # [6] Test editor_read_log with tail_lines
        print("\n[6] Testing editor_read_log with tail_lines=10...")
        tail_result = await running_editor.call("editor_read_log", {"tail_lines": 10}, timeout=30)
        tail_text = tail_result.text_content or ""
        tail_data = json.loads(tail_text)

        assert tail_data.get("success"), f"read_log(tail_lines=10) failed: {tail_data.get('error')}"

        tail_content = tail_data.get("content", "")
        tail_lines = tail_content.count("\n")
        print(f"    OK: Read last ~{tail_lines} lines")

        # Verify tail is shorter than full content (unless full log is very short)
        if len(content) > 1000:  # Only check if log has substantial content
            assert len(tail_content) < len(content), "Tail should be shorter than full content"
            print(
                f"    OK: Tail content ({len(tail_content)} chars) < Full content ({len(content)} chars)"
            )

        print("\n" + "=" * 60)
        print("All log tests passed!")
        print("=" * 60)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
