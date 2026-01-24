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
    return (
        Path(__file__).parent / "fixtures" / "ThirdPersonTemplate" / "thirdperson_template.uproject"
    )


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


# =============================================================================
# Session Output Directory Management
# =============================================================================

# Maximum number of session directories to keep
MAX_SESSION_DIRS = 10


def _get_session_dirs(output_dir: Path) -> list[Path]:
    """Get all session directories sorted by name (oldest first)."""
    if not output_dir.exists():
        return []

    session_dirs = [
        d for d in output_dir.iterdir()
        if d.is_dir() and d.name.startswith("session_")
    ]
    # Sort by name (which includes timestamp, so chronological order)
    return sorted(session_dirs, key=lambda d: d.name)


def _cleanup_old_sessions(output_dir: Path, keep_count: int = MAX_SESSION_DIRS):
    """Remove old session directories, keeping only the most recent ones."""
    session_dirs = _get_session_dirs(output_dir)

    # If we have more than keep_count, remove the oldest ones
    dirs_to_remove = session_dirs[:-keep_count] if len(session_dirs) > keep_count else []

    for old_dir in dirs_to_remove:
        try:
            shutil.rmtree(old_dir)
        except (PermissionError, OSError):
            # Skip directories that are in use or can't be deleted
            pass


@pytest.fixture(scope="session", autouse=True)
def clean_old_sessions():
    """
    Clean old session directories before test session starts.

    This fixture runs automatically before all tests to:
    1. Keep only the most recent MAX_SESSION_DIRS (10) session directories
    2. Clean up any non-session files in the output directory

    Note: The current session directory is created AFTER this cleanup runs.
    """
    tests_dir = Path(__file__).parent
    output_dir = tests_dir / "test_output"

    if output_dir.exists():
        # Clean up old session directories (keep last MAX_SESSION_DIRS)
        _cleanup_old_sessions(output_dir, MAX_SESSION_DIRS)

        # Clean up any loose files (not in session directories)
        for item in output_dir.iterdir():
            if item.is_file():
                try:
                    item.unlink()
                except (PermissionError, OSError):
                    pass

    yield


@pytest.fixture(scope="session")
def test_session_dir(request) -> Path:
    """
    Get the timestamped session directory for this test run.

    The session directory is created in pytest_configure to ensure
    both log files and test outputs go to the same directory.

    Each test session gets its own unique directory with format:
        session_YYYYMMDD_HHMMSS

    This ensures test outputs from different runs don't overwrite each other.

    Returns:
        Path to the session-specific output directory
    """
    # Get session directory from pytest config (created in pytest_configure)
    session_dir = getattr(request.config, "_test_session_dir", None)

    if session_dir is None:
        # Fallback: create session directory if not set (e.g., in some test scenarios)
        from datetime import datetime

        tests_dir = Path(__file__).parent
        output_dir = tests_dir / "test_output"
        output_dir.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        session_dir = output_dir / f"session_{timestamp}"
        session_dir.mkdir(exist_ok=True)

    return session_dir


@pytest.fixture(scope="session")
def test_output_dir(test_session_dir: Path) -> Path:
    """
    Test output directory for screenshots and test artifacts.

    Returns the current session's output directory. Each test session
    gets a unique timestamped directory to preserve outputs across runs.

    Directory structure:
        tests/test_output/
            └── session_YYYYMMDD_HHMMSS/   <- Current session
                ├── log/                    - Pytest log file
                ├── orbital/                - Orbital capture screenshots
                ├── pie/                    - PIE capture screenshots
                ├── window/                 - Window capture screenshots
                ├── test_trace_*/           - Actor trace outputs
                └── ...

    Returns:
        Path to the current session's output directory
    """
    return test_session_dir


@pytest.fixture
def temp_engine_ini(temp_project: Path) -> Path:
    """Return the path to the temp project's DefaultEngine.ini file."""
    return temp_project / "Config" / "DefaultEngine.ini"


# =============================================================================
# Shared Editor Fixture for Integration Tests
# =============================================================================


