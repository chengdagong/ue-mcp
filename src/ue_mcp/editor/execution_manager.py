"""
ExecutionManager - Handles Python code execution in the UE5 editor.

This subsystem manages:
- Executing Python code in the editor
- Auto-installing missing packages
- Managing Python environment
"""

import logging
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from ..core.pip_install import (
    extract_bundled_module_imports,
    extract_import_statements,
    generate_module_unload_code,
    get_missing_module_from_result,
    is_import_error,
    module_to_package,
    pip_install,
)
from ..remote_client import RemoteExecutionClient
from ..tracking.actor_snapshot import (
    compare_level_actor_snapshots,
    create_level_actor_snapshot,
)
from ..tracking.asset_tracker import (
    compare_snapshots,
    create_snapshot,
    extract_game_paths,
    extract_level_paths,
    get_current_level_path,
    get_dirty_asset_paths,
)
from ..tools._helpers import build_env_injection_code
from ..validation.code_inspector import inspect_code
from .crash_detector import CrashDetector
from .health_monitor import HealthMonitor

if TYPE_CHECKING:
    from .context import EditorContext
    from .launch_manager import LaunchManager
    from .types import NotifyCallback

logger = logging.getLogger(__name__)


@dataclass
class PreExecutionContext:
    """Context captured before code execution for tracking and validation."""

    code: str
    """The code being executed (original or read from script)."""

    import_statements: list[str] = field(default_factory=list)
    """Extracted import statements from the code."""

    game_paths: list[str] = field(default_factory=list)
    """Extracted /Game/ paths from the code."""

    level_paths: list[str] = field(default_factory=list)
    """Extracted level paths from the code."""

    pre_snapshot: dict[str, Any] | None = None
    """Asset snapshot taken before execution."""

    pre_actor_snapshot: dict[str, Any] | None = None
    """Actor snapshot taken before execution."""

    bundled_imports: list[str] = field(default_factory=list)
    """Bundled module imports that need reloading."""

    installed_packages: list[str] = field(default_factory=list)
    """Packages auto-installed during import resolution."""


def _build_crash_response(ctx: "EditorContext", details: dict[str, Any]) -> dict[str, Any]:
    """
    Build a detailed error response when editor crash is detected.

    Checks the process exit code and provides detailed crash information.

    Args:
        ctx: Editor context to check process status
        details: Original error details from remote client

    Returns:
        Error response with detailed crash information
    """
    ctx.editor.status = "stopped"

    # Try to get exit code for detailed analysis
    exit_info: dict[str, Any] | None = None
    if ctx.editor and ctx.editor.process:
        exit_code = ctx.editor.process.poll()
        if exit_code is not None:
            # Use HealthMonitor's analyze_exit for consistent analysis
            # Create a temporary instance just for analysis
            exit_info = HealthMonitor(ctx).analyze_exit(exit_code)

    if exit_info:
        return {
            "success": False,
            "error": f"{exit_info['description']}. Use 'editor_launch' to restart.",
            "exit_type": exit_info["exit_type"],
            "exit_code": exit_info["exit_code"],
            "hex_code": exit_info.get("hex_code"),
            "details": details,
        }
    else:
        return {
            "success": False,
            "error": "Editor connection lost (process may have crashed). Use 'editor_launch' to restart.",
            "details": details,
        }


