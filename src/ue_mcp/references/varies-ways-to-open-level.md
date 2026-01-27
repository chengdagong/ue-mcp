# Unreal Engine 5 Python API 关卡加载方法完全指南

UE5 中用于打开关卡的 Python API 主要分为三大类：**编辑器专用方法**（LevelEditorSubsystem）、**运行时方法**（GameplayStatics）和**流式加载方法**（LevelStreamingDynamic）。最重要的变化是 **EditorLevelLibrary 在 UE5 中已弃用**，官方推荐使用 `LevelEditorSubsystem` 替代。根据使用场景选择正确的 API 类至关重要：编辑器脚本使用子系统方法，游戏运行时使用 GameplayStatics，动态关卡实例化使用 LevelStreamingDynamic。

---

## 编辑器环境 API（仅限 Editor 模式）

### LevelEditorSubsystem（UE5 推荐方案）

这是 UE5 官方推荐的编辑器关卡操作类，必须通过 `get_editor_subsystem()` 获取实例后调用。

| 方法名 | 参数 | 返回值 | 功能描述 |
|--------|------|--------|----------|
| `load_level(asset_path)` | `asset_path: str` | `bool` | 关闭当前关卡（不保存），加载指定关卡 |
| `new_level(asset_path)` | `asset_path: str` | `bool` | 创建新空白关卡并保存、加载 |
| `new_level_from_template(asset_path, template_path)` | `asset_path: str`, `template_path: str` | `bool` | 基于模板创建新关卡 |
| `get_current_level()` | 无 | `Level` | 获取当前活动关卡引用 |
| `save_current_level()` | 无 | `bool` | 保存当前关卡 |
| `save_all_dirty_levels()` | 无 | `bool` | 保存所有已修改的关卡 |
| `set_current_level_by_name(level_name)` | `level_name: Name` | `bool` | 切换当前活动子关卡 |

**标准使用模式：**
```python
import unreal

# 获取子系统实例（必须步骤）
level_editor = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)

# 加载已有关卡
success = level_editor.load_level("/Game/Maps/MainLevel")

# 从模板创建新关卡
success = level_editor.new_level_from_template(
    "/Game/Maps/NewMap",
    "/Game/Maps/Template"
)
```

### EditorLoadingAndSavingUtils 提供更底层的控制

该类返回 **World 对象引用**而非布尔值，适合需要直接操作世界对象的场景。

| 方法名 | 返回值 | 特殊功能 |
|--------|--------|----------|
| `load_map(filename)` | `World` | 加载地图并返回 World 引用 |
| `load_map_with_dialog()` | `World` | 弹出对话框让用户选择地图 |
| `new_blank_map(save_existing)` | `World` | 创建空白地图，可选是否保存当前地图 |
| `new_map_from_template(template_path, save_existing)` | `World` | 从模板创建，返回 World |

### EditorLevelUtils 专注子关卡管理

该类用于管理 **流式子关卡**（Streaming Sub-levels），是实现关卡分层的关键工具。

```python
# 将已有关卡添加为子关卡
streaming_level = unreal.EditorLevelUtils.add_level_to_world(
    editor_world,                          # 目标世界
    "/Game/Maps/SubLevel",                 # 子关卡路径
    unreal.LevelStreamingAlwaysLoaded      # 流式类型（必须是子类）
)

# 带变换的版本 - 可指定子关卡位置
streaming_level = unreal.EditorLevelUtils.add_level_to_world_with_transform(
    editor_world,
    "/Game/Maps/SubLevel",
    unreal.LevelStreamingDynamic,
    unreal.Transform()  # 关卡原点偏移
)
```

**关键警告：** `create_new_streaming_level()` 方法的第一个参数必须传入 `LevelStreaming` 的**子类**（如 `LevelStreamingDynamic` 或 `LevelStreamingAlwaysLoaded`），传入父类 `LevelStreaming` 会导致编辑器冻结或崩溃。

---

## 运行时 API（游戏运行中使用）

### GameplayStatics 是运行时关卡切换的核心类

