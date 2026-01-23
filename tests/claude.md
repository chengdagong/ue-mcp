# UE-MCP 测试套件说明

本目录包含 UE-MCP 项目的所有自动化测试。测试分为单元测试和集成测试两类。

## 测试执行要求

- **Python 环境**: Python 3.10+
- **测试框架**: pytest + mcp-pytest 插件
- **UE5 要求**: 集成测试需要 UE5 安装并可用
- **测试项目**: 使用 ThirdPersonTemplate 测试项目（位于 `fixtures/ThirdPersonTemplate/`）

## 测试运行命令

```bash
# 运行所有测试（简洁模式，不显示日志）
pytest tests/

# 运行所有测试（详细模式，显示测试名称和日志）
pytest tests/ -v

# 运行特定测试文件
pytest tests/test_capture_mcp.py -v

# 只运行集成测试
pytest tests/ -v -m integration

# 只运行单元测试（不需要 UE5）
pytest tests/ -v -m "not integration"

# 跳过慢速测试
pytest tests/ -v -m "not slow"
```

### 命令参数说明

- **无参数**: 简洁模式，只显示测试进度（PASSED/FAILED）
- **`-v` (verbose)**: 详细模式，显示每个测试的完整名称和实时日志输出
- **`-s` (no capture)**: 禁用输出捕获（通常不需要，`-v` 已足够）
- **`-m <marker>`**: 只运行带特定标记的测试

---

## 测试日志系统

### 日志输出控制

- **简洁模式**（不带 `-v`）：只显示测试进度，不显示日志
- **详细模式**（带 `-v`）：显示实时日志输出和详细测试信息

### 日志文件

每次测试运行会自动生成一个带时间戳的日志文件：
```
tests/test_output/log/pytest-{YYYYMMDD_HHMMSS}.log
```

**特点**：
- 每次运行生成独立的日志文件，不会覆盖
- 包含完整的 DEBUG 级别日志
- 测试结束后显示日志文件路径，方便查看
- 日志文件会被保留，便于事后分析

**示例输出**：
```bash
============================== 6 passed in 0.02s ==============================
================================ Test Log File ================================
Log file: D:\Code\ue-mcp\tests\test_output\log\pytest-20260123_205757.log
View with: cat D:\Code\ue-mcp\tests\test_output\log\pytest-20260123_205757.log
```

---

## 测试文件说明

### 1. test_capture_mcp.py
**截图捕获工具集成测试**

测试 UE-MCP 提供的三种截图捕获工具：
- `editor_capture_orbital`: 围绕目标位置的多角度截图捕获（使用 SceneCapture2D）
- `editor_capture_pie`: PIE 会话期间的截图捕获（支持多角度和指定 Actor）
- `editor_capture_window`: Windows API 窗口截图捕获（仅 Windows）

**测试内容**:
- 验证工具正确列出
- 测试 orbital 捕获的多角度截图生成
- 测试 window 捕获的窗口截图
- 测试各种捕获参数验证（level、output_dir、asset_path 等）
- 验证截图文件正确生成且大小合理

**依赖**: 需要运行中的 UE5 编辑器和有效的测试关卡

---

### 2. test_client_init.py
**MCP 客户端初始化测试**

测试 MCP 服务器的基础功能和工具可见性：
- 工具列表功能（`list_tools`）
- `project_set_path` 工具的可见性（用于自动测试客户端）
- 项目初始化后的基础工具操作

**测试内容**:
- 验证核心工具正确注册（editor_launch、editor_stop、editor_status 等）
- 确认 project_set_path 对自动测试客户端可见
- 测试未启动编辑器时的 editor_status 功能
- 测试 editor_configure 的配置检查功能

**依赖**: 仅需要 MCP 服务器启动，无需运行编辑器

---

### 3. test_code_inspector.py
**代码检查器单元测试**

