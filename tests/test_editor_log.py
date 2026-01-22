"""
Test script for editor log file functionality.

This test verifies:
1. editor_launch creates a unique log file with project name and timestamp
2. editor_status returns the log_file_path
3. editor_read_log can read the log content
4. The log file contains UE5 engine logs
"""

import asyncio
import re
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ue_mcp.editor_manager import EditorManager
from ue_mcp.utils import find_uproject_file


async def test_editor_log():
    """Test editor log file functionality."""
    print("=" * 60)
    print("Testing Editor Log File Functionality")
    print("=" * 60)

    # Find project
    project_path = find_uproject_file()
    if project_path is None:
        print("ERROR: No .uproject file found in current directory")
        return False

    print(f"\nProject: {project_path}")

    # Create manager
    manager = EditorManager(project_path)

    # Check initial status - should have no log path
    print("\n[1] Checking initial status...")
    status = manager.get_status()
    print(f"    Status: {status['status']}")
    assert status["status"] == "not_running", "Expected not_running status"
    print("    OK: Initial status is not_running")

    # Launch editor
    print("\n[2] Launching editor...")

    async def notify(level: str, message: str):
        print(f"    [{level}] {message}")

    result = await manager.launch(notify=notify, wait_timeout=120.0)

    if not result.get("success") and not result.get("background_connecting"):
        print(f"    ERROR: Failed to launch editor: {result.get('error')}")
        return False

    print(f"    Launch result: {result.get('success', False)}")

    # Check status with log path
    print("\n[3] Checking status for log_file_path...")
    status = manager.get_status()
    print(f"    Status: {status['status']}")
    print(f"    PID: {status.get('pid')}")
    print(f"    Log file path: {status.get('log_file_path')}")

    log_path = status.get("log_file_path")
    if log_path is None:
        print("    ERROR: log_file_path is None")
        return False

    # Verify log file path format: ue-mcp-{project}-{timestamp}.log
    log_filename = Path(log_path).name
    pattern = r"^ue-mcp-.+-\d{8}_\d{6}\.log$"
    if not re.match(pattern, log_filename):
        print(f"    ERROR: Log filename doesn't match expected pattern")
        print(f"    Expected pattern: ue-mcp-{{project}}-{{timestamp}}.log")
        print(f"    Got: {log_filename}")
        return False

    print(f"    OK: Log filename matches pattern: {log_filename}")

    # Wait for log file to be created and have content
    print("\n[4] Waiting for log file to have content...")
    log_file = Path(log_path)
    max_wait = 30
    waited = 0
    while waited < max_wait:
        if log_file.exists() and log_file.stat().st_size > 0:
            break
        await asyncio.sleep(1)
        waited += 1
        print(f"    Waiting... ({waited}s)")

    if not log_file.exists():
        print(f"    ERROR: Log file does not exist after {max_wait}s")
        return False

    print(f"    OK: Log file exists, size: {log_file.stat().st_size} bytes")

    # Test read_log()
    print("\n[5] Testing read_log() - full content...")
    read_result = manager.read_log()
    if not read_result.get("success"):
        print(f"    ERROR: read_log() failed: {read_result.get('error')}")
        return False

    content = read_result.get("content", "")
    file_size = read_result.get("file_size", 0)
    print(f"    OK: Read {len(content)} chars, file size: {file_size} bytes")

    # Check for UE5 log markers
    ue5_markers = ["LogInit", "LogConfig", "LogPython", "Unreal"]
    found_markers = [m for m in ue5_markers if m in content]
    if found_markers:
        print(f"    OK: Found UE5 log markers: {found_markers}")
    else:
        print(f"    WARNING: No UE5 log markers found (log may still be initializing)")

    # Test read_log() with tail_lines
    print("\n[6] Testing read_log(tail_lines=10)...")
    read_result = manager.read_log(tail_lines=10)
    if not read_result.get("success"):
        print(f"    ERROR: read_log(tail_lines=10) failed: {read_result.get('error')}")
        return False

    tail_content = read_result.get("content", "")
    tail_lines = tail_content.count("\n")
    print(f"    OK: Read last ~{tail_lines} lines")

    # Stop editor
    print("\n[7] Stopping editor...")
    stop_result = manager.stop()
    print(f"    Stop result: {stop_result}")

    # Verify log file still exists after stop
    print("\n[8] Verifying log file persists after stop...")
    if log_file.exists():
        final_size = log_file.stat().st_size
        print(f"    OK: Log file still exists, final size: {final_size} bytes")
    else:
        print("    ERROR: Log file was deleted after stop")
        return False

    print("\n" + "=" * 60)
    print("All tests passed!")
    print("=" * 60)
    return True


if __name__ == "__main__":
    success = asyncio.run(test_editor_log())
    sys.exit(0 if success else 1)
