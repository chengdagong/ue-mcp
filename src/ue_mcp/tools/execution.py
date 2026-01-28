"""Code and script execution tools."""

import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any

from pydantic import Field

if TYPE_CHECKING:
    from fastmcp import FastMCP

    from ..state import ServerState


def register_tools(mcp: "FastMCP", state: "ServerState") -> None:
    """Register code and script execution tools."""

    from ._helpers import build_env_injection_code

    @mcp.tool(name="editor_execute_code")
    async def execute_code(
        code: Annotated[str, Field(description="Python code to execute")],
        timeout: Annotated[
            float, Field(default=30.0, description="Execution timeout in seconds")
        ],
    ) -> dict[str, Any]:
        """
        Execute Python code in the managed Unreal Editor.

        The code is executed in the editor's Python environment with access to
        the 'unreal' module and all editor APIs.

        If the editor is not running, it will be automatically launched.

        Args:
            code: Python code to execute
            timeout: Execution timeout in seconds (default: 30)

        Returns:
            Execution result containing:
            - success: Whether execution succeeded
            - result: Return value (if any)
            - output: Console output from the code
            - error: Error message (if failed)

        Example:
            execute_code("import unreal; print(unreal.EditorAssetLibrary.list_assets('/Game/'))")
        """
        execution = state.get_execution_subsystem()
        return await execution.execute_code_with_auto_launch(code, timeout=timeout)

    @mcp.tool(name="editor_execute_script")
    async def execute_script(
        script_path: Annotated[
            str, Field(description="Path to the Python script file to execute")
        ],
        timeout: Annotated[
            float, Field(default=30.0, description="Execution timeout in seconds")
        ],
        args: Annotated[
            list[str] | None,
            Field(
                default=None,
                description="List of command-line arguments passed to the script via sys.argv[1:]",
            ),
        ] = None,
        kwargs: Annotated[
            dict[str, Any] | None,
            Field(
                default=None,
                description="Dictionary of keyword arguments accessible via __SCRIPT_ARGS__ global variable",
            ),
        ] = None,
        wait_for_latent: Annotated[
            bool,
            Field(
                default=True,
                description="Whether to wait for latent commands (async execution) to complete before returning",
            ),
        ] = True,
        latent_timeout: Annotated[
            float,
            Field(
                default=60.0,
                description="Maximum time in seconds to wait for latent commands to complete",
            ),
        ] = 60.0,
    ) -> dict[str, Any]:
        """
        Execute a Python script file in the managed Unreal Editor.

        The script is executed directly from disk using EXECUTE_FILE mode,
        enabling true hot-reload (modifications take effect without restart).
        Parameters are passed via environment variables.

        For scripts using @unreal.AutomationScheduler.add_latent_command (async execution),
        the tool will wait for all latent commands to complete before returning output.

        Scripts must call bootstrap_from_env() at the start of main() to
        read parameters from env vars and set up sys.argv for argparse.

        If the editor is not running, it will be automatically launched.

        Args:
            script_path: Path to the Python script file to execute
            timeout: Execution timeout in seconds (default: 30)
            args: List of command-line arguments to pass to the script via sys.argv[1:]
            kwargs: Dictionary of keyword arguments accessible via __SCRIPT_ARGS__ global variable
            wait_for_latent: Whether to wait for async latent commands to complete (default: True)
            latent_timeout: Max time to wait for latent commands in seconds (default: 60)

        Returns:
            Execution result containing:
            - success: Whether execution succeeded
            - result: Return value (if any)
            - output: Console output from the script
            - error: Error message (if failed)
            - latent_warning: Warning if latent commands did not complete in time

        Example:
            execute_script("/path/to/my_script.py")

            # With command-line arguments (accessible via sys.argv or argparse):
            execute_script("/path/to/my_script.py", args=["--level", "/Game/Maps/Test", "--verbose"])

            # With keyword arguments (accessible via __SCRIPT_ARGS__):
            execute_script("/path/to/my_script.py", kwargs={"level": "/Game/Maps/Test", "actors": ["A", "B"]})
        """
        path = Path(script_path)
        if not path.exists():
            return {
                "success": False,
                "error": f"Script file not found: {script_path}",
            }

        if not path.is_file():
            return {
                "success": False,
                "error": f"Path is not a file: {script_path}",
            }

        # Build params from args/kwargs
        # For args: pass as special __args__ key for raw argv handling
        # For kwargs: pass directly as key-value pairs
        params: dict[str, Any] = {}
        if args:
            params["__args__"] = args
        if kwargs:
            params.update(kwargs)

        execution = state.get_execution_subsystem()

        # Ensure editor is ready (may auto-launch)
        ensure_result = await execution._ensure_editor_ready()
        if ensure_result is not None:
            return ensure_result

        # Generate temp file for capturing stdout/stderr output
        # EXECUTE_FILE mode doesn't return print() output in the protocol response,
        # so we redirect stdout/stderr to a temp file and read it after execution
        temp_output_file = tempfile.NamedTemporaryFile(
            mode="w", delete=False, suffix="_ue_mcp_output.txt", encoding="utf-8"
        )
        temp_output_path = temp_output_file.name
        temp_output_file.close()

        # Step 1: Inject parameters via environment variables
        # Also sets up TeeWriter to capture stdout/stderr to temp file
        injection_code = build_env_injection_code(str(path), params, output_file=temp_output_path)
        inject_result = execution.execute_code(injection_code, timeout=5.0)

        if not inject_result.get("success"):
            # Clean up temp file on failure
            try:
                Path(temp_output_path).unlink(missing_ok=True)
            except Exception:
                pass
            return {
                "success": False,
                "error": f"Failed to inject parameters: {inject_result.get('error')}",
            }

        # Step 2: Execute script file directly (true hot-reload)
        # Wait for latent commands (async scripts) to complete before reading output
        return execution.execute_script_file(
            str(path),
            timeout=timeout,
            output_file=temp_output_path,
            wait_for_latent=wait_for_latent,
            latent_timeout=latent_timeout,
        )

    @mcp.tool(name="editor_pip_install")
    async def pip_install_packages(
        packages: Annotated[
            list[str],
            Field(
                description="List of package names to install (e.g., ['Pillow', 'numpy'])"
            ),
        ],
        upgrade: Annotated[
            bool,
            Field(
                default=False,
                description="Whether to upgrade packages if already installed",
            ),
        ],
    ) -> dict[str, Any]:
        """
        Install Python packages in UE5's embedded Python environment.

        This tool uses UE5's bundled Python interpreter to install packages via pip.
        Installed packages will be available for use in editor.execute_code() calls.

        If the editor is not running, it will be automatically launched.

        Args:
            packages: List of package names to install (e.g., ["Pillow", "numpy"])
            upgrade: Whether to upgrade packages if already installed (default: False)

        Returns:
            Installation result containing:
            - success: Whether installation succeeded
            - packages: List of packages that were installed
            - output: pip output
            - python_path: Path to UE5's Python interpreter used

        Example:
            pip_install_packages(["Pillow", "numpy"])
        """
        execution = state.get_execution_subsystem()
        return await execution.pip_install_with_auto_launch(packages, upgrade=upgrade)
