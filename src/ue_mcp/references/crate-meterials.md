现在我来整理完整的 API 文档汇总：

---

## Unreal Engine Python API 材质创建完整指南

### 1. 核心类概览

| 类名 | 用途 | 模块 |
|------|------|------|
| `MaterialEditingLibrary` | 创建/编辑材质节点、连接、编译 | MaterialEditor |
| `AssetToolsHelpers` | 获取 AssetTools 实例 | AssetTools |
| `AssetTools` | 创建资产（包括材质） | AssetTools |
| `MaterialFactoryNew` | 创建新材质的工厂类 | UnrealEd |

---

### 2. 创建材质资产

```python
import unreal

# 获取 AssetTools
asset_tools = unreal.AssetToolsHelpers.get_asset_tools()

# 创建材质
material = asset_tools.create_asset(
    asset_name="M_MyMaterial",        # 资产名称
    package_path="/Game/Materials",   # 保存路径
    asset_class=unreal.Material,      # 资产类型
    factory=unreal.MaterialFactoryNew()  # 工厂
)
```

**`create_asset()` 参数：**
- `asset_name` (str): 新资产名称
- `package_path` (str): 包路径
- `asset_class` (type): 资产类
- `factory` (Factory): 工厂实例
- `calling_context` (Name): 可选，调用上下文

---

### 3. MaterialEditingLibrary 核心方法

#### 3.1 创建材质表达式节点

```python
node = unreal.MaterialEditingLibrary.create_material_expression(
    material,                                    # Material 资产
    unreal.MaterialExpressionConstant3Vector,   # 表达式类
    node_pos_x=-300,                            # X 位置
    node_pos_y=0                                # Y 位置
)
```

#### 3.2 连接节点到材质属性

```python
unreal.MaterialEditingLibrary.connect_material_property(
    from_expression,    # 源表达式节点
    from_output_name,   # 输出名称（空字符串使用第一个输出）
    property_           # MaterialProperty 枚举值
)
```

#### 3.3 连接两个节点

```python
unreal.MaterialEditingLibrary.connect_material_expressions(
    from_expression,    # 源节点
    from_output_name,   # 源输出名（空=第一个）
    to_expression,      # 目标节点
    to_input_name       # 目标输入名（空=第一个）
)
```

#### 3.4 其他重要方法

| 方法 | 说明 |
|------|------|
| `recompile_material(material)` | 重新编译材质 |
| `delete_material_expression(material, expr)` | 删除节点 |
| `delete_all_material_expressions(material)` | 删除所有节点 |
| `layout_material_expressions(material)` | 自动布局节点 |
| `get_num_material_expressions(material)` | 获取节点数量 |
| `get_inputs_for_material_expression(mat, expr)` | 获取节点的输入连接 |
| `get_material_expression_node_position(expr)` | 获取节点位置 |

#### 3.5 材质实例相关

```python
# 设置材质实例父级
unreal.MaterialEditingLibrary.set_material_instance_parent(instance, new_parent)

# 设置标量参数
unreal.MaterialEditingLibrary.set_material_instance_scalar_parameter_value(
    instance, "ParameterName", 0.5
)

# 设置向量参数
unreal.MaterialEditingLibrary.set_material_instance_vector_parameter_value(
    instance, "Color", unreal.LinearColor(1,0,0,1)
)

# 设置纹理参数
unreal.MaterialEditingLibrary.set_material_instance_texture_parameter_value(
    instance, "BaseTexture", texture
)
```

---

### 4. MaterialProperty 枚举值

| 枚举值 | 说明 |
|--------|------|
| `MP_BASE_COLOR` | 基础颜色 |
| `MP_METALLIC` | 金属度 |
| `MP_SPECULAR` | 高光 |
| `MP_ROUGHNESS` | 粗糙度 |
| `MP_NORMAL` | 法线 |
| `MP_EMISSIVE_COLOR` | 自发光颜色 |
| `MP_OPACITY` | 不透明度 |
| `MP_OPACITY_MASK` | 不透明度蒙版 |
| `MP_AMBIENT_OCCLUSION` | 环境光遮蔽 |
| `MP_ANISOTROPY` | 各向异性 |
| `MP_REFRACTION` | 折射 |
| `MP_SUBSURFACE_COLOR` | 次表面颜色 |
| `MP_TANGENT` | 切线 |
| `MP_WORLD_POSITION_OFFSET` | 世界位置偏移 |

