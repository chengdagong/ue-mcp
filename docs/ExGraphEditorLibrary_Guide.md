# ExGraphEditorLibrary Python API Guide

ExGraphEditorLibrary 是 UE-MCP 的 ExtraPythonAPIs 插件提供的 Blueprint 图表编辑 API，支持通过 Python 脚本创建、修改、查询和删除 Blueprint 节点。

## 概述

### CRUD 操作模型

| 操作类型 | 功能 |
|---------|------|
| **CREATE** | 创建蓝图、添加节点（函数、事件、变量等） |
| **READ** | 查询节点、引脚、连接 |
| **UPDATE** | 连接节点、设置引脚默认值、编译 |
| **DELETE** | 删除节点、断开引脚连接 |

### 前置条件

1. 确保 ExtraPythonAPIs 插件已安装并启用（通过 `editor_launch` 或 `editor_configure` 自动安装）
2. 如果插件是新安装的，需要先调用 `project_build` 编译插件

---

## CREATE 操作

### CreateBlueprintAsset - 创建蓝图资产

创建一个新的 Blueprint 资产。

```python
import unreal

# 创建继承自 AActor 的蓝图（默认）
bp = unreal.ExGraphEditorLibrary.create_blueprint_asset(
    "/Game/Blueprints",  # 资产目录
    "BP_MyActor"         # 资产名称
)

# 创建继承自特定类的蓝图
bp = unreal.ExGraphEditorLibrary.create_blueprint_asset(
    "/Game/Blueprints",
    "BP_MyPawn",
    unreal.Pawn.static_class()  # 父类
)

# 创建继承自 Character 的蓝图
bp = unreal.ExGraphEditorLibrary.create_blueprint_asset(
    "/Game/Blueprints",
    "BP_MyCharacter",
    unreal.Character.static_class()
)
```

**参数说明：**
- `asset_path`: 资产目录路径（如 `/Game/Blueprints`）
- `asset_name`: 资产名称（如 `BP_MyActor`）
- `parent_class`: 父类（可选，默认为 `AActor`）

---

### AddEventNode - 添加事件节点

添加事件节点（如 BeginPlay、Tick）。

```python
import unreal

bp = unreal.load_asset("/Game/Blueprints/BP_MyActor")

# 添加 BeginPlay 事件
begin_play = unreal.ExGraphEditorLibrary.add_event_node(
    bp,
    unreal.Actor.static_class(),      # 事件定义类
    "ReceiveBeginPlay",               # 事件名称
    0,                                # X 位置
    0                                 # Y 位置
)

# 添加 Tick 事件
tick_event = unreal.ExGraphEditorLibrary.add_event_node(
    bp,
    unreal.Actor.static_class(),
    "ReceiveTick",
    0,
    200
)

# 添加 ActorBeginOverlap 事件
overlap_event = unreal.ExGraphEditorLibrary.add_event_node(
    bp,
    unreal.Actor.static_class(),
    "ReceiveActorBeginOverlap",
    0,
    400
)
```

**常用事件名称：**

| 事件名称 | 描述 | 事件类 |
|---------|------|-------|
| `ReceiveBeginPlay` | BeginPlay | `AActor` |
| `ReceiveTick` | Tick | `AActor` |
| `ReceiveEndPlay` | EndPlay | `AActor` |
| `ReceiveActorBeginOverlap` | ActorBeginOverlap | `AActor` |
| `ReceiveActorEndOverlap` | ActorEndOverlap | `AActor` |
| `ReceiveHit` | Hit | `AActor` |
| `ReceiveAnyDamage` | AnyDamage | `AActor` |

---

### AddCallFunctionNode - 添加函数调用节点（精确指定类）

添加指定类的函数调用节点。

```python
import unreal

bp = unreal.load_asset("/Game/Blueprints/BP_MyActor")

# 添加 PrintString 节点
print_node = unreal.ExGraphEditorLibrary.add_call_function_node(
    bp,
    unreal.SystemLibrary.static_class(),  # 函数所在类 (C++ KismetSystemLibrary)
    "PrintString",                        # 函数名
    200,                                  # X 位置
    0                                     # Y 位置
)

# 添加 Delay 节点
delay_node = unreal.ExGraphEditorLibrary.add_call_function_node(
    bp,
    unreal.SystemLibrary.static_class(),
    "Delay",
    400,
    0
)

# 添加 GetActorLocation 节点
get_location = unreal.ExGraphEditorLibrary.add_call_function_node(
    bp,
    unreal.Actor.static_class(),
    "K2_GetActorLocation",
    200,
    100
)
```

---

