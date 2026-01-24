# Unreal Engine 5 Python API 完全指南

UE5 Python API 为资产管理和关卡操作提供了强大的编程接口，但需注意 **EditorLevelLibrary 已被弃用**，应使用新的 Subsystem 架构。本指南覆盖资产查找、遍历、属性读取、Level 处理及 Actor 操作的完整方法与示例代码。

## 核心模块与访问方式

UE5 将功能分散到专门的 Subsystem 中，这是现代化的推荐做法：

```python
import unreal

# 资产相关
asset_registry = unreal.AssetRegistryHelpers.get_asset_registry()

# Level 和编辑器相关 (UE5 推荐方式)
level_editor = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
editor_subsystem = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
```

---

## 资产查找方法 (Asset Discovery)

### EditorAssetLibrary 基础查找

`unreal.EditorAssetLibrary` 提供简单直观的资产操作，适合大多数场景。

```python
# 检查资产是否存在
exists = unreal.EditorAssetLibrary.does_asset_exist('/Game/Materials/MyMaterial')

# 检查目录是否存在
dir_exists = unreal.EditorAssetLibrary.does_directory_exist('/Game/Characters')

# 检查目录是否包含资产
has_assets = unreal.EditorAssetLibrary.does_directory_have_assets('/Game/Textures', recursive=True)

# 获取资产数据 (不加载资产)
asset_data = unreal.EditorAssetLibrary.find_asset_data('/Game/Materials/MyMaterial')
print(f"资产名: {asset_data.asset_name}, 类型: {asset_data.asset_class_path}")
```

**支持的路径格式**包括：引用路径 `StaticMesh'/Game/MyAsset.MyAsset'`、完整名称 `StaticMesh /Game/MyAsset.MyAsset`、路径名 `/Game/MyAsset.MyAsset`、以及包名 `/Game/MyAsset`。

### AssetRegistry 高级查询

AssetRegistry 提供更强大的过滤和批量查询能力，适合复杂搜索场景。

```python
asset_reg = unreal.AssetRegistryHelpers.get_asset_registry()

# 按路径获取资产
assets = asset_reg.get_assets_by_path('/Game/Characters/Meshes', recursive=True)

# 按类型获取资产 (UE5.1+ 使用 TopLevelAssetPath)
static_mesh_path = unreal.TopLevelAssetPath('/Script/Engine', 'StaticMesh')
all_meshes = asset_reg.get_assets_by_class(static_mesh_path, search_sub_classes=True)

# 按对象路径精确获取 (注意: 字符串版本已弃用，推荐使用 SoftObjectPath)
asset_data = asset_reg.get_asset_by_object_path(
    unreal.SoftObjectPath('/Game/Materials/M_Metal.M_Metal')
)
loaded_asset = asset_data.get_asset()  # 加载实际对象
```

### ARFilter 复杂过滤器

ARFilter 是最强大的查询工具，支持多条件组合过滤。

**重要**: ARFilter 的属性必须在构造函数中设置，创建后不能修改属性值。

```python
# 创建过滤器 (必须使用构造函数参数)
ar_filter = unreal.ARFilter(
    package_paths=['/Game/Characters', '/Game/Props'],  # 多路径
    class_paths=[
        unreal.TopLevelAssetPath('/Script/Engine', 'StaticMesh'),
        unreal.TopLevelAssetPath('/Script/Engine', 'SkeletalMesh')
    ],
    recursive_paths=True,      # 递归搜索子目录
    recursive_classes=True     # 包含子类
)

# 执行查询
filtered_assets = asset_reg.get_assets(ar_filter)

# 过滤现有列表
all_assets = asset_reg.get_all_assets()
filter_for_meshes = unreal.ARFilter(
    class_paths=[unreal.TopLevelAssetPath('/Script/Engine', 'StaticMesh')],
    recursive_classes=True
)
result = asset_reg.run_assets_through_filter(all_assets, filter_for_meshes)
```

**过滤逻辑**：组件之间是 AND 关系，组件内数组元素是 OR 关系。例如设置 `package_paths=['/Game/A']` 且 `class_paths=[StaticMesh, Material]` 时，只返回 `/Game/A` 路径下的 StaticMesh 或 Material 资产。

### 常用类型的 TopLevelAssetPath

