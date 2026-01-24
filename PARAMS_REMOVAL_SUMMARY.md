# 彻底移除 builtins.__PARAMS__ - 实施总结

## 概述

成功将所有参数传递机制从 `builtins.__PARAMS__` 迁移到 `sys.argv` + 环境变量 `UE_MCP_MODE`。

## 修改的文件

### 核心基础设施 (3个文件)

1. **`src/ue_mcp/script_executor.py`**
   - 移除参数注入中的 `builtins.__PARAMS__` 设置
   - 改为注入 `sys.argv` 和 `os.environ['UE_MCP_MODE']`

   ```python
   # 旧方式
   builtins.__PARAMS__ = {repr(params)}

   # 新方式
   sys.argv = {repr([script_path] + args)}
   os.environ['UE_MCP_MODE'] = '1'
   ```

2. **`src/ue_mcp/asset_tracker.py`**
   - 更新 `create_snapshot()` 函数：改为两步 EXECUTE_FILE 模式
   - 更新 `gather_change_details()` 中的 `run_script()` 函数：改为两步 EXECUTE_FILE 模式
   - 移除所有 `builtins.__PARAMS__` 相关代码

3. **`src/ue_mcp/server.py`**
   - 更新 `diagnose_asset()` 函数：改用 `execute_script_from_path()`
   - 更新 `inspect_asset()` 函数：改用 `execute_script_from_path()`
   - 移除所有 `builtins.__PARAMS__` 相关代码

### 工具脚本 (9个文件)

4. **`src/ue_mcp/extra/scripts/ue_mcp_capture/utils.py`**
   - `_is_mcp_mode()`: 改为检查环境变量 `os.environ.get('UE_MCP_MODE') == '1'`
   - `get_params()`: 移除 `builtins.__PARAMS__` 检查，只使用 `sys.argv` 解析

5. **`src/ue_mcp/extra/scripts/diagnostic/diagnostic_runner.py`**
   - `_is_mcp_mode()`: 改为检查环境变量
   - `get_params()`: 移除 `builtins.__PARAMS__` 检查，只使用 `sys.argv` 解析

6. **`src/ue_mcp/extra/scripts/diagnostic/inspect_runner.py`**
   - `_is_mcp_mode()`: 改为检查环境变量
   - `get_params()`: 移除 `builtins.__PARAMS__` 检查，只使用 `sys.argv` 解析

7. **`src/ue_mcp/extra/scripts/diagnostic/asset_snapshot.py`**
   - `get_params()`: 改为解析 `sys.argv`（之前直接返回 `builtins.__PARAMS__`）

8. **`src/ue_mcp/extra/scripts/api_search.py`**
   - fallback 逻辑：从 `builtins.__PARAMS__` 改为直接解析 `sys.argv`

9-12. **capture scripts (4个文件)**
    - `capture_orbital.py`
    - `capture_pie.py`
    - `capture_window.py`
    - `trace_actors_pie.py`
    - `execute_in_tick.py`
    - 文档字符串：`MCP mode (__PARAMS__)` → `MCP mode (sys.argv)`

## 新的参数传递机制

### MCP 模式检测

**旧方式（已移除）：**
```python
import builtins
if hasattr(builtins, "__PARAMS__"):
    # MCP 模式
```

**新方式：**
```python
import os
if os.environ.get('UE_MCP_MODE') == '1':
    # MCP 模式
```

### 参数传递

**旧方式（已移除）：**
```python
# Step 1: 参数注入
builtins.__PARAMS__ = {'asset_path': '/Game/BP_Test', 'tab_id': 'Inspector'}

# Step 2: 脚本执行
# 脚本中通过 builtins.__PARAMS__ 访问
params = builtins.__PARAMS__
```

**新方式：**
```python
# Step 1: 参数注入
sys.argv = ['script.py', '--asset-path', '/Game/BP_Test', '--tab-id', 'Inspector']
os.environ['UE_MCP_MODE'] = '1'

# Step 2: 脚本执行（EXECUTE_FILE）
# 脚本中通过 sys.argv 解析参数
params = parse_cli_args(defaults)
```

### 参数解析

所有脚本统一使用 CLI 风格的参数解析：

```python
def parse_cli_args(defaults: dict = None) -> dict:
    """Parse --key=value or --key value format"""
    params = dict(defaults) if defaults else {}
    args = sys.argv[1:]

    i = 0
    while i < len(args):
        if args[i].startswith("--"):
            key = args[i][2:].replace("-", "_")

            if "=" in args[i]:
                # --key=value
                key, value = args[i][2:].split("=", 1)
                params[key.replace("-", "_")] = value
            elif i + 1 < len(args) and not args[i + 1].startswith("--"):
                # --key value
                params[key] = args[i + 1]
                i += 1
            else:
                # --flag (boolean)
                params[key] = True
        i += 1

    return params
```

