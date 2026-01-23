"""
UE5 fundamental data types as Pydantic models.

These types mirror Unreal Engine's core math and color types,
providing bidirectional conversion between Python dicts and UE5 values.
"""

from __future__ import annotations

from typing import Annotated, Any, Optional

from pydantic import BaseModel, Field, field_validator


class Vector2D(BaseModel):
    """2D Vector (mirrors unreal.Vector2D)."""

    x: float = 0.0
    y: float = 0.0

    model_config = {"frozen": True}

    @classmethod
    def from_ue(cls, ue_vector: Any) -> Vector2D:
        """Create from unreal.Vector2D."""
        return cls(x=float(ue_vector.x), y=float(ue_vector.y))

    @classmethod
    def zero(cls) -> Vector2D:
        """Return a zero vector."""
        return cls(x=0.0, y=0.0)

    @classmethod
    def one(cls) -> Vector2D:
        """Return a unit vector (1, 1)."""
        return cls(x=1.0, y=1.0)


class Vector3(BaseModel):
    """3D Vector (mirrors unreal.Vector).

    UE5 Coordinate System:
    - X: Forward/Back direction
    - Y: Left/Right direction
    - Z: Up/Down direction
    """

    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

    model_config = {"frozen": True}

    @classmethod
    def from_ue(cls, ue_vector: Any) -> Vector3:
        """Create from unreal.Vector."""
        return cls(
            x=float(ue_vector.x),
            y=float(ue_vector.y),
            z=float(ue_vector.z),
        )

    @classmethod
    def zero(cls) -> Vector3:
        """Return a zero vector."""
        return cls(x=0.0, y=0.0, z=0.0)

    @classmethod
    def one(cls) -> Vector3:
        """Return a unit vector (1, 1, 1)."""
        return cls(x=1.0, y=1.0, z=1.0)

    @classmethod
    def forward(cls) -> Vector3:
        """Return the forward direction (+X)."""
        return cls(x=1.0, y=0.0, z=0.0)

    @classmethod
    def right(cls) -> Vector3:
        """Return the right direction (+Y)."""
        return cls(x=0.0, y=1.0, z=0.0)

    @classmethod
    def up(cls) -> Vector3:
        """Return the up direction (+Z)."""
        return cls(x=0.0, y=0.0, z=1.0)


class Vector4(BaseModel):
    """4D Vector (mirrors unreal.Vector4)."""

    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    w: float = 1.0

    model_config = {"frozen": True}

    @classmethod
    def from_ue(cls, ue_vector: Any) -> Vector4:
        """Create from unreal.Vector4."""
        return cls(
            x=float(ue_vector.x),
            y=float(ue_vector.y),
            z=float(ue_vector.z),
            w=float(ue_vector.w),
        )


class Rotator(BaseModel):
    """Euler rotation (mirrors unreal.Rotator).

    Angles in degrees:
    - pitch: Rotation around Y axis (up/down tilt)
    - yaw: Rotation around Z axis (left/right turn)
    - roll: Rotation around X axis (banking)
    """

    pitch: float = 0.0
    yaw: float = 0.0
    roll: float = 0.0

    model_config = {"frozen": True}

    @classmethod
    def from_ue(cls, ue_rotator: Any) -> Rotator:
        """Create from unreal.Rotator."""
        return cls(
            pitch=float(ue_rotator.pitch),
            yaw=float(ue_rotator.yaw),
            roll=float(ue_rotator.roll),
        )

    @classmethod
    def zero(cls) -> Rotator:
        """Return a zero rotation."""
        return cls(pitch=0.0, yaw=0.0, roll=0.0)


class Quat(BaseModel):
    """Quaternion rotation (mirrors unreal.Quat)."""

    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    w: float = 1.0

    model_config = {"frozen": True}

    @classmethod
    def from_ue(cls, ue_quat: Any) -> Quat:
        """Create from unreal.Quat."""
        return cls(
            x=float(ue_quat.x),
            y=float(ue_quat.y),
            z=float(ue_quat.z),
            w=float(ue_quat.w),
        )

    @classmethod
    def identity(cls) -> Quat:
        """Return the identity quaternion (no rotation)."""
        return cls(x=0.0, y=0.0, z=0.0, w=1.0)