```python
# UE5.1+ 常用资产类型路径
ASSET_TYPES = {
    'StaticMesh': unreal.TopLevelAssetPath('/Script/Engine', 'StaticMesh'),
    'SkeletalMesh': unreal.TopLevelAssetPath('/Script/Engine', 'SkeletalMesh'),
    'Material': unreal.TopLevelAssetPath('/Script/Engine', 'Material'),
    'Texture2D': unreal.TopLevelAssetPath('/Script/Engine', 'Texture2D'),
    'Blueprint': unreal.TopLevelAssetPath('/Script/Engine', 'Blueprint'),
    'AnimSequence': unreal.TopLevelAssetPath('/Script/Engine', 'AnimSequence'),
    'SoundWave': unreal.TopLevelAssetPath('/Script/Engine', 'SoundWave'),
}
```

---

## 资产遍历方法 (Asset Iteration)

### 目录遍历

```python
# 方法1: EditorAssetLibrary.list_assets (简单直接)
asset_paths = unreal.EditorAssetLibrary.list_assets(
    directory_path='/Game/Materials',
    recursive=True,           # 递归子目录
    include_folder=False      # 不包含文件夹路径
)
for path in asset_paths:
    print(path)  # 输出: /Game/Materials/MyMaterial.MyMaterial

# 方法2: AssetRegistry.get_assets_by_path (返回AssetData)
assets = asset_reg.get_assets_by_path('/Game/Meshes', recursive=True)
for asset in assets:
    print(f"{asset.asset_name} - {asset.package_path}")
```

### 按类型批量获取

```python
def get_all_assets_of_type(asset_type_path, base_path=None):
    """获取指定类型的所有资产"""
    asset_reg = unreal.AssetRegistryHelpers.get_asset_registry()

    if base_path:
        ar_filter = unreal.ARFilter(
            package_paths=[base_path],
            class_paths=[asset_type_path],
            recursive_paths=True
        )
        return asset_reg.get_assets(ar_filter)
    else:
        return asset_reg.get_assets_by_class(asset_type_path, search_sub_classes=True)

# 使用示例
all_materials = get_all_assets_of_type(
    unreal.TopLevelAssetPath('/Script/Engine', 'Material')
)
character_meshes = get_all_assets_of_type(
    unreal.TopLevelAssetPath('/Script/Engine', 'SkeletalMesh'),
    base_path='/Game/Characters'
)
```

### 构建资产字典

```python
def build_asset_dictionary(asset_type_path=None):
    """构建资产名到路径的映射字典"""
    asset_reg = unreal.AssetRegistryHelpers.get_asset_registry()
    
    if asset_type_path:
        assets = asset_reg.get_assets_by_class(asset_type_path)
    else:
        assets = asset_reg.get_all_assets()
    
    asset_dict = {}
    if assets:
        for asset in assets:
            name = str(asset.asset_name)
            path = str(asset.package_name)
            asset_dict.setdefault(name, []).append(path)
    return asset_dict

# 构建材质字典
material_dict = build_asset_dictionary(
    unreal.TopLevelAssetPath('/Script/Engine', 'Material')
)
```

---

## 获取资产属性 (Asset Properties)

### 加载资产

```python
# 方法1: 全局函数
asset = unreal.load_asset('/Game/MyFolder/MyAsset')

# 方法2: EditorAssetLibrary (带验证)
if unreal.EditorAssetLibrary.does_asset_exist('/Game/MyAsset'):
    asset = unreal.EditorAssetLibrary.load_asset('/Game/MyAsset')

# 加载蓝图类
bp_class = unreal.EditorAssetLibrary.load_blueprint_class('/Game/Blueprints/BP_Character')
```

### get_editor_property 读取属性

这是读取资产属性的核心方法，属性名使用 **snake_case** 格式：

```python
# 加载并读取 StaticMesh 属性
mesh = unreal.load_asset('/Game/Meshes/SM_Chair')
num_lods = mesh.get_num_lods()  # 使用方法获取 LOD 数量
materials = mesh.get_editor_property('static_materials')
source_file = mesh.get_editor_property('source_file_path')

# 材质属性
material = unreal.load_asset('/Game/Materials/M_Base')
two_sided = material.get_editor_property('two_sided')
blend_mode = material.get_editor_property('blend_mode')

# 修改属性
material.set_editor_property('two_sided', True)
unreal.EditorAssetLibrary.save_loaded_asset(material)  # 保存更改
```

**查找属性名的方法**：在编辑器详情面板中悬停属性，第一行显示 API 名称。也可使用 `dir(asset)` 列出所有属性和方法。

### 访问嵌套属性

```python
# 访问 LOD 链中的嵌套属性
lod_settings = unreal.load_asset('/Game/LODSettings')
pipelines = lod_settings.get_editor_property('per_lod_pipeline_settings')
reduction_settings = pipelines[1].get_editor_property('settings')
reduction = reduction_settings.get_editor_property('reduction_settings')
ratio = reduction.get_editor_property('reduction_target_triangle_ratio')
```

