# UE5 Python Deprecated API 参考

本文档记录 UE5 中已废弃的 Python API 及其替代方案。

## EditorLevelLibrary（已废弃）

`unreal.EditorLevelLibrary` 中的大部分函数已被废弃，应使用 `LevelEditorSubsystem` 替代。

### 废弃 API 对照表

| 废弃的 API | 替代方案 |
|-----------|----------|
| `unreal.EditorLevelLibrary.new_level(path)` | `level_subsystem.new_level(path)` |
| `unreal.EditorLevelLibrary.save_current_level()` | `level_subsystem.save_current_level()` |
| `unreal.EditorLevelLibrary.load_level(path)` | `level_subsystem.load_level(path)` |
| `unreal.EditorLevelLibrary.get_editor_world()` | `unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()` |

### 获取 Subsystem 的方法

```python
import unreal

# LevelEditorSubsystem - 关卡操作
level_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)

# EditorActorSubsystem - Actor 操作
actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)

# UnrealEditorSubsystem - 编辑器通用操作
editor_subsystem = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
```

### 正确用法示例

```python
import unreal

def create_and_save_level(level_path):
    """创建并保存关卡的正确方式"""

    # 获取 subsystem
    level_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)

    # 创建新关卡（不要用 EditorLevelLibrary.new_level）
    success = level_subsystem.new_level(level_path)
    if not success:
        print(f"Failed to create level: {level_path}")
        return False

    # 在关卡中添加 Actor
    actor = actor_subsystem.spawn_actor_from_class(
        unreal.StaticMeshActor,
        unreal.Vector(0, 0, 0),
        unreal.Rotator(0, 0, 0)
    )

    # 保存关卡（不要用 EditorLevelLibrary.save_current_level）
    level_subsystem.save_current_level()

    return True
```

### 错误用法（会产生 DeprecationWarning）

```python
# 错误 - 会产生废弃警告
unreal.EditorLevelLibrary.new_level("/Game/Maps/MyLevel")
unreal.EditorLevelLibrary.save_current_level()

# 正确
level_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
level_subsystem.new_level("/Game/Maps/MyLevel")
level_subsystem.save_current_level()
```

---

## EditorAssetLibrary

`unreal.EditorAssetLibrary` 目前仍可使用，但部分函数可能在未来版本中废弃。

### 常用函数（当前可用）

```python
import unreal

# 检查资产是否存在
exists = unreal.EditorAssetLibrary.does_asset_exist("/Game/MyAsset")

# 删除资产
unreal.EditorAssetLibrary.delete_asset("/Game/MyAsset")

# 复制资产
unreal.EditorAssetLibrary.duplicate_asset("/Game/Source", "/Game/Dest")

# 列出目录下的资产
assets = unreal.EditorAssetLibrary.list_assets("/Game/Folder")
```

---

## 检查 API 是否废弃

如果不确定某个 API 是否废弃，可以：

1. **查看运行时警告**：执行代码时会输出 `DeprecationWarning`
2. **查看 UE5 文档**：官方文档会标注 `Deprecated`
3. **检查函数注释**：在 Python stubs 中查看函数的 docstring

---

## 版本说明

- 本文档基于 **UE5.3+** 版本
- `EditorLevelLibrary` 的废弃是因为 "Editor Scripting Utilities Plugin" 被废弃
- 推荐使用 Subsystem 模式，这是 UE5 的标准实践