class ExecutionManager:
    """
    Manages Python code execution in the Unreal Editor.

    Public API (3 async methods with auto-launch):
    - execute_code(code, timeout, checks): Execute Python code
    - execute_script(script_path, ...): Execute Python script file
    - pip_install(packages, upgrade): Install Python packages

    All public methods automatically launch the editor if not running.
    """

    def __init__(self, context: "EditorContext"):
        """
        Initialize ExecutionManager.

        Args:
            context: Shared editor context
        """
        self._ctx = context
        self._launch_manager: "LaunchManager | None" = None

    def set_launch_manager(self, launch_manager: "LaunchManager") -> None:
        """Set the LaunchManager reference for auto-launch capability.

        This allows ExecutionManager to automatically launch the editor
        when tools require it but the editor is not running.

        Args:
            launch_manager: The LaunchManager instance
        """
        self._launch_manager = launch_manager

    # =========================================================================
    # PUBLIC API (3 async methods) - Always auto-launch if editor not running
    # =========================================================================

    async def execute_code(
        self,
        code: str,
        timeout: float = 30.0,
        checks: bool = True,
        notify: "NotifyCallback | None" = None,
    ) -> dict[str, Any]:
        """
        Execute Python code in the editor.

        Auto-launches editor if not running. Use checks=False for simple
        queries that don't need validation or asset tracking.

        Args:
            code: Python code to execute
            timeout: Execution timeout in seconds
            checks: Enable validation and tracking (default: True)
            notify: Optional callback for launch progress notifications

        Returns:
            Execution result dictionary
        """
        ensure_result = await self._ensure_editor_ready(notify)
        if ensure_result is not None:
            return ensure_result

        if checks:
            return self._execute_with_checks_impl(code, timeout=timeout)
        else:
            return self._execute_code_impl(code, timeout=timeout)

    async def execute_script(
        self,
        script_path: str,
        timeout: float = 120.0,
        params: dict[str, Any] | None = None,
        checks: bool = True,
        wait_for_latent: bool = True,
        latent_timeout: float = 60.0,
        notify: "NotifyCallback | None" = None,
    ) -> dict[str, Any]:
        """
        Execute a Python script file in the editor.

        Auto-launches editor if not running. If params is provided, parameters
        are injected via environment variables before script execution.

        Args:
            script_path: Absolute path to the Python script file
            timeout: Execution timeout in seconds
            params: Optional parameters to pass to the script via environment variables
            checks: Enable validation and tracking (default: True)
            wait_for_latent: Whether to wait for latent commands to complete
            latent_timeout: Max time to wait for latent commands
            notify: Optional callback for launch progress notifications

        Returns:
            Execution result dictionary
        """
        ensure_result = await self._ensure_editor_ready(notify)
        if ensure_result is not None:
            return ensure_result

        # Use appropriate execution method based on checks flag
        if checks:
            # Checks impl handles params internally
            return self._execute_script_with_checks_impl(
                script_path,
                timeout=timeout,
                params=params,
                wait_for_latent=wait_for_latent,
                latent_timeout=latent_timeout,
            )
        else:
            # No checks - use direct execution with optional params
            if params is not None:
                return self._execute_script_with_params(
                    script_path,
                    params,
                    timeout=timeout,
                    wait_for_latent=wait_for_latent,
                    latent_timeout=latent_timeout,
                )
            else:
                return self._execute_script_impl(
                    script_path,
                    timeout=timeout,
                    wait_for_latent=wait_for_latent,
                    latent_timeout=latent_timeout,
                )

    async def pip_install(
        self,
        packages: list[str],
        upgrade: bool = False,
        notify: "NotifyCallback | None" = None,
    ) -> dict[str, Any]:
        """
        Install Python packages in UE5's Python environment.

        Auto-launches editor if not running.

        Args:
            packages: List of package names to install
            upgrade: Whether to upgrade existing packages
            notify: Optional callback for launch progress notifications

        Returns:
            Installation result dictionary
        """
        ensure_result = await self._ensure_editor_ready(notify)
        if ensure_result is not None:
            return ensure_result
        return self._pip_install_impl(packages, upgrade=upgrade)

    # =========================================================================
    # PRIVATE IMPLEMENTATION METHODS
    # These are sync methods used internally and by tracking modules.
    # External callers should use the public async methods above.
    # =========================================================================

    def _execute_code_impl(self, code: str, timeout: float = 30.0) -> dict[str, Any]:
        """
        Execute Python code in the managed editor (internal use only).

        This is a low-level execution method without validation or tracking.
        Used by tracking modules and internal queries.

        Args:
            code: Python code to execute
            timeout: Execution timeout in seconds

        Returns:
            Execution result dictionary
        """
        if self._ctx.editor is None:
            return {
                "success": False,
                "error": "No editor is running. Call launch() first.",
            }

        if self._ctx.editor.status != "ready":
            return {
                "success": False,
                "error": f"Editor is not ready (status: {self._ctx.editor.status})",
            }

        if (
            self._ctx.editor.remote_client is None
            or not self._ctx.editor.remote_client.is_connected()
        ):
            # Try to reconnect using stored node_id and PID
            logger.info("Remote client disconnected, attempting to reconnect...")

            # Clean up old remote_client if it exists
            if self._ctx.editor.remote_client is not None:
                self._ctx.editor.remote_client._cleanup_sockets()
                self._ctx.editor.remote_client = None

            remote_client = RemoteExecutionClient(
                project_name=self._ctx.project_name,
                expected_node_id=self._ctx.editor.node_id,  # Prefer known node
                expected_pid=self._ctx.editor.process.pid,  # Verify PID
                multicast_group=("239.0.0.1", self._ctx.editor.multicast_port),
            )

            # Use find_and_verify_instance for reconnection
            if remote_client.find_and_verify_instance(timeout=5.0):
                self._ctx.editor.remote_client = remote_client
                logger.info("Reconnected successfully")
            else:
                remote_client._cleanup_sockets()
                return {
                    "success": False,
                    "error": "Failed to reconnect to editor. Editor may have crashed.",
                }

        # Execute code using EXECUTE_STATEMENT
        # Multi-line code must be wrapped in exec() as EXECUTE_STATEMENT only supports single statements
        if "\n" in code:
            # Wrap multi-line code in exec()
            wrapped_code = f"exec({repr(code)})"
            result = self._ctx.editor.remote_client.execute(
                wrapped_code,
                exec_type=self._ctx.editor.remote_client.ExecTypes.EXECUTE_STATEMENT,
                timeout=timeout,
            )
        else:
            # Single line, execute directly
            result = self._ctx.editor.remote_client.execute(
                code,
                exec_type=self._ctx.editor.remote_client.ExecTypes.EXECUTE_STATEMENT,
                timeout=timeout,
            )

        # Check for crash using CrashDetector
        if CrashDetector.check_execution_result(result):
            return _build_crash_response(self._ctx, result)

        return result

    def _execute_script_impl(
        self,
        script_path: str,
        timeout: float = 120.0,
        output_file: str | None = None,
        wait_for_latent: bool = True,
        latent_timeout: float = 60.0,
    ) -> dict[str, Any]:
        """
        Execute a Python script file using EXECUTE_FILE mode (internal use only).

        This enables true hot-reload as the file is executed directly from disk.
        Parameters should be injected before calling this method.

        Args:
            script_path: Absolute path to the Python script file
            timeout: Execution timeout in seconds
            output_file: Optional path to temp file containing captured stdout/stderr
            wait_for_latent: Whether to wait for latent commands to complete (default: True)
            latent_timeout: Max time to wait for latent commands in seconds (default: 60)

        Returns:
            Execution result dictionary with captured output
        """
        if self._ctx.editor is None:
            return {
                "success": False,
                "error": "No editor is running. Call launch() first.",
            }

        if self._ctx.editor.status != "ready":
            return {
                "success": False,
                "error": f"Editor is not ready (status: {self._ctx.editor.status})",
            }

        # Pre-scan script to detect if it contains latent commands
        # Skip waiting if no latent patterns are found
        has_latent_commands = False
        if wait_for_latent:
            has_latent_commands = self._script_has_latent_commands(script_path)
            if not has_latent_commands:
                logger.debug(f"No latent commands detected in {script_path}, skipping wait")

        try:
            # Execute file directly (no string reading, no concatenation)
            result = self._ctx.editor.remote_client.execute(
                script_path,
                exec_type=self._ctx.editor.remote_client.ExecTypes.EXECUTE_FILE,
                timeout=timeout,
            )

            # Check for crash using CrashDetector
            if CrashDetector.check_execution_result(result):
                return _build_crash_response(self._ctx, result)

            # Wait for latent commands to complete if script contains them
            # This handles async scripts using @unreal.AutomationScheduler.add_latent_command
            if has_latent_commands and result.get("success", False):
                latent_result = self._wait_for_latent_commands(latent_timeout)
                if latent_result.get("timed_out"):
                    result["latent_warning"] = (
                        f"Latent commands did not complete within {latent_timeout}s. "
                        "Output may be incomplete."
                    )

            # Clean up TeeWriter AFTER latent commands complete to capture their output
            if output_file:
                cleanup_code = (
                    "import sys, builtins\n"
                    "if hasattr(builtins, '__ue_mcp_orig_stdout__'):\n"
                    "    sys.stdout = builtins.__ue_mcp_orig_stdout__\n"
                    "if hasattr(builtins, '__ue_mcp_orig_stderr__'):\n"
                    "    sys.stderr = builtins.__ue_mcp_orig_stderr__\n"
                    "if hasattr(builtins, '__ue_mcp_output_file__'):\n"
                    "    builtins.__ue_mcp_output_file__.close()"
                )
                self._execute_code_impl(cleanup_code, timeout=5.0)

            # Read captured stdout/stderr from temp file if provided
            if output_file:
                captured_output = self._read_captured_output_file(output_file)
                if captured_output:
                    # Return as plain text with log level prefixes
                    result["output"] = self._format_log_output(captured_output)

            return result
        finally:
            # Always clean up temp file
            if output_file:
                try:
                    Path(output_file).unlink(missing_ok=True)
                except Exception as e:
                    logger.debug(f"Failed to clean up temp output file: {e}")

    def _execute_script_with_params(
        self,
        script_path: str,
        params: dict[str, Any],
        timeout: float = 120.0,
        wait_for_latent: bool = True,
        latent_timeout: float = 60.0,
    ) -> dict[str, Any]:
        """
        Execute a script with parameter injection via environment variables.

        This is the internal implementation for scripts that need parameters.
        It handles:
        1. Creating a temporary file for output capture
        2. Injecting parameters via environment variables (EXECUTE_STATEMENT)
        3. Executing the script file (EXECUTE_FILE)
        4. Reading captured output and cleaning up

        Args:
            script_path: Absolute path to the Python script file
            params: Parameters to pass to the script
            timeout: Execution timeout in seconds
            wait_for_latent: Whether to wait for latent commands to complete
            latent_timeout: Max time to wait for latent commands

        Returns:
            Execution result dictionary

        Raises:
            FileNotFoundError: If the script does not exist
        """
        path = Path(script_path)
        if not path.exists():
            return {"success": False, "error": f"Script not found: {script_path}"}

        # Step 1: Create temporary file for output capture
        temp_dir = Path(tempfile.gettempdir())
        output_file = str(temp_dir / f"ue_mcp_output_{uuid.uuid4().hex[:8]}.txt")

        # Step 2: Inject parameters via environment variables with output capture
        injection_code = build_env_injection_code(str(script_path), params, output_file)
        inject_result = self._execute_code_impl(injection_code, timeout=5.0)

        if not inject_result.get("success"):
            # Log full result for troubleshooting (error details often in result/output)
            logger.warning(f"Parameter injection failed. Full result: {inject_result}")
            # Extract error from result or output when error key is missing
            error_msg = inject_result.get("error")
            if not error_msg:
                error_msg = inject_result.get("result") or ""
                output = inject_result.get("output", [])
                if output:
                    output_str = "\n".join(str(o) for o in output) if isinstance(output, list) else str(output)
                    error_msg = f"{error_msg}\nOutput: {output_str}".strip()
            return {
                "success": False,
                "error": f"Failed to inject parameters: {error_msg or 'Unknown error'}",
            }

        # Step 3: Execute script file directly (true hot-reload)
        return self._execute_script_impl(
            script_path,
            timeout=timeout,
            output_file=output_file,
            wait_for_latent=wait_for_latent,
            latent_timeout=latent_timeout,
        )

    def _execute_with_checks_impl(
        self,
        code: str,
        timeout: float = 30.0,
        max_install_attempts: int = 3,
    ) -> dict[str, Any]:
        """
        Execute Python code with automatic missing module installation
        and bundled module reloading (internal implementation).

        Flow:
        1. Validate syntax and run code inspection
        2. Prepare pre-execution context (snapshots, paths)
        3. Handle bundled module reload
        4. Auto-install missing imports
        5. Execute the code
        6. Process post-execution tracking

        Args:
            code: Python code to execute
            timeout: Execution timeout in seconds
            max_install_attempts: Maximum number of packages to auto-install

        Returns:
            Execution result dictionary
        """
        # Step 1: Validate and inspect code
        validation_error = self._validate_and_inspect_code(code)
        if validation_error:
            return validation_error

        # Step 2: Prepare pre-execution context
        pre_ctx = self._prepare_pre_execution_context(code)

        # Step 3: Handle bundled module reload by injecting unload code
        exec_code = code
        if pre_ctx.bundled_imports:
            unload_code = generate_module_unload_code(pre_ctx.bundled_imports)
            exec_code = unload_code + code
            logger.debug(f"Injected unload code for bundled modules: {pre_ctx.bundled_imports}")

        # Step 4: Handle imports with auto-install
        self._handle_imports_with_auto_install(
            pre_ctx.import_statements,
            pre_ctx.installed_packages,
            max_install_attempts,
        )

        # Step 5: Execute the code
        result = self._execute_code_impl(exec_code, timeout=timeout)

        # Add installation info
        if pre_ctx.installed_packages:
            result["auto_installed"] = pre_ctx.installed_packages

        # Step 6: Process post-execution tracking
        self._process_post_execution_tracking(pre_ctx, result)

        return result

    def _execute_script_with_checks_impl(
        self,
        script_path: str,
        timeout: float = 120.0,
        params: dict[str, Any] | None = None,
        wait_for_latent: bool = True,
        latent_timeout: float = 60.0,
        max_install_attempts: int = 3,
    ) -> dict[str, Any]:
        """
        Execute a Python script file with validation and tracking (internal implementation).

        Provides the same checks as _execute_with_checks_impl:
        - Syntax validation
        - Server-side code inspection (blocking calls, deprecated APIs)
        - Editor-side code inspection (UnrealAPIChecker)
        - Import auto-install for missing packages
        - Asset change tracking
        - Actor change tracking

        Args:
            script_path: Absolute path to the Python script file
            timeout: Execution timeout in seconds
            params: Optional parameters to pass to the script via environment variables
            wait_for_latent: Whether to wait for latent commands to complete
            latent_timeout: Max time to wait for latent commands
            max_install_attempts: Maximum number of packages to auto-install

        Returns:
            Execution result with asset_changes, dirty_assets, etc.
        """
        path = Path(script_path)
        if not path.exists():
            return {"success": False, "error": f"Script not found: {script_path}"}

        # Step 1: Read script content
        try:
            code = path.read_text(encoding="utf-8")
        except Exception as e:
            return {"success": False, "error": f"Failed to read script: {e}"}

        # Step 2: Validate and inspect code
        validation_error = self._validate_and_inspect_code(code)
        if validation_error:
            return validation_error

        # Step 3: Prepare pre-execution context
        pre_ctx = self._prepare_pre_execution_context(code)

        # Step 4: Handle bundled module reload (execute separately since we can't modify script)
        if pre_ctx.bundled_imports:
            unload_code = generate_module_unload_code(pre_ctx.bundled_imports)
            self._execute_code_impl(unload_code, timeout=5.0)
            logger.debug(f"Executed unload code for bundled modules: {pre_ctx.bundled_imports}")

        # Step 5: Handle imports with auto-install
        self._handle_imports_with_auto_install(
            pre_ctx.import_statements,
            pre_ctx.installed_packages,
            max_install_attempts,
        )

        # Step 6: Handle parameter injection if params provided
        output_file: str | None = None
        if params is not None:
            # Create temporary file for output capture
            temp_dir = Path(tempfile.gettempdir())
            output_file = str(temp_dir / f"ue_mcp_output_{uuid.uuid4().hex[:8]}.txt")

            # Inject parameters via environment variables with output capture
            injection_code = build_env_injection_code(str(script_path), params, output_file)
            inject_result = self._execute_code_impl(injection_code, timeout=5.0)

            if not inject_result.get("success"):
                return {
                    "success": False,
                    "error": f"Failed to inject parameters: {inject_result.get('error')}",
                }

        # Step 7: Execute the script file
        result = self._execute_script_impl(
            script_path,
            timeout=timeout,
            output_file=output_file,
            wait_for_latent=wait_for_latent,
            latent_timeout=latent_timeout,
        )

        # Add installation info
        if pre_ctx.installed_packages:
            result["auto_installed"] = pre_ctx.installed_packages

        # Step 8: Process post-execution tracking
        self._process_post_execution_tracking(pre_ctx, result)

        return result

    def _pip_install_impl(
        self,
        packages: list[str],
        upgrade: bool = False,
    ) -> dict[str, Any]:
        """
        Install Python packages in UE5's Python environment (internal implementation).

        Args:
            packages: List of package names to install
            upgrade: Whether to upgrade existing packages

        Returns:
            Installation result dictionary
        """
        python_path = self._get_python_path()
        return pip_install(packages, python_path=python_path, upgrade=upgrade)

    # =========================================================================
    # EXECUTION HELPERS - Shared logic for checked execution
    # =========================================================================

    def _validate_and_inspect_code(self, code: str) -> dict[str, Any] | None:
        """
        Validate syntax and run code inspection checks.

        Performs:
        1. Syntax validation via import extraction
        2. Server-side code inspection (blocking calls, deprecated APIs)
        3. Editor-side code inspection (UnrealAPIChecker)

        Args:
            code: Python code to validate

        Returns:
            None if validation passes, error dict if validation fails.
        """
        # Step 1: Extract import statements (also validates syntax)
        import_statements, syntax_error = extract_import_statements(code)
        if syntax_error:
            return {"success": False, "error": syntax_error}

        # Step 2: Server-side code inspection
        inspection = inspect_code(code)
        if not inspection.allowed:
            return {
                "success": False,
                "error": inspection.format_error(),
                "inspection_issues": [i.to_dict() for i in inspection.issues],
            }

        # Step 3: Editor-side code inspection (only if editor is ready)
        if self._ctx.editor and self._ctx.editor.status == "ready":
            editor_error = self._run_editor_inspection(code)
            if editor_error:
                return editor_error

        return None

    def _run_editor_inspection(self, code: str) -> dict[str, Any] | None:
        """
        Run code inspection in the UE5 editor.

        Args:
            code: Python code to inspect

        Returns:
            None if inspection passes, error dict if inspection fails.
        """
        logger.debug("Running editor-side code inspection for UnrealAPIChecker")
        src_path = Path(__file__).parent.parent.parent

        inspector_code = f'''
import sys

# Add src to path (absolute path, since __file__ is not available in editor)
src_path = r"{str(src_path)}"
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from ue_mcp.validation.code_inspector import inspect_code

# Inspect the user's code
code_to_inspect = r"""
{code.replace(chr(92), chr(92) * 2).replace('"""', chr(92) + '"""')}
"""

result = inspect_code(code_to_inspect)

if not result.allowed:
    # Return error information
    print("CODE_INSPECTION_FAILED")
    print(result.format_error())
else:
    print("CODE_INSPECTION_PASSED")
'''

        logger.debug("Inspector code prepared, executing in editor...")
        inspector_result = self._execute_code_impl(inspector_code, timeout=10.0)

        logger.debug(f"Inspector execution result: success={inspector_result.get('success')}")

        if inspector_result.get("success"):
            output = inspector_result.get("output", [])
            output_str = ""
            if isinstance(output, list):
                for line in output:
                    if isinstance(line, dict):
                        output_str += str(line.get("output", ""))
                    else:
                        output_str += str(line)
            else:
                output_str = str(output)

            logger.debug(f"Inspector output: {output_str[:200]}")

            if "CODE_INSPECTION_FAILED" in output_str:
                error_msg = output_str.split("CODE_INSPECTION_FAILED", 1)[1].strip()
                logger.info(f"Code inspection failed in editor: {error_msg[:200]}")
                return {"success": False, "error": error_msg}
            elif "CODE_INSPECTION_PASSED" in output_str:
                logger.debug("Code inspection passed in editor")
        elif not inspector_result.get("success"):
            logger.warning(
                f"Editor-side code inspection failed to execute: {inspector_result.get('error')}"
            )

        return None

    def _prepare_pre_execution_context(self, code: str) -> PreExecutionContext:
        """
        Prepare context before code execution including snapshots.

        Creates pre-execution snapshots for asset and actor tracking.

        Args:
            code: Python code to execute

        Returns:
            PreExecutionContext with snapshots and extracted paths.
        """
        ctx = PreExecutionContext(code=code)

        # Extract import statements
        ctx.import_statements, _ = extract_import_statements(code)

        # Extract paths from code
        ctx.game_paths = extract_game_paths(code)
        ctx.level_paths = extract_level_paths(code)

        # Detect bundled module imports
        ctx.bundled_imports = extract_bundled_module_imports(code)

        # Auto-add current level path to tracking list
        if self._ctx.editor and self._ctx.editor.status == "ready":
            current_level_dir = get_current_level_path(self)
            if current_level_dir and current_level_dir not in ctx.game_paths:
                ctx.game_paths.append(current_level_dir)
                logger.debug(f"Asset tracking: auto-added current level {current_level_dir}")

        # Create asset snapshot
        if ctx.game_paths and self._ctx.editor and self._ctx.editor.status == "ready":
            logger.debug(f"Asset tracking: creating pre-snapshot for paths {ctx.game_paths}")
            ctx.pre_snapshot = create_snapshot(self, ctx.game_paths, str(self._ctx.project_root))
            if ctx.pre_snapshot:
                logger.debug(
                    f"Asset tracking: pre-snapshot captured "
                    f"{len(ctx.pre_snapshot.get('assets', {}))} assets"
                )

        # Create actor snapshot for OFPA mode support
        if self._ctx.editor and self._ctx.editor.status == "ready":
            ctx.pre_actor_snapshot = create_level_actor_snapshot(self, ctx.level_paths)
            if ctx.pre_actor_snapshot:
                levels_count = len(ctx.pre_actor_snapshot.get("levels", {}))
                total_actors = sum(
                    level.get("actor_count", 0)
                    for level in ctx.pre_actor_snapshot.get("levels", {}).values()
                )
                logger.debug(
                    f"Actor tracking: pre-snapshot captured {total_actors} actors "
                    f"across {levels_count} level(s)"
                )

        return ctx

    def _handle_imports_with_auto_install(
        self,
        import_statements: list[str],
        installed_packages: list[str],
        max_install_attempts: int = 3,
    ) -> None:
        """
        Execute import statements with automatic package installation.

        Tries to execute imports, and if ImportError occurs, attempts to
        install the missing package and retry.

        Args:
            import_statements: List of import statement strings
            installed_packages: List to append installed package names to
            max_install_attempts: Maximum number of packages to auto-install
        """
        if not import_statements:
            return

        import_code = "\n".join(import_statements)
        attempts = 0

        while attempts <= max_install_attempts:
            result = self._execute_code_impl(import_code, timeout=10.0)

            if result.get("success"):
                break

            if not is_import_error(result):
                break

            missing_module = get_missing_module_from_result(result)
            if not missing_module:
                logger.warning("Import error detected but could not extract module name")
                break

            package_name = module_to_package(missing_module)
            if package_name in installed_packages:
                logger.warning(f"Already attempted to install {package_name}, giving up")
                break

            python_path = self._get_python_path()
            logger.info(f"Pre-installing missing package: {package_name}")
            install_result = pip_install([package_name], python_path=python_path)

            if not install_result.get("success", False):
                logger.warning(
                    f"Failed to install {package_name}: {install_result.get('error')}"
                )
                break

            installed_packages.append(package_name)
            logger.info(f"Successfully pre-installed {package_name}, retrying imports...")
            attempts += 1

    def _process_post_execution_tracking(
        self,
        pre_ctx: PreExecutionContext,
        result: dict[str, Any],
    ) -> None:
        """
        Process post-execution tracking and update result dict.

        Compares pre/post snapshots, detects changes, and updates result with:
        - asset_changes: List of changed asset paths
        - temp_level_warning: Warning if changes in temp level
        - dirty_assets: List of dirty asset paths
        Also refreshes Slate UI if changes detected.

        Args:
            pre_ctx: Pre-execution context with snapshots
            result: Execution result dict to update in place
        """
        if not result.get("success"):
            return

        changed_paths: set[str] = set()
        temp_level_warning: str | None = None

        # Asset change tracking
        if pre_ctx.pre_snapshot is not None:
            try:
                post_snapshot = create_snapshot(
                    self, pre_ctx.game_paths, str(self._ctx.project_root)
                )
                if post_snapshot:
                    snapshot_changes = compare_snapshots(pre_ctx.pre_snapshot, post_snapshot)
                    if snapshot_changes:
                        changed_paths.update(snapshot_changes)
                        logger.debug(
                            f"Asset tracking: detected {len(snapshot_changes)} changed assets"
                        )
                    else:
                        logger.debug("Asset tracking: no changes detected")
            except Exception as e:
                logger.warning(f"Asset tracking failed: {e}")

        # Actor-based change tracking for OFPA mode
        if pre_ctx.pre_actor_snapshot is not None:
            try:
                post_actor_snapshot = create_level_actor_snapshot(self, pre_ctx.level_paths)
                if post_actor_snapshot:
                    actor_changes = compare_level_actor_snapshots(
                        pre_ctx.pre_actor_snapshot, post_actor_snapshot
                    )

                    if actor_changes:
                        for level_path, changed_actors in actor_changes.items():
                            logger.info(
                                f"Actor tracking: detected {len(changed_actors)} changes "
                                f"in {level_path}"
                            )

                            if level_path.startswith("/Temp/"):
                                temp_level_warning = (
                                    f"Changes detected in temporary level '{level_path}'. "
                                    "This level is not saved. If you intended to modify a "
                                    "persistent level, please load it first using "
                                    "editor_load_level."
                                )
                                logger.warning(f"Actor changes in temporary level: {level_path}")

                            changed_paths.add(level_path)
                            logger.debug(
                                f"Added level {level_path} to changed paths via actor tracking"
                            )
                    else:
                        logger.debug("Actor tracking: no changes detected")
            except Exception as e:
                logger.warning(f"Actor tracking failed: {e}")

        # Update result with tracking info
        if changed_paths:
            result["asset_changes"] = sorted(changed_paths)
        if temp_level_warning:
            result["temp_level_warning"] = temp_level_warning

        # Get dirty asset paths
        dirty_paths: list[str] = []
        try:
            dirty_paths = get_dirty_asset_paths(self)
            if dirty_paths:
                result["dirty_assets"] = dirty_paths
                logger.debug(f"Dirty assets: {dirty_paths}")
        except Exception as e:
            logger.warning(f"Failed to get dirty asset paths: {e}")

        # Refresh Slate UI if changes were detected
        if changed_paths or dirty_paths:
            try:
                refresh_result = self._execute_code_impl(
                    "import unreal; unreal.ExSlateTabLibrary.refresh_slate_view()",
                    timeout=5.0,
                )
                if refresh_result.get("success"):
                    logger.debug("Refreshed Slate UI after detected changes")
            except Exception as e:
                logger.debug(f"RefreshSlateView failed (non-critical): {e}")

    # =========================================================================
    # PRIVATE HELPER METHODS
    # =========================================================================

    async def _ensure_editor_ready(
        self, notify: "NotifyCallback | None" = None
    ) -> dict[str, Any] | None:
        """
        Ensure editor is running and ready, auto-launching if needed.

        This method checks if the editor is running and ready. If not, it
        automatically launches the editor using the configured LaunchManager.

        Args:
            notify: Optional callback for launch progress notifications

        Returns:
            None if editor is ready (caller should proceed with execution).
            Error dict if auto-launch failed or LaunchManager not configured.
        """
        # Check if editor is already ready
        if self._ctx.editor is not None and self._ctx.editor.status == "ready":
            return None  # Editor ready, proceed
        
        # Check if editor stopped due to crash
        if self._ctx.editor is not None and self._ctx.editor.status == "stopped":
            if self._ctx.editor.log_file_path:
                if CrashDetector.check_log_file(self._ctx.editor.log_file_path):
                    return {
                        "success": False,
                        "error": "Editor crashed. Use 'editor_launch' to restart.",
                        "exit_type": "crash",
                    }

        # Check if LaunchManager is available for auto-launch
        if self._launch_manager is None:
            return {
                "success": False,
                "error": "No editor is running. Call editor_launch() first.",
            }

        # Auto-launch the editor
        logger.info("Editor not running, auto-launching...")

        async def default_notify(level: str, message: str) -> None:
            logger.info(f"[AUTO-LAUNCH] {level}: {message}")

        actual_notify = notify or default_notify
        await actual_notify("info", "Auto-launching Unreal Editor...")

        launch_result = await self._launch_manager.launch(
            notify=actual_notify,
            wait_timeout=120.0,
        )

        if not launch_result.get("success"):
            # Check if editor crashed (log may show crash even if status is stopped)
            if self._ctx.editor and self._ctx.editor.log_file_path:
                if CrashDetector.check_log_file(self._ctx.editor.log_file_path):
                    return {
                        "success": False,
                        "error": "Editor crashed. Use 'editor_launch' to restart.",
                        "exit_type": "crash",
                        "auto_launch_attempted": True,
                        "launch_result": launch_result,
                    }
            
            return {
                "success": False,
                "error": f"Auto-launch failed: {launch_result.get('error', 'Unknown error')}",
                "auto_launch_attempted": True,
                "launch_result": launch_result,
            }

        await actual_notify("info", "Editor auto-launched successfully")
        return None  # Editor now ready

    def _wait_for_latent_commands(
        self, timeout: float = 60.0, poll_interval: float = 5.0
    ) -> dict[str, Any]:
        """Wait for latent commands to complete.

        Uses unreal.PyAutomationTest.get_is_running_py_latent_command() to check
        if any latent commands are still running.

        Args:
            timeout: Maximum time to wait in seconds
            poll_interval: Time between checks in seconds

        Returns:
            Dict with:
            - completed: Whether latent commands finished
            - timed_out: Whether we timed out waiting
            - elapsed: Time spent waiting
        """
        import time

        start_time = time.time()
        check_code = (
            "import unreal; print(unreal.PyAutomationTest.get_is_running_py_latent_command())"
        )

        while True:
            elapsed = time.time() - start_time
            if elapsed >= timeout:
                return {"completed": False, "timed_out": True, "elapsed": elapsed}

            # Check if latent commands are still running
            check_result = self._execute_code_impl(check_code, timeout=5.0)

            if not check_result.get("success"):
                # If check fails, assume no latent commands (or API not available)
                logger.debug(f"Latent command check failed: {check_result.get('error')}")
                return {"completed": True, "timed_out": False, "elapsed": elapsed}

            # Parse the result - look for "True" or "False" in output
            output = check_result.get("output", [])
            output_str = ""
            for line in output:
                if isinstance(line, dict):
                    output_str += str(line.get("output", ""))
                else:
                    output_str += str(line)

            # If not running latent commands, we're done
            if "False" in output_str:
                logger.debug(f"Latent commands completed after {elapsed:.2f}s")
                return {"completed": True, "timed_out": False, "elapsed": elapsed}

            # Still running, wait and check again
            time.sleep(poll_interval)

    def _script_has_latent_commands(self, script_path: str) -> bool:
        """Check if a script file contains latent command definitions.

        Scans the script content for patterns that indicate async execution:
        - @unreal.AutomationScheduler.add_latent_command decorator
        - AutomationScheduler.add_latent_command calls
        - add_latent_command function references

        Args:
            script_path: Path to the script file to scan

        Returns:
            True if latent command patterns are found, False otherwise
        """
        import re

        # Patterns that indicate latent commands
        latent_patterns = [
            r"@unreal\.AutomationScheduler\.add_latent_command",
            r"AutomationScheduler\.add_latent_command",
            r"add_latent_command\s*\(",
            r"@.*add_latent_command",
        ]

        try:
            path = Path(script_path)
            if not path.exists():
                return False

            content = path.read_text(encoding="utf-8")

            for pattern in latent_patterns:
                if re.search(pattern, content):
                    logger.debug(f"Found latent command pattern '{pattern}' in {script_path}")
                    return True

            return False
        except Exception as e:
            logger.warning(f"Failed to scan script for latent commands: {e}")
            # If we can't read the file, assume it might have latent commands
            return True

    def _read_captured_output_file(self, output_file: str) -> str | None:
        """Read captured output from temp file.

        Args:
            output_file: Path to the temp file containing captured output

        Returns:
            File contents as string, or None if file doesn't exist or is empty
        """
        try:
            path = Path(output_file)
            if path.exists():
                content = path.read_text(encoding="utf-8")
                if content.strip():
                    return content
        except Exception as e:
            logger.warning(f"Failed to read captured output file: {e}")
        return None

    def _format_log_output(self, output: str) -> str:
        """Format output with log level prefixes.

        Adds [INFO] prefix to lines that don't already have a log level prefix.
        Recognized prefixes: [INFO], [WARNING], [ERROR], [DEBUG], [CRITICAL]

        Args:
            output: Raw output string

        Returns:
            Formatted output with log level prefixes on each line
        """
        import re

        # Pattern to match existing log level prefixes
        log_prefix_pattern = re.compile(r"^\[(INFO|WARNING|ERROR|DEBUG|CRITICAL)\]")

        lines = output.splitlines()
        formatted_lines = []

        for line in lines:
            # Skip empty lines (keep them as-is)
            if not line.strip():
                formatted_lines.append(line)
                continue

            # Check if line already has a log level prefix
            if log_prefix_pattern.match(line):
                formatted_lines.append(line)
            else:
                # Add default [INFO] prefix
                formatted_lines.append(f"[INFO] {line}")

        return "\n".join(formatted_lines)

    def _get_python_path(self) -> Optional[Path]:
        """
        Get Python interpreter path from the running editor.

        Returns:
            Path to Python interpreter, or None if failed
        """
        try:
            result = self._execute_code_impl(
                "import unreal; print(unreal.get_interpreter_executable_path())", timeout=5.0
            )
            if result.get("success") and result.get("output"):
                output = result["output"]
                lines = []
                if isinstance(output, list):
                    for line in output:
                        if isinstance(line, dict):
                            lines.append(str(line.get("output", "")))
                        else:
                            lines.append(str(line))
                else:
                    lines = [str(output)]

                # Extract path from output
                for line in lines:
                    for subline in line.strip().split("\n"):
                        subline = subline.strip()
                        if subline and (subline.endswith(".exe") or "python" in subline.lower()):
                            return Path(subline)
        except Exception as e:
            logger.error(f"Failed to get Python path from editor: {e}")
        return None
