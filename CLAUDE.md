# Development Guildelines

## Available MCP Tools

UE-MCP 服务器提供以下工具：

### 项目管理
| 工具 | 描述 |
|------|------|
| `project_set_path` | 设置 UE5 项目目录 |
| `project_build` | 使用 UnrealBuildTool 构建项目（支持 Editor、Game 等目标，包括 C++ 插件） |

### 编辑器控制
| 工具 | 描述 |
|------|------|
| `editor_launch` | 启动绑定项目的 Unreal Editor（自动安装 ExtraPythonAPIs 插件） |
| `editor_status` | 获取当前编辑器状态（not_running/starting/ready/stopped） |
| `editor_stop` | 停止运行中的编辑器 |
| `editor_configure` | 检查和修复项目的 Python 远程执行配置（包括 ExtraPythonAPIs 插件安装） |
| `editor_load_level` | 加载指定关卡到编辑器（使用 LevelEditorSubsystem） |

### Python 执行
| 工具 | 描述 |
|------|------|
| `editor_execute_code` | 在编辑器中执行 Python 代码 |
| `editor_execute_script` | 在编辑器中执行 Python 脚本文件 |
| `editor_pip_install` | 在 UE5 的嵌入式 Python 环境中安装包 |

### PIE (Play-In-Editor) 控制
| 工具 | 描述 |
|------|------|
| `editor_start_pie` | 启动 PIE 会话 |
| `editor_stop_pie` | 停止当前 PIE 会话 |
| `editor_trace_actors_in_pie` | 在 PIE 会话期间追踪指定 actors 的位置、旋转、速度 |

### 截图捕获
| 工具 | 描述 |
|------|------|
| `editor_capture_orbital` | 使用 SceneCapture2D 围绕目标位置捕获多角度截图 |
| `editor_capture_pie` | 在 PIE 会话期间自动捕获截图 |
| `editor_capture_window` | 使用 Windows API 捕获编辑器窗口截图（仅 Windows） |

### 资产操作
| 工具 | 描述 |
|------|------|
| `editor_asset_open` | 在编辑器中打开资产（蓝图编辑器、材质编辑器等） |
| `editor_asset_diagnostic` | 对 UE5 资产运行诊断，检测常见问题 |
| `editor_asset_inspect` | 获取资产属性 |

---

## 脚本热重载 (Hot-Reload)

### 核心机制：EXECUTE_FILE 模式

所有 MCP 工具的底层实现都是独立 Python 脚本，位于 `src/ue_mcp/extra/scripts/`。这些脚本支持**真正的热重载**：修改脚本后无需重启 MCP 服务器或 UE5 编辑器，立即生效。

**执行方式（两步执行）：**
1. **参数注入** (EXECUTE_STATEMENT) - MCP 将参数注入到 `sys.argv` 和 `builtins.__PARAMS__`
2. **文件执行** (EXECUTE_FILE) - UE5 从磁盘直接加载并执行脚本文件

**关键特性：**
- 脚本文件在执行时从磁盘读取，而非服务器启动时缓存
- 修改脚本 → 保存 → 调用工具 → 修改立即生效
- 无需重启 MCP 服务器或 UE5 编辑器

### 热重载工作流程

```python
# 1. 修改脚本：编辑 src/ue_mcp/extra/scripts/asset_open.py
def main():
    params = get_params(defaults=DEFAULTS, required=REQUIRED)
    print(f"DEBUG: Opening {params['asset_path']}")  # 添加调试输出
    # ... 现有代码 ...

# 2. 保存文件：Ctrl+S

# 3. 调用工具（无需任何重启）
result = editor_asset_open(asset_path="/Game/BP_Test")

# 4. 修改立即生效 - 看到调试输出！
```

**开发迭代流程：**
```
编辑脚本 → 保存 → 测试 → 看到效果 → 重复
(无需任何重启操作！)
```

### 可用脚本列表

所有脚本位于 `src/ue_mcp/extra/scripts/`：

