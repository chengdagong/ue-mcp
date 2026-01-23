"""
Asset inspection runner script for MCP.

Inspects a UE5 asset and returns all its properties as structured JSON.
For Blueprint and Level assets, also captures a viewport screenshot.

Usage (CLI):
    python inspect_runner.py --asset-path=/Game/Meshes/MyMesh

    Optional arguments:
        --component-name=<name>   Name of a specific component to inspect (for Blueprints)

MCP mode (__PARAMS__):
    asset_path: str - Asset path to inspect (e.g., /Game/Meshes/MyMesh)
    component_name: str (optional) - Name of a specific component to inspect (for Blueprints)
"""
import json
import os
import sys
import tempfile
import time

import unreal
import asset_diagnostic


from asset_diagnostic import detect_asset_type, load_asset, get_asset_references, AssetType

# Flag to track if running in MCP mode (vs CLI mode)
_mcp_mode = None


def _is_mcp_mode() -> bool:
    """Check if running in MCP mode (vs CLI mode)."""
    global _mcp_mode
    if _mcp_mode is None:
        import builtins
        _mcp_mode = hasattr(builtins, "__PARAMS__")
    return _mcp_mode


def _parse_cli_value(value_str: str):
    """Parse a CLI argument value string to appropriate Python type."""
    if value_str.lower() in ("none", "null"):
        return None
    if value_str.lower() in ("true", "yes", "1"):
        return True
    if value_str.lower() in ("false", "no", "0"):
        return False
    try:
        return int(value_str)
    except ValueError:
        pass
    try:
        return float(value_str)
    except ValueError:
        pass
    return value_str


def get_params() -> dict:
    """
    Get parameters from MCP server or CLI arguments.

    The MCP server injects __PARAMS__ into builtins before executing the script.
    For direct execution, parameters are parsed from sys.argv.
    """
    import builtins

    # Check MCP mode first
    if hasattr(builtins, "__PARAMS__"):
        return builtins.__PARAMS__

    # CLI mode: parse arguments
    params = {}
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        arg = args[i]
        if arg.startswith("--"):
            arg = arg[2:]
            if "=" in arg:
                key, value = arg.split("=", 1)
                params[key.replace("-", "_")] = _parse_cli_value(value)
            elif i + 1 < len(args) and not args[i + 1].startswith("--"):
                key = arg.replace("-", "_")
                params[key] = _parse_cli_value(args[i + 1])
                i += 1
            else:
                params[arg.replace("-", "_")] = True
        i += 1

    # Validate required parameters
    if "asset_path" not in params:
        raise RuntimeError(
            "Missing required parameter: asset_path\n"
            "Usage: python inspect_runner.py --asset-path=/Game/Meshes/MyMesh\n"
            "       python inspect_runner.py --asset-path=/Game/BP_Test --component-name=Mesh"
        )

    return params


def output_result(data: dict) -> None:
    """
    Output result in format appropriate for current mode.

    In MCP mode: Outputs JSON with special prefix for parsing.
    In CLI mode: Outputs human-readable formatted JSON.
    """
    if _is_mcp_mode():
        print("__DIAGNOSTIC_RESULT__" + json.dumps(data))
    else:
        print("\n" + "=" * 60)
        print("INSPECTION RESULT")
        print("=" * 60)
        print(json.dumps(data, indent=2))
        print("=" * 60)