### 元数据操作

```python
# 读取元数据
asset = unreal.EditorAssetLibrary.load_asset('/Game/MyMesh')
author = unreal.EditorAssetLibrary.get_metadata_tag(asset, 'Author')
all_metadata = unreal.EditorAssetLibrary.get_metadata_tag_values(asset)

for tag, value in all_metadata.items():
    print(f"{tag}: {value}")

# 设置元数据
unreal.EditorAssetLibrary.set_metadata_tag(asset, 'Author', 'John')
unreal.EditorAssetLibrary.set_metadata_tag(asset, 'Version', '1.0')
unreal.EditorAssetLibrary.save_loaded_asset(asset)

# 删除元数据
unreal.EditorAssetLibrary.remove_metadata_tag(asset, 'ObsoleteTag')
```

### 依赖关系查询

```python
def analyze_dependencies(asset_path):
    """分析资产的依赖关系"""
    asset_reg = unreal.AssetRegistryHelpers.get_asset_registry()
    package_name = asset_path.split('.')[0] if '.' in asset_path else asset_path
    
    # 配置选项
    options = unreal.AssetRegistryDependencyOptions()
    options.include_soft_package_references = True
    options.include_hard_package_references = True
    
    # 获取依赖项 (此资产引用了什么)
    dependencies = asset_reg.get_dependencies(package_name, options)
    print("依赖项 (此资产使用的资源):")
    for dep in (dependencies or []):
        print(f"  → {dep}")
    
    # 获取引用者 (什么引用了此资产)
    referencers = asset_reg.get_referencers(package_name, options)
    print("引用者 (使用此资产的资源):")
    for ref in (referencers or []):
        print(f"  ← {ref}")
    
    # EditorAssetLibrary 替代方法
    ea_refs = unreal.EditorAssetLibrary.find_package_referencers_for_asset(asset_path)
    return dependencies, referencers

analyze_dependencies('/Game/Materials/M_BaseMaterial')
```

---

## Level 资产处理

### 重要变更：EditorLevelLibrary 已弃用

UE5 中应使用新的 Subsystem 架构：

| 旧方法 (弃用) | 新方法 (推荐) |
|--------------|--------------|
| `EditorLevelLibrary.get_editor_world()` | `UnrealEditorSubsystem.get_editor_world()` |
| `EditorLevelLibrary.load_level()` | `LevelEditorSubsystem.load_level()` |
| `EditorLevelLibrary.save_current_level()` | `LevelEditorSubsystem.save_current_level()` |
| `EditorLevelLibrary.get_all_level_actors()` | `EditorActorSubsystem.get_all_level_actors()` |

### 加载和访问 Level

```python
level_editor = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
editor_sub = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)

# 加载关卡
success = level_editor.load_level("/Game/Maps/MyLevel")

# 获取当前世界
world = editor_sub.get_editor_world()
map_name = world.get_name()
world_path = world.get_path_name()

# 获取当前关卡
current_level = level_editor.get_current_level()

# 保存关卡
level_editor.save_current_level()
level_editor.save_all_dirty_levels()
```

### 访问 World Settings

```python
world = editor_sub.get_editor_world()
settings = world.get_world_settings()

# 读取世界设置属性
kill_z = settings.get_editor_property('kill_z')
world_to_meters = settings.get_editor_property('world_to_meters')
lightmass = settings.get_editor_property('lightmass_settings')
```

### 子关卡 (Streaming Levels) 操作

```python
world = editor_sub.get_editor_world()

# 添加子关卡
streaming_level = unreal.EditorLevelUtils.add_level_to_world(
    world=world,
    level_package_name="/Game/Maps/SubLevel",
    level_streaming_class=unreal.LevelStreamingAlwaysLoaded
)

# 带变换的子关卡
streaming_level = unreal.EditorLevelUtils.add_level_to_world_with_transform(
    world=world,
    level_package_name="/Game/Maps/SubLevel",
    level_streaming_class=unreal.LevelStreamingDynamic,
    level_transform=unreal.Transform(
        location=unreal.Vector(1000, 0, 0),
        rotation=unreal.Rotator(0, 0, 0),
        scale=unreal.Vector(1, 1, 1)
    )
)

# 获取所有关卡
all_levels = unreal.EditorLevelUtils.get_levels(world)
for level in all_levels:
    print(f"关卡: {level.get_name()}")

# 设置关卡可见性
unreal.EditorLevelUtils.set_level_visibility(
    level=my_level,
    should_be_visible=True,
    force_layers_visible=True
)

# 移动 Actor 到其他关卡
unreal.EditorLevelUtils.move_actors_to_level(
    actors_to_move=[actor1, actor2],
    dest_streaming_level=target_level
)
```