测试 `code_inspector` 模块的代码静态分析功能：
- `BlockingCallChecker`: 检测阻塞调用（如 `time.sleep()`）
- `CodeInspector`: 代码检查器框架
- `InspectionResult`: 检查结果格式化

**测试内容**:
- 检测各种形式的 `time.sleep()` 调用（直接调用、别名导入、from import）
- 验证警告级别和错误级别的分类
- 测试自定义检查器注册机制
- 测试语法错误处理
- 验证检查结果的格式化输出

**依赖**: 纯单元测试，无外部依赖

---

### 4. test_diagnostic_mcp.py
**资产诊断工具集成测试**

测试 `editor_asset_diagnostic` 工具对 UE5 资产的诊断功能：
- 对 Level、Blueprint、Material 等资产类型运行诊断
- 检测常见问题（缺失引用、性能问题、配置错误等）
- 返回错误和警告列表

**测试内容**:
- 验证 diagnostic 工具正确列出
- 测试对关卡资产的诊断
- 测试参数验证（asset_path 必填）
- 验证诊断结果包含必要字段（asset_type、errors、warnings、issues）

**依赖**: 需要运行中的 UE5 编辑器

---

### 5. test_editor_log.py
**编辑器日志功能测试**

测试编辑器日志文件的创建、读取和管理：
- 编辑器启动时创建唯一日志文件（项目名+时间戳）
- `editor_status` 返回 log_file_path
- `editor_read_log` 读取日志内容（支持 tail_lines 参数）

**测试内容**:
- 验证日志文件命名格式（`ue-mcp-{project}-{timestamp}.log`）
- 确认日志文件被正确创建
- 测试完整日志内容读取
- 测试 tail_lines 参数限制输出
- 验证日志包含 UE5 日志标记（LogInit、LogConfig 等）

**依赖**: 需要运行中的 UE5 编辑器

---

### 6. test_fuzzy_actor_matching.py
**模糊 Actor 匹配测试**

测试 PIE 捕获中对 `target_actor` 参数的模糊匹配功能：

**匹配优先级**:
1. 对象名称精确匹配
2. Label 精确匹配
3. 类名精确匹配
4. 对象名称部分匹配（包含）
5. Label 部分匹配（包含）
6. 类名部分匹配（包含）

**测试内容**:
- 测试精确 Label 匹配（如 "PlayerStart"）
- 测试部分 Label 匹配（如 "Start" 匹配 "PlayerStart"）
- 测试多个匹配时返回错误和 `matched_actors` 列表
- 测试无匹配时返回错误和 `available_actors` 列表
- 测试类名匹配的多结果场景

**依赖**: 需要运行中的 UE5 编辑器和包含多个 Actor 的测试关卡

---

### 7. test_inspect_screenshot.py
**资产检查截图功能测试**

测试 `editor_asset_inspect` 工具的截图捕获功能：
- Blueprint 资产检查时自动捕获 Viewport 截图
- Level 资产检查时自动捕获关卡截图
- 截图保存到系统临时目录

**测试内容**:
- 测试 Blueprint 资产检查返回 screenshot_path
- 测试 Level 资产检查返回 screenshot_path
- 测试 GameMode Blueprint 的截图字段
- 验证截图文件存在且非空
- 处理截图失败场景（headless 系统）返回 screenshot_error

**依赖**: 需要运行中的 UE5 编辑器

---

### 8. test_multi_instance_isolation.py
**多实例隔离测试**

测试多个 `EditorManager` 实例同时运行时的隔离性：
- 每个管理器启动独立的编辑器进程
- 每个管理器使用独立的多播端口
- 远程代码执行在正确的编辑器实例中运行

**测试内容**:
- 验证两个编辑器有不同的 PID
- 验证使用不同的多播端口（动态分配，>= 6767）
- 验证代码执行在正确的编辑器实例中
- 测试交错执行保持隔离
- 测试重连后保持隔离