### AddFunctionNodeByName - 按名称添加函数节点（推荐）

按函数名自动查找并添加节点，更便于使用。

```python
import unreal

bp = unreal.load_asset("/Game/Blueprints/BP_MyActor")

# 不指定 OwnerClass - 自动在常用库类中搜索
print_node = unreal.ExGraphEditorLibrary.add_function_node_by_name(
    bp,
    "PrintString",  # 自动在 SystemLibrary 中找到
    None,           # 不指定类
    200, 0
)

# 指定 OwnerClass - 在特定类中搜索（支持成员方法）
get_location = unreal.ExGraphEditorLibrary.add_function_node_by_name(
    bp,
    "K2_GetActorLocation",
    unreal.Actor.static_class(),  # 指定类
    200, 100
)

# 调用组件类的方法
set_static_mesh = unreal.ExGraphEditorLibrary.add_function_node_by_name(
    bp,
    "SetStaticMesh",
    unreal.StaticMeshComponent.static_class(),
    400, 100
)
```

**自动搜索的库类（当 OwnerClass 为 None 时）：**

| C++ 类名 | Python 类名 | 功能 |
|---------|------------|------|
| `UKismetSystemLibrary` | `unreal.SystemLibrary` | PrintString, Delay, SetTimer 等 |
| `UGameplayStatics` | `unreal.GameplayStatics` | GetPlayerController, SpawnActor 等 |
| `UKismetMathLibrary` | `unreal.MathLibrary` | 数学运算 |
| `UKismetStringLibrary` | `unreal.StringLibrary` | 字符串操作 |
| `UKismetArrayLibrary` | `unreal.ArrayLibrary` | 数组操作 |
| `UKismetTextLibrary` | `unreal.TextLibrary` | 文本操作 |
| `AActor` | `unreal.Actor` | Actor 方法 |
| `UActorComponent` | `unreal.ActorComponent` | 组件方法 |

> **注意**：C++ 中的 `Kismet*Library` 类在 Python 中去掉了 `Kismet` 前缀。

---

### AddBranchNode - 添加分支节点

添加 Branch (If) 条件判断节点。

```python
import unreal

bp = unreal.load_asset("/Game/Blueprints/BP_MyActor")

# 添加 Branch 节点
branch = unreal.ExGraphEditorLibrary.add_branch_node(bp, 300, 0)

# Branch 节点有以下引脚:
# - In:execute (输入执行)
# - In:Condition (bool 输入)
# - Out:then (True 分支)
# - Out:else (False 分支)
```

---

### AddVariableGetNode / AddVariableSetNode - 添加变量节点

添加变量 Getter 或 Setter 节点（变量必须先存在）。

```python
import unreal

bp = unreal.load_asset("/Game/Blueprints/BP_MyActor")

# 首先添加成员变量
unreal.ExGraphEditorLibrary.add_member_variable(bp, "Health", "float")
unreal.ExGraphEditorLibrary.add_member_variable(bp, "IsAlive", "bool")

# 编译以使变量生效
unreal.ExGraphEditorLibrary.compile_blueprint(bp)

# 添加 Variable Get 节点（读取变量）
get_health = unreal.ExGraphEditorLibrary.add_variable_get_node(
    bp, "Health", 100, 0
)

# 添加 Variable Set 节点（写入变量）
set_health = unreal.ExGraphEditorLibrary.add_variable_set_node(
    bp, "Health", 300, 0
)
```

---

### AddMemberVariable - 添加成员变量

为蓝图添加新的成员变量。

```python
import unreal

bp = unreal.load_asset("/Game/Blueprints/BP_MyActor")

# 添加各种类型的变量
unreal.ExGraphEditorLibrary.add_member_variable(bp, "Health", "float")
unreal.ExGraphEditorLibrary.add_member_variable(bp, "MaxHealth", "float")
unreal.ExGraphEditorLibrary.add_member_variable(bp, "IsAlive", "bool")
unreal.ExGraphEditorLibrary.add_member_variable(bp, "PlayerName", "string")
unreal.ExGraphEditorLibrary.add_member_variable(bp, "SpawnLocation", "vector")
unreal.ExGraphEditorLibrary.add_member_variable(bp, "SpawnRotation", "rotator")

# 编译使变量生效
unreal.ExGraphEditorLibrary.compile_blueprint(bp)
```

**支持的变量类型：**

