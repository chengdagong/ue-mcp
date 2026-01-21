"""
Asset inspection runner script for MCP.

Inspects a UE5 asset and returns all its properties as structured JSON.

Expected __PARAMS__:
    asset_path: str - Asset path to inspect (e.g., /Game/Meshes/MyMesh)
"""
import json

import unreal
from asset_diagnostic import detect_asset_type, load_asset, get_asset_references


def get_params() -> dict:
    """Get parameters injected by MCP server."""
    import builtins

    if hasattr(builtins, "__PARAMS__"):
        return builtins.__PARAMS__
    raise RuntimeError(
        "__PARAMS__ not found. If testing manually, set builtins.__PARAMS__ = {...} first."
    )


def output_result(data: dict) -> None:
    """Output result in format expected by MCP server."""
    print("__DIAGNOSTIC_RESULT__" + json.dumps(data))


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


def main():
    """Main entry point for asset inspection."""
    params = get_params()
    asset_path = params["asset_path"]

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

    # Get all properties
    properties = get_asset_properties(asset)

    # Get metadata
    metadata = get_asset_metadata(asset_path)

    # Get references
    references = get_asset_references(asset_path)

    # Output the result
    output_result({
        "success": True,
        "asset_path": asset_path,
        "asset_type": asset_type.value,
        "asset_name": asset_name,
        "asset_class": asset_class,
        "properties": properties,
        "property_count": len(properties),
        "metadata": metadata,
        "references": references,
    })


if __name__ == "__main__":
    main()