def serialize_value(value, depth=0, max_depth=3):
    """
    Serialize UE5 values to JSON-compatible format.

    Args:
        value: The value to serialize
        depth: Current recursion depth
        max_depth: Maximum recursion depth

    Returns:
        JSON-serializable value
    """
    if depth > max_depth:
        return f"<{type(value).__name__}>"

    # Handle None
    if value is None:
        return None

    # Primitives
    if isinstance(value, (bool, int, float, str)):
        return value

    # UE5 Vector types (Vector, Vector2D, Vector4, IntVector, etc.)
    if hasattr(value, "x") and hasattr(value, "y"):
        if hasattr(value, "z"):
            if hasattr(value, "w"):  # Vector4, Quat, LinearColor
                return {
                    "x": float(value.x),
                    "y": float(value.y),
                    "z": float(value.z),
                    "w": float(value.w),
                }
            return {
                "x": float(value.x),
                "y": float(value.y),
                "z": float(value.z),
            }  # Vector
        return {"x": float(value.x), "y": float(value.y)}  # Vector2D

    # UE5 Rotator
    if hasattr(value, "pitch") and hasattr(value, "yaw") and hasattr(value, "roll"):
        return {
            "pitch": float(value.pitch),
            "yaw": float(value.yaw),
            "roll": float(value.roll),
        }

    # UE5 Color (FColor has r,g,b,a as integers)
    if (
        hasattr(value, "r")
        and hasattr(value, "g")
        and hasattr(value, "b")
        and hasattr(value, "a")
    ):
        return {
            "r": int(value.r),
            "g": int(value.g),
            "b": int(value.b),
            "a": int(value.a),
        }

    # UE5 Transform
    if hasattr(value, "translation") and hasattr(value, "rotation") and hasattr(value, "scale3d"):
        return {
            "translation": serialize_value(value.translation, depth + 1, max_depth),
            "rotation": serialize_value(value.rotation, depth + 1, max_depth),
            "scale3d": serialize_value(value.scale3d, depth + 1, max_depth),
        }

    # UE5 Box (has min and max vectors)
    if hasattr(value, "min") and hasattr(value, "max") and hasattr(value.min, "x"):
        return {
            "min": serialize_value(value.min, depth + 1, max_depth),
            "max": serialize_value(value.max, depth + 1, max_depth),
        }

    # Arrays and tuples
    if isinstance(value, (list, tuple)):
        return [serialize_value(v, depth + 1, max_depth) for v in value]

    # Dictionaries
    if isinstance(value, dict):
        return {str(k): serialize_value(v, depth + 1, max_depth) for k, v in value.items()}

    # UE5 Enum - check for name attribute that enums have
    if hasattr(value, "name") and hasattr(type(value), "__members__"):
        return value.name

    # UE5 objects - get class name as reference
    if hasattr(value, "get_class"):
        try:
            class_name = value.get_class().get_name()
            # Try to get object name/path for reference
            if hasattr(value, "get_name"):
                obj_name = value.get_name()
                return f"<{class_name}: {obj_name}>"
            return f"<{class_name}>"
        except Exception:
            pass

    # Fallback to string representation
    try:
        return str(value)
    except Exception:
        return f"<{type(value).__name__}>"


def get_asset_properties(asset, max_depth=3) -> dict:
    """
    Extract all accessible properties from an asset.

    Args:
        asset: The loaded UE5 asset object
        max_depth: Maximum depth for nested property serialization

    Returns:
        Dictionary of property names to serialized values
    """
    properties = {}

    # Get all attribute names
    attr_names = dir(asset)

    # Filter and extract properties
    for name in attr_names:
        # Skip private/internal attributes
        if name.startswith("_"):
            continue

        # Skip common method names that aren't properties
        if name in (
            "get_editor_property",
            "set_editor_property",
            "get_class",
            "get_name",
            "get_outer",
            "get_world",
            "get_path_name",
            "get_full_name",
            "cast",
            "static_class",
            "call_method",
        ):
            continue

        # Try get_editor_property first (preferred UE5 way)
        try:
            value = asset.get_editor_property(name)
            properties[name] = serialize_value(value, 0, max_depth)
        except Exception:
            # Property might not be accessible via get_editor_property
            # Try direct attribute access for non-callable attributes
            try:
                attr = getattr(asset, name)
                if not callable(attr):
                    properties[name] = serialize_value(attr, 0, max_depth)
            except Exception:
                pass

    return properties