| 类型字符串 | UE5 类型 |
|-----------|---------|
| `bool`, `boolean` | Boolean |
| `int`, `int32`, `integer` | Integer |
| `int64` | Int64 |
| `float`, `real` | Float |
| `double` | Double |
| `string`, `fstring` | String |
| `name`, `fname` | Name |
| `text`, `ftext` | Text |
| `vector`, `fvector` | Vector |
| `rotator`, `frotator` | Rotator |
| `transform`, `ftransform` | Transform |
| `vector2d`, `fvector2d` | Vector2D |
| `linearcolor`, `color` | LinearColor |

---

## UPDATE 操作

### ConnectNodes - 连接节点

连接两个节点的引脚。支持模糊匹配引脚名称。

```python
import unreal

bp = unreal.load_asset("/Game/Blueprints/BP_MyActor")

# 创建节点
begin_play = unreal.ExGraphEditorLibrary.add_event_node(
    bp, unreal.Actor.static_class(), "ReceiveBeginPlay", 0, 0
)
print_node = unreal.ExGraphEditorLibrary.add_function_node_by_name(
    bp, "PrintString", None, 200, 0
)

# 连接 BeginPlay -> PrintString
# 执行引脚连接
unreal.ExGraphEditorLibrary.connect_nodes(
    begin_play, "then",      # 源节点的输出执行引脚
    print_node, "execute"    # 目标节点的输入执行引脚
)
```

**常用引脚名称：**

| 引脚类型 | 常见名称 |
|---------|---------|
| 输入执行 | `execute` |
| 输出执行 | `then` |
| 返回值 | `ReturnValue` |
| 字符串输入 | `InString` |
| 对象/目标 | `Target`, `self` |
| 条件 | `Condition` |
| True 分支 | `then` (Branch 节点) |
| False 分支 | `else` (Branch 节点) |

**模糊匹配：** 引脚名称支持子字符串匹配，例如 `"then"` 可以匹配 `"Then"` 或包含 then 的引脚。

---

### SetPinDefaultValue - 设置引脚默认值

设置引脚的默认值。

```python
import unreal

bp = unreal.load_asset("/Game/Blueprints/BP_MyActor")

# 添加 PrintString 节点
print_node = unreal.ExGraphEditorLibrary.add_function_node_by_name(
    bp, "PrintString", None, 200, 0
)

# 设置要打印的字符串
unreal.ExGraphEditorLibrary.set_pin_default_value(
    print_node,
    "InString",           # 引脚名称
    "Hello from Python!"  # 默认值
)

# 添加 Delay 节点并设置延迟时间
delay_node = unreal.ExGraphEditorLibrary.add_function_node_by_name(
    bp, "Delay", None, 400, 0
)
unreal.ExGraphEditorLibrary.set_pin_default_value(
    delay_node,
    "Duration",
    "2.0"  # 2 秒延迟
)
```

---

### CompileBlueprint - 编译蓝图

编译蓝图使修改生效。**修改完成后必须调用！**

```python
import unreal

bp = unreal.load_asset("/Game/Blueprints/BP_MyActor")

# ... 进行各种修改 ...

# 编译蓝图
success = unreal.ExGraphEditorLibrary.compile_blueprint(bp)

if success:
    print("Blueprint compiled successfully!")
else:
    print("Blueprint compilation failed - check for errors")
```

---

## READ 操作

### GetAllNodes - 获取所有节点

获取蓝图 Event Graph 中的所有节点。

```python
import unreal

bp = unreal.load_asset("/Game/Blueprints/BP_MyActor")

nodes = unreal.ExGraphEditorLibrary.get_all_nodes(bp)

for node in nodes:
    title = unreal.ExGraphEditorLibrary.get_node_title(node)
    print(f"Node: {title}")
```

---

### GetNodePinNames - 获取节点引脚

获取节点的所有引脚名称和方向。

```python
import unreal

bp = unreal.load_asset("/Game/Blueprints/BP_MyActor")

# 获取某个节点
nodes = unreal.ExGraphEditorLibrary.get_all_nodes(bp)
if nodes:
    node = nodes[0]
    pins = unreal.ExGraphEditorLibrary.get_node_pin_names(node)

    for pin_info in pins:
        print(pin_info)  # 格式: "In:execute" 或 "Out:ReturnValue"
```

---

### GetNodeTitle - 获取节点标题

获取节点的显示标题。

```python
import unreal

bp = unreal.load_asset("/Game/Blueprints/BP_MyActor")

nodes = unreal.ExGraphEditorLibrary.get_all_nodes(bp)
for node in nodes:
    title = unreal.ExGraphEditorLibrary.get_node_title(node)
    print(f"Node title: {title}")
```

---

### GetBlueprintVariables - 获取蓝图变量

获取蓝图中定义的所有成员变量名称。

