# Development Guildelines

## Available MCP Tools

UE-MCP 服务器提供以下工具：

### 项目管理
| 工具 | 描述 |
|------|------|
| `project_set_path` | 设置 UE5 项目目录（仅限 claude-ai/Automatic-Testing 客户端） |
| `project_build` | 使用 UnrealBuildTool 构建项目（支持 Editor、Game 等目标） |

### 编辑器控制
| 工具 | 描述 |
|------|------|
| `editor_launch` | 启动绑定项目的 Unreal Editor |
| `editor_status` | 获取当前编辑器状态（not_running/starting/ready/stopped） |
| `editor_stop` | 停止运行中的编辑器 |
| `editor_configure` | 检查和修复项目的 Python 远程执行配置 |

### Python 执行
| 工具 | 描述 |
|------|------|
| `editor_execute` | 在编辑器中执行 Python 代码 |
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

            # Launch editor
            result = await asyncio.wait_for(
                session.call_tool("editor_launch", {"wait": True, "wait_timeout": 300}),
                timeout=360
            )
            if not json.loads(result.content[0].text).get("success"):
                print("Failed to launch editor")
                return

            print("Editor launched!")
            await asyncio.sleep(3)

            result = await session.call_tool(...
```
