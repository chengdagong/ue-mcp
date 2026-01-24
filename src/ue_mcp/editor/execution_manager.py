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

from ..asset_tracker import (
    compare_snapshots,
    create_snapshot,
    extract_game_paths,
    gather_change_details,
    get_current_level_path,
)
from ..actor_snapshot import (
    compare_level_actor_snapshots,
    create_level_actor_snapshot,
)
from ..code_inspector import inspect_code
from ..pip_install import (
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

    def _execute(self, code: str, timeout: float = 30.0) -> dict[str, Any]:
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

        if self._ctx.editor.remote_client is None or not self._ctx.editor.remote_client.is_connected():
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

        # Wrap multi-line code in exec() since EXECUTE_STATEMENT only handles single statements
        # For single-line code without newlines, execute directly
        if "\n" in code:
            # Escape the code for use in exec()
            escaped_code = code.replace("\\", "\\\\").replace("'", "\\'")
            wrapped_code = f"exec('''{escaped_code}''')"
            result = self._ctx.editor.remote_client.execute(
                wrapped_code,
                exec_type=self._ctx.editor.remote_client.ExecTypes.EXECUTE_STATEMENT,
                timeout=timeout,
            )
        else:
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

    def _get_python_path(self) -> Optional[Path]:
        """
        Get Python interpreter path from the running editor.

        Returns:
            Path to Python interpreter, or None if failed
        """
        try:
            result = self._execute(
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
        2.5. Detect bundled module imports and inject unload code
        3. Execute import statements in UE to detect missing modules
        4. Auto-install missing modules and retry imports
        5. Execute the full code

        The bundled module reload feature (step 2.5) detects imports of modules
        from our custom site-packages (asset_diagnostic, editor_capture) and
        removes them from sys.modules before execution, ensuring the latest
        code is always used without requiring editor restart.

        Args:
            code: Python code to execute
            timeout: Execution timeout in seconds
            max_install_attempts: Maximum number of packages to auto-install

        Returns:
            Execution result dictionary (same as execute())
            Additional fields when auto-install occurs:
            - auto_installed: List of packages that were auto-installed
        """
        installed_packages: list[str] = []

        # Step 1: Extract import statements (also validates syntax)
        import_statements, syntax_error = extract_import_statements(code)

        # Step 2: If syntax error, return immediately
        if syntax_error:
            return {
                "success": False,
                "error": syntax_error,
            }

        # Step 2.5: Code inspection for blocking calls and other issues
        # Run inspection in two phases:
        # 1. Server-side inspection (for checks that don't need unreal module)
        # 2. Editor-side inspection (for UnrealAPIChecker that needs unreal module)

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
            # Prepare code inspector execution in editor
            # Calculate src path relative to this file
            src_path = Path(__file__).parent.parent.parent

            inspector_code = f'''
import sys

# Add src to path (absolute path, since __file__ is not available in editor)
src_path = r"{str(src_path)}"
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from ue_mcp.code_inspector import inspect_code

# Inspect the user's code
code_to_inspect = r"""
{code.replace(chr(92), chr(92)*2).replace('"""', chr(92)+'"""')}
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
            # Execute inspector in editor
            inspector_result = self._execute(inspector_code, timeout=10.0)

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

        # Step 3: Detect and prepare bundled module reload
        # This ensures bundled modules are reloaded to pick up latest code changes
        bundled_imports = extract_bundled_module_imports(code)
        if bundled_imports:
            unload_code = generate_module_unload_code(bundled_imports)
            code = unload_code + code
            logger.debug(f"Injected unload code for bundled modules: {bundled_imports}")

        # Step 3.5: Asset change tracking - Pre-execution snapshot
        # Extract /Game/xxx/ paths from code and take a snapshot before execution
        # Also auto-track the current level even if not explicitly referenced in code
        pre_snapshot = None
        pre_actor_snapshot = None
        game_paths = extract_game_paths(code)

        # Auto-add current level path to tracking list
        # This ensures changes to the current level are tracked even when the code
        # doesn't explicitly contain /Game/ path strings
        if self._ctx.editor and self._ctx.editor.status == "ready":
            current_level_dir = get_current_level_path(self)
            if current_level_dir and current_level_dir not in game_paths:
                game_paths.append(current_level_dir)
                logger.debug(f"Asset tracking: auto-added current level {current_level_dir}")

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

        if import_statements:
            # Combine all import statements into one code block
            import_code = "\n".join(import_statements)

            # Step 3: Try executing imports, install missing modules and retry
            attempts = 0
            while attempts <= max_install_attempts:
                result = self._execute(import_code, timeout=10.0)

                if result.get("success"):
                    # All imports succeeded
                    break

                # Check if it's an ImportError
                if not is_import_error(result):
                    # Not an import error, skip pre-installation
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

        # Step 4: Execute the full code
        result = self._execute(code, timeout=timeout)

        # Add installation info
        if installed_packages:
            result["auto_installed"] = installed_packages

        # Step 5: Asset change tracking - Post-execution snapshot and comparison
        if pre_snapshot is not None and result.get("success"):
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
        if pre_actor_snapshot is not None and result.get("success"):
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
                    else:
                        logger.debug("Actor tracking: no changes detected")
                    result["actor_changes"] = actor_changes
            except Exception as e:
                logger.warning(f"Actor tracking failed: {e}")

        return result

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