**依赖**: 需要 UE5 安装，会启动**两个**编辑器实例（需要约 16GB 内存）

---

### 9. test_pie_mcp.py
**PIE 控制工具测试**

测试 Play-In-Editor（PIE）的启动和停止控制：
- `editor_start_pie`: 启动 PIE 会话
- `editor_stop_pie`: 停止 PIE 会话

**测试内容**:
- 验证 PIE 工具正确列出
- 测试基本的 PIE 启动和停止循环
- 测试重复启动 PIE 报告 "already running"
- 测试在未运行时停止 PIE 报告 "not running"

**依赖**: 需要运行中的 UE5 编辑器

---

### 10. test_port_allocator.py
**端口分配器单元测试**

测试 `port_allocator` 模块的动态端口分配功能：
- `_is_port_available()`: 检查端口是否可用
- `find_available_port()`: 查找可用端口

**测试内容**:
- 测试空闲端口被识别为可用
- 测试已绑定端口被识别为不可用
- 测试 find_available_port 返回指定范围内的端口
- 测试多次调用返回不同端口（当之前的被占用时）
- 测试自定义端口范围参数

**依赖**: 纯单元测试，无外部依赖

---

### 11. test_slate_tab_api.py
**Slate UI Tab 切换 API 测试**

测试 `ExtraPythonAPIs` 插件提供的 Slate Tab 切换功能：
- `ExSlateTabLibrary`: UE5 蓝图编辑器 Tab 切换 API
- 支持在 Viewport、Graph、Details 等视图间切换

**测试内容**:
- 验证 ExSlateTabLibrary 在 Python 中可用
- 测试 `get_blueprint_editor_tab_ids()` 返回可用 Tab ID
- 测试打开蓝图并切换到不同 Tab（Viewport、Graph）
- 测试聚焦 Details 和 MyBlueprint 面板
- 测试通过 Tab ID 调用特定 Tab
- 测试 `is_asset_editor_open()` 检查编辑器状态

**依赖**: 需要运行中的 UE5 编辑器，且 ExtraPythonAPIs 插件已编译安装

---

### 12. test_trace_actors_mcp.py
**Actor 追踪工具测试**

测试 `editor_trace_actors_in_pie` 工具在 PIE 期间追踪 Actor 的功能：
- 记录 Actor 的位置、旋转、速度
- 可选截图捕获（多角度或单角度）
- 输出结构化的 JSON 数据

**测试内容**:
- 验证追踪工具正确列出
- 测试单个 Actor 追踪（BP_ThirdPersonCharacter）
- 测试不存在的 Actor 报告 actors_not_found
- 测试多个 Actor 同时追踪（包含存在和不存在的）
- 测试带截图的追踪（多角度）
- 测试单角度截图追踪
- 验证输出目录结构（metadata.json、actor 子目录、sample 子目录、transform.json、screenshots）

**输出结构**:
```
output_dir/
├── metadata.json
└── ActorName/
    ├── sample_at_tick_6/
    │   ├── transform.json
    │   └── screenshots/
    │       ├── front.png
    │       ├── side.png
    │       ├── back.png
    │       └── perspective.png
    └── sample_at_tick_12/
        └── ...
```

**依赖**: 需要运行中的 UE5 编辑器

---

## 测试 Fixtures

### Pytest Fixtures (conftest.py)

| Fixture | Scope | 说明 |
|---------|-------|------|
| `tool_caller` | function | 基础 MCP 工具调用器（未初始化项目） |
| `initialized_tool_caller` | session | 已初始化项目的工具调用器 |
| `running_editor` | session | **共享的运行中编辑器实例**（所有测试共享以减少启动次数） |
| `test_output_dir` | function | 测试输出目录（自动清理） |
| `test_level_path` | session | 测试关卡路径 |

### 测试项目 Fixture

位于 `tests/fixtures/ThirdPersonTemplate/`：
- 标准 UE5 第三人称模板项目
- 包含 BP_ThirdPersonCharacter、BP_ThirdPersonGameMode 等资产
- 用于集成测试和功能验证

