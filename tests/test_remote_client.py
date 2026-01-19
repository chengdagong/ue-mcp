"""Tests for ue_mcp.remote_client module."""

from unittest.mock import MagicMock, patch

import pytest

from ue_mcp.remote_client import RemoteExecutionClient


class TestRemoteExecutionClientInit:
    """Tests for RemoteExecutionClient initialization."""

    def test_default_init(self):
        """Test default initialization."""
        client = RemoteExecutionClient()
        assert client.multicast_group == ("239.0.0.1", 6766)
        assert client.multicast_bind_address == "0.0.0.0"
        assert client.project_name == ""
        assert client.expected_node_id is None
        assert client.expected_pid is None

    def test_init_with_project_name(self):
        """Test initialization with project name."""
        client = RemoteExecutionClient(project_name="TestProject")
        assert client.project_name == "TestProject"

    def test_init_with_expected_node_id(self):
        """Test initialization with expected node ID."""
        client = RemoteExecutionClient(expected_node_id="node-123")
        assert client.expected_node_id == "node-123"

    def test_init_with_expected_pid(self):
        """Test initialization with expected PID."""
        client = RemoteExecutionClient(expected_pid=12345)
        assert client.expected_pid == 12345

    def test_init_with_custom_multicast(self):
        """Test initialization with custom multicast settings."""
        client = RemoteExecutionClient(
            multicast_group=("239.0.0.2", 6767),
            multicast_bind_address="127.0.0.1",
        )
        assert client.multicast_group == ("239.0.0.2", 6767)
        assert client.multicast_bind_address == "127.0.0.1"


class TestRemoteExecutionClientConnection:
    """Tests for connection-related methods."""

    def test_is_connected_false_initially(self):
        """Test that client is not connected initially."""
        client = RemoteExecutionClient()
        assert client.is_connected() is False

    def test_get_node_id_none_initially(self):
        """Test that node ID is None initially."""
        client = RemoteExecutionClient()
        assert client.get_node_id() is None

    def test_is_connected_true_when_connected(self):
        """Test is_connected returns True when connection established."""
        client = RemoteExecutionClient()
        client.cmd_connection = MagicMock()
        client.unreal_node_id = "test-node"
        assert client.is_connected() is True

    def test_is_connected_false_without_node_id(self):
        """Test is_connected returns False without node ID."""
        client = RemoteExecutionClient()
        client.cmd_connection = MagicMock()
        client.unreal_node_id = None
        assert client.is_connected() is False


class TestRemoteExecutionClientVerifyPid:
    """Tests for verify_pid method."""

    def test_verify_pid_not_connected(self):
        """Test verify_pid returns False when not connected."""
        client = RemoteExecutionClient()
        assert client.verify_pid(12345) is False

    def test_verify_pid_success(self):
        """Test verify_pid returns True on PID match."""
        client = RemoteExecutionClient()
        client.cmd_connection = MagicMock()
        client.unreal_node_id = "test-node"

        # Mock execute to return matching PID
        with patch.object(client, "execute") as mock_execute:
            mock_execute.return_value = {
                "success": True,
                "output": [{"output": "12345\n"}],
            }
            result = client.verify_pid(12345)
            assert result is True

    def test_verify_pid_mismatch(self):
        """Test verify_pid returns False on PID mismatch."""
        client = RemoteExecutionClient()
        client.cmd_connection = MagicMock()
        client.unreal_node_id = "test-node"

        with patch.object(client, "execute") as mock_execute:
            mock_execute.return_value = {
                "success": True,
                "output": [{"output": "99999\n"}],
            }
            result = client.verify_pid(12345)
            assert result is False

    def test_verify_pid_execute_failed(self):
        """Test verify_pid returns False when execution fails."""
        client = RemoteExecutionClient()
        client.cmd_connection = MagicMock()
        client.unreal_node_id = "test-node"

        with patch.object(client, "execute") as mock_execute:
            mock_execute.return_value = {"success": False, "output": []}
            result = client.verify_pid(12345)
            assert result is False

    def test_verify_pid_unparseable_output(self):
        """Test verify_pid returns False with unparseable output."""
        client = RemoteExecutionClient()
        client.cmd_connection = MagicMock()
        client.unreal_node_id = "test-node"

        with patch.object(client, "execute") as mock_execute:
            mock_execute.return_value = {
                "success": True,
                "output": [{"output": "not a number\n"}],
            }
            result = client.verify_pid(12345)
            assert result is False


class TestRemoteExecutionClientMessageParsing:
    """Tests for message parsing logic."""

    def test_exec_types(self):
        """Test ExecTypes enum values."""
        assert RemoteExecutionClient.ExecTypes.EXECUTE_FILE == "ExecuteFile"
        assert RemoteExecutionClient.ExecTypes.EXECUTE_STATEMENT == "ExecuteStatement"
        assert RemoteExecutionClient.ExecTypes.EVALUATE_STATEMENT == "EvaluateStatement"

    def test_buffer_size(self):
        """Test buffer size constant."""
        client = RemoteExecutionClient()
        assert client.BUFFER_SIZE == 2_097_152
