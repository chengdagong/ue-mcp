# Development Guildelines

## Available MCP Tools

UE-MCP 服务器提供以下工具：

### 项目管理
| 工具 | 描述 |
|------|------|
| `project_set_path` | 设置 UE5 项目目录（仅限 claude-ai/Automatic-Testing 客户端） |
| `project_build` | 使用 UnrealBuildTool 构建项目（支持 Editor、Game 等目标，包括 C++ 插件） |

### 编辑器控制
| 工具 | 描述 |
|------|------|
| `editor_launch` | 启动绑定项目的 Unreal Editor（自动安装 ExtraPythonAPIs 插件） |
| `editor_status` | 获取当前编辑器状态（not_running/starting/ready/stopped） |
| `editor_stop` | 停止运行中的编辑器 |
| `editor_configure` | 检查和修复项目的 Python 远程执行配置（包括 ExtraPythonAPIs 插件安装） |

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

### 截图捕获
| 工具 | 描述 |
|------|------|
| `editor_capture_orbital` | 使用 SceneCapture2D 围绕目标位置捕获多角度截图 |
| `editor_capture_pie` | 在 PIE 会话期间自动捕获截图 |
| `editor_capture_window` | 使用 Windows API 捕获编辑器窗口截图（仅 Windows） |

### 资产诊断与检查
| 工具 | 描述 |
|------|------|
| `editor_asset_diagnostic` | 对 UE5 资产运行诊断，检测常见问题 |
| `editor_asset_inspect` | 获取资产属性 |

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

## How to write testing scripts

### Use MCP client named Automatic-Testing

UE-MCP has two modes:

- If the client's name is claude-ai or Automatic-Testing, then after MCP server starts, tool project_set_path could be called to set the path to the UE project
- If not, MCP server searches UE5 .uproject in current working directory and launches UE editor automatically, and would fail if it's not a UE5 project directory.

So, any testing script should name the MCP client it created as Automatic-Testing and then set the project path. Refer to following code:

```python
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(
            read, write,
            client_info=Implementation(name="Automatic-Testing", version="1.0.0")
        ) as session:
            await session.initialize()

            # Set project path
            result = await session.call_tool(
                "project_set_path",
                {"project_path": r"/PATH/TO/UE/PROJECT"}
            )

            # Launch editor (may require build if ExtraPythonAPIs plugin was installed)
            result = await asyncio.wait_for(
                session.call_tool("editor_launch", {"wait": True, "wait_timeout": 300}),
                timeout=360
            )
            data = json.loads(result.content[0].text)

            # If build is required (new C++ plugin installed), build first then retry
            if not data.get("success") and data.get("requires_build"):
                print("Building project (ExtraPythonAPIs plugin needs compilation)...")
                build_result = await session.call_tool(
                    "project_build",
                    {"target": "Editor", "wait": True}
                )
                if not json.loads(build_result.content[0].text).get("success"):
                    print("Failed to build project")
                    return

                # Retry launch after build
                result = await asyncio.wait_for(
                    session.call_tool("editor_launch", {"wait": True, "wait_timeout": 300}),
                    timeout=360
                )
                data = json.loads(result.content[0].text)

            if not data.get("success"):
                print("Failed to launch editor")
                return

            print("Editor launched!")
            await asyncio.sleep(3)

            result = await session.call_tool(...
```
