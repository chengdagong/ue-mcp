"""Code and script execution tools."""

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
    def execute_code(
        code: Annotated[str, Field(description="Python code to execute")],
        timeout: Annotated[
            float, Field(default=30.0, description="Execution timeout in seconds")
        ],
    ) -> dict[str, Any]:
        """
        Execute Python code in the managed Unreal Editor.

        The code is executed in the editor's Python environment with access to
        the 'unreal' module and all editor APIs.

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
        manager = state.get_editor_manager()
        return manager.execute_with_checks(code, timeout=timeout)

    @mcp.tool(name="editor_execute_script")
    def execute_script(
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
    ) -> dict[str, Any]:
        """
        Execute a Python script file in the managed Unreal Editor.

        The script is executed directly from disk using EXECUTE_FILE mode,
        enabling true hot-reload (modifications take effect without restart).
        Parameters are passed via environment variables.

        Scripts must call bootstrap_from_env() at the start of main() to
        read parameters from env vars and set up sys.argv for argparse.

        Args:
            script_path: Path to the Python script file to execute
            timeout: Execution timeout in seconds (default: 30)
            args: List of command-line arguments to pass to the script via sys.argv[1:]
            kwargs: Dictionary of keyword arguments accessible via __SCRIPT_ARGS__ global variable

        Returns:
            Execution result containing:
            - success: Whether execution succeeded
            - result: Return value (if any)
            - output: Console output from the script
            - error: Error message (if failed)

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

        manager = state.get_editor_manager()

        # Step 1: Inject parameters via environment variables
        injection_code = build_env_injection_code(str(path), params)
        inject_result = manager.execute(injection_code, timeout=5.0)

        if not inject_result.get("success"):
            return {
                "success": False,
                "error": f"Failed to inject parameters: {inject_result.get('error')}",
            }

        # Step 2: Execute script file directly (true hot-reload)
        return manager.execute_script_file(str(path), timeout=timeout)

    @mcp.tool(name="editor_pip_install")
    def pip_install_packages(
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
        Installed packages will be available for use in editor.execute() calls.

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
        manager = state.get_editor_manager()
        return manager.pip_install_packages(packages, upgrade=upgrade)