```python
import unreal

bp = unreal.load_asset("/Game/Blueprints/BP_MyActor")

variables = unreal.ExGraphEditorLibrary.get_blueprint_variables(bp)

for var_name in variables:
    print(f"Variable: {var_name}")
```

---

## DELETE 操作

### DeleteNode - 删除节点

从蓝图中删除指定节点。

```python
import unreal

bp = unreal.load_asset("/Game/Blueprints/BP_MyActor")

# 获取所有节点
nodes = unreal.ExGraphEditorLibrary.get_all_nodes(bp)

# 找到并删除特定节点
for node in nodes:
    title = unreal.ExGraphEditorLibrary.get_node_title(node)
    if "PrintString" in title:
        unreal.ExGraphEditorLibrary.delete_node(bp, node)
        print(f"Deleted node: {title}")
        break

# 编译以应用更改
unreal.ExGraphEditorLibrary.compile_blueprint(bp)
```

---

### DisconnectPin - 断开引脚连接

断开指定引脚的所有连接。

```python
import unreal

bp = unreal.load_asset("/Game/Blueprints/BP_MyActor")

nodes = unreal.ExGraphEditorLibrary.get_all_nodes(bp)

# 断开某节点的输出执行引脚
for node in nodes:
    title = unreal.ExGraphEditorLibrary.get_node_title(node)
    if "BeginPlay" in title:
        unreal.ExGraphEditorLibrary.disconnect_pin(node, "then")
        print(f"Disconnected 'then' pin from {title}")
        break
```

---

## 完整示例

### 示例 1：创建带 BeginPlay -> PrintString 的蓝图

```python
import unreal

# 1. 创建蓝图
bp = unreal.ExGraphEditorLibrary.create_blueprint_asset(
    "/Game/Blueprints",
    "BP_HelloWorld"
)

if not bp:
    print("Failed to create blueprint")
else:
    # 2. 添加 BeginPlay 事件
    begin_play = unreal.ExGraphEditorLibrary.add_event_node(
        bp,
        unreal.Actor.static_class(),
        "ReceiveBeginPlay",
        0, 0
    )

    # 3. 添加 PrintString 节点
    print_node = unreal.ExGraphEditorLibrary.add_function_node_by_name(
        bp,
        "PrintString",
        None,
        300, 0
    )

    # 4. 设置打印内容
    unreal.ExGraphEditorLibrary.set_pin_default_value(
        print_node,
        "InString",
        "Hello, World!"
    )

    # 5. 连接节点
    unreal.ExGraphEditorLibrary.connect_nodes(
        begin_play, "then",
        print_node, "execute"
    )

    # 6. 编译
    if unreal.ExGraphEditorLibrary.compile_blueprint(bp):
        print("Blueprint created and compiled successfully!")

    # 7. 保存
    unreal.EditorAssetLibrary.save_asset(bp.get_path_name())
```

### 示例 2：创建带条件分支的蓝图

```python
import unreal

bp = unreal.load_asset("/Game/Blueprints/BP_MyActor")

# 添加布尔变量
unreal.ExGraphEditorLibrary.add_member_variable(bp, "bShouldPrint", "bool")
unreal.ExGraphEditorLibrary.compile_blueprint(bp)

# 添加节点
begin_play = unreal.ExGraphEditorLibrary.add_event_node(
    bp, unreal.Actor.static_class(), "ReceiveBeginPlay", 0, 0
)

get_var = unreal.ExGraphEditorLibrary.add_variable_get_node(
    bp, "bShouldPrint", 200, 100
)

branch = unreal.ExGraphEditorLibrary.add_branch_node(bp, 300, 0)

print_true = unreal.ExGraphEditorLibrary.add_function_node_by_name(
    bp, "PrintString", None, 500, -50
)
unreal.ExGraphEditorLibrary.set_pin_default_value(
    print_true, "InString", "Condition is TRUE"
)

print_false = unreal.ExGraphEditorLibrary.add_function_node_by_name(
    bp, "PrintString", None, 500, 100
)
unreal.ExGraphEditorLibrary.set_pin_default_value(
    print_false, "InString", "Condition is FALSE"
)

# 连接节点
unreal.ExGraphEditorLibrary.connect_nodes(begin_play, "then", branch, "execute")
unreal.ExGraphEditorLibrary.connect_nodes(get_var, "bShouldPrint", branch, "Condition")
unreal.ExGraphEditorLibrary.connect_nodes(branch, "then", print_true, "execute")
unreal.ExGraphEditorLibrary.connect_nodes(branch, "else", print_false, "execute")

# 编译
unreal.ExGraphEditorLibrary.compile_blueprint(bp)
```

### 示例 3：修改现有蓝图

