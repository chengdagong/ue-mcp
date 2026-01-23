"""
UE5 Asset Description Models

Pydantic v2 models for describing UE5 assets in a structured, type-safe way.

Supports:
- Serialization to JSON, YAML, and Python DSL
- Deserialization from JSON and YAML
- Full type validation and static type checking
- Integration with existing inspect_runner.py output

Example:
    from ue_mcp.models import (
        BlueprintDescription, ComponentHierarchy, StaticMeshComponent,
        BlueprintVariable, Vector3, Transform,
        serialize_to_json, serialize_to_yaml
    )

    # Create a blueprint description
    bp = BlueprintDescription(
        asset_path="/Game/Blueprints/BP_Character",
        asset_name="BP_Character",
        parent_class="Character",
        components=ComponentHierarchy(
            root_component="CapsuleComponent",
            components=[
                StaticMeshComponent(
                    name="Mesh",
                    transform=Transform(translation=Vector3(x=0, y=0, z=-90))
                )
            ]
        ),
        variables=[
            BlueprintVariable(name="Health", type="Float", default_value=100.0)
        ]
    )

    # Serialize to different formats
    json_str = serialize_to_json(bp)
    yaml_str = serialize_to_yaml(bp)
"""

# Base types
from .base import (
    AssetReference,
    Box,
    Color,
    LinearColor,
    Quat,
    Rotator,
    Transform,
    Vector2D,
    Vector3,
    Vector4,
)

# Components
from .components import (
    AnyComponent,
    ArrowComponent,
    AudioComponent,
    BillboardComponent,
    BoxComponent,
    CameraComponent,
    CapsuleComponent,
    CharacterMovementComponent,
    ChildActorComponent,
    COMPONENT_CLASS_MAP,
    ComponentAttachment,
    ComponentBase,
    ComponentHierarchy,
    DirectionalLightComponent,
    NiagaraComponent,
    ParticleSystemComponent,
    PointLightComponent,
    PrimitiveComponent,
    ProjectileMovementComponent,
    SceneComponent,
    ShapeComponent,
    SkeletalMeshComponent,
    SphereComponent,
    SpotLightComponent,
    SpringArmComponent,
    StaticMeshComponent,
    TextRenderComponent,
    WidgetComponent,
    component_from_dict,
)

# Blueprint
from .blueprint import (
    BlueprintDescription,
    BlueprintEventDispatcher,
    BlueprintFunction,
    BlueprintInterface,
    BlueprintVariable,
    FunctionParameter,
    VariableMetadata,
    VariableType,
)

# Level
from .level import (
    ACTOR_CLASS_MAP,
    ActorDescription,
    AnyActorDescription,
    AudioVolumeDescription,
    BlockingVolumeDescription,
    BoxReflectionCaptureDescription,
    CameraActorDescription,
    DecalActorDescription,
    DirectionalLightDescription,
    ExponentialHeightFogDescription,
    KillZVolumeDescription,
    LevelBounds,
    LevelDescription,
    LevelSequenceActorDescription,
    LightActorDescription,
    PainCausingVolumeDescription,
    PhysicsVolumeDescription,
    PlayerStartDescription,
    PointLightDescription,
    PostProcessVolumeDescription,
    RectLightDescription,
    ReflectionCaptureDescription,
    SkeletalMeshActorDescription,
    SkyAtmosphereDescription,
    SkyLightDescription,
    SphereReflectionCaptureDescription,
    SpotLightDescription,
    StaticMeshActorDescription,
    TriggerVolumeDescription,
    VolumeDescription,
    VolumetricCloudDescription,
    WorldSettings,
    actor_from_dict,
)

# Assets
from .assets import (
    ASSET_CLASS_MAP,
    AnimationBlueprintDescription,
    AnimationDescription,
    AssetMetadata,
    AssetReferences,
    AssetType,
    BaseAssetDescription,
    BoneInfo,
    DataAssetDescription,
    LODInfo,
    MaterialDescription,
    MaterialInstanceDescription,
    MaterialParameterInfo,
    MaterialSlot,
    ParticleSystemDescription,
    PhysicsAssetDescription,
    SkeletalMeshDescription,
    SkeletonDescription,
    SoundDescription,
    StaticMeshDescription,
    TextureDescription,
    WidgetBlueprintDescription,
    asset_from_dict,
)

