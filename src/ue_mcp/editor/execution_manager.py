"""
ExecutionManager - Handles Python code execution in the UE5 editor.

This subsystem manages:
- Executing Python code in the editor
- Auto-installing missing packages
- Managing Python environment
"""

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from ..tracking.asset_tracker import (
    compare_snapshots,
    create_snapshot,
    extract_game_paths,
    gather_actor_change_details,
    gather_change_details,
    get_current_level_path,
)
from ..tracking.actor_snapshot import (
    compare_level_actor_snapshots,
    create_level_actor_snapshot,
)
from ..validation.code_inspector import inspect_code
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

if TYPE_CHECKING:
    from .context import EditorContext

logger = logging.getLogger(__name__)


class ExecutionManager:
    """
    Manages Python code execution in the Unreal Editor.

    This subsystem handles code execution with automatic missing module
    installation and bundled module reloading.
    """

    def __init__(self, context: "EditorContext"):
        """
        Initialize ExecutionManager.

        Args:
            context: Shared editor context
        """
        self._ctx = context

    def execute_code(self, code: str, timeout: float = 30.0) -> dict[str, Any]:
        """
        Execute Python code in the editor without additional checks.

        This is a low-level execution method for simple operations like
        parameter injection or querying editor state. For general code
        execution with auto-install and bundled module support, use
        execute_with_checks() instead.

        Args:
            code: Python code to execute
            timeout: Execution timeout in seconds

        Returns:
            Execution result dictionary
        """
        return self._execute_code(code, timeout)

    def _execute_code(self, code: str, timeout: float = 30.0) -> dict[str, Any]:
        """
        Execute Python code in the managed editor (internal use only).

        External callers should use execute_with_checks() instead.

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

        # Check for crash
        if result.get("crashed", False):
            self._ctx.editor.status = "stopped"
            return {
                "success": False,
                "error": "Editor connection lost (may have crashed)",
                "details": result,
            }

        return result

    def execute_script_file(
        self,
        script_path: str,
        timeout: float = 120.0,
        output_file: str | None = None,
        wait_for_latent: bool = True,
        latent_timeout: float = 60.0,
    ) -> dict[str, Any]:
        """
        Execute a Python script file using EXECUTE_FILE mode.

        This enables true hot-reload as the file is executed directly from disk.
        Parameters should be injected before calling this method using _execute().

        After script execution, if the script uses latent commands (async execution),
        waits for them to complete before reading output. The script is pre-scanned
        to detect latent command patterns - if none are found, waiting is skipped.

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

            # Check for crash
            if result.get("crashed", False):
                self._ctx.editor.status = "stopped"
                return {
                    "success": False,
                    "error": "Editor connection lost (may have crashed)",
                    "details": result,
                }

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
                self._execute_code(cleanup_code, timeout=5.0)

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
            check_result = self._execute_code(check_code, timeout=5.0)

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

    def _run_code_inspection(self, code: str) -> dict[str, Any] | None:
        """Run code inspection (server-side and editor-side).

        This performs validation checks on Python code before execution:
        - Server-side: BlockingCallChecker, DeprecatedAPIChecker
        - Editor-side: UnrealAPIChecker (requires running editor)

        Args:
            code: Python code to inspect

        Returns:
            Error dict if inspection fails, None if passed
        """
        # Server-side inspection
        inspection = inspect_code(code)
        if not inspection.allowed:
            return {
                "success": False,
                "error": inspection.format_error(),
                "inspection_issues": [i.to_dict() for i in inspection.issues],
            }

        # Editor-side inspection (only if editor is ready)
        if self._ctx.editor and self._ctx.editor.status == "ready":
            logger.debug("Running editor-side code inspection for UnrealAPIChecker")
            # Calculate src path relative to this file
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
            inspector_result = self._execute_code(inspector_code, timeout=10.0)

            logger.debug(f"Inspector execution result: success={inspector_result.get('success')}")

            # Check inspection result
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
                    # Extract error message
                    error_msg = output_str.split("CODE_INSPECTION_FAILED", 1)[1].strip()
                    logger.info(f"Code inspection failed in editor: {error_msg[:200]}")
                    return {
                        "success": False,
                        "error": error_msg,
                    }
                elif "CODE_INSPECTION_PASSED" in output_str:
                    logger.debug("Code inspection passed in editor")
            # If inspection execution failed or output unclear, log but continue
            # (better to allow code execution than block it due to inspector issues)
            elif not inspector_result.get("success"):
                logger.warning(
                    f"Editor-side code inspection failed to execute: {inspector_result.get('error')}"
                )
        else:
            logger.debug(
                f"Skipping editor-side inspection: editor_status="
                f"{self._ctx.editor.status if self._ctx.editor else 'None'}"
            )

        return None  # Inspection passed

    def _get_python_path(self) -> Optional[Path]:
        """
        Get Python interpreter path from the running editor.

        Returns:
            Path to Python interpreter, or None if failed
        """
        try:
            result = self._execute_code(
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

    def _create_tracking_snapshots(
        self, game_paths: list[str]
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        """Create pre-execution tracking snapshots.

        Creates asset and actor snapshots before code execution for
        change tracking purposes.

        Args:
            game_paths: List of /Game/ paths to track

        Returns:
            Tuple of (asset_snapshot, actor_snapshot)
        """
        pre_snapshot = None
        pre_actor_snapshot = None

        if game_paths and self._ctx.editor and self._ctx.editor.status == "ready":
            logger.debug(f"Asset tracking: creating pre-snapshot for paths {game_paths}")
            pre_snapshot = create_snapshot(self, game_paths, str(self._ctx.project_root))
            if pre_snapshot:
                logger.debug(
                    f"Asset tracking: pre-snapshot captured "
                    f"{len(pre_snapshot.get('assets', {}))} assets"
                )

        # Also create actor snapshot for OFPA mode support
        if self._ctx.editor and self._ctx.editor.status == "ready":
            pre_actor_snapshot = create_level_actor_snapshot(self)
            if pre_actor_snapshot:
                logger.debug(
                    f"Actor tracking: pre-snapshot captured "
                    f"{pre_actor_snapshot.get('actor_count', 0)} actors"
                )

        return pre_snapshot, pre_actor_snapshot

    def _handle_imports_with_auto_install(
        self,
        import_statements: list[str],
        max_install_attempts: int = 3,
    ) -> tuple[list[str], bool]:
        """Execute imports and auto-install missing packages.

        Tries to execute import statements in UE, and if an ImportError
        occurs, attempts to install the missing package and retry.

        Args:
            import_statements: List of import statement strings
            max_install_attempts: Maximum number of packages to auto-install

        Returns:
            Tuple of (installed_packages, success)
        """
        installed_packages: list[str] = []
        if not import_statements:
            return installed_packages, True

        import_code = "\n".join(import_statements)
        attempts = 0

        while attempts <= max_install_attempts:
            result = self._execute_code(import_code, timeout=10.0)

            if result.get("success"):
                return installed_packages, True

            # Check if it's an ImportError
            if not is_import_error(result):
                break

            # Extract missing module name
            missing_module = get_missing_module_from_result(result)
            if not missing_module:
                logger.warning("Import error detected but could not extract module name")
                break

            # Convert to package name
            package_name = module_to_package(missing_module)

            # Prevent duplicate installation
            if package_name in installed_packages:
                logger.warning(f"Already attempted to install {package_name}, giving up")
                break

            # Get Python path from running editor
            python_path = self._get_python_path()

            # Install the missing package
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

        return installed_packages, len(installed_packages) > 0

    def _process_tracking_results(
        self,
        result: dict[str, Any],
        pre_snapshot: dict[str, Any] | None,
        pre_actor_snapshot: dict[str, Any] | None,
        game_paths: list[str],
    ) -> dict[str, Any]:
        """Process post-execution tracking and add results.

        Compares pre and post snapshots to detect changes made during
        code execution, and adds diagnostic information.

        Args:
            result: Execution result dict to update
            pre_snapshot: Asset snapshot taken before execution
            pre_actor_snapshot: Actor snapshot taken before execution
            game_paths: List of /Game/ paths being tracked

        Returns:
            Updated result dict with asset_changes, actor_changes, diagnostic_summary
        """
        if not result.get("success"):
            return result

        # Asset change tracking - Post-execution snapshot and comparison
        if pre_snapshot is not None:
            try:
                post_snapshot = create_snapshot(self, game_paths, str(self._ctx.project_root))
                if post_snapshot:
                    changes = compare_snapshots(pre_snapshot, post_snapshot)
                    if changes.get("detected"):
                        logger.debug(
                            f"Asset tracking: detected changes - "
                            f"created={len(changes.get('created', []))}, "
                            f"deleted={len(changes.get('deleted', []))}, "
                            f"modified={len(changes.get('modified', []))}"
                        )
                        # Gather detailed info for changed assets
                        changes = gather_change_details(self, changes)
                    else:
                        logger.debug("Asset tracking: no changes detected")
                    # Always include asset_changes to show what was tracked
                    result["asset_changes"] = changes
            except Exception as e:
                logger.warning(f"Asset tracking failed: {e}")

        # Actor-based change tracking for OFPA mode
        if pre_actor_snapshot is not None:
            try:
                post_actor_snapshot = create_level_actor_snapshot(self)
                if post_actor_snapshot:
                    actor_changes = compare_level_actor_snapshots(
                        pre_actor_snapshot, post_actor_snapshot
                    )
                    if actor_changes.get("detected"):
                        logger.info(
                            f"Actor tracking: detected changes - "
                            f"created={len(actor_changes.get('created', []))}, "
                            f"deleted={len(actor_changes.get('deleted', []))}, "
                            f"modified={len(actor_changes.get('modified', []))}"
                        )
                        # Warn if changes are in a temporary level
                        level_path = actor_changes.get("level_path", "")
                        if level_path.startswith("/Temp/"):
                            actor_changes["warning"] = (
                                f"Changes detected in temporary level '{level_path}'. "
                                "This level is not saved. If you intended to modify a "
                                "persistent level, please load it first using editor_load_level."
                            )
                            logger.warning(f"Actor changes in temporary level: {level_path}")
                        # Run diagnostic for the level with actor changes
                        actor_changes = gather_actor_change_details(self, actor_changes)

                        # Promote diagnostic summary to top level for visibility
                        if "level_diagnostic" in actor_changes:
                            diag = actor_changes["level_diagnostic"]
                            errors = diag.get("errors", 0)
                            warnings = diag.get("warnings", 0)
                            if errors > 0 or warnings > 0:
                                # Brief summary with issue messages only (no details)
                                brief_issues = [
                                    f"[{i.get('severity', 'ERROR')}] {i.get('actor', 'Unknown')}: {i.get('message', '')}"
                                    for i in diag.get("issues", [])
                                    if i.get("severity") in ("ERROR", "WARNING")
                                ]
                                result["diagnostic_summary"] = {
                                    "level": diag.get("asset_path", ""),
                                    "errors": errors,
                                    "warnings": warnings,
                                    "issues": brief_issues[:5],  # Limit to top 5
                                }
                    else:
                        logger.debug("Actor tracking: no changes detected")
                    result["actor_changes"] = actor_changes
            except Exception as e:
                logger.warning(f"Actor tracking failed: {e}")

        return result

    def execute_with_checks(
        self,
        code: str,
        timeout: float = 30.0,
        max_install_attempts: int = 3,
    ) -> dict[str, Any]:
        """
        Execute Python code with automatic missing module installation
        and bundled module reloading.

        Flow:
        1. Extract import statements from code (also checks syntax)
        2. If syntax error, return error immediately
        3. Run code inspection (server-side and editor-side)
        4. Detect bundled module imports and inject unload code
        5. Create pre-execution tracking snapshots
        6. Execute import statements in UE, auto-install missing modules
        7. Execute the full code
        8. Process post-execution tracking

        Args:
            code: Python code to execute
            timeout: Execution timeout in seconds
            max_install_attempts: Maximum number of packages to auto-install

        Returns:
            Execution result dictionary (same as execute())
            Additional fields when auto-install occurs:
            - auto_installed: List of packages that were auto-installed
        """
        # Step 1: Extract import statements (also validates syntax)
        import_statements, syntax_error = extract_import_statements(code)

        # Step 2: If syntax error, return immediately
        if syntax_error:
            return {
                "success": False,
                "error": syntax_error,
            }

        # Step 3: Code inspection (server-side and editor-side)
        inspection_error = self._run_code_inspection(code)
        if inspection_error:
            return inspection_error

        # Step 4: Detect and prepare bundled module reload
        bundled_imports = extract_bundled_module_imports(code)
        if bundled_imports:
            unload_code = generate_module_unload_code(bundled_imports)
            code = unload_code + code
            logger.debug(f"Injected unload code for bundled modules: {bundled_imports}")

        # Step 5: Pre-execution tracking snapshots
        game_paths = extract_game_paths(code)
        # Auto-add current level path to tracking list
        if self._ctx.editor and self._ctx.editor.status == "ready":
            current_level_dir = get_current_level_path(self)
            if current_level_dir and current_level_dir not in game_paths:
                game_paths.append(current_level_dir)
                logger.debug(f"Asset tracking: auto-added current level {current_level_dir}")
        pre_snapshot, pre_actor_snapshot = self._create_tracking_snapshots(game_paths)

        # Step 6: Import handling with auto-install
        installed_packages, _ = self._handle_imports_with_auto_install(
            import_statements, max_install_attempts
        )

        # Step 7: Execute the full code
        result = self._execute_code(code, timeout=timeout)

        # Add installation info
        if installed_packages:
            result["auto_installed"] = installed_packages

        # Step 8: Post-execution tracking
        return self._process_tracking_results(result, pre_snapshot, pre_actor_snapshot, game_paths)

    def execute_script_with_checks(
        self,
        script_path: str,
        timeout: float = 120.0,
        output_file: str | None = None,
        wait_for_latent: bool = True,
        latent_timeout: float = 60.0,
        max_install_attempts: int = 3,
    ) -> dict[str, Any]:
        """
        Execute a Python script file with validation and tracking.

        Provides the same checks as execute_with_checks:
        - Syntax validation
        - Server-side code inspection (blocking calls, deprecated APIs)
        - Editor-side code inspection (UnrealAPIChecker)
        - Import auto-install for missing packages
        - Asset change tracking
        - Actor change tracking with diagnostics

        Flow:
        1. Read script content
        2. Validate syntax via import extraction
        3. Run code inspection (server-side and editor-side)
        4. Execute bundled module unload (separately, can't modify script)
        5. Create pre-execution tracking snapshots
        6. Execute import statements, auto-install missing modules
        7. Execute the script file
        8. Process post-execution tracking

        Args:
            script_path: Absolute path to the Python script file
            timeout: Execution timeout in seconds
            output_file: Optional path to temp file for stdout/stderr capture
            wait_for_latent: Whether to wait for latent commands to complete
            latent_timeout: Max time to wait for latent commands
            max_install_attempts: Maximum number of packages to auto-install

        Returns:
            Execution result with asset_changes, actor_changes, diagnostic_summary
        """
        path = Path(script_path)
        if not path.exists():
            return {"success": False, "error": f"Script not found: {script_path}"}

        # Step 1: Read script content
        try:
            code = path.read_text(encoding="utf-8")
        except Exception as e:
            return {"success": False, "error": f"Failed to read script: {e}"}

        # Step 2: Syntax validation via import extraction
        import_statements, syntax_error = extract_import_statements(code)
        if syntax_error:
            return {"success": False, "error": syntax_error}

        # Step 3: Code inspection (server-side and editor-side)
        inspection_error = self._run_code_inspection(code)
        if inspection_error:
            return inspection_error

        # Step 4: Bundled module reload (execute separately since we can't modify script)
        bundled_imports = extract_bundled_module_imports(code)
        if bundled_imports:
            unload_code = generate_module_unload_code(bundled_imports)
            self._execute_code(unload_code, timeout=5.0)
            logger.debug(f"Executed unload code for bundled modules: {bundled_imports}")

        # Step 5: Pre-execution tracking snapshots
        game_paths = extract_game_paths(code)
        # Auto-add current level path to tracking list
        if self._ctx.editor and self._ctx.editor.status == "ready":
            current_level_dir = get_current_level_path(self)
            if current_level_dir and current_level_dir not in game_paths:
                game_paths.append(current_level_dir)
                logger.debug(f"Asset tracking: auto-added current level {current_level_dir}")
        pre_snapshot, pre_actor_snapshot = self._create_tracking_snapshots(game_paths)

        # Step 6: Import handling with auto-install
        installed_packages, _ = self._handle_imports_with_auto_install(
            import_statements, max_install_attempts
        )

        # Step 7: Execute the script file
        result = self.execute_script_file(
            script_path,
            timeout=timeout,
            output_file=output_file,
            wait_for_latent=wait_for_latent,
            latent_timeout=latent_timeout,
        )

        # Add installation info
        if installed_packages:
            result["auto_installed"] = installed_packages

        # Step 8: Post-execution tracking
        return self._process_tracking_results(result, pre_snapshot, pre_actor_snapshot, game_paths)

    def pip_install_packages(
        self,
        packages: list[str],
        upgrade: bool = False,
    ) -> dict[str, Any]:
        """
        Install Python packages in UE5's Python environment.

        Args:
            packages: List of package names to install
            upgrade: Whether to upgrade existing packages

        Returns:
            Installation result dictionary
        """
        python_path = self._get_python_path()
        return pip_install(packages, python_path=python_path, upgrade=upgrade)
