"""Asset diagnostic and inspection tools."""

from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any

from pydantic import Field

if TYPE_CHECKING:
    from fastmcp import FastMCP

    from ..state import ServerState


def register_tools(mcp: "FastMCP", state: "ServerState") -> None:
    """Register asset diagnostic and inspection tools."""

    from ..script_executor import execute_script_from_path, get_diagnostic_scripts_dir

    from ._helpers import parse_json_result

    @mcp.tool(name="editor_asset_open")
    def open_asset(
        asset_path: Annotated[
            str,
            Field(
                description="Path to the asset to open (e.g., /Game/Blueprints/BP_Character)"
            ),
        ],
        tab_id: Annotated[
            str | None,
            Field(
                default=None,
                description="Optional tab ID to open/focus after the editor opens (e.g., 'Inspector', 'SCSViewport', 'GraphEditor')",
            ),
        ],
    ) -> dict[str, Any]:
        """
        Open an asset in its editor within Unreal Editor.

        This tool loads the specified asset and opens its appropriate editor
        (e.g., Blueprint Editor for Blueprints, Material Editor for Materials).

        Args:
            asset_path: Path to the asset to open (e.g., /Game/Blueprints/BP_Character)
            tab_id: Optional tab ID to open/focus after the editor opens.
                    Common Blueprint Editor tab IDs:
                    - "Inspector" (Details panel)
                    - "SCSViewport" (Viewport/Components view)
                    - "GraphEditor" (Event Graph - only available in Graph mode)
                    - "MyBlueprint" (My Blueprint panel)
                    - "PaletteList" (Palette)
                    - "CompilerResults" (Compiler Results)
                    - "FindResults" (Find Results)
                    - "ConstructionScriptEditor" (Construction Script)
                    Note: Some tabs may not be available depending on the editor mode/layout.

        Returns:
            Result containing:
            - success: Whether the asset was opened successfully
            - asset_path: Path of the opened asset
            - asset_name: Name of the asset
            - tab_id: The requested tab ID (if provided)
            - tab_switched: Whether tab switching succeeded (if tab_id provided)
            - tab_error: Error message if tab switching failed (if applicable)
            - error: Error message (if failed)
        """
        manager = state.get_editor_manager()

        script_path = (
            Path(__file__).parent.parent / "extra" / "scripts" / "asset_open.py"
        )

        result = execute_script_from_path(
            manager,
            script_path,
            params={"asset_path": asset_path, "tab_id": tab_id},
            timeout=30.0,
        )

        return parse_json_result(result)

    @mcp.tool(name="editor_asset_diagnostic")
    def diagnose_asset(
        asset_path: Annotated[
            str,
            Field(
                description="Path to the asset to diagnose (e.g., /Game/Maps/TestLevel)"
            ),
        ],
    ) -> dict[str, Any]:
        """
        Run diagnostics on a UE5 asset to detect common issues.

        The tool automatically detects the asset type and runs appropriate
        diagnostics. Supported types include: Level, Blueprint, Material,
        StaticMesh, SkeletalMesh, Texture, and more.

        Args:
            asset_path: Path to the asset to diagnose (e.g., /Game/Maps/TestLevel)

        Returns:
            Diagnostic result containing:
            - success: Whether diagnostic ran successfully
            - asset_path: Path of diagnosed asset
            - asset_type: Detected asset type (Level, Blueprint, etc.)
            - asset_name: Name of the asset
            - errors: Number of errors found
            - warnings: Number of warnings found
            - issues: List of issues, each with severity, category, message, actor, details, suggestion
            - summary: Optional summary message
            - metadata: Additional asset metadata
        """
        manager = state.get_editor_manager()

        scripts_dir = get_diagnostic_scripts_dir()
        script_path = scripts_dir / "diagnostic_runner.py"

        result = execute_script_from_path(
            manager,
            script_path,
            params={"asset_path": asset_path},
            timeout=120.0,
        )

        return parse_json_result(result)

    @mcp.tool(name="editor_asset_inspect")
    def inspect_asset(
        asset_path: Annotated[
            str,
            Field(
                description="Path to the asset to inspect (e.g., /Game/Meshes/MyStaticMesh)"
            ),
        ],
        component_name: Annotated[
            str | None,
            Field(
                default=None,
                description="Optional name of a specific component to inspect (only valid for Blueprint assets)",
            ),
        ],
    ) -> dict[str, Any]:
        """
        Inspect a UE5 asset and return all its properties.

        This tool loads an asset and extracts all accessible properties,
        metadata, and reference information.

        For Blueprint assets, you can optionally specify a component to inspect.
        When no component is specified for Blueprints, the response includes a list
        of available components with their names, class types, and hierarchy.

        For Blueprint and Level assets, a viewport screenshot is automatically captured
        and saved to the system temp directory.

        Args:
            asset_path: Path to the asset (e.g., /Game/Meshes/MyStaticMesh)
            component_name: Optional name of a specific component to inspect
                           (only valid for Blueprint assets)

        Returns:
            Inspection result containing:
            - success: Whether inspection succeeded
            - asset_path: Path of inspected asset
            - asset_type: Detected asset type (Level, Blueprint, StaticMesh, etc.)
            - asset_name: Name of the asset
            - asset_class: UE5 class name of the asset
            - properties: Dictionary of all accessible properties with their values
            - property_count: Number of properties found
            - components: (For Blueprints) List of available components with hierarchy
            - component_info: (When component_name specified) Details of the component
            - metadata: Asset registry metadata (package info, etc.)
            - references: Dependencies and referencers
            - screenshot_path: (For Blueprint/Level) Path to viewport screenshot
            - screenshot_error: (For Blueprint/Level) Error message if screenshot failed
        """
        manager = state.get_editor_manager()

        scripts_dir = get_diagnostic_scripts_dir()
        script_path = scripts_dir / "inspect_runner.py"

        params: dict[str, Any] = {"asset_path": asset_path}
        if component_name is not None:
            params["component_name"] = component_name

        result = execute_script_from_path(
            manager,
            script_path,
            params=params,
            timeout=120.0,
        )

        return parse_json_result(result)
