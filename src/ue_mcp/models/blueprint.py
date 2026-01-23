"""
UE5 Blueprint description models.

Supports Actor Blueprints, with component hierarchy, variables, and function signatures.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from .components import ComponentHierarchy


class VariableType(str, Enum):
    """Common UE5 variable types."""

    # Primitive types
    BOOL = "Boolean"
    BYTE = "Byte"
    INT = "Integer"
    INT64 = "Integer64"
    FLOAT = "Float"
    DOUBLE = "Double"

    # String types
    STRING = "String"
    NAME = "Name"
    TEXT = "Text"

    # Math types
    VECTOR = "Vector"
    VECTOR2D = "Vector2D"
    VECTOR4 = "Vector4"
    ROTATOR = "Rotator"
    QUAT = "Quat"
    TRANSFORM = "Transform"

    # Color types
    COLOR = "Color"
    LINEAR_COLOR = "LinearColor"

    # Reference types
    OBJECT = "Object"
    CLASS = "Class"
    SOFT_OBJECT = "SoftObjectReference"
    SOFT_CLASS = "SoftClassReference"
    INTERFACE = "Interface"

    # Container types
    STRUCT = "Struct"
    ENUM = "Enum"
    ARRAY = "Array"
    SET = "Set"
    MAP = "Map"


class VariableMetadata(BaseModel):
    """Metadata for a Blueprint variable."""

    category: Optional[str] = Field(None, description="Category for organization in editor")
    tooltip: Optional[str] = Field(None, description="Tooltip shown in editor")
    display_name: Optional[str] = Field(None, description="Friendly display name")

    # Numeric constraints
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    slider_min: Optional[float] = None
    slider_max: Optional[float] = None

    # Clamp settings
    clamp_min: Optional[float] = None
    clamp_max: Optional[float] = None
    ui_min: Optional[float] = None
    ui_max: Optional[float] = None


class BlueprintVariable(BaseModel):
    """A variable defined in a Blueprint."""

    name: str = Field(..., description="Variable name")
    type: str = Field(
        ..., description="Variable type (use VariableType enum values or custom)"
    )

    # Container type flags
    is_array: bool = False
    is_set: bool = False
    is_map: bool = False
    map_key_type: Optional[str] = Field(
        None, description="For Map types, the key type"
    )

    # Object/Struct type references
    object_class: Optional[str] = Field(
        None, description="For Object types, the class name"
    )
    struct_type: Optional[str] = Field(
        None, description="For Struct types, the struct name"
    )
    enum_type: Optional[str] = Field(
        None, description="For Enum types, the enum name"
    )

    # Default value
    default_value: Optional[Any] = Field(None, description="Default value")

    # Editor flags
    is_instance_editable: bool = Field(True, description="Editable on instances")
    is_blueprint_read_only: bool = False
    is_expose_on_spawn: bool = False
    is_private: bool = False
    is_save_game: bool = Field(False, description="Saved with SaveGame")

    # Replication
    is_replicated: bool = False
    replication_condition: Optional[
        Literal[
            "None",
            "InitialOnly",
            "OwnerOnly",
            "SkipOwner",
            "SimulatedOnly",
            "AutonomousOnly",
            "SimulatedOrPhysics",
            "InitialOrOwner",
            "Custom",
            "ReplayOrOwner",
            "ReplayOnly",
        ]
    ] = None

    # Metadata
    metadata: VariableMetadata = Field(default_factory=VariableMetadata)


class FunctionParameter(BaseModel):
    """A parameter in a Blueprint function."""

    name: str = Field(..., description="Parameter name")
    type: str = Field(..., description="Parameter type")

    # Type modifiers
    is_reference: bool = Field(False, description="Pass by reference")
    is_const: bool = Field(False, description="Const parameter")
    is_array: bool = False
    is_set: bool = False
    is_map: bool = False
    map_key_type: Optional[str] = None

    # Object/Struct references
    object_class: Optional[str] = None
    struct_type: Optional[str] = None
    enum_type: Optional[str] = None

    # Default value (for optional parameters)
    default_value: Optional[Any] = None


class BlueprintFunction(BaseModel):
    """A function signature defined in a Blueprint.

    Note: Does not include node graph implementation, only signature.
    """

    name: str = Field(..., description="Function name")
    description: Optional[str] = None
    category: Optional[str] = None

    # Parameters
    inputs: List[FunctionParameter] = Field(default_factory=list)
    outputs: List[FunctionParameter] = Field(default_factory=list)

    # Function flags
    is_pure: bool = Field(False, description="Pure function (no side effects)")
    is_const: bool = Field(False, description="Const function")
    is_static: bool = False
    is_blueprint_callable: bool = True
    is_blueprint_pure: bool = False
    access_specifier: Literal["Public", "Protected", "Private"] = "Public"

    # Event flags
    is_event: bool = False
    is_override: bool = False
    is_native_event: bool = False
    is_replicated: bool = False

    # Keywords for search
    keywords: Optional[str] = None
    compact_node_title: Optional[str] = None


class BlueprintEventDispatcher(BaseModel):
    """Event dispatcher (delegate) in a Blueprint."""

    name: str = Field(..., description="Event dispatcher name")
    delegate_signature: List[FunctionParameter] = Field(
        default_factory=list, description="Parameters of the delegate"
    )
    is_multicast: bool = True
    is_replicated: bool = False
    category: Optional[str] = None


class BlueprintInterface(BaseModel):
    """Blueprint interface reference."""

    interface_path: str = Field(..., description="Asset path to the interface")
    interface_name: str = Field(..., description="Interface name")


class BlueprintDescription(BaseModel):
    """Complete description of an Actor Blueprint.

    This model describes the blueprint structure including:
    - Parent class
    - Component hierarchy with transforms
    - Variables (with types and defaults)
    - Function signatures (no node graphs)
    """

    # Asset identification
    asset_path: str = Field(
        ..., description="Asset path e.g. /Game/Blueprints/BP_Character"
    )
    asset_name: str = Field(..., description="Asset name without path")

    # Blueprint metadata
    parent_class: str = Field(
        "Actor", description="Parent class name e.g. Character, Pawn, Actor"
    )
    native_parent_class: Optional[str] = Field(
        None, description="Native C++ parent if any"
    )
    blueprint_type: Literal[
        "Normal",
        "Const",
        "MacroLibrary",
        "Interface",
        "LevelScript",
        "FunctionLibrary",
    ] = "Normal"

    # Description
    description: Optional[str] = Field(None, description="Blueprint description/tooltip")
    category: Optional[str] = None

    # Component structure
    components: ComponentHierarchy = Field(
        default_factory=lambda: ComponentHierarchy(
            root_component="DefaultSceneRoot", components=[]
        )
    )

    # Variables
    variables: List[BlueprintVariable] = Field(default_factory=list)

    # Functions (signatures only, no node graphs)
    functions: List[BlueprintFunction] = Field(default_factory=list)

    # Event dispatchers
    event_dispatchers: List[BlueprintEventDispatcher] = Field(default_factory=list)

    # Interfaces implemented
    implemented_interfaces: List[BlueprintInterface] = Field(default_factory=list)

    # Tags for organization
    asset_tags: Dict[str, str] = Field(default_factory=dict)

    # Compile status
    is_data_only: bool = Field(
        False, description="True if blueprint has no custom logic (data-only)"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "asset_path": "/Game/Blueprints/BP_Character",
                    "asset_name": "BP_Character",
                    "parent_class": "Character",
                    "components": {
                        "root_component": "CapsuleComponent",
                        "components": [
                            {
                                "name": "CapsuleComponent",
                                "component_class": "CapsuleComponent",
                                "is_root": True,
                            },
                            {
                                "name": "Mesh",
                                "component_class": "SkeletalMeshComponent",
                                "attachment": {"parent_component": "CapsuleComponent"},
                            },
                        ],
                    },
                    "variables": [
                        {"name": "Health", "type": "Float", "default_value": 100.0}
                    ],
                }
            ]
        }
    }

    def get_variable(self, name: str) -> Optional[BlueprintVariable]:
        """Get a variable by name."""
        for var in self.variables:
            if var.name == name:
                return var
        return None

    def get_function(self, name: str) -> Optional[BlueprintFunction]:
        """Get a function by name."""
        for func in self.functions:
            if func.name == name:
                return func
        return None

    def add_variable(self, variable: BlueprintVariable) -> None:
        """Add a variable to the blueprint."""
        self.variables.append(variable)

    def add_function(self, function: BlueprintFunction) -> None:
        """Add a function to the blueprint."""
        self.functions.append(function)