| 方法名 | 是否卸载当前关卡 | 是否阻塞 | 是否潜在操作 | 适用场景 |
|--------|------------------|----------|--------------|----------|
| `open_level()` | ✅ 是 | ✅ 是 | ❌ 否 | 完整关卡切换 |
| `load_stream_level()` | ❌ 否 | ⚙️ 可选 | ✅ 是 | 加载流式子关卡 |
| `unload_stream_level()` | N/A | ⚙️ 可选 | ✅ 是 | 卸载流式子关卡 |
| `flush_level_streaming()` | N/A | ✅ 是 | ❌ 否 | 强制完成所有流式操作 |
| `get_streaming_level()` | N/A | ❌ 否 | ❌ 否 | 获取流式关卡对象 |

**open_level() 完整签名：**
```python
unreal.GameplayStatics.open_level(
    world_context_object,    # 世界上下文（通常是调用的 Actor）
    level_name,              # 关卡路径，如 "/Game/Maps/Level1"
    absolute=True,           # True=重置选项；False=携带当前选项
    options=""               # URL 选项字符串，如 "?game=MyGameMode"
)
```

**load_stream_level() 完整签名：**
```python
unreal.GameplayStatics.load_stream_level(
    world_context_object,
    level_name,              # 流式关卡包名
    make_visible_after_load, # 加载后是否立即可见
    should_block_on_load,    # 是否阻塞等待加载完成
    latent_info              # 潜在操作信息（用于异步回调）
)
```

**重要说明：** 运行时的流式关卡必须已在持久关卡的子关卡列表中注册，否则需要使用 `LevelStreamingDynamic.load_level_instance()` 进行动态加载。

---

## 动态关卡实例化（运行时动态加载）

### LevelStreamingDynamic 支持多实例和任意位置加载

这是最灵活的运行时关卡加载方式，支持在任意世界坐标生成关卡的多个实例。

```python
streaming_level, success = unreal.LevelStreamingDynamic.load_level_instance(
    world_context_object,              # 世界上下文
    level_name="/Game/Maps/Room",      # 关卡完整路径（短名会触发慢速磁盘搜索）
    location=unreal.Vector(1000, 2000, 0),   # 世界空间位置
    rotation=unreal.Rotator(0, 45, 0),       # 世界空间旋转
    optional_level_name_override="Room_01",  # 可选：自定义名称（网络同步用）
    optional_level_streaming_class=None,     # 可选：自定义流式类
    load_as_temp_package=False               # 是否作为临时包加载
)
```

**UE4 与 UE5 参数差异：**
- UE4.26/4.27：**5 个参数**
- UE5.0+：**7 个参数**（新增 `optional_level_streaming_class` 和 `load_as_temp_package`）

**典型使用场景：**
- 程序化生成：地牢房间、城市街区
- 无缝大世界：动态加载周围区域
- 多实例场景：同一关卡模板生成多个副本

---

## LevelStreaming 基类的关键属性和方法

所有流式关卡对象都继承自此类，通过这些属性可精细控制加载行为。

| 属性 | 类型 | 作用 |
|------|------|------|
| `should_be_loaded` | `bool` | 是否应该加载 |
| `should_be_visible` | `bool` | 是否应该可见（前提是已加载） |
| `should_block_on_load` | `bool` | 是否强制同步加载 |
| `streaming_priority` | `int` | 流式优先级（数值越高越优先） |
| `level_transform` | `Transform` | 关卡加载后的变换偏移 |
| `disable_distance_streaming` | `bool` | 禁用基于距离的自动流式 |

**事件委托（可绑定回调）：**
- `on_level_loaded`：关卡加载完成时触发
- `on_level_shown`：关卡变为可见时触发
- `on_level_hidden`：关卡被隐藏时触发
- `on_level_unloaded`：关卡卸载完成时触发

**状态检查方法：**
```python
streaming_level.is_level_loaded()          # 是否已加载到内存
streaming_level.is_level_visible()         # 是否当前可见
streaming_level.is_streaming_state_pending()  # 是否有状态变更待处理
streaming_level.get_loaded_level()         # 获取 Level 对象引用
```