# Descriptors
from .descriptors import (
    AnyAssetDescription,
    AssetDescriptorV1,
    BlueprintDesc,
    LevelDesc,
    MaterialDesc,
    MeshDesc,
)

# Serializers
from .serializers import (
    deserialize_from_json,
    deserialize_from_yaml,
    from_inspect_result,
    load_from_file,
    save_to_file,
    serialize_to_dict,
    serialize_to_json,
    serialize_to_python_dsl,
    serialize_to_yaml,
    wrap_with_version,
)

__all__ = [
    # Base types
    "Vector2D",
    "Vector3",
    "Vector4",
    "Rotator",
    "Quat",
    "Transform",
    "Color",
    "LinearColor",
    "Box",
    "AssetReference",
    # Components
    "ComponentBase",
    "ComponentAttachment",
    "ComponentHierarchy",
    "SceneComponent",
    "PrimitiveComponent",
    "StaticMeshComponent",
    "SkeletalMeshComponent",
    "ShapeComponent",
    "CapsuleComponent",
    "BoxComponent",
    "SphereComponent",
    "CameraComponent",
    "SpringArmComponent",
    "CharacterMovementComponent",
    "ProjectileMovementComponent",
    "WidgetComponent",
    "AudioComponent",
    "PointLightComponent",
    "SpotLightComponent",
    "DirectionalLightComponent",
    "ArrowComponent",
    "BillboardComponent",
    "TextRenderComponent",
    "ChildActorComponent",
    "ParticleSystemComponent",
    "NiagaraComponent",
    "AnyComponent",
    "COMPONENT_CLASS_MAP",
    "component_from_dict",
    # Blueprint
    "BlueprintDescription",
    "BlueprintVariable",
    "BlueprintFunction",
    "BlueprintEventDispatcher",
    "BlueprintInterface",
    "FunctionParameter",
    "VariableType",
    "VariableMetadata",
    # Level
    "LevelDescription",
    "LevelBounds",
    "WorldSettings",
    "ActorDescription",
    "StaticMeshActorDescription",
    "SkeletalMeshActorDescription",
    "LightActorDescription",
    "DirectionalLightDescription",
    "PointLightDescription",
    "SpotLightDescription",
    "RectLightDescription",
    "SkyLightDescription",
    "PlayerStartDescription",
    "CameraActorDescription",
    "VolumeDescription",
    "BlockingVolumeDescription",
    "TriggerVolumeDescription",
    "KillZVolumeDescription",
    "PainCausingVolumeDescription",
    "PhysicsVolumeDescription",
    "PostProcessVolumeDescription",
    "AudioVolumeDescription",
    "LevelSequenceActorDescription",
    "DecalActorDescription",
    "ReflectionCaptureDescription",
    "SphereReflectionCaptureDescription",
    "BoxReflectionCaptureDescription",
    "ExponentialHeightFogDescription",
    "SkyAtmosphereDescription",
    "VolumetricCloudDescription",
    "AnyActorDescription",
    "ACTOR_CLASS_MAP",
    "actor_from_dict",
    # Assets
    "AssetType",
    "AssetMetadata",
    "AssetReferences",
    "BaseAssetDescription",
    "LODInfo",
    "MaterialSlot",
    "BoneInfo",
    "StaticMeshDescription",
    "SkeletalMeshDescription",
    "SkeletonDescription",
    "TextureDescription",
    "MaterialDescription",
    "MaterialInstanceDescription",
    "MaterialParameterInfo",
    "AnimationDescription",
    "AnimationBlueprintDescription",
    "SoundDescription",
    "ParticleSystemDescription",
    "WidgetBlueprintDescription",
    "PhysicsAssetDescription",
    "DataAssetDescription",
    "ASSET_CLASS_MAP",
    "asset_from_dict",
    # Descriptors
    "AnyAssetDescription",
    "AssetDescriptorV1",
    "LevelDesc",
    "BlueprintDesc",
    "MeshDesc",
    "MaterialDesc",
    # Serializers
    "serialize_to_json",
    "serialize_to_dict",
    "serialize_to_yaml",
    "serialize_to_python_dsl",
    "deserialize_from_json",
    "deserialize_from_yaml",
    "load_from_file",
    "save_to_file",
    "wrap_with_version",
    "from_inspect_result",
]