def get_asset_metadata(asset_path: str) -> dict:
    """
    Get asset metadata from the asset registry.

    Args:
        asset_path: Path to the asset

    Returns:
        Dictionary of metadata
    """
    metadata = {}

    try:
        asset_data = unreal.EditorAssetLibrary.find_asset_data(asset_path)

        if asset_data and asset_data.is_valid():
            metadata["asset_name"] = str(asset_data.asset_name)
            metadata["asset_class"] = str(asset_data.asset_class_path.asset_name)
            metadata["package_name"] = str(asset_data.package_name)
            metadata["package_path"] = str(asset_data.package_path)

            # Try to get additional metadata if available
            try:
                # Check if asset is a redirector
                metadata["is_redirector"] = asset_data.is_redirector()
            except Exception:
                pass

            try:
                # Check if asset is valid
                metadata["is_valid"] = asset_data.is_valid()
            except Exception:
                pass

    except Exception as e:
        metadata["error"] = str(e)

    return metadata


def get_blueprint_components(blueprint) -> list:
    """
    Get all components defined in a Blueprint with hierarchy information.

    Args:
        blueprint: The loaded Blueprint asset

    Returns:
        List of component info dictionaries with name, class, parent, children
    """
    components = []

    try:
        # Get the generated class from the Blueprint
        generated_class = blueprint.generated_class()
        if generated_class is None:
            return components

        # Get the Class Default Object (CDO)
        cdo = unreal.get_default_object(generated_class)
        if cdo is None:
            return components

        # Get all components (ActorComponent is the base class for all components)
        all_components = cdo.get_components_by_class(unreal.ActorComponent)
        if not all_components:
            return components

        # Build a mapping from component name to component info
        comp_map = {}
        for comp in all_components:
            comp_name = comp.get_name()
            comp_info = {
                "name": comp_name,
                "class": comp.get_class().get_name(),
                "parent": None,
                "children": [],
            }
            comp_map[comp_name] = comp_info

        # Build hierarchy by checking attachment parent (for SceneComponents)
        for comp in all_components:
            comp_name = comp.get_name()
            # Check if this is a SceneComponent with attachment info
            if hasattr(comp, "get_attach_parent"):
                try:
                    parent_comp = comp.get_attach_parent()
                    if parent_comp is not None:
                        parent_name = parent_comp.get_name()
                        comp_map[comp_name]["parent"] = parent_name
                        # Add to parent's children list
                        if parent_name in comp_map:
                            comp_map[parent_name]["children"].append(comp_name)
                except Exception:
                    pass

        components = list(comp_map.values())

    except Exception as e:
        unreal.log(f"[WARNING] Failed to get Blueprint components: {e}")

    return components


def get_component_properties(blueprint, component_name: str, max_depth=3) -> dict:
    """
    Get properties of a specific component in a Blueprint.

    Args:
        blueprint: The loaded Blueprint asset
        component_name: Name of the component to inspect
        max_depth: Maximum depth for nested property serialization

    Returns:
        Dictionary with component info and properties, or error info
    """
    try:
        generated_class = blueprint.generated_class()
        if generated_class is None:
            return {"error": "Blueprint has no generated class"}

        cdo = unreal.get_default_object(generated_class)
        if cdo is None:
            return {"error": "Could not get Class Default Object (CDO)"}

        # Get all components
        all_components = cdo.get_components_by_class(unreal.ActorComponent)
        if not all_components:
            return {"error": "No components found in Blueprint"}

        # Find the target component by name
        target_component = None
        available_names = []
        for comp in all_components:
            name = comp.get_name()
            available_names.append(name)
            if name == component_name:
                target_component = comp
                break

        if target_component is None:
            return {
                "error": f"Component '{component_name}' not found",
                "available_components": available_names,
            }

        # Build component info with properties
        comp_info = {
            "name": target_component.get_name(),
            "class": target_component.get_class().get_name(),
            "parent": None,
            "children": [],
        }

        # Get parent attachment info
        if hasattr(target_component, "get_attach_parent"):
            try:
                parent_comp = target_component.get_attach_parent()
                if parent_comp is not None:
                    comp_info["parent"] = parent_comp.get_name()
            except Exception:
                pass

        # Get children
        for comp in all_components:
            if hasattr(comp, "get_attach_parent"):
                try:
                    parent = comp.get_attach_parent()
                    if parent is not None and parent.get_name() == component_name:
                        comp_info["children"].append(comp.get_name())
                except Exception:
                    pass

        # Extract properties
        properties = get_asset_properties(target_component, max_depth)
        comp_info["properties"] = properties
        comp_info["property_count"] = len(properties)

        return comp_info

    except Exception as e:
        return {"error": str(e)}