---

## World Partition（UE5 专属大世界系统）

UE5 引入的 World Partition 与传统流式加载**互斥**，是专为超大世界设计的新系统。

### 核心组件

| 类/组件 | 功能 |
|---------|------|
| `WorldPartition` | 管理整个世界分区 |
| `WorldPartitionStreamingSourceComponent` | 控制流式加载源 |
| `WorldPartitionBlueprintLibrary` | 提供 Actor 描述和加载功能 |
| `DataLayerSubsystem` | 运行时控制 Data Layer 状态 |

```python
# 获取世界分区中的 Actor 描述
actor_descs = unreal.WorldPartitionBlueprintLibrary.get_actor_descs()

# 通过 GUID 加载特定 Actor
unreal.WorldPartitionBlueprintLibrary.load_actors([guid_list])
```

**Data Layer 运行时状态：**
- `Unloaded`：未加载
- `Loaded`：已加载但不可见
- `Activated`：已加载且可见

---

## 各方法对比与选型指南

| 方法 | 使用环境 | 是否替换当前关卡 | 是否异步 | 支持多实例 | 推荐场景 |
|------|----------|------------------|----------|------------|----------|
| `LevelEditorSubsystem.load_level()` | 编辑器 | ✅ | ❌ | ❌ | 编辑器脚本切换关卡 |
| `EditorLoadingAndSavingUtils.load_map()` | 编辑器 | ✅ | ❌ | ❌ | 需要 World 引用 |
| `EditorLevelUtils.add_level_to_world()` | 编辑器 | ❌ | ❌ | ❌ | 添加子关卡 |
| `GameplayStatics.open_level()` | 运行时 | ✅ | ❌ | ❌ | 单人游戏关卡切换 |
| `GameplayStatics.load_stream_level()` | 运行时 | ❌ | ⚙️ | ❌ | 预注册的流式关卡 |
| `LevelStreamingDynamic.load_level_instance()` | 运行时 | ❌ | ✅ | ✅ | 动态位置、多实例 |

---

## 最佳实践和常见错误

### 路径格式规范

```python
# ✅ 正确格式
level_path = "/Game/Maps/MyLevel"

# ❌ 错误格式
level_path = "Maps/MyLevel"              # 缺少 /Game/
level_path = "/Game/Maps/MyLevel.umap"   # 不需要扩展名
level_path = "\\Game\\Maps\\MyLevel"     # 错误的斜杠方向
```

### 子系统调用方式

```python
# ❌ 错误：直接类调用
unreal.LevelEditorSubsystem.load_level("/Game/Maps/Level")  # TypeError

# ✅ 正确：先获取实例
subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
subsystem.load_level("/Game/Maps/Level")
```

### 批量处理关卡时的内存管理

```python
import unreal

def batch_process_levels(level_paths):
    level_editor = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    
    for path in level_paths:
        level_editor.load_level(path)
        
        # 执行操作...
        
        level_editor.save_current_level()
        
        # 可选：强制垃圾回收释放内存
        unreal.SystemLibrary.collect_garbage()
```

### World Partition 与传统流式的选择

- **新项目**：优先使用 World Partition（UE5 默认启用）
- **已有项目迁移**：传统 Level Streaming 仍然有效
- **两者不可混用**：同一地图只能选择其一

---

## Conclusion

UE5 Python API 的关卡加载方法形成了清晰的层次结构：`LevelEditorSubsystem` 取代了已弃用的 `EditorLevelLibrary` 成为编辑器脚本的首选；`GameplayStatics` 提供运行时的同步关卡切换；`LevelStreamingDynamic` 支持最灵活的异步多实例加载。对于 UE5 的大型开放世界项目，World Partition 系统提供了更现代化的流式方案，但它与传统 Level Streaming 互斥。选择正确的 API 取决于三个关键因素：**执行环境**（编辑器/运行时）、**是否需要保留当前关卡**（替换/叠加）、以及**是否需要多实例或自定义位置**。