---

### 5. 常用材质表达式节点类（417+个）

**常量/参数类：**
- `MaterialExpressionConstant` - 标量常量
- `MaterialExpressionConstant2Vector` - 2D向量常量
- `MaterialExpressionConstant3Vector` - 3D向量常量 (RGB)
- `MaterialExpressionConstant4Vector` - 4D向量常量 (RGBA)

**数学运算类：**
- `MaterialExpressionAdd` - 加法
- `MaterialExpressionSubtract` - 减法
- `MaterialExpressionMultiply` - 乘法
- `MaterialExpressionDivide` - 除法
- `MaterialExpressionAbs` - 绝对值
- `MaterialExpressionClamp` - 钳制
- `MaterialExpressionDotProduct` - 点积
- `MaterialExpressionCrossProduct` - 叉积
- `MaterialExpressionLerp` - 线性插值
- `MaterialExpressionPower` - 幂运算

**纹理类：**
- `MaterialExpressionTextureSample` - 纹理采样
- `MaterialExpressionTextureCoordinate` - 纹理坐标

**工具类：**
- `MaterialExpressionComponentMask` - 分量遮罩
- `MaterialExpressionAppendVector` - 向量拼接
- `MaterialExpressionDesaturation` - 去饱和

---

### 6. 完整示例：创建 PBR 材质

```python
import unreal

def create_pbr_material(name, save_path, base_color, metallic, roughness):
    """创建一个简单的 PBR 材质"""
    
    # 1. 创建材质资产
    asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
    material = asset_tools.create_asset(
        asset_name=name,
        package_path=save_path,
        asset_class=unreal.Material,
        factory=unreal.MaterialFactoryNew()
    )
    
    if not material:
        print("创建材质失败!")
        return None
    
    mel = unreal.MaterialEditingLibrary
    
    # 2. 创建 Base Color 节点
    color_node = mel.create_material_expression(
        material, 
        unreal.MaterialExpressionConstant3Vector,
        -400, 0
    )
    color_node.set_editor_property('constant', base_color)
    mel.connect_material_property(color_node, "", unreal.MaterialProperty.MP_BASE_COLOR)
    
    # 3. 创建 Metallic 节点
    metallic_node = mel.create_material_expression(
        material,
        unreal.MaterialExpressionConstant,
        -400, 150
    )
    metallic_node.set_editor_property('r', metallic)
    mel.connect_material_property(metallic_node, "", unreal.MaterialProperty.MP_METALLIC)
    
    # 4. 创建 Roughness 节点
    roughness_node = mel.create_material_expression(
        material,
        unreal.MaterialExpressionConstant,
        -400, 300
    )
    roughness_node.set_editor_property('r', roughness)
    mel.connect_material_property(roughness_node, "", unreal.MaterialProperty.MP_ROUGHNESS)
    
    # 5. 自动布局并编译
    mel.layout_material_expressions(material)
    mel.recompile_material(material)
    
    # 6. 保存
    unreal.EditorAssetLibrary.save_asset(material.get_path_name())
    
    print(f"材质创建成功: {material.get_path_name()}")
    return material

# 使用示例
material = create_pbr_material(
    name="M_RedMetal",
    save_path="/Game/Materials",
    base_color=unreal.LinearColor(0.8, 0.1, 0.1, 1.0),  # 红色
    metallic=1.0,
    roughness=0.3
)
```

---

### 7. 总结

Python API 完全支持材质创建，主要工作流程：

1. **`AssetToolsHelpers.get_asset_tools().create_asset()`** - 创建材质资产
2. **`MaterialEditingLibrary.create_material_expression()`** - 添加节点
3. **`MaterialEditingLibrary.connect_material_property()`** - 连接到材质输出
4. **`MaterialEditingLibrary.connect_material_expressions()`** - 节点间连接
5. **`MaterialEditingLibrary.recompile_material()`** - 编译材质
6. **`EditorAssetLibrary.save_asset()`** - 保存