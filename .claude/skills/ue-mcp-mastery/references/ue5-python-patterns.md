# UE5 Python Best Practices

## Use Subsystems, Not Deprecated APIs

```python
# WRONG - Deprecated!
unreal.EditorLevelLibrary.new_level()
unreal.EditorLevelLibrary.load_level(path)

# CORRECT - Use Subsystems
level_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
level_subsystem.new_level("/Game/Maps/NewLevel")
level_subsystem.load_level("/Game/Maps/MyLevel")

actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
all_actors = actor_subsystem.get_all_level_actors()
```

## Memory Management

When running code snippets directly via `editor_execute_code`, release UE object references before level operations to avoid "World Memory Leaks" assertions.

```python
# WRONG - Holds references during level operations
level = level_subsystem.get_current_level()
package = level.get_outermost()
# ... do work that loads another level
# level and package still held - memory leak!

# CORRECT - Extract data, release references immediately
level_obj = level_subsystem.get_current_level()
package = level_obj.get_outermost()

# Extract string data we need
level_path = package.get_path_name()
level_name = package.get_name()

# CRITICAL: Release references BEFORE any level operations
del package
del level_obj

# Force GC before loading new level
import gc
gc.collect()

level_subsystem.load_level("/Game/Maps/NewLevel")
```

## Physics Setup Order

Setting physics on a component requires this specific order:

```python
mesh_comp = actor.get_component_by_class(unreal.StaticMeshComponent)

# 1. FIRST: Set Mobility to Movable (required for physics!)
mesh_comp.set_mobility(unreal.ComponentMobility.MOVABLE)

# 2. THEN: Enable physics simulation
mesh_comp.set_simulate_physics(True)

# 3. Set collision
mesh_comp.set_collision_enabled(unreal.CollisionEnabled.QUERY_AND_PHYSICS)
```

## Property Access

```python
# Preferred: Use get_editor_property/set_editor_property
value = actor.get_editor_property("relative_location")
actor.set_editor_property("relative_location", unreal.Vector(0, 0, 100))
```

## Transaction-Based Cleanup

Use transactions to auto-cleanup temporary actors:

```python
actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)

with unreal.ScopedEditorTransaction("Temporary Capture Setup"):
    capture = actor_subsystem.spawn_actor_from_class(
        unreal.SceneCapture2D,
        unreal.Vector(0, 0, 100)
    )
    capture.set_actor_label("TempCapture_Front")
    # ... do work ...

# Undo transaction to remove all temporary actors
unreal.SystemLibrary.execute_console_command(None, "TRANSACTION UNDO")
```

## Error Handling Pattern

```python
def safe_operation():
    try:
        subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        if not subsystem:
            return {"success": False, "error": "Could not get LevelEditorSubsystem"}
        # ... operation ...
        return {"success": True, "result": data}
    except Exception as e:
        return {"success": False, "error": str(e)}
```
