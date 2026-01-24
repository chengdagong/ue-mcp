"""
Multi-Instance Isolation Tests for UE-MCP.

Tests that when multiple EditorManager instances are created for the same project,
each manager's remote code execution runs in its own launched editor instance.

This is a critical test for ensuring isolation when multiple ue-mcp servers
run simultaneously (e.g., for different AI agents working on the same project).

Usage:
    pytest tests/test_multi_instance_isolation.py -v -s

Note: These tests require UE5 to be installed and will launch TWO editor instances.
      Ensure sufficient system resources (~16GB RAM) are available.
"""

from pathlib import Path
from typing import Any

import pytest

from ue_mcp import EditorManager


def parse_pid_from_output(output: list[Any]) -> int:
    """
    Extract PID integer from execution output.

    Args:
        output: List of output items from execute_with_checks()

    Returns:
        Parsed PID as integer

    Raises:
        ValueError: If PID cannot be parsed from output
    """
    for item in output:
        if isinstance(item, dict):
            text = item.get("output", "")
        else:
            text = str(item)
        text = text.strip()
        if text.isdigit():
            return int(text)
    raise ValueError(f"Could not parse PID from output: {output}")


def extract_output_text(output: list[Any]) -> str:
    """Extract text from execution output list."""
    texts = []
    for item in output:
        if isinstance(item, dict):
            texts.append(item.get("output", ""))
        else:
            texts.append(str(item))
    return "".join(texts)


@pytest.fixture(scope="module")
def project_path() -> Path:
    """Return path to the ThirdPersonTemplate test project."""
    path = (
        Path(__file__).parent / "fixtures" / "ThirdPersonTemplate" / "thirdperson_template.uproject"
    )
    if not path.exists():
        pytest.skip(f"Test project not found: {path}")
    return path


