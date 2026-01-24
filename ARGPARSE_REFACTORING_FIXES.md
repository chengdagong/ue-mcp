# argparse 重构问题修复总结

## 问题1: EXECUTE_STATEMENT 不支持多行代码

**错误**:
```
LogPython: Error: SyntaxError: multiple statements found while compiling a single statement
```

**原因**:
- 在"阶段2.3"中移除了 exec() 包装逻辑
- UE5 的 EXECUTE_STATEMENT 模式只能执行单条语句
- 多行代码（如参数注入代码）导致语法错误

**修复** (execution_manager.py):
```python
# 修复前
result = self._ctx.editor.remote_client.execute(
    code,
    exec_type=EXECUTE_STATEMENT,
    timeout=timeout,
)

# 修复后
if "\n" in code:
    # 多行代码需要用 exec() 包装
    wrapped_code = f"exec({repr(code)})"
    result = self._ctx.editor.remote_client.execute(
        wrapped_code,
        exec_type=EXECUTE_STATEMENT,
        timeout=timeout,
    )
else:
    # 单行代码直接执行
    result = self._ctx.editor.remote_client.execute(
        code,
        exec_type=EXECUTE_STATEMENT,
        timeout=timeout,
    )
```

---

## 问题2: 两步 EXECUTE_FILE 执行方式不work

**错误**:
- sys.argv 没有包含参数，只有脚本路径
- 所有参数都使用默认值

**原因**:
- 第1步：通过 EXECUTE_STATEMENT 设置 sys.argv
- 第2步：通过 EXECUTE_FILE 执行脚本文件
- 两次执行的 Python 上下文是隔离的，第1步的 sys.argv 不会保留到第2步

**修复** (script_executor.py, asset_tracker.py):
```python
# 修复前（两步执行，不work）
# Step 1: 参数注入
param_injection_code = f"exec({repr(injection_code)})"
result = manager.execute(param_injection_code, timeout=10.0)

# Step 2: 执行脚本文件
return manager.execute_script_file(str(script_path), timeout=timeout)

# 修复后（字符串拼接，work）
# 读取脚本内容
script_content = script_path.read_text(encoding="utf-8")

# 拼接注入代码 + 脚本内容
full_code = injection_code + script_content

# 一次性执行完整代码
return manager.execute_with_checks(full_code, timeout=timeout)
```

**注**: 这意味着我们回退到读取文件内容的方式，但仍然支持"热重载"（每次调用都重新读取文件）

---

## 问题3: 布尔参数处理错误

**错误**:
- `include_private=False` 也会传递 `--include-private` 参数
- 导致 argparse 将其解析为 True

**原因**:
```python
# 错误的处理方式
for key, value in params.items():
    args.append(f"--{key.replace('_', '-')}")
    if not isinstance(value, bool):
        args.append(str(value))
```

当 value 是 bool 时，只添加 flag 而不添加值，导致:
- `include_private=True` → `['--include-private']` ✅
- `include_private=False` → `['--include-private']` ❌ （应该不传参数）

**修复**:
```python
# 正确的处理方式
if isinstance(value, bool):
    if value:
        # True 时才传递 flag
        args.append(f"--{key.replace('_', '-')}")
    # False 时不传参数，使用 argparse 默认值
else:
    args.append(f"--{key.replace('_', '-')}")
    args.append(str(value))
```

---

## 问题4: None 值被传递为字符串 "None"

**错误**:
- `query=None` 被传递为 `--query None`
- argparse 解析为字符串 `"None"` 而不是 None

**原因**:
```python
# 错误处理
for key, value in params.items():
    args.append(f"--{key.replace('_', '-')}")
    args.append(str(value))  # str(None) == "None"
```

**修复**:
```python
# 正确处理
for key, value in params.items():
    # 跳过 None 值
    if value is None:
        continue

    # 处理其他值...
```

---

## 问题5: 列表/字典参数传递错误

**错误**:
```
json.decoder.JSONDecodeError: Expecting value: line 1 column 2 (char 1)
```

**原因**:
- 列表/字典使用 `str(value)` 转换
- 产生单引号格式: `"['/Game/Maps/']"`
- 脚本使用 `json.loads()` 解析，但单引号不是有效的 JSON

**示例**:
```python
value = ["/Game/Maps/", "/Game/Blueprints/"]

# 错误方式
str(value)  # → "['/Game/Maps/', '/Game/Blueprints/']"  # 单引号，非JSON

# 正确方式
json.dumps(value)  # → "["/Game/Maps/", "/Game/Blueprints/"]"  # 双引号，合法JSON
```

**修复**:
```python
import json as json_module

for key, value in params.items():
    args.append(f"--{key.replace('_', '-')}")

    # 使用 JSON 编码 lists/dicts
    if isinstance(value, (list, dict)):
        args.append(json_module.dumps(value))
    else:
        args.append(str(value))
```

---

## 修复的文件

### 核心文件

1. **src/ue_mcp/editor/execution_manager.py**
   - 恢复了 exec() 包装逻辑处理多行代码

2. **src/ue_mcp/script_executor.py**
   - 从两步 EXECUTE_FILE 改回字符串拼接
   - 修复布尔参数处理
   - 修复 None 值处理
   - 修复 JSON 参数编码

3. **src/ue_mcp/asset_tracker.py**
   - 两个位置修复：create_snapshot() 和 gather_change_details()
   - 应用与 script_executor.py 相同的修复

---

## 测试结果

### 修复前
- 15 failed, 10 passed（初始 API search 测试全失败）

### 修复后
- **3 failed, 112 passed, 10 skipped**

**剩余的 3 个失败**：
1. `test_capture_orbital_with_editor` - 需要单独调查
2. `test_capture_window_with_editor` - 需要单独调查
3. `test_complete_isolation` - 多实例隔离测试

---

## 关键教训

### 1. EXECUTE_FILE 的上下文隔离
- ❌ 不能通过两次分离的执行来传递参数（上下文隔离）
- ✅ 必须将参数注入和脚本内容拼接为单个代码块执行

### 2. "热重载"的真正含义
- 原计划：直接执行磁盘文件（EXECUTE_FILE）实现真正热重载
- 实际情况：每次读取文件内容并拼接执行，也实现了"热重载"
- 结论：只要每次都重新读取文件，就实现了热重载（无需重启）

### 3. CLI 参数构建的复杂性
- 布尔值：True 传 flag，False 不传
- None 值：跳过不传
- 列表/字典：使用 JSON 编码（双引号）
- 字符串/数字：直接 str() 转换

### 4. 多行代码执行
- EXECUTE_STATEMENT 不支持多行代码
- 必须用 exec() 包装：`exec(repr(multi_line_code))`
- execute_with_checks 内部会自动处理（因为恢复了 exec() 包装逻辑）

---

## 后续工作

1. 调查剩余 3 个失败测试的原因
2. 可能需要为 capture 工具脚本应用相同的修复
3. 确保所有测试通过后，创建最终的 refactoring 总结
4. 更新文档反映新的实现方式（字符串拼接 vs EXECUTE_FILE）