# ============================================
# Screenshot Capture Functions
# ============================================


def get_screenshot_output_path(asset_path: str) -> str:
    """
    Generate screenshot output path in system temp directory.

    Path format: {tempdir}/ue-mcp/screenshots/{project_name}_{asset_name}_{timestamp}/screenshot.png

    Args:
        asset_path: The asset path (e.g., /Game/Blueprints/BP_Character)

    Returns:
        Full path to the screenshot file
    """
    # Get project name from project directory
    project_dir = unreal.Paths.project_dir()
    project_name = project_dir.rstrip("/\\").replace("\\", "/").split("/")[-1]

    # Get asset name from path
    asset_name = asset_path.rsplit("/", 1)[-1] if "/" in asset_path else asset_path

    # Generate timestamp
    timestamp = time.strftime("%Y%m%d_%H%M%S")

    # Build path: {tempdir}/ue-mcp/screenshots/{project_name}_{asset_name}_{timestamp}/
    temp_dir = tempfile.gettempdir()
    screenshot_dir = os.path.join(
        temp_dir, "ue-mcp", "screenshots",
        f"{project_name}_{asset_name}_{timestamp}"
    )
    os.makedirs(screenshot_dir, exist_ok=True)

    return os.path.join(screenshot_dir, "screenshot.png")


def _do_capture(output_path: str) -> dict:
    """
    Execute window capture using editor_capture module.

    Args:
        output_path: Path to save the screenshot

    Returns:
        dict with keys: success, screenshot_path (if success), error (if failed)
    """
    try:
        import editor_capture
    except ImportError as e:
        return {"success": False, "error": f"editor_capture module not available: {e}"}

    try:
        result = editor_capture.capture_ue5_window(output_path)
        if isinstance(result, dict):
            if result.get("success"):
                return {"success": True, "screenshot_path": output_path}
            else:
                return {"success": False, "error": result.get("error", "Capture failed")}
        else:
            # Legacy bool return
            if result:
                return {"success": True, "screenshot_path": output_path}
            else:
                return {"success": False, "error": "Capture failed"}
    except Exception as e:
        return {"success": False, "error": f"Capture exception: {e}"}


def _capture_blueprint_screenshot(blueprint, output_path: str) -> dict:
    """
    Capture screenshot of a Blueprint's viewport.

    Opens the Blueprint editor, switches to viewport mode, and captures.

    Args:
        blueprint: The loaded Blueprint asset
        output_path: Path to save the screenshot

    Returns:
        dict with keys: success, screenshot_path (if success), error (if failed)
    """
    try:
        # Open the blueprint editor
        subsystem = unreal.get_editor_subsystem(unreal.AssetEditorSubsystem)
        subsystem.open_editor_for_assets([blueprint])

        # Wait for editor to initialize and render
        time.sleep(1.5)

        # Switch to viewport mode using ExSlateTabLibrary
        try:
            unreal.ExSlateTabLibrary.switch_to_viewport_mode(blueprint)
            time.sleep(0.5)
        except AttributeError:
            unreal.log_warning("[WARNING] ExSlateTabLibrary not available, skipping viewport switch")

        # Capture the window
        return _do_capture(output_path)

    except Exception as e:
        return {"success": False, "error": f"Blueprint screenshot failed: {e}"}