---

## 测试架构说明

### 共享编辑器实例

**重要**: 为了减少测试时间，所有集成测试共享同一个 UE5 编辑器实例（`running_editor` fixture，session 级别）。

**优点**:
- 大幅减少测试时间（避免每个测试启动/关闭编辑器）
- 减少系统资源占用

**注意事项**:
- 测试之间可能存在状态共享（需要注意清理）
- 测试失败可能影响后续测试
- 测试应该尽量保持幂等性

### 测试数据隔离

每个测试使用独立的输出目录：
- 通过 `test_output_dir` fixture 提供
- 自动创建和清理
- 位于 `tests/fixtures/ThirdPersonTemplate/Saved/Tests/` 下

---

## 测试标记 (Markers)

| Marker | 说明 |
|--------|------|
| `@pytest.mark.integration` | 集成测试（需要 UE5） |
| `@pytest.mark.slow` | 慢速测试（运行时间较长） |
| `@pytest.mark.asyncio` | 异步测试（使用 async/await） |

**使用示例**:
```python
@pytest.mark.integration
@pytest.mark.slow
class TestSlowIntegration:
    @pytest.mark.asyncio
    async def test_something(self, running_editor):
        ...
```

---

## 故障排查

当测试失败时，请查看以下日志以获取详细错误信息：

1. **Pytest 日志文件**: 测试结束后显示的日志文件路径
   ```
   tests/test_output/log/pytest-{timestamp}.log
   ```
   
2. **UE5 Editor 日志**: 编辑器运行时生成的日志
   ```
   tests/fixtures/ThirdPersonTemplate/Saved/Logs/ue-mcp-*.log
   ```

**提示**: 使用 `-v` 参数运行测试可以在终端实时查看详细日志输出。

---

## 持续集成

推荐 CI/CD 配置：

```yaml
# 示例 GitHub Actions 配置
- name: Run unit tests
  run: pytest tests/ -v -m "not integration"

- name: Run integration tests (with UE5)
  run: pytest tests/ -v -m integration
  timeout-minutes: 30

- name: Upload test logs
  if: always()
  uses: actions/upload-artifact@v3
  with:
    name: test-logs
    path: tests/test_output/log/
```

**注意**: 
- 集成测试需要 UE5 安装环境，CI 环境需要相应配置
- 使用 `-v` 参数可以在 CI 日志中查看详细测试过程
- 上传日志文件便于事后分析失败原因

---

## 贡献指南

### 添加新测试

1. **命名规范**: `test_<feature>_<type>.py`
   - 例如: `test_asset_importer_mcp.py`

2. **使用 Fixtures**: 优先使用现有 fixtures，避免重复创建编辑器实例

3. **添加标记**: 为测试添加适当的 markers（integration/slow）

4. **文档**: 在测试文件顶部添加 docstring 说明测试目的和用法

5. **清理**: 确保测试后清理临时文件和状态

### 测试质量要求

- **独立性**: 测试应该独立运行，不依赖其他测试的执行顺序
- **可重复**: 测试结果应该可重复，不受环境变化影响
- **断言清晰**: 使用清晰的断言消息，便于定位问题
- **超时设置**: 为长时间操作设置合理的超时
- **日志输出**: 使用 `logging.getLogger(__name__)` 记录关键信息，便于调试
  ```python
  import logging
  logger = logging.getLogger(__name__)
  
  logger.info("Test started")
  logger.debug("Detailed debug info")
  ```

---

## 参考资料

- [pytest 文档](https://docs.pytest.org/)
- [mcp-pytest 插件](https://github.com/anthropics/anthropic-tools/tree/main/mcp-pytest)
- [UE-MCP 项目文档](../README.md)
- [ExtraPythonAPIs 插件文档](../CLAUDE.md#extrapythonapis-plugin)