class Transform(BaseModel):
    """Complete transformation (mirrors unreal.Transform)."""

    translation: Vector3 = Field(default_factory=Vector3.zero)
    rotation: Rotator = Field(default_factory=Rotator.zero)
    scale3d: Vector3 = Field(default_factory=Vector3.one)

    model_config = {"frozen": True}

    @classmethod
    def from_ue(cls, ue_transform: Any) -> Transform:
        """Create from unreal.Transform."""
        return cls(
            translation=Vector3.from_ue(ue_transform.translation),
            rotation=Rotator.from_ue(ue_transform.rotation),
            scale3d=Vector3.from_ue(ue_transform.scale3d),
        )

    @classmethod
    def identity(cls) -> Transform:
        """Return the identity transform."""
        return cls()


class Color(BaseModel):
    """RGBA Color (mirrors unreal.Color, 0-255 integers)."""

    r: Annotated[int, Field(ge=0, le=255)] = 255
    g: Annotated[int, Field(ge=0, le=255)] = 255
    b: Annotated[int, Field(ge=0, le=255)] = 255
    a: Annotated[int, Field(ge=0, le=255)] = 255

    model_config = {"frozen": True}

    @classmethod
    def from_ue(cls, ue_color: Any) -> Color:
        """Create from unreal.Color."""
        return cls(
            r=int(ue_color.r),
            g=int(ue_color.g),
            b=int(ue_color.b),
            a=int(ue_color.a),
        )

    @classmethod
    def white(cls) -> Color:
        """Return white color."""
        return cls(r=255, g=255, b=255, a=255)

    @classmethod
    def black(cls) -> Color:
        """Return black color."""
        return cls(r=0, g=0, b=0, a=255)

    @classmethod
    def transparent(cls) -> Color:
        """Return transparent color."""
        return cls(r=0, g=0, b=0, a=0)


class LinearColor(BaseModel):
    """Linear RGBA Color (mirrors unreal.LinearColor, 0.0-1.0 floats)."""

    r: float = 1.0
    g: float = 1.0
    b: float = 1.0
    a: float = 1.0

    model_config = {"frozen": True}

    @classmethod
    def from_ue(cls, ue_color: Any) -> LinearColor:
        """Create from unreal.LinearColor."""
        return cls(
            r=float(ue_color.r),
            g=float(ue_color.g),
            b=float(ue_color.b),
            a=float(ue_color.a),
        )

    @classmethod
    def white(cls) -> LinearColor:
        """Return white color."""
        return cls(r=1.0, g=1.0, b=1.0, a=1.0)

    @classmethod
    def black(cls) -> LinearColor:
        """Return black color."""
        return cls(r=0.0, g=0.0, b=0.0, a=1.0)


class Box(BaseModel):
    """Axis-aligned bounding box (mirrors unreal.Box)."""

    min: Vector3 = Field(default_factory=Vector3.zero)
    max: Vector3 = Field(default_factory=Vector3.zero)

    model_config = {"frozen": True}

    @classmethod
    def from_ue(cls, ue_box: Any) -> Box:
        """Create from unreal.Box."""
        return cls(
            min=Vector3.from_ue(ue_box.min),
            max=Vector3.from_ue(ue_box.max),
        )

    @classmethod
    def from_origin_extent(cls, origin: Vector3, extent: Vector3) -> Box:
        """Create from origin and extent (half-size)."""
        return cls(
            min=Vector3(
                x=origin.x - extent.x,
                y=origin.y - extent.y,
                z=origin.z - extent.z,
            ),
            max=Vector3(
                x=origin.x + extent.x,
                y=origin.y + extent.y,
                z=origin.z + extent.z,
            ),
        )


class AssetReference(BaseModel):
    """Reference to another UE5 asset."""

    path: str = Field(..., description="Asset path e.g. /Game/Meshes/SM_Cube")
    asset_class: Optional[str] = Field(
        None, description="Asset class name e.g. StaticMesh"
    )

    model_config = {"frozen": True}

    @field_validator("path")
    @classmethod
    def validate_path(cls, v: str) -> str:
        """Validate that the path starts with /."""
        if not v.startswith("/"):
            raise ValueError("Asset path must start with /")
        return v

    @classmethod
    def from_path(cls, path: str, asset_class: Optional[str] = None) -> AssetReference:
        """Create from path string."""
        return cls(path=path, asset_class=asset_class)
