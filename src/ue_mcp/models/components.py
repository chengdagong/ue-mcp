"""
UE5 Component description models.

Supports the component hierarchy pattern used in Blueprints and Actors.
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field

from .base import AssetReference, Transform, Vector3


class ComponentAttachment(BaseModel):
    """Describes how a component is attached to its parent."""

    parent_component: Optional[str] = Field(
        None, description="Name of parent component"
    )
    socket_name: Optional[str] = Field(
        None, description="Socket/bone name for attachment"
    )
    attachment_rule: Literal["KeepRelative", "KeepWorld", "SnapToTarget"] = (
        "KeepRelative"
    )


class ComponentBase(BaseModel):
    """Base model for all components."""

    name: str = Field(..., description="Component name (unique within blueprint)")
    component_class: str = Field(
        ..., description="UE5 component class e.g. StaticMeshComponent"
    )
    is_root: bool = Field(False, description="Whether this is the root component")
    attachment: Optional[ComponentAttachment] = None

    # Generic properties dict for any additional properties
    properties: Dict[str, Any] = Field(default_factory=dict)


class SceneComponent(ComponentBase):
    """A component with transform and hierarchy (mirrors USceneComponent)."""

    component_class: str = "SceneComponent"
    transform: Transform = Field(default_factory=Transform.identity)
    mobility: Literal["Static", "Stationary", "Movable"] = "Static"
    visible: bool = True
    hidden_in_game: bool = False


class PrimitiveComponent(SceneComponent):
    """Base for components with rendering/physics (mirrors UPrimitiveComponent)."""

    component_class: str = "PrimitiveComponent"
    collision_enabled: bool = True
    generate_overlap_events: bool = False
    cast_shadow: bool = True


class StaticMeshComponent(PrimitiveComponent):
    """Static mesh component (mirrors UStaticMeshComponent)."""

    component_class: str = "StaticMeshComponent"
    static_mesh: Optional[AssetReference] = None
    materials: List[AssetReference] = Field(default_factory=list)


class SkeletalMeshComponent(PrimitiveComponent):
    """Skeletal mesh component (mirrors USkeletalMeshComponent)."""

    component_class: str = "SkeletalMeshComponent"
    skeletal_mesh: Optional[AssetReference] = None
    anim_class: Optional[AssetReference] = None
    materials: List[AssetReference] = Field(default_factory=list)


class ShapeComponent(PrimitiveComponent):
    """Base for shape collision components (mirrors UShapeComponent)."""

    component_class: str = "ShapeComponent"
    shape_color: Optional[str] = None  # Hex color string


class CapsuleComponent(ShapeComponent):
    """Capsule collision component (mirrors UCapsuleComponent)."""

    component_class: str = "CapsuleComponent"
    capsule_radius: float = 42.0
    capsule_half_height: float = 96.0


class BoxComponent(ShapeComponent):
    """Box collision component (mirrors UBoxComponent)."""

    component_class: str = "BoxComponent"
    box_extent: Vector3 = Field(
        default_factory=lambda: Vector3(x=32.0, y=32.0, z=32.0)
    )


class SphereComponent(ShapeComponent):
    """Sphere collision component (mirrors USphereComponent)."""

    component_class: str = "SphereComponent"
    sphere_radius: float = 32.0


class CameraComponent(SceneComponent):
    """Camera component (mirrors UCameraComponent)."""

    component_class: str = "CameraComponent"
    field_of_view: float = 90.0
    aspect_ratio: float = 1.777778
    constrain_aspect_ratio: bool = False
    use_pawn_control_rotation: bool = False
    post_process_blend_weight: float = 1.0


class SpringArmComponent(SceneComponent):
    """Spring arm for cameras (mirrors USpringArmComponent)."""

    component_class: str = "SpringArmComponent"
    target_arm_length: float = 300.0
    socket_offset: Vector3 = Field(default_factory=Vector3.zero)
    target_offset: Vector3 = Field(default_factory=Vector3.zero)
    use_pawn_control_rotation: bool = True
    inherit_pitch: bool = True
    inherit_yaw: bool = True
    inherit_roll: bool = True
    do_collision_test: bool = True
    probe_size: float = 12.0
    probe_channel: str = "Camera"
    enable_camera_lag: bool = False
    camera_lag_speed: float = 10.0
    enable_camera_rotation_lag: bool = False
    camera_rotation_lag_speed: float = 10.0


class CharacterMovementComponent(ComponentBase):
    """Character movement component (mirrors UCharacterMovementComponent)."""

    component_class: str = "CharacterMovementComponent"

    # Walking
    max_walk_speed: float = 600.0
    max_walk_speed_crouched: float = 300.0
    max_acceleration: float = 2048.0
    braking_deceleration_walking: float = 2048.0
    ground_friction: float = 8.0

    # Jumping
    jump_z_velocity: float = 420.0
    air_control: float = 0.2
    air_control_boost_multiplier: float = 2.0
    air_control_boost_velocity_threshold: float = 25.0

    # Flying
    max_fly_speed: float = 600.0
    braking_deceleration_flying: float = 0.0

    # Swimming
    max_swim_speed: float = 300.0
    braking_deceleration_swimming: float = 0.0

    # Physics
    gravity_scale: float = 1.0
    default_land_movement_mode: Literal["Walking", "NavWalking", "Falling", "Swimming", "Flying", "Custom"] = "Walking"
    default_water_movement_mode: Literal["Walking", "NavWalking", "Falling", "Swimming", "Flying", "Custom"] = "Swimming"

    # Step
    max_step_height: float = 45.0
    walkable_floor_angle: float = 44.765846
    walkable_floor_z: float = 0.71


class ProjectileMovementComponent(ComponentBase):
    """Projectile movement component (mirrors UProjectileMovementComponent)."""

    component_class: str = "ProjectileMovementComponent"
    initial_speed: float = 3000.0
    max_speed: float = 3000.0
    should_bounce: bool = False
    bounciness: float = 0.6
    friction: float = 0.2
    gravity_scale: float = 1.0
    homing_acceleration_magnitude: float = 0.0


class WidgetComponent(SceneComponent):
    """Widget component for 3D UI (mirrors UWidgetComponent)."""

    component_class: str = "WidgetComponent"
    widget_class: Optional[AssetReference] = None
    draw_size: Vector3 = Field(
        default_factory=lambda: Vector3(x=500.0, y=500.0, z=1.0)
    )
    space: Literal["World", "Screen"] = "World"
    draw_at_desired_size: bool = False
    pivot: Vector3 = Field(default_factory=lambda: Vector3(x=0.5, y=0.5, z=0.0))


class AudioComponent(SceneComponent):
    """Audio component (mirrors UAudioComponent)."""

    component_class: str = "AudioComponent"
    sound: Optional[AssetReference] = None
    volume_multiplier: float = 1.0
    pitch_multiplier: float = 1.0
    auto_activate: bool = True
    is_ui_sound: bool = False


class PointLightComponent(SceneComponent):
    """Point light component (mirrors UPointLightComponent)."""

    component_class: str = "PointLightComponent"
    intensity: float = 5000.0
    attenuation_radius: float = 1000.0
    source_radius: float = 0.0
    soft_source_radius: float = 0.0
    light_color: str = "#FFFFFFFF"  # Hex RGBA
    cast_shadows: bool = True


class SpotLightComponent(SceneComponent):
    """Spot light component (mirrors USpotLightComponent)."""

    component_class: str = "SpotLightComponent"
    intensity: float = 5000.0
    attenuation_radius: float = 1000.0
    inner_cone_angle: float = 0.0
    outer_cone_angle: float = 44.0
    source_radius: float = 0.0
    light_color: str = "#FFFFFFFF"  # Hex RGBA
    cast_shadows: bool = True


class DirectionalLightComponent(SceneComponent):
    """Directional light component (mirrors UDirectionalLightComponent)."""

    component_class: str = "DirectionalLightComponent"
    intensity: float = 3.14159
    light_source_angle: float = 0.5357
    light_color: str = "#FFFFFFFF"  # Hex RGBA
    cast_shadows: bool = True
    dynamic_shadow_distance_movable_light: float = 20000.0


class ArrowComponent(SceneComponent):
    """Arrow component for visualization (mirrors UArrowComponent)."""

    component_class: str = "ArrowComponent"
    arrow_color: str = "#FF0000FF"  # Hex RGBA (red by default)
    arrow_size: float = 1.0
    is_screen_size_scaled: bool = False


class BillboardComponent(SceneComponent):
    """Billboard/sprite component (mirrors UBillboardComponent)."""

    component_class: str = "BillboardComponent"
    sprite: Optional[AssetReference] = None
    is_screen_size_scaled: bool = False
    screen_size: float = 0.0025


class TextRenderComponent(SceneComponent):
    """3D text render component (mirrors UTextRenderComponent)."""

    component_class: str = "TextRenderComponent"
    text: str = ""
    text_render_color: str = "#FFFFFFFF"  # Hex RGBA
    world_size: float = 12.0
    horizontal_alignment: Literal["Left", "Center", "Right"] = "Center"
    vertical_alignment: Literal["Top", "Center", "Bottom", "QuadTop"] = "Center"


class ChildActorComponent(SceneComponent):
    """Child actor component (mirrors UChildActorComponent)."""

    component_class: str = "ChildActorComponent"
    child_actor_class: Optional[AssetReference] = None


class ParticleSystemComponent(SceneComponent):
    """Particle system component - Cascade (mirrors UParticleSystemComponent)."""

    component_class: str = "ParticleSystemComponent"
    template: Optional[AssetReference] = None
    auto_activate: bool = True


class NiagaraComponent(SceneComponent):
    """Niagara particle component (mirrors UNiagaraComponent)."""

    component_class: str = "NiagaraComponent"
    asset: Optional[AssetReference] = None
    auto_activate: bool = True


# Type alias for any component
AnyComponent = Union[
    ComponentBase,
    SceneComponent,
    PrimitiveComponent,
    StaticMeshComponent,
    SkeletalMeshComponent,
    ShapeComponent,
    CapsuleComponent,
    BoxComponent,
    SphereComponent,
    CameraComponent,
    SpringArmComponent,
    CharacterMovementComponent,
    ProjectileMovementComponent,
    WidgetComponent,
    AudioComponent,
    PointLightComponent,
    SpotLightComponent,
    DirectionalLightComponent,
    ArrowComponent,
    BillboardComponent,
    TextRenderComponent,
    ChildActorComponent,
    ParticleSystemComponent,
    NiagaraComponent,
]


class ComponentHierarchy(BaseModel):
    """Complete component hierarchy for a Blueprint or Actor."""

    root_component: str = Field(..., description="Name of the root component")
    components: List[AnyComponent] = Field(default_factory=list)

    def get_component(self, name: str) -> Optional[AnyComponent]:
        """Get a component by name."""
        for comp in self.components:
            if comp.name == name:
                return comp
        return None

    def get_children(self, parent_name: str) -> List[AnyComponent]:
        """Get all direct children of a component."""
        return [
            c
            for c in self.components
            if c.attachment and c.attachment.parent_component == parent_name
        ]

    def get_root(self) -> Optional[AnyComponent]:
        """Get the root component."""
        return self.get_component(self.root_component)

    def add_component(self, component: AnyComponent) -> None:
        """Add a component to the hierarchy."""
        self.components.append(component)


# Mapping from UE5 class names to model classes
COMPONENT_CLASS_MAP: Dict[str, type] = {
    "SceneComponent": SceneComponent,
    "PrimitiveComponent": PrimitiveComponent,
    "StaticMeshComponent": StaticMeshComponent,
    "SkeletalMeshComponent": SkeletalMeshComponent,
    "ShapeComponent": ShapeComponent,
    "CapsuleComponent": CapsuleComponent,
    "BoxComponent": BoxComponent,
    "SphereComponent": SphereComponent,
    "CameraComponent": CameraComponent,
    "SpringArmComponent": SpringArmComponent,
    "CharacterMovementComponent": CharacterMovementComponent,
    "ProjectileMovementComponent": ProjectileMovementComponent,
    "WidgetComponent": WidgetComponent,
    "AudioComponent": AudioComponent,
    "PointLightComponent": PointLightComponent,
    "SpotLightComponent": SpotLightComponent,
    "DirectionalLightComponent": DirectionalLightComponent,
    "ArrowComponent": ArrowComponent,
    "BillboardComponent": BillboardComponent,
    "TextRenderComponent": TextRenderComponent,
    "ChildActorComponent": ChildActorComponent,
    "ParticleSystemComponent": ParticleSystemComponent,
    "NiagaraComponent": NiagaraComponent,
}


def component_from_dict(data: Dict[str, Any]) -> AnyComponent:
    """Create a component from a dictionary, using the appropriate model class."""
    component_class = data.get("component_class", "ComponentBase")
    model_class = COMPONENT_CLASS_MAP.get(component_class, ComponentBase)
    return model_class.model_validate(data)