### 创建新关卡

```python
# 创建空白关卡
level_editor.new_level("/Game/Maps/NewLevel")

# 从模板创建
level_editor.new_level_from_template(
    asset_path="/Game/Maps/NewLevel",
    template_asset_path="/Game/Maps/Template"
)

# 创建新的流式子关卡
streaming = unreal.EditorLevelUtils.create_new_streaming_level(
    level_streaming_class=unreal.LevelStreamingAlwaysLoaded,
    new_level_path="/Game/Maps/NewSubLevel",
    move_selected_actors_into_new_level=True
)
```

---

## 获取 Level 内 Actor 的属性

### Actor 遍历方法

```python
actor_sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()

# 获取所有 Actor
all_actors = actor_sub.get_all_level_actors()

# 获取选中的 Actor
selected = actor_sub.get_selected_level_actors()

# 获取所有组件
all_components = actor_sub.get_all_level_actors_components()
```

### 按类型筛选 Actor

```python
# 使用 GameplayStatics 按类型获取
static_mesh_actors = unreal.GameplayStatics.get_all_actors_of_class(
    world, unreal.StaticMeshActor
)
lights = unreal.GameplayStatics.get_all_actors_of_class(world, unreal.Light)
cameras = unreal.GameplayStatics.get_all_actors_of_class(world, unreal.CameraActor)

# 按类型和标签获取
tagged_actors = unreal.GameplayStatics.get_all_actors_of_class_with_tag(
    world, unreal.StaticMeshActor, "MyTag"
)

# 仅按标签获取
enemies = unreal.GameplayStatics.get_all_actors_with_tag(world, "Enemy")
```

### 按标签和层级过滤

```python
# 检查 Actor 是否有标签
if actor.actor_has_tag("Enemy"):
    print("这是敌人")

# 获取/设置标签
tags = actor.get_editor_property('tags')
actor.set_editor_property('tags', ['Tag1', 'Tag2'])

# 按层级过滤
def get_actors_in_layer(layer_name):
    all_actors = actor_sub.get_all_level_actors()
    return [a for a in all_actors if layer_name in a.get_editor_property('layers')]
```

### Actor 属性访问

```python
# 变换属性
location = actor.get_actor_location()      # Vector
rotation = actor.get_actor_rotation()      # Rotator  
scale = actor.get_actor_scale3d()          # Vector
transform = actor.get_actor_transform()    # Transform

# 设置变换
actor.set_actor_location(unreal.Vector(100, 200, 0), sweep=False, teleport=True)
actor.set_actor_rotation(unreal.Rotator(0, 90, 0), teleport_physics=True)
actor.set_actor_scale3d(unreal.Vector(2, 2, 2))

# 名称和标签
label = actor.get_actor_label()            # 编辑器显示名
name = actor.get_name()                    # 内部名称
path = actor.get_path_name()               # 完整路径
folder = actor.get_folder_path()           # World Outliner 文件夹

# 通用属性
hidden = actor.get_editor_property('hidden')
can_be_damaged = actor.get_editor_property('can_be_damaged')
root_component = actor.get_editor_property('root_component')
```

### 组件访问与属性读取

```python
# 获取指定类型的组件
static_mesh_comps = actor.get_components_by_class(unreal.StaticMeshComponent)
skeletal_comps = actor.get_components_by_class(unreal.SkeletalMeshComponent)
scene_comps = actor.get_components_by_class(unreal.SceneComponent)

# 获取单个组件
smc = actor.get_component_by_class(unreal.StaticMeshComponent)

# StaticMeshComponent 属性
if smc:
    mesh = smc.get_editor_property('static_mesh')
    mobility = smc.get_editor_property('mobility')
    cast_shadow = smc.get_editor_property('cast_shadow')
    
    # 材质操作
    num_materials = smc.get_num_materials()
    for i in range(num_materials):
        mat = smc.get_material(i)
        print(f"材质 {i}: {mat.get_name()}")
    
    # 设置材质
    smc.set_material(0, new_material)

# SkeletalMeshComponent 属性
skc = actor.get_component_by_class(unreal.SkeletalMeshComponent)
if skc:
    skel_mesh = skc.get_skeletal_mesh_asset()
    anim_instance = skc.get_anim_instance()
    bone_transform = skc.get_bone_transform("head")
```

### 组件层级遍历