@pytest.fixture(scope="session")
async def running_editor(initialized_tool_caller, request):
    """
    Session-scoped fixture that launches the editor once for all tests.

    This fixture:
    1. Launches UE5 editor at the start of the test session
    2. Keeps it running for all tests that need it
    3. Stops the editor after all tests complete

    Usage:
        @pytest.mark.asyncio
        async def test_something_with_editor(running_editor, initialized_tool_caller):
            # Editor is already running, just use initialized_tool_caller
            result = await initialized_tool_caller.call("editor_execute_code", ...)

    Benefits:
        - Editor startup time (~2-3 min) is incurred only ONCE per test session
        - All editor-dependent tests share the same editor instance
        - Automatic cleanup after all tests complete
    """
    import json
    import logging

    logger = logging.getLogger(__name__)

    # Helper: Store editor log path in pytest config for terminal summary
    def store_editor_log_path(status_data):
        log_path = status_data.get("log_file_path")
        if log_path:
            request.config._ue5_editor_log_path = log_path
            logger.info(f"UE5 editor log path: {log_path}")

    # Check if editor is already running
    status_result = await initialized_tool_caller.call("editor_status", timeout=30)
    status_text = status_result.text_content
    if status_text:
        try:
            status_data = json.loads(status_text)
            if status_data.get("status") == "ready":
                logger.info("Editor already running, reusing existing instance")
                store_editor_log_path(status_data)
                yield initialized_tool_caller
                return
        except json.JSONDecodeError:
            pass

    # Launch editor
    logger.info("Launching editor for test session...")
    launch_result = await initialized_tool_caller.call(
        "editor_launch",
        {"wait": True, "wait_timeout": 180},
        timeout=240,
    )

    launch_text = launch_result.text_content
    if launch_text:
        try:
            launch_data = json.loads(launch_text)
            if not launch_data.get("success"):
                raise RuntimeError(f"Editor launch failed: {launch_data}")
            logger.info("Editor launched successfully")

            # Get status to retrieve and store log path
            status_result = await initialized_tool_caller.call("editor_status", timeout=30)
            if status_result.text_content:
                try:
                    status_data = json.loads(status_result.text_content)
                    store_editor_log_path(status_data)
                except json.JSONDecodeError:
                    pass
        except json.JSONDecodeError:
            raise RuntimeError(f"Failed to parse editor launch result: {launch_text}")
    else:
        raise RuntimeError("Editor launch returned no result")

    try:
        yield initialized_tool_caller
    finally:
        # Stop editor after all tests complete
        logger.info("Stopping editor after test session...")
        await initialized_tool_caller.call("editor_stop", timeout=30)
        logger.info("Editor stopped")


# =============================================================================
# Auto-Generated Test Level Fixtures
# =============================================================================

# Path for the auto-generated test level
TEST_LEVEL_PATH = "/Game/Tests/AutoGeneratedTestLevel"
GENERATE_SCRIPT_PATH = Path(__file__).parent / "scripts" / "generate_test_level.py"


@pytest.fixture(scope="session")
async def ensure_test_level(running_editor):
    """
    Session-scoped fixture that ensures the test level is freshly generated.

    This fixture:
    1. Deletes any existing test level to ensure fresh state
    2. Generates a new level via UE5 Python script
    3. Returns the level path for tests to use

    The level is regenerated at the start of each test session to ensure
    it stays in sync with the generate_test_level.py script.

    Returns:
        str: The test level path (e.g., "/Game/Tests/AutoGeneratedTestLevel")
    """
    import json
    import logging

    logger = logging.getLogger(__name__)

    # Always delete existing level to ensure fresh generation
    # This keeps the level in sync with generate_test_level.py
    delete_code = f'''
import unreal

level_path = "{TEST_LEVEL_PATH}"
if unreal.EditorAssetLibrary.does_asset_exist(level_path):
    # Load the default ThirdPerson map to unload the test level
    # This avoids creating temporary levels which can cause crashes
    level_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    level_subsystem.load_level("/Game/ThirdPerson/Maps/ThirdPersonMap")

    # Delete the test level
    deleted = unreal.EditorAssetLibrary.delete_asset(level_path)
    print(f"DELETED:{{deleted}}")
else:
    print("DELETED:skipped")
'''
    result = await running_editor.call(
        "editor_execute_code",
        {"code": delete_code},
        timeout=60,
    )

    output = result.text_content or ""
    if "DELETED:True" in output:
        logger.info(f"Deleted existing test level: {TEST_LEVEL_PATH}")
    elif "DELETED:skipped" in output:
        logger.info("No existing test level to delete")
    else:
        logger.warning(f"Failed to delete test level: {output}")

    # Generate fresh level
    logger.info("Generating test level...")

    gen_result = await running_editor.call(
        "editor_execute_script",
        {"script_path": str(GENERATE_SCRIPT_PATH)},
        timeout=120,
    )

    gen_output = gen_result.text_content or ""

    # Parse result from script output
    # Use the LAST occurrence of __RESULT__ to avoid matching code in script output
    if "__RESULT__" in gen_output:
        # Split and take the last part (actual result, not code)
        result_parts = gen_output.split("__RESULT__")
        result_json = result_parts[-1].strip()

        # Handle escaped JSON (when \" is used instead of ")
        if result_json.startswith('{\\"') or result_json.startswith('{\\"'):
            # Unescape the JSON string
            result_json = result_json.encode().decode("unicode_escape")

        # Extract JSON object - find the matching closing brace
        if result_json.startswith("{"):
            brace_count = 0
            json_end = 0
            for i, char in enumerate(result_json):
                if char == "{":
                    brace_count += 1
                elif char == "}":
                    brace_count -= 1
                    if brace_count == 0:
                        json_end = i + 1
                        break
            if json_end > 0:
                result_json = result_json[:json_end]

        try:
            gen_data = json.loads(result_json)
            if not gen_data.get("success"):
                raise RuntimeError(f"Failed to generate test level: {gen_data}")

            if gen_data.get("created"):
                logger.info(
                    f"Test level generated: {TEST_LEVEL_PATH} "
                    f"with actors: {gen_data.get('actors_created', [])}"
                )
            else:
                logger.info(f"Test level already exists: {TEST_LEVEL_PATH}")

            return TEST_LEVEL_PATH
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Failed to parse generation result: {result_json}, error: {e}")
    else:
        raise RuntimeError(f"Script did not return expected result format: {gen_output}")