```python
import unreal

bp = unreal.load_asset("/Game/Blueprints/BP_Existing")

# 获取所有现有节点
nodes = unreal.ExGraphEditorLibrary.get_all_nodes(bp)
print(f"Found {len(nodes)} nodes")

# 打印节点信息
for node in nodes:
    title = unreal.ExGraphEditorLibrary.get_node_title(node)
    pins = unreal.ExGraphEditorLibrary.get_node_pin_names(node)
    print(f"\nNode: {title}")
    print(f"  Pins: {pins}")

# 查找 BeginPlay 节点
begin_play_node = None
for node in nodes:
    if "BeginPlay" in unreal.ExGraphEditorLibrary.get_node_title(node):
        begin_play_node = node
        break

if begin_play_node:
    # 在 BeginPlay 后添加新节点
    new_print = unreal.ExGraphEditorLibrary.add_function_node_by_name(
        bp, "PrintString", None, 400, 0
    )
    unreal.ExGraphEditorLibrary.set_pin_default_value(
        new_print, "InString", "Added by Python!"
    )

    # 断开原有连接
    unreal.ExGraphEditorLibrary.disconnect_pin(begin_play_node, "then")

    # 建立新连接
    unreal.ExGraphEditorLibrary.connect_nodes(
        begin_play_node, "then",
        new_print, "execute"
    )

    unreal.ExGraphEditorLibrary.compile_blueprint(bp)
    print("Blueprint modified successfully!")
```

---

## 最佳实践

### 1. 始终编译修改后的蓝图

```python
# 所有修改完成后
unreal.ExGraphEditorLibrary.compile_blueprint(bp)
```

### 2. 添加变量后先编译再使用

```python
# 添加变量
unreal.ExGraphEditorLibrary.add_member_variable(bp, "MyVar", "float")

# 必须编译才能使用变量节点
unreal.ExGraphEditorLibrary.compile_blueprint(bp)

# 现在可以添加变量节点了
get_node = unreal.ExGraphEditorLibrary.add_variable_get_node(bp, "MyVar", 0, 0)
```

### 3. 使用有意义的节点位置

```python
# 按照从左到右、从上到下的顺序排列节点
event_x, event_y = 0, 0
first_node_x = event_x + 250  # 每个节点间隔约 250
second_node_x = first_node_x + 250
```

### 4. 检查操作返回值

```python
node = unreal.ExGraphEditorLibrary.add_function_node_by_name(bp, "PrintString", None, 0, 0)
if node is None:
    print("Failed to create node!")
```

### 5. 保存蓝图资产

```python
# 修改完成后保存
unreal.EditorAssetLibrary.save_asset(bp.get_path_name())
```

---

## 错误排查

| 问题 | 可能原因 | 解决方案 |
|-----|---------|---------|
| 函数节点创建失败 | 函数名拼写错误 | 检查 UE5 中的正确函数名 |
| 变量节点创建失败 | 变量不存在或未编译 | 先添加变量并编译 |
| 连接失败 | 引脚名称错误或类型不匹配 | 使用 `get_node_pin_names()` 查看可用引脚 |
| 编译失败 | 蓝图有错误 | 在 UE5 编辑器中检查编译错误 |
| 节点位置重叠 | 坐标相同 | 调整 NodePosX/NodePosY |

---

## API 参考速查表

| 函数 | 用途 |
|-----|------|
| `create_blueprint_asset(path, name, parent)` | 创建蓝图 |
| `add_event_node(bp, class, name, x, y)` | 添加事件节点 |
| `add_call_function_node(bp, class, name, x, y)` | 添加函数节点（精确） |
| `add_function_node_by_name(bp, name, class, x, y)` | 添加函数节点（按名称） |
| `add_branch_node(bp, x, y)` | 添加分支节点 |
| `add_member_variable(bp, name, type)` | 添加成员变量 |
| `add_variable_get_node(bp, name, x, y)` | 添加变量 Getter |
| `add_variable_set_node(bp, name, x, y)` | 添加变量 Setter |
| `connect_nodes(nodeA, pinA, nodeB, pinB)` | 连接节点 |
| `set_pin_default_value(node, pin, value)` | 设置引脚默认值 |
| `compile_blueprint(bp)` | 编译蓝图 |
| `get_all_nodes(bp)` | 获取所有节点 |
| `get_node_pin_names(node)` | 获取节点引脚 |
| `get_node_title(node)` | 获取节点标题 |
| `get_blueprint_variables(bp)` | 获取变量列表 |
| `delete_node(bp, node)` | 删除节点 |
| `disconnect_pin(node, pin)` | 断开引脚连接 |