def _capture_level_screenshot(level_path: str, output_path: str) -> dict:
    """
    Capture screenshot of a Level's main editor viewport.

    The level should already be loaded by the inspection process.

    Args:
        level_path: The level asset path
        output_path: Path to save the screenshot

    Returns:
        dict with keys: success, screenshot_path (if success), error (if failed)
    """
    try:
        # Wait for viewport to be ready
        time.sleep(1.0)

        # Capture the main editor window
        return _do_capture(output_path)

    except Exception as e:
        return {"success": False, "error": f"Level screenshot failed: {e}"}


def capture_asset_screenshot(asset, asset_path: str, asset_type) -> dict:
    """
    Capture screenshot for Blueprint or Level asset.

    Args:
        asset: The loaded asset object
        asset_path: The asset path
        asset_type: The detected AssetType

    Returns:
        dict with keys: success, screenshot_path (if success), error (if failed)
    """
    output_path = get_screenshot_output_path(asset_path)

    if asset_type == AssetType.BLUEPRINT:
        return _capture_blueprint_screenshot(asset, output_path)
    elif asset_type == AssetType.LEVEL:
        return _capture_level_screenshot(asset_path, output_path)
    else:
        return {"success": False, "error": f"Screenshot not supported for asset type: {asset_type.value}"}


def main():
    """Main entry point for asset inspection."""
    params = get_params()
    asset_path = params["asset_path"]
    component_name = params.get("component_name")  # Optional parameter

    # Detect asset type
    asset_type = detect_asset_type(asset_path)

    # Load the asset
    asset = load_asset(asset_path)

    if asset is None:
        output_result({
            "success": False,
            "error": f"Failed to load asset: {asset_path}",
        })
        return

    # Get asset class name
    try:
        asset_class = asset.get_class().get_name()
    except Exception:
        asset_class = "Unknown"

    # Extract asset name from path
    asset_name = asset_path.rsplit("/", 1)[-1] if "/" in asset_path else asset_path

    # Base result structure
    result = {
        "success": True,
        "asset_path": asset_path,
        "asset_type": asset_type.value,
        "asset_name": asset_name,
        "asset_class": asset_class,
    }

    # Handle Blueprint-specific inspection
    if asset_type == AssetType.BLUEPRINT:
        if component_name:
            # Inspect a specific component
            comp_result = get_component_properties(asset, component_name)
            if "error" in comp_result:
                result["success"] = False
                result["error"] = comp_result["error"]
                if "available_components" in comp_result:
                    result["available_components"] = comp_result["available_components"]
            else:
                result["component_info"] = comp_result
                result["property_count"] = comp_result.get("property_count", 0)
        else:
            # List all components and get asset-level properties
            result["components"] = get_blueprint_components(asset)
            result["properties"] = get_asset_properties(asset)
            result["property_count"] = len(result["properties"])
    else:
        # Non-Blueprint: standard property extraction
        result["properties"] = get_asset_properties(asset)
        result["property_count"] = len(result["properties"])

    # Add metadata and references
    result["metadata"] = get_asset_metadata(asset_path)
    result["references"] = get_asset_references(asset_path)

    # Capture screenshot for Blueprint and Level assets
    if asset_type in (AssetType.BLUEPRINT, AssetType.LEVEL):
        screenshot_result = capture_asset_screenshot(asset, asset_path, asset_type)
        if screenshot_result["success"]:
            result["screenshot_path"] = screenshot_result["screenshot_path"]
        else:
            result["screenshot_error"] = screenshot_result.get("error", "Unknown screenshot error")

    # Output the result
    output_result(result)


if __name__ == "__main__":
    main()