@pytest.fixture(scope="session")
def test_level_path(ensure_test_level) -> str:
    """
    Convenience fixture that returns the test level path.

    This is a synchronous wrapper around ensure_test_level for tests
    that don't need to await the level generation.

    Usage:
        async def test_something(running_editor, test_level_path):
            result = await running_editor.call(
                "editor_capture_orbital",
                {"level": test_level_path, ...}
            )

    Returns:
        str: The test level path
    """
    return ensure_test_level


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


# =============================================================================
# Pytest Hooks for Conditional Logging and Log File Path Display
# =============================================================================


def pytest_configure(config):
    """
    Configure pytest to show logs only when -v flag is used.
    Also sets up session directory and log file.

    This hook runs before tests start and:
    1. Creates a timestamped session directory for all test outputs
    2. Sets up log file within the session directory
    3. Adjusts log_cli setting based on verbosity level
    """
    from datetime import datetime

    # Check if verbose mode is enabled (-v or -vv)
    verbose = config.option.verbose

    # Disable CLI logging if not in verbose mode
    if verbose == 0:
        # Disable live logging to terminal
        config.option.log_cli_level = None
        # Set to very high level to effectively disable
        config._inicache["log_cli_level"] = "CRITICAL"

    # Create session directory with timestamp
    tests_dir = Path(__file__).parent
    output_dir = tests_dir / "test_output"
    output_dir.mkdir(exist_ok=True)

    # Generate timestamp for session directory
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    session_dir = output_dir / f"session_{timestamp}"
    session_dir.mkdir(exist_ok=True)

    # Store session directory path in config for fixtures to access
    config._test_session_dir = session_dir

    # Set up log file in session directory
    log_dir = session_dir / "log"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / "pytest.log"

    # Set log file path
    config.option.log_file = str(log_file)
    config._log_file_path = log_file


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    """
    Display session directory and log file paths after test session completes.

    This hook runs after all tests finish and displays the location
    of the session output directory, pytest log, and UE5 editor log.
    """
    from pathlib import Path

    # Get session directory from config (set in pytest_configure)
    session_dir = getattr(config, "_test_session_dir", None)

    # Get pytest log file path from config (set in pytest_configure)
    log_file = getattr(config, "_log_file_path", None)

    # Get UE5 editor log file path from config (set in running_editor fixture)
    ue5_log_path = getattr(config, "_ue5_editor_log_path", None)

    # Check which paths exist
    has_session_dir = session_dir and session_dir.exists()
    has_pytest_log = log_file and log_file.exists()
    has_ue5_log = ue5_log_path and Path(ue5_log_path).exists()

    if has_session_dir or has_pytest_log or has_ue5_log:
        terminalreporter.write_sep("=", "Test Session Output")

    if has_session_dir:
        terminalreporter.write_line(f"Session directory: {session_dir.resolve()}")

    if has_pytest_log:
        abs_path = log_file.resolve()
        terminalreporter.write_line(f"Pytest log: {abs_path}")

    if has_ue5_log:
        ue5_abs_path = Path(ue5_log_path).resolve()
        terminalreporter.write_line(f"UE5 Editor log: {ue5_abs_path}")