```python
def traverse_actor_hierarchy(actor):
    """遍历 Actor 的完整组件层级"""
    print(f"\n=== {actor.get_actor_label()} ===")
    
    components = actor.get_components_by_class(unreal.ActorComponent)
    for comp in components:
        print(f"组件: {comp.get_name()} ({comp.get_class().get_name()})")
        
        # SceneComponent 有子组件
        if isinstance(comp, unreal.SceneComponent):
            children = comp.get_children_components(include_all_descendants=False)
            for child in children:
                print(f"  └─ 子组件: {child.get_name()}")
    
    # 获取附加的子 Actor
    child_actors = actor.get_all_child_actors()
    for child in child_actors:
        print(f"子 Actor: {child.get_actor_label()}")

# 使用
for actor in actor_sub.get_selected_level_actors():
    traverse_actor_hierarchy(actor)
```

---

## 完整工作流示例

### 批量处理场景中的 StaticMesh

```python
import unreal

def batch_process_static_meshes():
    """批量处理场景中所有 StaticMesh Actor"""
    actor_sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    
    sm_actors = unreal.GameplayStatics.get_all_actors_of_class(world, unreal.StaticMeshActor)
    
    results = []
    for actor in sm_actors:
        smc = actor.get_component_by_class(unreal.StaticMeshComponent)
        if not smc:
            continue
            
        mesh = smc.get_editor_property('static_mesh')
        if not mesh:
            continue
        
        results.append({
            'actor_name': actor.get_actor_label(),
            'mesh_name': mesh.get_name(),
            'location': actor.get_actor_location(),
            'num_lods': mesh.get_num_lods(),
            'num_materials': smc.get_num_materials(),
            'cast_shadow': smc.get_editor_property('cast_shadow')
        })
    
    return results

# 执行并输出
for item in batch_process_static_meshes():
    print(f"{item['actor_name']}: {item['mesh_name']} (LODs: {item['num_lods']})")
```

### 资产依赖关系完整分析

```python
import unreal

def full_asset_analysis(asset_path):
    """完整的资产分析：加载、属性、元数据、依赖"""
    
    if not unreal.EditorAssetLibrary.does_asset_exist(asset_path):
        print(f"资产不存在: {asset_path}")
        return
    
    # 1. 加载资产
    asset = unreal.EditorAssetLibrary.load_asset(asset_path)
    asset_data = unreal.EditorAssetLibrary.find_asset_data(asset_path)
    
    print(f"=== {asset.get_name()} ({asset.get_class().get_name()}) ===")
    print(f"包路径: {asset_data.package_name}")
    
    # 2. 尝试读取常见属性
    for prop in ['source_file_path', 'static_materials', 'two_sided']:
        try:
            value = asset.get_editor_property(prop)
            print(f"  {prop}: {value}")
        except:
            pass

    # StaticMesh 的 LOD 数量需要使用方法获取
    if hasattr(asset, 'get_num_lods'):
        print(f"  num_lods: {asset.get_num_lods()}")
    
    # 3. 元数据
    metadata = unreal.EditorAssetLibrary.get_metadata_tag_values(asset)
    if metadata:
        print("元数据:")
        for tag, value in metadata.items():
            print(f"  {tag}: {value}")
    
    # 4. 依赖分析
    asset_reg = unreal.AssetRegistryHelpers.get_asset_registry()
    options = unreal.AssetRegistryDependencyOptions()
    options.include_soft_package_references = True
    options.include_hard_package_references = True
    
    package_name = asset_path.split('.')[0] if '.' in asset_path else asset_path
    
    deps = asset_reg.get_dependencies(package_name, options)
    refs = asset_reg.get_referencers(package_name, options)
    
    print(f"依赖: {len(deps or [])} 个资产")
    print(f"被引用: {len(refs or [])} 次")

full_asset_analysis('/Game/StarterContent/Materials/M_Metal_Brushed_Nickel')
```

## 关键类速查表

| 类 | 用途 | UE5 状态 |
|---|------|---------|
| `EditorAssetLibrary` | 资产基础操作 | 可用 |
| `AssetRegistry` | 高级资产查询 | 推荐 |
| `ARFilter` | 复杂过滤条件 | 推荐 |
| `EditorLevelLibrary` | Level 操作 | **已弃用** |
| `LevelEditorSubsystem` | Level 加载/保存 | **推荐** |
| `UnrealEditorSubsystem` | World/视口访问 | **推荐** |
| `EditorActorSubsystem` | Actor 操作 | **推荐** |
| `EditorLevelUtils` | 流式关卡工具 | 可用 |
| `GameplayStatics` | 运行时 Actor 查询 | 可用 |

以上方法覆盖了 UE5 Python API 中资产和关卡操作的核心功能，建议优先使用新的 Subsystem 架构以确保未来兼容性。