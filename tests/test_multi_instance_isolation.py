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
        output: List of output items from execute_with_auto_install()

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

    These tests verify that the PID verification mechanism in RemoteExecutionClient
    correctly ensures each EditorManager communicates only with its own editor.
    """

    @pytest.mark.asyncio
    async def test_two_editors_have_different_pids(self, project_path: Path):
        """
        Test that two EditorManagers launch separate UE5 processes with different PIDs.

        This is the foundation test - if two managers launch the same PID,
        isolation is fundamentally broken.
        """
        manager1 = EditorManager(project_path)
        manager2 = EditorManager(project_path)

        try:
            # Launch both editors sequentially
            result1 = await manager1.launch(wait_timeout=180)
            assert result1.get("success"), f"Manager 1 launch failed: {result1}"

            result2 = await manager2.launch(wait_timeout=180)
            assert result2.get("success"), f"Manager 2 launch failed: {result2}"

            # Get PIDs from status
            status1 = manager1.get_status()
            status2 = manager2.get_status()

            pid1 = status1.get("pid")
            pid2 = status2.get("pid")

            # Verify different PIDs
            assert pid1 is not None, "Manager 1 should have a PID"
            assert pid2 is not None, "Manager 2 should have a PID"
            assert pid1 != pid2, f"Both managers should have different PIDs, got {pid1} and {pid2}"

            print(f"\n[OK] Manager 1 PID: {pid1}")
            print(f"[OK] Manager 2 PID: {pid2}")

        finally:
            # Cleanup - stop both editors
            manager1.stop()
            manager2.stop()

    @pytest.mark.asyncio
    async def test_code_execution_isolation(self, project_path: Path):
        """
        [CORE TEST] Verify code execution runs in the correct editor instance.

        This is the primary isolation test:
        1. Launch two editors with two managers
        2. Execute os.getpid() via each manager
        3. Verify the returned PID matches each manager's editor PID

        If this test fails, it indicates that code execution from one manager
        is being routed to another manager's editor - a critical isolation failure.
        """
        manager1 = EditorManager(project_path)
        manager2 = EditorManager(project_path)

        try:
            # Launch both editors
            result1 = await manager1.launch(wait_timeout=180)
            assert result1.get("success"), f"Manager 1 launch failed: {result1}"

            result2 = await manager2.launch(wait_timeout=180)
            assert result2.get("success"), f"Manager 2 launch failed: {result2}"

            # Get expected PIDs from status
            expected_pid1 = manager1.get_status().get("pid")
            expected_pid2 = manager2.get_status().get("pid")

            print(f"\n[INFO] Manager 1 launched editor with PID: {expected_pid1}")
            print(f"[INFO] Manager 2 launched editor with PID: {expected_pid2}")

            # Execute code to get actual PIDs from inside the editor
            code = "import os; print(os.getpid())"

            exec_result1 = manager1.execute_with_auto_install(code, timeout=30.0)
            assert exec_result1.get("success"), f"Execution 1 failed: {exec_result1}"
            actual_pid1 = parse_pid_from_output(exec_result1.get("output", []))

            exec_result2 = manager2.execute_with_auto_install(code, timeout=30.0)
            assert exec_result2.get("success"), f"Execution 2 failed: {exec_result2}"
            actual_pid2 = parse_pid_from_output(exec_result2.get("output", []))

            print(f"[INFO] Manager 1 execute returned PID: {actual_pid1}")
            print(f"[INFO] Manager 2 execute returned PID: {actual_pid2}")

            # CRITICAL ASSERTIONS - Verify isolation
            assert actual_pid1 == expected_pid1, (
                f"ISOLATION FAILURE: Manager 1 executed code in wrong editor! "
                f"Expected PID {expected_pid1}, but code ran in PID {actual_pid1}"
            )
            assert actual_pid2 == expected_pid2, (
                f"ISOLATION FAILURE: Manager 2 executed code in wrong editor! "
                f"Expected PID {expected_pid2}, but code ran in PID {actual_pid2}"
            )

            # Double-check they're different (should be, but verify)
            assert actual_pid1 != actual_pid2, (
                f"ISOLATION FAILURE: Code from both managers ran in same process "
                f"(PID {actual_pid1})!"
            )

            print(f"\n[PASS] Isolation verified:")
            print(f"  Manager 1: launched PID {expected_pid1}, executed in PID {actual_pid1}")
            print(f"  Manager 2: launched PID {expected_pid2}, executed in PID {actual_pid2}")

        finally:
            manager1.stop()
            manager2.stop()

    @pytest.mark.asyncio
    async def test_interleaved_execution(self, project_path: Path):
        """
        Test isolation with interleaved code execution.

        This tests a more realistic scenario where both managers
        execute code in an alternating pattern, ensuring isolation
        is maintained across multiple executions.
        """
        manager1 = EditorManager(project_path)
        manager2 = EditorManager(project_path)

        try:
            # Launch both editors
            await manager1.launch(wait_timeout=180)
            await manager2.launch(wait_timeout=180)

            expected_pid1 = manager1.get_status().get("pid")
            expected_pid2 = manager2.get_status().get("pid")

            print(f"\n[INFO] Starting interleaved execution test")
            print(f"[INFO] Manager 1 PID: {expected_pid1}, Manager 2 PID: {expected_pid2}")

            # Execute multiple times in alternating pattern
            for i in range(3):
                # Execute via manager1
                r1 = manager1.execute_with_auto_install(
                    f"import os; print(f'M1-{i}:{{os.getpid()}}')", timeout=30.0
                )
                assert r1.get("success"), f"Iteration {i} manager1 failed: {r1}"

                # Execute via manager2
                r2 = manager2.execute_with_auto_install(
                    f"import os; print(f'M2-{i}:{{os.getpid()}}')", timeout=30.0
                )
                assert r2.get("success"), f"Iteration {i} manager2 failed: {r2}"

                # Verify PIDs in output
                output1 = self._extract_output_text(r1.get("output", []))
                output2 = self._extract_output_text(r2.get("output", []))

                assert str(expected_pid1) in output1, (
                    f"Iteration {i}: Manager 1 executed in wrong editor. "
                    f"Expected PID {expected_pid1} in output: {output1}"
                )
                assert str(expected_pid2) in output2, (
                    f"Iteration {i}: Manager 2 executed in wrong editor. "
                    f"Expected PID {expected_pid2} in output: {output2}"
                )

                print(f"[OK] Iteration {i}: M1 -> {output1.strip()}, M2 -> {output2.strip()}")

        finally:
            manager1.stop()
            manager2.stop()

    @staticmethod
    def _extract_output_text(output: list[Any]) -> str:
        """Extract text from execution output list."""
        texts = []
        for item in output:
            if isinstance(item, dict):
                texts.append(item.get("output", ""))
            else:
                texts.append(str(item))
        return "".join(texts)

    @pytest.mark.asyncio
    async def test_node_id_isolation(self, project_path: Path):
        """
        Test that each EditorManager connects to a different node_id.

        The node_id is a unique identifier assigned by UE5's remote execution
        system. Different editor instances should have different node_ids,
        and this is used as part of the filtering mechanism.
        """
        manager1 = EditorManager(project_path)
        manager2 = EditorManager(project_path)

        try:
            await manager1.launch(wait_timeout=180)
            await manager2.launch(wait_timeout=180)

            # Access internal _editor to get node_id
            node_id1 = manager1._editor.node_id if manager1._editor else None
            node_id2 = manager2._editor.node_id if manager2._editor else None

            assert node_id1 is not None, "Manager 1 should have a node_id"
            assert node_id2 is not None, "Manager 2 should have a node_id"
            assert node_id1 != node_id2, (
                f"Both managers connected to the same node_id ({node_id1})! "
                "This indicates they might be talking to the same UE5 instance."
            )

            print(f"\n[OK] Manager 1 node_id: {node_id1}")
            print(f"[OK] Manager 2 node_id: {node_id2}")

        finally:
            manager1.stop()
            manager2.stop()


@pytest.mark.integration
@pytest.mark.slow
class TestMultiInstanceReconnection:
    """
    Test isolation during reconnection scenarios.

    These tests verify that when a connection is lost and re-established,
    each manager still connects to its own editor instance.
    """

    @pytest.mark.asyncio
    async def test_reconnection_maintains_isolation(self, project_path: Path):
        """
        Test that reconnection after disconnect maintains proper isolation.

        Simulates connection loss by closing remote_client and verifying
        that execute_with_auto_install() reconnects to the correct editor.
        """
        manager1 = EditorManager(project_path)
        manager2 = EditorManager(project_path)

        try:
            await manager1.launch(wait_timeout=180)
            await manager2.launch(wait_timeout=180)

            expected_pid1 = manager1.get_status().get("pid")
            expected_pid2 = manager2.get_status().get("pid")

            # First execution - establish baseline
            r1 = manager1.execute_with_auto_install("import os; print(os.getpid())")
            assert r1.get("success")

            r2 = manager2.execute_with_auto_install("import os; print(os.getpid())")
            assert r2.get("success")

            # Force disconnect by closing remote_client sockets
            # The next execute should trigger reconnection
            if manager1._editor and manager1._editor.remote_client:
                manager1._editor.remote_client._cleanup_sockets()
                manager1._editor.remote_client = None

            if manager2._editor and manager2._editor.remote_client:
                manager2._editor.remote_client._cleanup_sockets()
                manager2._editor.remote_client = None

            print("\n[INFO] Forced disconnect, testing reconnection...")

            # Execute again - should trigger reconnection
            r1_after = manager1.execute_with_auto_install("import os; print(os.getpid())")
            assert r1_after.get("success"), f"Manager 1 reconnection failed: {r1_after}"
            pid1_after = parse_pid_from_output(r1_after.get("output", []))

            r2_after = manager2.execute_with_auto_install("import os; print(os.getpid())")
            assert r2_after.get("success"), f"Manager 2 reconnection failed: {r2_after}"
            pid2_after = parse_pid_from_output(r2_after.get("output", []))

            # Verify isolation maintained after reconnection
            assert pid1_after == expected_pid1, (
                f"After reconnection, Manager 1 connected to wrong editor! "
                f"Expected {expected_pid1}, got {pid1_after}"
            )
            assert pid2_after == expected_pid2, (
                f"After reconnection, Manager 2 connected to wrong editor! "
                f"Expected {expected_pid2}, got {pid2_after}"
            )

            print(f"[PASS] Reconnection isolation verified:")
            print(f"  Manager 1: expected {expected_pid1}, got {pid1_after}")
            print(f"  Manager 2: expected {expected_pid2}, got {pid2_after}")

        finally:
            manager1.stop()
            manager2.stop()