| 脚本 | MCP 工具 | CLI 用法示例 |
|------|---------|-------------|
| `asset_open.py` | `editor_asset_open` | `python asset_open.py --asset-path=/Game/BP_Test --tab-id=Inspector` |
| `pie_control.py` | `editor_start_pie`, `editor_stop_pie` | `python pie_control.py --command=start` |
| `level_load.py` | `editor_load_level` | `python level_load.py --level-path=/Game/Maps/MyLevel` |
| `api_search.py` | `python_api_search` | `python api_search.py --mode=list_classes --query=*Actor*` |
| `ue_mcp_capture/capture_orbital.py` | `editor_capture_orbital` | `python capture_orbital.py --level=/Game/Maps/Test --target-x=0 ...` |
| `ue_mcp_capture/capture_pie.py` | `editor_capture_pie` | `python capture_pie.py --output-dir=./screenshots --level=/Game/Maps/Test` |
| `ue_mcp_capture/capture_window.py` | `editor_capture_window` | `python capture_window.py --level=/Game/Maps/Test --output-file=./screen.png` |
| `ue_mcp_capture/trace_actors_pie.py` | `editor_trace_actors_in_pie` | `python trace_actors_pie.py --output-dir=./trace --level=/Game/Maps/Test` |
| `ue_mcp_capture/execute_in_tick.py` | `editor_pie_execute_in_tick` | 参见脚本内文档 |
| `diagnostic/diagnostic_runner.py` | `editor_asset_diagnostic` | `python diagnostic_runner.py --asset-path=/Game/Maps/TestLevel` |
| `diagnostic/inspect_runner.py` | `editor_asset_inspect` | `python inspect_runner.py --asset-path=/Game/Meshes/Cube` |

### 参数传递机制

脚本支持两种参数访问方式：

**1. MCP 模式（自动）：**
```python
from ue_mcp_capture.utils import get_params

# MCP 调用时自动注入参数
params = get_params(defaults=DEFAULTS, required=REQUIRED)
asset_path = params["asset_path"]

# 等价于：
# builtins.__PARAMS__ = {'asset_path': '/Game/BP_Test', 'tab_id': 'Inspector'}
# sys.argv = ['asset_open.py', '--asset-path', '/Game/BP_Test', '--tab-id', 'Inspector']
```

**2. CLI 模式（手动）：**
```python
# 在 UE5 Python 控制台直接执行
import sys
sys.argv = ['asset_open.py', '--asset-path', '/Game/BP_Test', '--tab-id', 'Inspector']
exec(open(r'D:\code\ue-mcp\src\ue_mcp\extra\scripts\asset_open.py').read())
```

### 开发建议

1. **快速迭代**：修改脚本 → 保存 → 测试 → 重复（无需重启）
2. **调试输出**：随时添加 `print()` 语句调试，修改立即生效
3. **使用 argparse**：脚本可使用标准 `argparse` 解析 `sys.argv`
4. **保持简洁**：复杂逻辑放入 `site-packages` 模块，脚本作为入口点
5. **纯 JSON 输出**：脚本输出纯 JSON（无特殊标记），MCP 解析最后一个有效 JSON 对象

**脚本模板：**
```python
"""
脚本描述和用法示例。

Parameters:
    param1: 必需参数描述
    param2: 可选参数描述
"""

import json
import unreal
from ue_mcp_capture.utils import get_params

DEFAULTS = {"param2": None}
REQUIRED = ["param1"]

def main():
    params = get_params(defaults=DEFAULTS, required=REQUIRED)
    # ... 实现逻辑 ...
    result = {"success": True, "data": data}
    print(json.dumps(result))  # 输出纯 JSON

if __name__ == "__main__":
    main()
```

**详细文档：** 参见 `src/ue_mcp/extra/scripts/README.md`

---

## ExtraPythonAPIs Plugin

UE-MCP 包含一个 C++ 插件 `ExtraPythonAPIs`，提供 UE5 默认未暴露给 Python 的额外 API。

### 自动安装

- 当 `editor_launch` 或 `editor_configure` 执行时，插件会自动从 `src/ue_mcp/extra/plugin/ExtraPythonAPIs` 复制到项目的 `Plugins` 目录
- 如果插件是新安装的（二进制文件不存在），`editor_launch` 会返回 `requires_build: True`，需要先调用 `project_build` 编译插件

### 可用的 Python API

#### UExBlueprintComponentLibrary
操作蓝图组件的工具函数：

