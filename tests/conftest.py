"""
Shared pytest fixtures for UE-MCP tests.

This module provides fixtures for:
- mcp-pytest plugin integration for MCP server testing
- Copying EmptyProjectTemplate to temp directories for test isolation
- Mocking socket and subprocess for unit tests
"""

import os
import re
import shutil
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import yaml

# Note: mcp-pytest plugin is auto-registered via entry_points
# No need to add to pytest_plugins manually

# =============================================================================
# Path Constants for mcp_servers.yaml variable substitution
# =============================================================================

PROJECT_ROOT = Path(__file__).parent.parent
TESTS_DIR = Path(__file__).parent

# Set environment variables at module load time (before pytest_configure)
# This ensures they are available when mcp_servers.yaml is loaded
os.environ["PROJECT_ROOT"] = str(PROJECT_ROOT)
os.environ["TESTS_DIR"] = str(TESTS_DIR)


# =============================================================================
# Custom MCP Config Loader with Environment Variable Substitution
# =============================================================================


def _substitute_env_vars(value: Any) -> Any:
    """Recursively substitute ${VAR} patterns with environment variables."""
    if isinstance(value, str):
        # Replace ${VAR} patterns with environment variable values
        pattern = r"\$\{([^}]+)\}"

        def replacer(match):
            var_name = match.group(1)
            return os.environ.get(var_name, match.group(0))

        return re.sub(pattern, replacer, value)
    elif isinstance(value, dict):
        return {k: _substitute_env_vars(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [_substitute_env_vars(item) for item in value]
    return value


@pytest.fixture(scope="session")
def mcp_config(request: pytest.FixtureRequest):
    """
    Load MCP test configuration with environment variable substitution.

    Overrides the mcp-pytest default to support ${VAR} syntax in YAML.
    """
    from mcp_pytest.config.models import MCPTestConfig

    config_path = request.config.getoption("mcp_config")
    if config_path is None:
        config_path = request.config.getini("mcp_config_file")

    # Search in tests directory first, then project root
    search_paths = [TESTS_DIR, PROJECT_ROOT]

    config_file = None
    for search_dir in search_paths:
        candidate = search_dir / config_path
        if candidate.exists():
            config_file = candidate
            break

    if config_file is None:
        # Return default config
        return MCPTestConfig()

    # Load YAML with environment variable substitution
    with open(config_file, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if data is None:
        data = {}

    # Substitute environment variables
    data = _substitute_env_vars(data)

    return MCPTestConfig.model_validate(data)


@pytest.fixture(scope="session")
def project_template_path() -> Path:
    """Return the path to EmptyProjectTemplate fixture."""
    return Path(__file__).parent / "fixtures" / "EmptyProjectTemplate"


@pytest.fixture(scope="session")
async def initialized_mcp_client(mcp_client, project_template_path):
    """
    MCP client with project path already set.

    For Automatic-Testing clients, project_set_path must be called first.
    This fixture handles that initialization.
    """
    from mcp_pytest import ToolCaller

    # Check if project_set_path is available (it should be for Automatic-Testing)
    tools = await mcp_client.list_tools()
    tool_names = [t.name for t in tools]

    if "project_set_path" in tool_names:
        # Call project_set_path to initialize
        result = await mcp_client.call_tool(
            "project_set_path",
            {"project_path": str(project_template_path)},
        )
        # Log the result for debugging
        import logging

        logger = logging.getLogger(__name__)
        logger.info(f"project_set_path result: {result}")

    return mcp_client


@pytest.fixture(scope="session")
async def initialized_tool_caller(
    initialized_mcp_client,
    mcp_config,
    file_tracker,
):
    """
    Tool caller with project path already set.

    Use this instead of tool_caller when testing tools that require
    the project to be initialized first.
    """
    from mcp_pytest import ToolCaller

    return ToolCaller(
        session=initialized_mcp_client,
        default_timeout=mcp_config.default_timeout,
        file_tracker=file_tracker,
    )


@pytest.fixture
def temp_project(tmp_path: Path, project_template_path: Path) -> Path:
    """
    Copy ThirdPersonTemplate to a temp directory before each test.

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
    return temp_project / "thirdperson_template.uproject"


@pytest.fixture(scope="session")
def test_output_dir() -> Path:
    """
    Create a persistent test output directory for screenshot captures.

    This directory is NOT automatically deleted, allowing inspection of
    generated files after tests pass or fail.

    Returns:
        Path to the test output directory
    """
    tests_dir = Path(__file__).parent
    output_dir = tests_dir / "test_output"
    output_dir.mkdir(exist_ok=True)
    return output_dir


@pytest.fixture
def temp_uproject(temp_project: Path) -> Path:
    """Return the path to the temp project's .uproject file."""
    return temp_project / "thirdperson_template.uproject"


@pytest.fixture(scope="session", autouse=True)
def clean_test_output_dir():
    """
    Clean test output directory before test session starts.

    This fixture runs automatically before all tests to ensure
    a clean slate and prevent old screenshots from interfering
    with verification.
    """
    import shutil

    tests_dir = Path(__file__).parent
    output_dir = tests_dir / "test_output"

    # Clear directory if it exists
    if output_dir.exists():
        shutil.rmtree(output_dir)

    yield

    # Clean up after session
    if output_dir.exists():
        shutil.rmtree(output_dir)


@pytest.fixture(scope="session")
def test_output_dir() -> Path:
    """
    Test output directory for screenshots and test artifacts.

    Directory is automatically cleaned at the start of each test session.

    Directory structure:
        tests/test_output/
            ├── orbital/       - Orbital capture screenshots
            ├── pie/          - PIE capture screenshots
            ├── window/       - Window capture screenshots
            └── batch/        - Batch capture screenshots

    Returns:
        Path to the test output directory
    """
    tests_dir = Path(__file__).parent
    output_dir = tests_dir / "test_output"
    output_dir.mkdir(exist_ok=True)
    return output_dir


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
