"""Tests for ue_mcp.editor_manager module."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ue_mcp.editor_manager import EditorInstance, EditorManager


class TestEditorInstance:
    """Tests for EditorInstance dataclass."""

    def test_create_instance(self):
        """Test creating an EditorInstance."""
        mock_process = MagicMock()
        mock_process.pid = 12345

        instance = EditorInstance(process=mock_process)
        assert instance.process.pid == 12345
        assert instance.status == "starting"
        assert instance.remote_client is None
        assert instance.node_id is None

    def test_instance_with_all_fields(self):
        """Test creating instance with all fields."""
        mock_process = MagicMock()
        mock_client = MagicMock()

        instance = EditorInstance(
            process=mock_process,
            status="ready",
            remote_client=mock_client,
            node_id="test-node",
        )
        assert instance.status == "ready"
        assert instance.remote_client is mock_client
        assert instance.node_id == "test-node"


class TestEditorManagerInit:
    """Tests for EditorManager initialization."""

    def test_init(self, temp_uproject: Path):
        """Test EditorManager initialization."""
        manager = EditorManager(temp_uproject)
        assert manager.project_name == "EmptyProjectTemplate"
        assert manager.project_root == temp_uproject.parent
        assert manager.project_path == temp_uproject

    def test_init_not_running(self, temp_uproject: Path):
        """Test that editor is not running initially."""
        manager = EditorManager(temp_uproject)
        assert manager.is_running() is False


class TestEditorManagerStatus:
    """Tests for EditorManager.get_status method."""

    def test_status_not_running(self, temp_uproject: Path):
        """Test status when editor is not running."""
        manager = EditorManager(temp_uproject)
        status = manager.get_status()

        assert status["status"] == "not_running"
        assert status["project_name"] == "EmptyProjectTemplate"
        assert status["project_path"] == str(temp_uproject)
        # When not running, pid and connected are not in status
        assert "pid" not in status
        assert "connected" not in status

    def test_status_running(self, temp_uproject: Path):
        """Test status when editor is running."""
        manager = EditorManager(temp_uproject)

        # Manually set up running state
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_process.poll.return_value = None

        mock_client = MagicMock()
        mock_client.is_connected.return_value = True

        manager._editor = EditorInstance(
            process=mock_process,
            status="ready",
            remote_client=mock_client,
            node_id="test-node",
        )

        status = manager.get_status()
        assert status["status"] == "ready"
        assert status["pid"] == 12345
        assert status["connected"] is True


class TestEditorManagerLaunch:
    """Tests for EditorManager.launch method."""

    def test_launch_success(
        self, temp_uproject: Path, mock_subprocess, mock_remote_client
    ):
        """Test successful editor launch."""
        mock_sub, mock_process = mock_subprocess
        mock_cls, mock_client = mock_remote_client

        manager = EditorManager(temp_uproject)

        with patch(
            "ue_mcp.editor_manager.find_ue5_editor_for_project"
        ) as mock_find:
            mock_find.return_value = Path("C:/UE5/Engine/Binaries/Win64/UnrealEditor.exe")
            result = manager.launch(wait_timeout=5.0)

        assert result["success"] is True
        assert manager.is_running()
        assert manager._editor.status == "ready"

    def test_launch_already_running(
        self, temp_uproject: Path, mock_subprocess, mock_remote_client
    ):
        """Test launch when editor is already running."""
        mock_sub, mock_process = mock_subprocess
        mock_cls, mock_client = mock_remote_client

        manager = EditorManager(temp_uproject)

        with patch(
            "ue_mcp.editor_manager.find_ue5_editor_for_project"
        ) as mock_find:
            mock_find.return_value = Path("C:/UE5/Engine/Binaries/Win64/UnrealEditor.exe")
            # First launch
            manager.launch(wait_timeout=5.0)
            # Second launch should fail
            result = manager.launch(wait_timeout=5.0)

        assert result["success"] is False
        assert "already running" in result["error"].lower()

    def test_launch_editor_not_found(self, temp_uproject: Path):
        """Test launch when editor executable not found."""
        manager = EditorManager(temp_uproject)

        with patch(
            "ue_mcp.editor_manager.find_ue5_editor_for_project"
        ) as mock_find:
            mock_find.return_value = None
            result = manager.launch(wait_timeout=5.0)

        assert result["success"] is False
        assert "could not find" in result["error"].lower()

    def test_launch_connection_timeout(self, temp_uproject: Path, mock_subprocess):
        """Test launch when connection times out."""
        mock_sub, mock_process = mock_subprocess

        manager = EditorManager(temp_uproject)

        with patch(
            "ue_mcp.editor_manager.find_ue5_editor_for_project"
        ) as mock_find, patch(
            "ue_mcp.editor_manager.RemoteExecutionClient"
        ) as mock_client_cls:
            mock_find.return_value = Path("C:/UE5/Engine/Binaries/Win64/UnrealEditor.exe")
            mock_client = MagicMock()
            mock_client.find_unreal_instance.return_value = False
            mock_client_cls.return_value = mock_client

            result = manager.launch(wait_timeout=0.1)  # Very short timeout

        assert result["success"] is False
        assert "timeout" in result["error"].lower()


class TestEditorManagerStop:
    """Tests for EditorManager.stop method."""

    def test_stop_not_running(self, temp_uproject: Path):
        """Test stop when editor is not running."""
        manager = EditorManager(temp_uproject)
        result = manager.stop()

        assert result["success"] is False
        assert "no editor is running" in result["error"].lower()

    def test_stop_graceful(
        self, temp_uproject: Path, mock_subprocess, mock_remote_client
    ):
        """Test graceful stop."""
        mock_sub, mock_process = mock_subprocess
        mock_cls, mock_client = mock_remote_client
        mock_process.wait.return_value = 0

        manager = EditorManager(temp_uproject)

        with patch(
            "ue_mcp.editor_manager.find_ue5_editor_for_project"
        ) as mock_find:
            mock_find.return_value = Path("C:/UE5/Engine/Binaries/Win64/UnrealEditor.exe")
            manager.launch(wait_timeout=5.0)
            result = manager.stop()

        assert result["success"] is True
        # Verify graceful shutdown was attempted
        mock_client.execute.assert_called()


class TestEditorManagerExecute:
    """Tests for EditorManager.execute method."""

    def test_execute_not_running(self, temp_uproject: Path):
        """Test execute when editor is not running."""
        manager = EditorManager(temp_uproject)
        result = manager.execute("print('hello')")

        assert result["success"] is False
        assert "no editor is running" in result["error"].lower()

    def test_execute_success(
        self, temp_uproject: Path, mock_subprocess, mock_remote_client
    ):
        """Test successful code execution."""
        mock_sub, mock_process = mock_subprocess
        mock_cls, mock_client = mock_remote_client
        mock_client.execute.return_value = {
            "success": True,
            "output": [{"output": "hello\n"}],
        }

        manager = EditorManager(temp_uproject)

        with patch(
            "ue_mcp.editor_manager.find_ue5_editor_for_project"
        ) as mock_find:
            mock_find.return_value = Path("C:/UE5/Engine/Binaries/Win64/UnrealEditor.exe")
            manager.launch(wait_timeout=5.0)
            result = manager.execute("print('hello')")

        assert result["success"] is True

    def test_execute_editor_not_ready(
        self, temp_uproject: Path, mock_subprocess, mock_remote_client
    ):
        """Test execute when editor is not ready."""
        mock_sub, mock_process = mock_subprocess

        manager = EditorManager(temp_uproject)
        manager._editor = EditorInstance(
            process=mock_process,
            status="starting",  # Not ready
        )

        result = manager.execute("print('hello')")
        assert result["success"] is False
        assert "not ready" in result["error"].lower()