| 函数 | 描述 |
|------|------|
| `set_component_socket_attachment(handle, socket_name)` | 设置组件的骨骼/插槽附加点 |
| `get_component_socket_attachment(handle)` | 获取组件当前的附加插槽名称 |
| `setup_component_attachment(child, parent, socket)` | 设置组件的父子附加关系及插槽 |

#### UExSlateTabLibrary
操作 Slate UI Tab 的工具函数（用于在蓝图编辑器中切换视图）：

| 函数 | 描述 |
|------|------|
| `invoke_blueprint_editor_tab(blueprint, tab_id)` | 在蓝图编辑器中打开/聚焦指定 Tab |
| `invoke_asset_editor_tab(asset, tab_id)` | 在任意资产编辑器中打开/聚焦指定 Tab |
| `get_blueprint_editor_tab_ids()` | 获取所有可用的蓝图编辑器 Tab ID |
| `switch_to_viewport_mode(blueprint)` | 切换到 Viewport/组件视图 |
| `switch_to_graph_mode(blueprint)` | 切换到 Event Graph 视图 |
| `focus_details_panel(blueprint)` | 聚焦 Details 面板 |
| `focus_my_blueprint_panel(blueprint)` | 聚焦 My Blueprint 面板 |
| `open_construction_script(blueprint)` | 打开 Construction Script |
| `open_compiler_results(blueprint)` | 打开编译结果面板 |
| `is_asset_editor_open(asset)` | 检查资产编辑器是否已打开 |
| `focus_asset_editor_window(asset)` | 聚焦资产编辑器窗口 |

### Blueprint Editor Tab IDs

| Tab ID | 描述 |
|--------|------|
| `SCSViewport` | Viewport/组件视图 |
| `GraphEditor` | Event Graph 等图表编辑器 |
| `Inspector` | Details 面板 |
| `MyBlueprint` | My Blueprint 面板 |
| `PaletteList` | Palette 面板 |
| `CompilerResults` | 编译结果 |
| `FindResults` | 查找结果 |
| `ConstructionScriptEditor` | Construction Script |
| `Debug` | 调试面板 |
| `BookmarkList` | 书签 |
| `TimelineEditor` | 时间轴编辑器 |

### 使用 ThirdPersonTemplate 项目来测试代码片段和脚本

./tests/fixtures/ThirdPersonTemplate

API调用、简短的代码、完整的脚本，都可以在这个测试用UE项目中运行，进行测试

### Python 使用示例

```python
import unreal

# 加载蓝图
blueprint = unreal.load_asset('/Game/MyBlueprint')

# 切换到 Viewport 模式
unreal.ExSlateTabLibrary.switch_to_viewport_mode(blueprint)

# 切换到 Graph 模式
unreal.ExSlateTabLibrary.switch_to_graph_mode(blueprint)

# 打开指定 Tab
unreal.ExSlateTabLibrary.invoke_blueprint_editor_tab(blueprint, unreal.Name("CompilerResults"))
```

---

## UE5 Python API 注意事项

### Deprecated API - 不要使用

以下 API 已废弃，**禁止在新代码中使用**：

| Deprecated API | 替代方案 |
|----------------|----------|
| `unreal.EditorLevelLibrary.new_level()` | `level_subsystem.new_level()` |
| `unreal.EditorLevelLibrary.save_current_level()` | `level_subsystem.save_current_level()` |
| `unreal.EditorLevelLibrary.load_level()` | `level_subsystem.load_level()` |

### 正确的 Subsystem 获取方式

```python
import unreal

# 获取 LevelEditorSubsystem（用于关卡操作）
level_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)

# 获取 EditorActorSubsystem（用于 Actor 操作）
actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)

# 创建新关卡
level_subsystem.new_level("/Game/Maps/MyLevel")

# 保存当前关卡
level_subsystem.save_current_level()
```

### 物理模拟设置

为 Actor 启用物理模拟时，必须按以下顺序设置：

```python
mesh_comp = actor.get_component_by_class(unreal.StaticMeshComponent)

# 1. 先设置 Mobility 为 Movable（必须！否则物理不生效）
mesh_comp.set_mobility(unreal.ComponentMobility.MOVABLE)

# 2. 启用物理模拟
mesh_comp.set_simulate_physics(True)

# 3. 设置碰撞
mesh_comp.set_collision_enabled(unreal.CollisionEnabled.QUERY_AND_PHYSICS)
```

