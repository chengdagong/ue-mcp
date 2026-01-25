# ExtraPythonAPIs Plugin & Diagnostic System

## ExtraPythonAPIs Plugin

The plugin provides APIs not exposed by default UE5 Python. Auto-installed on `editor_launch`.

### Tab Management (Blueprint Editor)

```python
import unreal

bp = unreal.load_asset("/Game/Blueprints/BP_Character")

# Switch views
unreal.ExSlateTabLibrary.switch_to_viewport_mode(bp)  # Components view
unreal.ExSlateTabLibrary.switch_to_graph_mode(bp)     # Event Graph

# Focus specific panels
unreal.ExSlateTabLibrary.focus_details_panel(bp)
unreal.ExSlateTabLibrary.focus_my_blueprint_panel(bp)
unreal.ExSlateTabLibrary.open_construction_script(bp)
unreal.ExSlateTabLibrary.open_compiler_results(bp)

# Open any tab by ID
unreal.ExSlateTabLibrary.invoke_blueprint_editor_tab(bp, unreal.Name("Inspector"))
```

**Available Tab IDs**: SCSViewport, GraphEditor, Inspector, MyBlueprint, PaletteList, CompilerResults, FindResults, ConstructionScriptEditor, Debug

### Component Attachment

```python
# Set socket attachment
unreal.ExBlueprintComponentLibrary.set_component_socket_attachment(handle, "socket_name")

# Get current socket
socket = unreal.ExBlueprintComponentLibrary.get_component_socket_attachment(handle)

# Setup parent-child attachment with socket
unreal.ExBlueprintComponentLibrary.setup_component_attachment(child, parent, "socket_name")
```

---

## Diagnostic System

### Asset Type Detection

Auto-detects: Level, Blueprint, Material, MaterialInstance, StaticMesh, SkeletalMesh, Texture, Animation, Sound, ParticleSystem, WidgetBlueprint, DataAsset

### Issue Severities

- **ERROR**: Critical - will cause problems
- **WARNING**: Should be addressed
- **INFO**: Informational
- **SUGGESTION**: Optimization tips

### Creating Diagnostic Results

```python
from asset_diagnostic import DiagnosticResult, AssetType, IssueSeverity

result = DiagnosticResult(
    asset_path="/Game/Maps/TestLevel",
    asset_type=AssetType.LEVEL,
    asset_name="TestLevel"
)

result.add_issue(
    severity=IssueSeverity.WARNING,
    category="Performance",
    message="Large actor count in level",
    actor=None,
    details=["Found 500 actors", "Consider streaming"],
    suggestion="Split into sub-levels for better performance"
)

data = result.to_dict()
```