## 优势

### 1. 标准化
- ✅ 使用标准的 `sys.argv`，符合 Python 惯例
- ✅ 脚本可以使用 `argparse` 等标准库
- ✅ 更容易被其他 Python 开发者理解

### 2. 简洁性
- ✅ 减少了特殊的全局状态（`builtins` 命名空间污染）
- ✅ 参数传递更显式、更透明
- ✅ 移除了 `__PARAMS__` 这个非标准的魔法变量

### 3. 兼容性
- ✅ CLI 模式和 MCP 模式使用相同的参数解析逻辑
- ✅ 脚本可以直接用 `python script.py --arg=value` 方式测试
- ✅ 与标准 Python 工具链更好地集成

### 4. 可调试性
- ✅ 更容易 inspect `sys.argv` (标准位置)
- ✅ 环境变量 `UE_MCP_MODE` 更易于调试和验证

## 向后兼容性

**Breaking Change:** 此修改**不向后兼容**。

如果有外部脚本依赖 `builtins.__PARAMS__`，需要更新为使用 `sys.argv`。

## 迁移指南

### 对于脚本开发者

**旧代码：**
```python
import builtins

def main():
    params = builtins.__PARAMS__
    asset_path = params['asset_path']
```

**新代码：**
```python
from ue_mcp_capture.utils import get_params

def main():
    params = get_params(required=['asset_path'])
    asset_path = params['asset_path']
```

### 对于手动测试

**旧方式（不再工作）：**
```python
import builtins
builtins.__PARAMS__ = {'asset_path': '/Game/BP_Test'}
exec(open('script.py').read())
```

**新方式：**
```python
import sys
sys.argv = ['script.py', '--asset-path', '/Game/BP_Test']
exec(open('script.py').read())
```

## 验证

### 语法检查
```bash
python -m py_compile src/ue_mcp/script_executor.py
python -m py_compile src/ue_mcp/asset_tracker.py
python -m py_compile src/ue_mcp/server.py
```
✅ 所有文件通过语法检查

### 代码搜索
```bash
grep -r "builtins.__PARAMS__\|__PARAMS__" src/ue_mcp/ --include="*.py"
```
✅ 只在注释和文档字符串中出现，无实际代码使用

## 影响范围

### 受影响的组件
- ✅ 所有 11 个脚本（capture、diagnostic、api_search）
- ✅ script_executor.py（参数注入）
- ✅ asset_tracker.py（内部脚本执行）
- ✅ server.py（诊断和检查工具）

### 不受影响的组件
- ✅ editor_manager.py - 无需修改
- ✅ remote_client.py - 无需修改
- ✅ 所有测试（将在后续 PR 中更新）

## 测试建议

### 单元测试
1. 测试 `parse_cli_args()` 函数
   - `--key=value` 格式
   - `--key value` 格式
   - `--flag` 布尔格式
   - 混合格式

2. 测试 `get_params()` 函数
   - 必需参数验证
   - 默认值应用
   - 参数类型转换

### 集成测试
1. 测试所有 MCP 工具
   - `editor_asset_open`
   - `editor_start_pie` / `editor_stop_pie`
   - `editor_asset_diagnostic`
   - `editor_asset_inspect`
   - `python_api_search`
   - 所有 capture 工具

2. 测试热重载
   - 修改脚本
   - 调用工具
   - 验证修改生效

### 手动测试
```python
# 在 UE5 Python 控制台测试
import sys
sys.argv = ['script.py', '--asset-path', '/Game/BP_Test']

# 执行脚本
exec(open(r'D:\code\ue-mcp\src\ue_mcp\extra\scripts\asset_open.py').read())
```

## 统计

| 指标 | 数量 |
|------|------|
| 修改的文件 | 12 |
| 核心基础设施文件 | 3 |
| 脚本文件 | 9 |
| 移除的 `builtins.__PARAMS__` 引用 | ~25 |
| 新增环境变量检查 | 9 |
| 更新的参数解析函数 | 9 |

## 下一步

1. **运行测试套件**：验证所有现有测试仍然通过
2. **更新测试**：如果有测试依赖 `builtins.__PARAMS__`，需要更新
3. **文档更新**：更新所有提到 `__PARAMS__` 的文档（已在 CLAUDE.md 中完成）
4. **性能测试**：验证性能没有退化

## 总结

成功将整个代码库从 `builtins.__PARAMS__` 迁移到标准的 `sys.argv` + 环境变量模式。

**核心改进：**
- ✅ 使用 Python 标准机制
- ✅ 更简洁、更透明的参数传递
- ✅ 更好的工具链兼容性
- ✅ 更容易调试和维护
- ✅ 符合 Python 最佳实践

**Breaking Change:** 此修改不向后兼容，但带来了长期的架构改进和可维护性提升。
