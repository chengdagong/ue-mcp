"""
Top-level asset descriptor supporting all asset types.

This is the main entry point for serializing/deserializing any UE5 asset.
"""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, Discriminator, Field, Tag

from .assets import (
    AnimationBlueprintDescription,
    AnimationDescription,
    AssetType,
    DataAssetDescription,
    MaterialDescription,
    MaterialInstanceDescription,
    ParticleSystemDescription,
    PhysicsAssetDescription,
    SkeletalMeshDescription,
    SkeletonDescription,
    SoundDescription,
    StaticMeshDescription,
    TextureDescription,
    WidgetBlueprintDescription,
)
from .blueprint import BlueprintDescription
from .level import LevelDescription


def get_asset_type_discriminator(v: dict) -> str:
    """Get the asset type from a dict for discriminator."""
    if isinstance(v, dict):
        return v.get("asset_type", "Unknown")
    return getattr(v, "asset_type", "Unknown")


# Union of all possible asset descriptions with discriminator
AnyAssetDescription = Annotated[
    Union[
        Annotated[LevelDescription, Tag("Level")],
        Annotated[BlueprintDescription, Tag("Blueprint")],
        Annotated[StaticMeshDescription, Tag("StaticMesh")],
        Annotated[SkeletalMeshDescription, Tag("SkeletalMesh")],
        Annotated[SkeletonDescription, Tag("Skeleton")],
        Annotated[TextureDescription, Tag("Texture")],
        Annotated[MaterialDescription, Tag("Material")],
        Annotated[MaterialInstanceDescription, Tag("MaterialInstance")],
        Annotated[AnimationDescription, Tag("Animation")],
        Annotated[AnimationBlueprintDescription, Tag("AnimationBlueprint")],
        Annotated[SoundDescription, Tag("Sound")],
        Annotated[ParticleSystemDescription, Tag("ParticleSystem")],
        Annotated[WidgetBlueprintDescription, Tag("WidgetBlueprint")],
        Annotated[PhysicsAssetDescription, Tag("PhysicsAsset")],
        Annotated[DataAssetDescription, Tag("DataAsset")],
    ],
    Discriminator(get_asset_type_discriminator),
]


class AssetDescriptorV1(BaseModel):
    """
    Versioned asset descriptor wrapper.

    Provides version metadata for forward compatibility.

    Example:
        descriptor = AssetDescriptorV1(
            asset=BlueprintDescription(
                asset_path="/Game/Blueprints/BP_Character",
                asset_name="BP_Character",
                parent_class="Character"
            )
        )
        json_str = descriptor.model_dump_json(indent=2)
    """

    version: Literal["1.0"] = "1.0"
    schema_name: str = "ue-mcp-asset-descriptor"
    asset: AnyAssetDescription

    # Optional metadata
    generated_by: str = "ue-mcp"

    model_config = {
        "json_schema_extra": {
            "title": "UE5 Asset Descriptor",
            "description": "Versioned wrapper for UE5 asset descriptions",
        }
    }


# Type aliases for convenience
LevelDesc = LevelDescription
BlueprintDesc = BlueprintDescription
MeshDesc = Union[StaticMeshDescription, SkeletalMeshDescription]
MaterialDesc = Union[MaterialDescription, MaterialInstanceDescription]
