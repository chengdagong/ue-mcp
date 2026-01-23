"""
UE5 Asset description models for non-Blueprint, non-Level assets.

Includes: StaticMesh, SkeletalMesh, Texture, Material, Animation, Sound, etc.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from .base import AssetReference, Box, LinearColor, Vector3


class AssetType(str, Enum):
    """Supported UE5 asset types (compatible with core.py)."""

    LEVEL = "Level"
    BLUEPRINT = "Blueprint"
    MATERIAL = "Material"
    MATERIAL_INSTANCE = "MaterialInstance"
    STATIC_MESH = "StaticMesh"
    SKELETAL_MESH = "SkeletalMesh"
    TEXTURE = "Texture"
    ANIMATION = "Animation"
    ANIMATION_BLUEPRINT = "AnimationBlueprint"
    SOUND = "Sound"
    PARTICLE_SYSTEM = "ParticleSystem"
    WIDGET_BLUEPRINT = "WidgetBlueprint"
    DATA_ASSET = "DataAsset"
    PHYSICS_ASSET = "PhysicsAsset"
    SKELETON = "Skeleton"
    UNKNOWN = "Unknown"


class AssetMetadata(BaseModel):
    """Common metadata for all assets."""

    package_name: str = Field(..., description="Package name e.g. /Game/Meshes/SM_Cube")
    package_path: str = Field(..., description="Package path e.g. /Game/Meshes")
    is_redirector: bool = False


class AssetReferences(BaseModel):
    """Asset dependency information."""

    dependencies: List[str] = Field(
        default_factory=list, description="Assets this asset references"
    )
    referencers: List[str] = Field(
        default_factory=list, description="Assets that reference this asset"
    )


class BaseAssetDescription(BaseModel):
    """Base model for all asset descriptions."""

    asset_path: str = Field(..., description="Full asset path")
    asset_name: str = Field(..., description="Asset name")
    asset_type: AssetType
    asset_class: str = Field(..., description="UE5 class name")

    metadata: Optional[AssetMetadata] = None
    references: AssetReferences = Field(default_factory=AssetReferences)

    # Generic properties
    properties: Dict[str, Any] = Field(default_factory=dict)


class LODInfo(BaseModel):
    """Level of Detail information."""

    lod_index: int
    screen_size: float = 1.0
    num_triangles: int = 0
    num_vertices: int = 0


class MaterialSlot(BaseModel):
    """Material slot information."""

    slot_name: str
    material: Optional[AssetReference] = None


class StaticMeshDescription(BaseAssetDescription):
    """Static Mesh asset description."""

    asset_type: AssetType = AssetType.STATIC_MESH

    # Geometry info
    bounding_box: Optional[Box] = None
    num_lods: int = 1
    lod_info: List[LODInfo] = Field(default_factory=list)

    # Total counts for LOD0
    num_triangles: int = 0
    num_vertices: int = 0
    num_uv_channels: int = 1

    # Materials
    material_slots: List[MaterialSlot] = Field(default_factory=list)

    # Collision
    has_collision: bool = True
    collision_complexity: Literal[
        "Default", "Simple", "UseComplexAsSimple", "UseSimpleAsComplex"
    ] = "Default"
    num_convex_pieces: int = 0

    # Lightmap
    lightmap_resolution: int = 64
    lightmap_coordinate_index: int = 0

    # Nanite
    is_nanite_enabled: bool = False

    # Distance field
    has_distance_field: bool = True


class BoneInfo(BaseModel):
    """Skeleton bone information."""

    name: str
    parent_index: int = -1
    parent_name: Optional[str] = None
    num_children: int = 0


class SkeletonDescription(BaseAssetDescription):
    """Skeleton asset description."""

    asset_type: AssetType = AssetType.SKELETON

    num_bones: int = 0
    bones: List[BoneInfo] = Field(default_factory=list)

    # Virtual bones
    virtual_bones: List[str] = Field(default_factory=list)

    # Sockets
    sockets: List[str] = Field(default_factory=list)


class SkeletalMeshDescription(BaseAssetDescription):
    """Skeletal Mesh asset description."""

    asset_type: AssetType = AssetType.SKELETAL_MESH

    # Skeleton
    skeleton: Optional[AssetReference] = None
    num_bones: int = 0
    bone_names: List[str] = Field(default_factory=list)

    # Geometry
    bounding_box: Optional[Box] = None
    num_lods: int = 1
    lod_info: List[LODInfo] = Field(default_factory=list)
    num_triangles: int = 0
    num_vertices: int = 0

    # Materials
    material_slots: List[MaterialSlot] = Field(default_factory=list)

    # Physics
    physics_asset: Optional[AssetReference] = None

    # Morph targets
    morph_targets: List[str] = Field(default_factory=list)

    # Clothing
    has_clothing: bool = False


class TextureDescription(BaseAssetDescription):
    """Texture asset description."""

    asset_type: AssetType = AssetType.TEXTURE

    # Dimensions
    width: int = 0
    height: int = 0
    depth: int = 1  # For 3D textures

    # Format
    pixel_format: str = "PF_Unknown"
    compression_settings: str = "TC_Default"

    # Mips
    num_mips: int = 1

    # SRGB
    srgb: bool = True

    # Texture group
    lod_group: str = "TEXTUREGROUP_World"

    # Source info
    source_format: Optional[str] = None
    has_alpha_channel: bool = False

    # Virtual texture
    is_virtual_texture_streaming: bool = False


class MaterialParameterInfo(BaseModel):
    """Material parameter definition."""

    name: str
    parameter_type: Literal[
        "Scalar", "Vector", "Texture", "StaticSwitch", "StaticComponentMask", "Font"
    ]
    default_value: Optional[Any] = None
    group: Optional[str] = None
    sort_priority: int = 32


class MaterialDescription(BaseAssetDescription):
    """Material asset description."""

    asset_type: AssetType = AssetType.MATERIAL

    # Material domain
    material_domain: Literal[
        "Surface", "DeferredDecal", "LightFunction", "PostProcess", "UI", "Volume"
    ] = "Surface"
    blend_mode: Literal[
        "Opaque", "Masked", "Translucent", "Additive", "Modulate", "AlphaComposite", "AlphaHoldout"
    ] = "Opaque"
    shading_model: str = "DefaultLit"

    # Two-sided
    two_sided: bool = False
    is_thin_surface: bool = False

    # Parameters
    scalar_parameters: List[MaterialParameterInfo] = Field(default_factory=list)
    vector_parameters: List[MaterialParameterInfo] = Field(default_factory=list)
    texture_parameters: List[MaterialParameterInfo] = Field(default_factory=list)
    static_switch_parameters: List[MaterialParameterInfo] = Field(default_factory=list)

    # Texture samples
    num_texture_samplers: int = 0

    # Instructions
    base_pass_instructions: int = 0


class MaterialInstanceDescription(BaseAssetDescription):
    """Material Instance asset description."""

    asset_type: AssetType = AssetType.MATERIAL_INSTANCE

    parent_material: Optional[AssetReference] = None

    # Parameter overrides
    scalar_parameter_values: Dict[str, float] = Field(default_factory=dict)
    vector_parameter_values: Dict[str, Dict[str, float]] = Field(
        default_factory=dict
    )  # name -> {r,g,b,a}
    texture_parameter_values: Dict[str, Optional[str]] = Field(
        default_factory=dict
    )  # name -> asset path
    static_switch_parameter_values: Dict[str, bool] = Field(default_factory=dict)

    # Override parent flags
    override_subsurface_profile: bool = False


class AnimationDescription(BaseAssetDescription):
    """Animation asset description."""

    asset_type: AssetType = AssetType.ANIMATION

    skeleton: Optional[AssetReference] = None

    # Timing
    sequence_length: float = 0.0  # In seconds
    num_frames: int = 0
    frame_rate: float = 30.0
    rate_scale: float = 1.0

    # Animation data
    num_tracks: int = 0
    is_additive: bool = False
    additive_anim_type: Optional[
        Literal["NoAdditive", "LocalSpaceBase", "SkeletonRefPose", "MeshRefPose"]
    ] = None

    # Root motion
    enable_root_motion: bool = False
    root_motion_root_lock: Optional[Literal["RefPose", "AnimFirstFrame", "Zero"]] = None

    # Curves
    num_curves: int = 0
    curve_names: List[str] = Field(default_factory=list)

    # Notifies
    num_notifies: int = 0
    notify_names: List[str] = Field(default_factory=list)

    # Sync markers
    sync_markers: List[str] = Field(default_factory=list)


class AnimationBlueprintDescription(BaseAssetDescription):
    """Animation Blueprint asset description."""

    asset_type: AssetType = AssetType.ANIMATION_BLUEPRINT

    target_skeleton: Optional[AssetReference] = None
    parent_class: str = "AnimInstance"

    # State machines
    state_machine_names: List[str] = Field(default_factory=list)

    # Variables (animation-specific)
    animation_variables: List[str] = Field(default_factory=list)


class SoundDescription(BaseAssetDescription):
    """Sound asset description."""

    asset_type: AssetType = AssetType.SOUND

    # Audio info
    duration: float = 0.0  # In seconds
    sample_rate: int = 44100
    num_channels: int = 2

    # Format
    compression_type: str = "None"
    is_streaming: bool = False

    # Sound class
    sound_class: Optional[AssetReference] = None
    attenuation_settings: Optional[AssetReference] = None
    concurrency_settings: Optional[AssetReference] = None

    # Looping
    is_looping: bool = False

    # Volume
    volume: float = 1.0
    pitch: float = 1.0


class ParticleSystemDescription(BaseAssetDescription):
    """Particle System (Niagara or Cascade) description."""

    asset_type: AssetType = AssetType.PARTICLE_SYSTEM

    # System type
    system_type: Literal["Niagara", "Cascade"] = "Niagara"

    # Emitters
    num_emitters: int = 0
    emitter_names: List[str] = Field(default_factory=list)

    # Bounds
    fixed_bounds: Optional[Box] = None
    use_fixed_bounds: bool = False

    # Warmup
    warmup_time: float = 0.0


class WidgetBlueprintDescription(BaseAssetDescription):
    """Widget Blueprint (UMG) description."""

    asset_type: AssetType = AssetType.WIDGET_BLUEPRINT

    # Root widget
    root_widget_class: str = "UserWidget"

    # Design size
    design_size_width: float = 1920.0
    design_size_height: float = 1080.0

    # Named slots
    named_slots: List[str] = Field(default_factory=list)

    # Animations
    animations: List[str] = Field(default_factory=list)


class PhysicsAssetDescription(BaseAssetDescription):
    """Physics Asset description."""

    asset_type: AssetType = AssetType.PHYSICS_ASSET

    skeleton: Optional[AssetReference] = None

    # Bodies
    num_bodies: int = 0
    body_names: List[str] = Field(default_factory=list)

    # Constraints
    num_constraints: int = 0
    constraint_names: List[str] = Field(default_factory=list)


class DataAssetDescription(BaseAssetDescription):
    """Generic Data Asset description."""

    asset_type: AssetType = AssetType.DATA_ASSET

    # The actual data class
    data_class: str = "DataAsset"

    # Row struct (for DataTables)
    row_struct: Optional[str] = None
    num_rows: int = 0

    # All properties as key-value pairs
    data: Dict[str, Any] = Field(default_factory=dict)


# Mapping from UE5 asset class names to model classes
ASSET_CLASS_MAP: Dict[str, type] = {
    "StaticMesh": StaticMeshDescription,
    "SkeletalMesh": SkeletalMeshDescription,
    "Skeleton": SkeletonDescription,
    "Texture": TextureDescription,
    "Texture2D": TextureDescription,
    "TextureCube": TextureDescription,
    "TextureRenderTarget2D": TextureDescription,
    "Material": MaterialDescription,
    "MaterialFunction": MaterialDescription,
    "MaterialInstanceConstant": MaterialInstanceDescription,
    "MaterialInstanceDynamic": MaterialInstanceDescription,
    "AnimSequence": AnimationDescription,
    "AnimMontage": AnimationDescription,
    "BlendSpace": AnimationDescription,
    "BlendSpace1D": AnimationDescription,
    "AnimBlueprint": AnimationBlueprintDescription,
    "SoundWave": SoundDescription,
    "SoundCue": SoundDescription,
    "ParticleSystem": ParticleSystemDescription,
    "NiagaraSystem": ParticleSystemDescription,
    "NiagaraEmitter": ParticleSystemDescription,
    "WidgetBlueprint": WidgetBlueprintDescription,
    "PhysicsAsset": PhysicsAssetDescription,
    "DataAsset": DataAssetDescription,
    "DataTable": DataAssetDescription,
    "CurveTable": DataAssetDescription,
}


def asset_from_dict(data: Dict[str, Any]) -> BaseAssetDescription:
    """Create an asset description from a dictionary, using the appropriate model class."""
    asset_class = data.get("asset_class", "Unknown")
    asset_type = data.get("asset_type", AssetType.UNKNOWN)

    # Try to find by asset_class first
    model_class = ASSET_CLASS_MAP.get(asset_class)

    # If not found, try by asset_type
    if model_class is None:
        type_to_class = {
            AssetType.STATIC_MESH: StaticMeshDescription,
            AssetType.SKELETAL_MESH: SkeletalMeshDescription,
            AssetType.SKELETON: SkeletonDescription,
            AssetType.TEXTURE: TextureDescription,
            AssetType.MATERIAL: MaterialDescription,
            AssetType.MATERIAL_INSTANCE: MaterialInstanceDescription,
            AssetType.ANIMATION: AnimationDescription,
            AssetType.ANIMATION_BLUEPRINT: AnimationBlueprintDescription,
            AssetType.SOUND: SoundDescription,
            AssetType.PARTICLE_SYSTEM: ParticleSystemDescription,
            AssetType.WIDGET_BLUEPRINT: WidgetBlueprintDescription,
            AssetType.PHYSICS_ASSET: PhysicsAssetDescription,
            AssetType.DATA_ASSET: DataAssetDescription,
        }
        if isinstance(asset_type, str):
            asset_type = AssetType(asset_type)
        model_class = type_to_class.get(asset_type, BaseAssetDescription)

    return model_class.model_validate(data)
