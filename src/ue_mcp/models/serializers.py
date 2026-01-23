"""
Serialization utilities for UE5 asset descriptions.

Supports JSON, YAML, and Python DSL output formats.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional, Union

from pydantic import BaseModel

from .assets import AssetType, asset_from_dict
from .blueprint import BlueprintDescription, BlueprintVariable
from .components import ComponentBase, ComponentHierarchy, component_from_dict
from .descriptors import AnyAssetDescription, AssetDescriptorV1
from .level import LevelDescription, actor_from_dict

# Optional YAML support
try:
    import yaml

    HAS_YAML = True
except ImportError:
    yaml = None  # type: ignore
    HAS_YAML = False


def serialize_to_json(
    asset: Union[AnyAssetDescription, AssetDescriptorV1],
    indent: int = 2,
    exclude_none: bool = True,
) -> str:
    """
    Serialize an asset description to JSON string.

    Args:
        asset: The asset description to serialize
        indent: JSON indentation level
        exclude_none: Whether to exclude None values

    Returns:
        JSON string
    """
    return asset.model_dump_json(indent=indent, exclude_none=exclude_none)


def serialize_to_dict(
    asset: Union[AnyAssetDescription, AssetDescriptorV1],
    exclude_none: bool = True,
) -> Dict[str, Any]:
    """
    Serialize an asset description to a dictionary.

    Args:
        asset: The asset description to serialize
        exclude_none: Whether to exclude None values

    Returns:
        Dictionary representation
    """
    return asset.model_dump(exclude_none=exclude_none)


def serialize_to_yaml(
    asset: Union[AnyAssetDescription, AssetDescriptorV1],
    exclude_none: bool = True,
) -> str:
    """
    Serialize an asset description to YAML string.

    Args:
        asset: The asset description to serialize
        exclude_none: Whether to exclude None values

    Returns:
        YAML string

    Raises:
        ImportError: If PyYAML is not installed
    """
    if not HAS_YAML:
        raise ImportError(
            "PyYAML is required for YAML serialization. Install with: pip install pyyaml"
        )

    data = asset.model_dump(exclude_none=exclude_none)
    return yaml.dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True)


def serialize_to_python_dsl(
    asset: AnyAssetDescription,
    variable_name: str = "asset",
) -> str:
    """
    Serialize an asset description to Python DSL (executable Python code).

    This generates Python code that can recreate the asset description.

    Args:
        asset: The asset description to serialize
        variable_name: Name of the variable to assign the asset to

    Returns:
        Python code string
    """
    lines = []
    lines.append("from ue_mcp.models import (")

    # Collect imports based on asset type
    model_name = type(asset).__name__
    imports = {model_name}

    # Add common imports
    if hasattr(asset, "transform"):
        imports.add("Transform")
        imports.add("Vector3")
        imports.add("Rotator")
    if hasattr(asset, "components"):
        imports.add("ComponentHierarchy")
    if hasattr(asset, "variables"):
        imports.add("BlueprintVariable")

    for imp in sorted(imports):
        lines.append(f"    {imp},")
    lines.append(")")
    lines.append("")

    # Generate the Python code representation
    data = asset.model_dump(exclude_none=True)
    dict_str = _format_dict_as_python(data, indent=0)

    lines.append(f"{variable_name} = {model_name}.model_validate({dict_str})")

    return "\n".join(lines)


def _format_dict_as_python(data: Any, indent: int = 0) -> str:
    """Format a dictionary as Python code with proper indentation."""
    indent_str = "    " * indent
    next_indent = "    " * (indent + 1)

    if isinstance(data, dict):
        if not data:
            return "{}"
        items = []
        for key, value in data.items():
            formatted_value = _format_dict_as_python(value, indent + 1)
            items.append(f'{next_indent}"{key}": {formatted_value}')
        return "{\n" + ",\n".join(items) + f"\n{indent_str}}}"

    elif isinstance(data, list):
        if not data:
            return "[]"
        items = [_format_dict_as_python(item, indent + 1) for item in data]
        if len(str(items)) < 60 and all("\n" not in str(i) for i in items):
            # Short list, keep on one line
            return "[" + ", ".join(items) + "]"
        return "[\n" + ",\n".join(f"{next_indent}{item}" for item in items) + f"\n{indent_str}]"

    elif isinstance(data, str):
        # Escape quotes and represent as string
        return repr(data)

    elif isinstance(data, bool):
        return "True" if data else "False"

    elif data is None:
        return "None"

    else:
        return repr(data)


def deserialize_from_json(json_str: str) -> AnyAssetDescription:
    """
    Deserialize an asset description from JSON string.

    Args:
        json_str: JSON string to parse

    Returns:
        Asset description model
    """
    data = json.loads(json_str)
    return _deserialize_from_dict(data)


def deserialize_from_yaml(yaml_str: str) -> AnyAssetDescription:
    """
    Deserialize an asset description from YAML string.

    Args:
        yaml_str: YAML string to parse

    Returns:
        Asset description model

    Raises:
        ImportError: If PyYAML is not installed
    """
    if not HAS_YAML:
        raise ImportError(
            "PyYAML is required for YAML deserialization. Install with: pip install pyyaml"
        )

    data = yaml.safe_load(yaml_str)
    return _deserialize_from_dict(data)


def _deserialize_from_dict(data: Dict[str, Any]) -> AnyAssetDescription:
    """Deserialize an asset description from a dictionary."""
    # Check if this is a versioned descriptor
    if "schema_name" in data and "asset" in data:
        descriptor = AssetDescriptorV1.model_validate(data)
        return descriptor.asset

    # Otherwise, determine the type and deserialize directly
    asset_type = data.get("asset_type")

    # Check for explicit asset_type field
    if asset_type == "Level" or asset_type == AssetType.LEVEL:
        return LevelDescription.model_validate(data)
    elif asset_type == "Blueprint" or asset_type == AssetType.BLUEPRINT:
        return BlueprintDescription.model_validate(data)
    elif asset_type is not None:
        # Has an asset_type field, use the asset deserializer
        return asset_from_dict(data)

    # No asset_type field - try to infer from structure
    # BlueprintDescription has unique fields: parent_class, blueprint_type, components (with root_component)
    if "parent_class" in data or "blueprint_type" in data:
        return BlueprintDescription.model_validate(data)

    # LevelDescription has unique fields: world_settings, actors, streaming_levels
    if "world_settings" in data or "actors" in data or "streaming_levels" in data:
        return LevelDescription.model_validate(data)

    # If we can't determine the type, try BlueprintDescription first (most common use case)
    # then fall back to asset_from_dict
    try:
        return BlueprintDescription.model_validate(data)
    except Exception:
        return asset_from_dict(data)


def load_from_file(path: Union[Path, str]) -> AnyAssetDescription:
    """
    Load an asset description from a file (JSON or YAML based on extension).

    Args:
        path: Path to the file

    Returns:
        Asset description model
    """
    path = Path(path)
    content = path.read_text(encoding="utf-8")

    if path.suffix.lower() in (".yaml", ".yml"):
        return deserialize_from_yaml(content)
    else:
        return deserialize_from_json(content)


def save_to_file(
    asset: Union[AnyAssetDescription, AssetDescriptorV1],
    path: Union[Path, str],
    format: str = "auto",
    exclude_none: bool = True,
) -> None:
    """
    Save an asset description to a file.

    Args:
        asset: The asset description to save
        path: Output file path
        format: "json", "yaml", or "auto" (detect from extension)
        exclude_none: Whether to exclude None values
    """
    path = Path(path)

    if format == "auto":
        format = "yaml" if path.suffix.lower() in (".yaml", ".yml") else "json"

    if format == "yaml":
        content = serialize_to_yaml(asset, exclude_none=exclude_none)
    else:
        content = serialize_to_json(asset, exclude_none=exclude_none)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def wrap_with_version(
    asset: AnyAssetDescription,
    generated_by: str = "ue-mcp",
) -> AssetDescriptorV1:
    """
    Wrap an asset description with version metadata.

    Args:
        asset: The asset description to wrap
        generated_by: Generator identifier

    Returns:
        Versioned asset descriptor
    """
    return AssetDescriptorV1(
        asset=asset,
        generated_by=generated_by,
    )


def from_inspect_result(inspect_result: Dict[str, Any]) -> AnyAssetDescription:
    """
    Convert inspect_runner.py output to a Pydantic model.

    This bridges the existing inspection code with the new model system.

    Args:
        inspect_result: Output from inspect_runner.py

    Returns:
        Asset description model
    """
    asset_type_str = inspect_result.get("asset_type", "Unknown")
    asset_path = inspect_result.get("asset_path", "")
    asset_name = inspect_result.get("asset_name", "")
    asset_class = inspect_result.get("asset_class", "")

    if asset_type_str == "Blueprint":
        # Convert blueprint inspection result
        components_data = inspect_result.get("components", [])
        components = []

        for comp_data in components_data:
            comp = ComponentBase(
                name=comp_data.get("name", ""),
                component_class=comp_data.get("class", "SceneComponent"),
                is_root=(comp_data.get("parent") is None),
            )
            components.append(comp)

        # Determine root component
        root_name = "DefaultSceneRoot"
        for comp in components:
            if comp.is_root:
                root_name = comp.name
                break

        return BlueprintDescription(
            asset_path=asset_path,
            asset_name=asset_name,
            parent_class=asset_class,
            components=ComponentHierarchy(
                root_component=root_name,
                components=components,
            ),
        )

    elif asset_type_str == "Level":
        return LevelDescription(
            asset_path=asset_path,
            asset_name=asset_name,
            actors=[],
        )

    else:
        # For other asset types, use the generic converter
        return asset_from_dict(
            {
                "asset_path": asset_path,
                "asset_name": asset_name,
                "asset_type": asset_type_str,
                "asset_class": asset_class,
                **inspect_result.get("properties", {}),
            }
        )
