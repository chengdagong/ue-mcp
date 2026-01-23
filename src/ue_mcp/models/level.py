"""
UE5 Level/World description models.

Describes level structure including actors, scene settings, and world composition.
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field

from .base import AssetReference, Box, LinearColor, Rotator, Transform, Vector3


class ActorDescription(BaseModel):
    """Description of an actor placed in a level."""

    # Identity
    label: str = Field(..., description="Actor label (display name in editor)")
    name: Optional[str] = Field(None, description="Actor object name (internal)")
    actor_class: str = Field(..., description="Actor class name")

    # For Blueprint actors
    blueprint_path: Optional[str] = Field(
        None, description="Blueprint asset path if this is a BP instance"
    )

    # Transform
    transform: Transform = Field(default_factory=Transform.identity)

    # Bounds
    bounds_origin: Optional[Vector3] = None
    bounds_extent: Optional[Vector3] = None

    # Hierarchy
    parent_actor: Optional[str] = Field(
        None, description="Parent actor label if attached"
    )
    attached_actors: List[str] = Field(default_factory=list)

    # Properties
    mobility: Literal["Static", "Stationary", "Movable"] = "Static"
    hidden: bool = False
    actor_hidden_in_game: bool = False
    can_be_damaged: bool = True

    # Organization
    tags: List[str] = Field(default_factory=list)
    layers: List[str] = Field(default_factory=list)
    folder_path: Optional[str] = Field(
        None, description="Editor folder path e.g. 'Props/Interior'"
    )

    # Additional properties
    properties: Dict[str, Any] = Field(default_factory=dict)


class StaticMeshActorDescription(ActorDescription):
    """Static mesh actor in a level."""

    actor_class: str = "StaticMeshActor"
    static_mesh: Optional[AssetReference] = None
    materials: List[AssetReference] = Field(default_factory=list)

    # Mesh properties
    cast_shadow: bool = True
    nanite_enabled: bool = False


class SkeletalMeshActorDescription(ActorDescription):
    """Skeletal mesh actor in a level."""

    actor_class: str = "SkeletalMeshActor"
    skeletal_mesh: Optional[AssetReference] = None
    anim_blueprint: Optional[AssetReference] = None
    materials: List[AssetReference] = Field(default_factory=list)


class LightActorDescription(ActorDescription):
    """Light actor base."""

    intensity: float = 1.0
    light_color: LinearColor = Field(default_factory=LinearColor.white)
    cast_shadows: bool = True
    affects_world: bool = True
    use_temperature: bool = False
    temperature: float = 6500.0


class DirectionalLightDescription(LightActorDescription):
    """Directional light (sun)."""

    actor_class: str = "DirectionalLight"
    light_source_angle: float = 0.5357
    light_source_soft_angle: float = 0.0
    atmosphere_sun_light: bool = True
    atmosphere_sun_light_index: int = 0

    # Cascade shadow maps
    dynamic_shadow_distance_movable_light: float = 20000.0
    dynamic_shadow_cascade_count: int = 3


class PointLightDescription(LightActorDescription):
    """Point light."""

    actor_class: str = "PointLight"
    attenuation_radius: float = 1000.0
    source_radius: float = 0.0
    soft_source_radius: float = 0.0
    source_length: float = 0.0
    use_inverse_squared_falloff: bool = True


class SpotLightDescription(LightActorDescription):
    """Spot light."""

    actor_class: str = "SpotLight"
    inner_cone_angle: float = 0.0
    outer_cone_angle: float = 44.0
    attenuation_radius: float = 1000.0
    source_radius: float = 0.0
    soft_source_radius: float = 0.0


class RectLightDescription(LightActorDescription):
    """Rectangular area light."""

    actor_class: str = "RectLight"
    source_width: float = 64.0
    source_height: float = 64.0
    barn_door_angle: float = 88.0
    barn_door_length: float = 20.0


class SkyLightDescription(LightActorDescription):
    """Sky light."""

    actor_class: str = "SkyLight"
    cubemap: Optional[AssetReference] = None
    source_type: Literal["CapturedScene", "SpecifiedCubemap"] = "CapturedScene"
    cubemap_resolution: int = 128
    sky_distance_threshold: float = 150000.0
    lower_hemisphere_is_solid_color: bool = True
    lower_hemisphere_color: LinearColor = Field(
        default_factory=lambda: LinearColor(r=0.0, g=0.0, b=0.0, a=1.0)
    )


class PlayerStartDescription(ActorDescription):
    """Player start location."""

    actor_class: str = "PlayerStart"
    player_start_tag: Optional[str] = None


class CameraActorDescription(ActorDescription):
    """Camera actor."""

    actor_class: str = "CameraActor"
    field_of_view: float = 90.0
    aspect_ratio: float = 1.777778
    constrain_aspect_ratio: bool = False


class VolumeDescription(ActorDescription):
    """Volume actor base."""

    brush_type: Literal["Additive", "Subtractive"] = "Additive"


class BlockingVolumeDescription(VolumeDescription):
    """Blocking volume for collision."""

    actor_class: str = "BlockingVolume"


class TriggerVolumeDescription(VolumeDescription):
    """Trigger volume."""

    actor_class: str = "TriggerVolume"


class KillZVolumeDescription(VolumeDescription):
    """Kill Z volume."""

    actor_class: str = "KillZVolume"


class PainCausingVolumeDescription(VolumeDescription):
    """Pain causing volume."""

    actor_class: str = "PainCausingVolume"
    damage_per_sec: float = 10.0
    damage_type: Optional[str] = None


class PhysicsVolumeDescription(VolumeDescription):
    """Physics volume."""

    actor_class: str = "PhysicsVolume"
    priority: int = 0
    fluid_friction: float = 0.3
    terminal_velocity: float = 4000.0
    water_volume: bool = False


class PostProcessVolumeDescription(VolumeDescription):
    """Post process volume."""

    actor_class: str = "PostProcessVolume"
    infinite_extent: bool = False
    blend_weight: float = 1.0
    blend_radius: float = 100.0
    priority: float = 0.0

    # Common post process settings (simplified)
    auto_exposure_enabled: bool = True
    bloom_enabled: bool = True
    ambient_occlusion_enabled: bool = True
    motion_blur_enabled: bool = True


class AudioVolumeDescription(VolumeDescription):
    """Audio volume."""

    actor_class: str = "AudioVolume"
    priority: float = 0.0
    reverb_settings: Optional[AssetReference] = None
    ambient_zone_settings: Optional[Dict[str, Any]] = None


class LevelSequenceActorDescription(ActorDescription):
    """Level sequence (cinematic) actor."""

    actor_class: str = "LevelSequenceActor"
    level_sequence: Optional[AssetReference] = None
    auto_play: bool = False
    loop_count: int = 0  # 0 = infinite


class DecalActorDescription(ActorDescription):
    """Decal actor."""

    actor_class: str = "DecalActor"
    decal_material: Optional[AssetReference] = None
    decal_size: Vector3 = Field(
        default_factory=lambda: Vector3(x=128.0, y=256.0, z=256.0)
    )
    sort_order: int = 0


class ReflectionCaptureDescription(ActorDescription):
    """Reflection capture base."""

    capture_offset: Vector3 = Field(default_factory=Vector3.zero)
    brightness: float = 1.0


class SphereReflectionCaptureDescription(ReflectionCaptureDescription):
    """Sphere reflection capture."""

    actor_class: str = "SphereReflectionCapture"
    influence_radius: float = 3000.0


class BoxReflectionCaptureDescription(ReflectionCaptureDescription):
    """Box reflection capture."""

    actor_class: str = "BoxReflectionCapture"
    box_transition_distance: float = 100.0


class ExponentialHeightFogDescription(ActorDescription):
    """Exponential height fog actor."""

    actor_class: str = "ExponentialHeightFog"
    fog_density: float = 0.02
    fog_height_falloff: float = 0.2
    fog_inscattering_color: LinearColor = Field(default_factory=LinearColor.white)
    fog_max_opacity: float = 1.0
    start_distance: float = 0.0
    fog_cutoff_distance: float = 0.0

    # Second fog
    second_fog_density: float = 0.0
    second_fog_height_falloff: float = 0.2
    second_fog_height_offset: float = 0.0

    # Volumetric fog
    volumetric_fog: bool = False
    volumetric_fog_scattering_distribution: float = 0.2
    volumetric_fog_albedo: LinearColor = Field(default_factory=LinearColor.white)
    volumetric_fog_extinction_scale: float = 1.0
    volumetric_fog_distance: float = 6000.0


class SkyAtmosphereDescription(ActorDescription):
    """Sky atmosphere actor."""

    actor_class: str = "SkyAtmosphere"
    ground_radius: float = 6360.0
    atmosphere_height: float = 100.0
    transform_mode: Literal["PlanetTopAtAbsoluteWorldOrigin", "PlanetCenterAtComponentTransform"] = "PlanetTopAtAbsoluteWorldOrigin"

    # Rayleigh scattering
    rayleigh_scattering_scale: float = 1.0
    rayleigh_exponential_distribution: float = 8.0

    # Mie scattering
    mie_scattering_scale: float = 1.0
    mie_absorption_scale: float = 1.0
    mie_anisotropy: float = 0.8
    mie_exponential_distribution: float = 1.2


class VolumetricCloudDescription(ActorDescription):
    """Volumetric cloud actor."""

    actor_class: str = "VolumetricCloud"
    layer_bottom_altitude: float = 5.0
    layer_height: float = 10.0
    tracing_start_max_distance: float = 350.0
    tracing_max_distance: float = 50.0
    planet_radius: float = 6360.0


class WorldSettings(BaseModel):
    """Level world settings."""

    game_mode_override: Optional[AssetReference] = None
    default_game_mode: Optional[str] = None
    kill_z: float = -100000.0

    # Physics
    world_gravity_z: float = -980.0
    global_gravity_z: float = -980.0

    # World origin
    enable_world_origin_rebasing: bool = False
    enable_large_worlds: bool = True

    # Streaming
    enable_world_composition: bool = False
    enable_world_partition: bool = False


class LevelBounds(BaseModel):
    """Level boundary information."""

    min: Vector3 = Field(default_factory=Vector3.zero)
    max: Vector3 = Field(default_factory=Vector3.zero)
    is_valid: bool = True


# Type alias for any actor description
AnyActorDescription = Union[
    ActorDescription,
    StaticMeshActorDescription,
    SkeletalMeshActorDescription,
    LightActorDescription,
    DirectionalLightDescription,
    PointLightDescription,
    SpotLightDescription,
    RectLightDescription,
    SkyLightDescription,
    PlayerStartDescription,
    CameraActorDescription,
    VolumeDescription,
    BlockingVolumeDescription,
    TriggerVolumeDescription,
    KillZVolumeDescription,
    PainCausingVolumeDescription,
    PhysicsVolumeDescription,
    PostProcessVolumeDescription,
    AudioVolumeDescription,
    LevelSequenceActorDescription,
    DecalActorDescription,
    ReflectionCaptureDescription,
    SphereReflectionCaptureDescription,
    BoxReflectionCaptureDescription,
    ExponentialHeightFogDescription,
    SkyAtmosphereDescription,
    VolumetricCloudDescription,
]


class LevelDescription(BaseModel):
    """Complete description of a UE5 Level/Map.

    This model describes the level structure including:
    - All actors with their transforms and properties
    - World settings
    - Lighting setup
    - Post processing
    """

    # Asset identification
    asset_path: str = Field(
        ..., description="Level asset path e.g. /Game/Maps/MainLevel"
    )
    asset_name: str

    # Level bounds
    level_bounds: Optional[LevelBounds] = None

    # World settings
    world_settings: WorldSettings = Field(default_factory=WorldSettings)

    # All actors
    actors: List[AnyActorDescription] = Field(default_factory=list)

    # Streaming levels
    streaming_levels: List[str] = Field(
        default_factory=list, description="Paths to streaming sub-levels"
    )

    # Level instances (World Partition)
    level_instances: List[str] = Field(
        default_factory=list, description="Paths to level instances"
    )

    # Statistics
    total_actor_count: int = 0

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "asset_path": "/Game/Maps/TestLevel",
                    "asset_name": "TestLevel",
                    "actors": [
                        {
                            "label": "Floor",
                            "actor_class": "StaticMeshActor",
                            "transform": {
                                "translation": {"x": 0, "y": 0, "z": 0},
                                "rotation": {"pitch": 0, "yaw": 0, "roll": 0},
                                "scale3d": {"x": 1, "y": 1, "z": 1},
                            },
                        }
                    ],
                }
            ]
        }
    }

    def get_actor(self, label: str) -> Optional[AnyActorDescription]:
        """Get an actor by label."""
        for actor in self.actors:
            if actor.label == label:
                return actor
        return None

    def get_actors_by_class(self, actor_class: str) -> List[AnyActorDescription]:
        """Get all actors of a specific class."""
        return [a for a in self.actors if a.actor_class == actor_class]

    def get_actors_in_folder(self, folder_path: str) -> List[AnyActorDescription]:
        """Get all actors in a specific editor folder."""
        return [
            a
            for a in self.actors
            if a.folder_path and a.folder_path.startswith(folder_path)
        ]

    def add_actor(self, actor: AnyActorDescription) -> None:
        """Add an actor to the level."""
        self.actors.append(actor)
        self.total_actor_count = len(self.actors)


# Mapping from UE5 actor class names to model classes
ACTOR_CLASS_MAP: Dict[str, type] = {
    "Actor": ActorDescription,
    "StaticMeshActor": StaticMeshActorDescription,
    "SkeletalMeshActor": SkeletalMeshActorDescription,
    "Light": LightActorDescription,
    "DirectionalLight": DirectionalLightDescription,
    "PointLight": PointLightDescription,
    "SpotLight": SpotLightDescription,
    "RectLight": RectLightDescription,
    "SkyLight": SkyLightDescription,
    "PlayerStart": PlayerStartDescription,
    "CameraActor": CameraActorDescription,
    "BlockingVolume": BlockingVolumeDescription,
    "TriggerVolume": TriggerVolumeDescription,
    "KillZVolume": KillZVolumeDescription,
    "PainCausingVolume": PainCausingVolumeDescription,
    "PhysicsVolume": PhysicsVolumeDescription,
    "PostProcessVolume": PostProcessVolumeDescription,
    "AudioVolume": AudioVolumeDescription,
    "LevelSequenceActor": LevelSequenceActorDescription,
    "DecalActor": DecalActorDescription,
    "SphereReflectionCapture": SphereReflectionCaptureDescription,
    "BoxReflectionCapture": BoxReflectionCaptureDescription,
    "ExponentialHeightFog": ExponentialHeightFogDescription,
    "SkyAtmosphere": SkyAtmosphereDescription,
    "VolumetricCloud": VolumetricCloudDescription,
}


def actor_from_dict(data: Dict[str, Any]) -> AnyActorDescription:
    """Create an actor from a dictionary, using the appropriate model class."""
    actor_class = data.get("actor_class", "Actor")
    model_class = ACTOR_CLASS_MAP.get(actor_class, ActorDescription)
    return model_class.model_validate(data)
