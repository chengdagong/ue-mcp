"""
Shared pytest fixtures for UE-MCP tests.

This module provides fixtures for:
- Copying EmptyProjectTemplate to temp directories for test isolation
- Mocking socket and subprocess for unit tests
"""

import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def project_template_path() -> Path:
    """Return the path to EmptyProjectTemplate fixture."""
    return Path(__file__).parent / "fixtures" / "EmptyProjectTemplate"


@pytest.fixture
def temp_project(tmp_path: Path, project_template_path: Path) -> Path:
    """
    Copy EmptyProjectTemplate to a temp directory before each test.

    This ensures test isolation - each test gets a fresh copy of the project.
    The copy excludes DerivedDataCache, Intermediate, and Saved directories
    to speed up the copy operation.

    Returns:
        Path to the temporary project root directory
    """
    dest = tmp_path / "TestProject"
    shutil.copytree(
        project_template_path,
        dest,
        ignore=shutil.ignore_patterns(
            "DerivedDataCache",
            "Intermediate",
            "Saved",
        ),
    )
    return dest


@pytest.fixture
def temp_uproject(temp_project: Path) -> Path:
    """Return the path to the temp project's .uproject file."""
    return temp_project / "EmptyProjectTemplate.uproject"


@pytest.fixture
def temp_engine_ini(temp_project: Path) -> Path:
    """Return the path to the temp project's DefaultEngine.ini file."""
    return temp_project / "Config" / "DefaultEngine.ini"


@pytest.fixture
def mock_socket():
    """Mock socket module for RemoteExecutionClient tests."""
    with patch("ue_mcp.remote_client.socket") as mock_sock:
        yield mock_sock


@pytest.fixture
def mock_subprocess():
    """
    Mock subprocess module for EditorManager tests.

    Returns a tuple of (mock_subprocess_module, mock_process).
    """
    with patch("ue_mcp.editor_manager.subprocess") as mock_sub:
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_process.poll.return_value = None  # Process is running
        mock_process.returncode = 0
        mock_sub.Popen.return_value = mock_process
        yield mock_sub, mock_process


@pytest.fixture
def mock_remote_client():
    """
    Mock RemoteExecutionClient for EditorManager tests.

    Returns a tuple of (mock_class, mock_instance).
    """
    with patch("ue_mcp.editor_manager.RemoteExecutionClient") as mock_cls:
        mock_client = MagicMock()
        mock_client.find_unreal_instance.return_value = True
        mock_client.open_connection.return_value = True
        mock_client.verify_pid.return_value = True
        mock_client.is_connected.return_value = True
        mock_client.get_node_id.return_value = "test-node-id"
        mock_client.execute.return_value = {"success": True, "output": []}
        mock_cls.return_value = mock_client
        yield mock_cls, mock_client