@pytest.mark.integration
@pytest.mark.slow
class TestMultiInstanceIsolation:
    """
    Test that multiple EditorManager instances correctly isolate their code execution.

    These tests verify that each EditorManager communicates only with its own editor
    via dynamic multicast port allocation.
    """

    @pytest.mark.asyncio
    async def test_complete_isolation(self, project_path: Path):
        """
        Comprehensive isolation test that verifies:
        1. Two editors have different PIDs
        2. Different multicast ports are used
        3. Code execution runs in the correct editor
        4. Interleaved execution maintains isolation
        5. Reconnection after disconnect maintains isolation

        This test launches two editors once and verifies all isolation properties.
        """
        manager1 = EditorManager(project_path)
        manager2 = EditorManager(project_path)

        try:
            # === STEP 1: Launch both editors ===
            print("\n[STEP 1] Launching two editors...")

            result1 = await manager1.launch(wait_timeout=180)
            assert result1.get("success"), f"Manager 1 launch failed: {result1}"

            result2 = await manager2.launch(wait_timeout=180)
            assert result2.get("success"), f"Manager 2 launch failed: {result2}"

            # Get status info
            status1 = manager1.get_status()
            status2 = manager2.get_status()

            pid1 = status1.get("pid")
            pid2 = status2.get("pid")
            port1 = manager1._context.editor.multicast_port
            port2 = manager2._context.editor.multicast_port

            print(f"  Manager 1: PID={pid1}, Port={port1}")
            print(f"  Manager 2: PID={pid2}, Port={port2}")

            # === STEP 2: Verify different PIDs ===
            print("\n[STEP 2] Verifying different PIDs...")
            assert pid1 is not None, "Manager 1 should have a PID"
            assert pid2 is not None, "Manager 2 should have a PID"
            assert pid1 != pid2, f"Both managers should have different PIDs, got {pid1} and {pid2}"
            print(f"  [OK] PIDs are different: {pid1} vs {pid2}")

            # === STEP 3: Verify different ports ===
            print("\n[STEP 3] Verifying different multicast ports...")
            assert port1 is not None, "Manager 1 should have a multicast port"
            assert port2 is not None, "Manager 2 should have a multicast port"
            assert port1 != port2, f"Both managers should use different ports, got {port1} and {port2}"
            assert port1 >= 6767, f"Port 1 should be in dynamic range (>= 6767), got {port1}"
            assert port2 >= 6767, f"Port 2 should be in dynamic range (>= 6767), got {port2}"
            print(f"  [OK] Ports are different: {port1} vs {port2}")

            # === STEP 4: Verify code execution isolation ===
            print("\n[STEP 4] Verifying code execution isolation...")
            code = "print(__import__('os').getpid())"

            exec_result1 = manager1.execute_with_checks(code, timeout=30.0)
            assert exec_result1.get("success"), f"Execution 1 failed: {exec_result1}"
            actual_pid1 = parse_pid_from_output(exec_result1.get("output", []))

            exec_result2 = manager2.execute_with_checks(code, timeout=30.0)
            assert exec_result2.get("success"), f"Execution 2 failed: {exec_result2}"
            actual_pid2 = parse_pid_from_output(exec_result2.get("output", []))

            assert actual_pid1 == pid1, (
                f"ISOLATION FAILURE: Manager 1 executed in wrong editor! "
                f"Expected PID {pid1}, but code ran in PID {actual_pid1}"
            )
            assert actual_pid2 == pid2, (
                f"ISOLATION FAILURE: Manager 2 executed in wrong editor! "
                f"Expected PID {pid2}, but code ran in PID {actual_pid2}"
            )
            assert actual_pid1 != actual_pid2, (
                f"ISOLATION FAILURE: Code from both managers ran in same process (PID {actual_pid1})!"
            )
            print(f"  [OK] Manager 1: launched PID {pid1}, executed in PID {actual_pid1}")
            print(f"  [OK] Manager 2: launched PID {pid2}, executed in PID {actual_pid2}")

            # === STEP 5: Verify interleaved execution ===
            print("\n[STEP 5] Verifying interleaved execution (3 iterations)...")
            for i in range(3):
                r1 = manager1.execute_with_checks(
                    f"import os; print(f'M1-{i}:{{os.getpid()}}')", timeout=30.0
                )
                assert r1.get("success"), f"Iteration {i} manager1 failed: {r1}"

                r2 = manager2.execute_with_checks(
                    f"import os; print(f'M2-{i}:{{os.getpid()}}')", timeout=30.0
                )
                assert r2.get("success"), f"Iteration {i} manager2 failed: {r2}"

                output1 = extract_output_text(r1.get("output", []))
                output2 = extract_output_text(r2.get("output", []))

                assert str(pid1) in output1, (
                    f"Iteration {i}: Manager 1 executed in wrong editor. "
                    f"Expected PID {pid1} in output: {output1}"
                )
                assert str(pid2) in output2, (
                    f"Iteration {i}: Manager 2 executed in wrong editor. "
                    f"Expected PID {pid2} in output: {output2}"
                )

                print(f"  [OK] Iteration {i}: {output1.strip()}, {output2.strip()}")

            # === STEP 6: Verify reconnection maintains isolation ===
            print("\n[STEP 6] Verifying reconnection maintains isolation...")

            # Force disconnect by closing remote_client sockets
            if manager1._context.editor and manager1._context.editor.remote_client:
                manager1._context.editor.remote_client._cleanup_sockets()
                manager1._context.editor.remote_client = None

            if manager2._context.editor and manager2._context.editor.remote_client:
                manager2._context.editor.remote_client._cleanup_sockets()
                manager2._context.editor.remote_client = None

            print("  Forced disconnect, testing reconnection...")

            # Execute again - should trigger reconnection
            r1_after = manager1.execute_with_checks("import os; print(os.getpid())")
            assert r1_after.get("success"), f"Manager 1 reconnection failed: {r1_after}"
            pid1_after = parse_pid_from_output(r1_after.get("output", []))

            r2_after = manager2.execute_with_checks("import os; print(os.getpid())")
            assert r2_after.get("success"), f"Manager 2 reconnection failed: {r2_after}"
            pid2_after = parse_pid_from_output(r2_after.get("output", []))

            # Verify isolation maintained after reconnection
            assert pid1_after == pid1, (
                f"After reconnection, Manager 1 connected to wrong editor! "
                f"Expected {pid1}, got {pid1_after}"
            )
            assert pid2_after == pid2, (
                f"After reconnection, Manager 2 connected to wrong editor! "
                f"Expected {pid2}, got {pid2_after}"
            )
            print(f"  [OK] Manager 1: expected {pid1}, got {pid1_after}")
            print(f"  [OK] Manager 2: expected {pid2}, got {pid2_after}")

            print("\n[PASS] All isolation checks passed!")

        finally:
            manager1.stop()
            manager2.stop()
