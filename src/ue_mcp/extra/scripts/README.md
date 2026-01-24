# UE-MCP Scripts - Hot-Reload Architecture

This directory contains standalone Python scripts that implement MCP tool functionality. All scripts support **true hot-reload** - you can modify and save scripts without restarting the MCP server or UE5 editor.

## How Hot-Reload Works

### Execution Model: Two-Step EXECUTE_FILE

All scripts use a two-step execution model for true hot-reload:

1. **Step 1: Parameter Injection** (EXECUTE_STATEMENT)
   - MCP injects parameters into `sys.argv` and `builtins.__PARAMS__`
   - Parameters are available to the script via both CLI-style args and dict access

2. **Step 2: Script File Execution** (EXECUTE_FILE)
   - UE5 executes the script file directly from disk
   - File is read at execution time, not when tool is called
   - **This enables hot-reload**: modify script → save → call tool → changes take effect

### What Makes This Different

**Traditional Approach (No Hot-Reload):**
```python
# script_executor.py - OLD WAY
script_content = script_path.read_text()  # Read once into string
full_code = params_code + script_content  # Concatenate strings
manager.execute(full_code)  # Execute string
# → Script is "frozen" at server start time
```

**Hot-Reload Approach (Current):**
```python
# script_executor.py - NEW WAY
# Step 1: Inject parameters
manager._execute(f"sys.argv = {args}; builtins.__PARAMS__ = {params}")

# Step 2: Execute file from disk
manager.execute_script_file(str(script_path))
# → Script is read from disk each time = instant hot-reload!
```

## Hot-Reload Workflow

1. **Modify a script**: Edit any `.py` file in this directory
2. **Save the file**: Ctrl+S (or :w in vim)
3. **Call the MCP tool**: No restart needed!
4. **Changes take effect**: Script runs with your modifications

**Example:**
```python
# 1. Edit asset_open.py, add debug output:
print(f"DEBUG: Opening asset {asset_path}")

# 2. Save file (Ctrl+S)

# 3. Call MCP tool (in Claude or via test):
result = editor_asset_open(asset_path="/Game/BP_Test")

# 4. See debug output immediately - no restart!
```

## Script Organization

### Core Scripts (Root Level)

| Script | MCP Tools | Purpose |
|--------|-----------|---------|
| `asset_open.py` | `editor_asset_open` | Open assets in their editors, switch tabs |
| `pie_control.py` | `editor_start_pie`, `editor_stop_pie` | Control PIE sessions |
| `api_search.py` | `python_api_search` | Runtime UE5 API introspection |

### Capture Scripts (`ue_mcp_capture/` package)

| Script | MCP Tools | Purpose |
|--------|-----------|---------|
| `capture_orbital.py` | `editor_capture_orbital` | Multi-angle screenshots around target |
| `capture_pie.py` | `editor_capture_pie` | Screenshot capture during PIE |
| `capture_window.py` | `editor_capture_window` | Windows API editor window capture |
| `trace_actors_pie.py` | `editor_trace_actors_in_pie` | Actor transform tracing in PIE |
| `execute_in_tick.py` | `editor_pie_execute_in_tick` | Execute code at specific PIE ticks |
| `utils.py` | N/A | Shared utilities for all capture scripts |

### Diagnostic Scripts (`diagnostic/` package)

| Script | MCP Tools | Purpose |
|--------|-----------|---------|
| `diagnostic_runner.py` | `editor_asset_diagnostic` | Asset diagnostics and issue detection |
| `inspect_runner.py` | `editor_asset_inspect` | Asset property inspection |

## Parameter Handling

Scripts support **dual-mode parameter access**:

### Mode 1: MCP Mode (Automatic)

When called via MCP tools, parameters are auto-injected:

```python
from ue_mcp_capture.utils import get_params

params = get_params(defaults=DEFAULTS, required=REQUIRED)
asset_path = params["asset_path"]
tab_id = params.get("tab_id")
```

**Available as:**
- `builtins.__PARAMS__` - Dict of all parameters
- `sys.argv` - CLI-style argument list

### Mode 2: CLI Mode (Manual)

For direct execution in UE5 Python console:

```python
import sys

# Set arguments
sys.argv = [
    'asset_open.py',
    '--asset-path', '/Game/BP_Test',
    '--tab-id', 'Inspector'
]

# Execute script
exec(open(r'D:\code\ue-mcp\src\ue_mcp\extra\scripts\asset_open.py').read())
```

**CLI Argument Format:**
- `--key value` → `{"key": "value"}`
- `--key=value` → `{"key": "value"}`
- `--flag` → `{"flag": True}`
- `--multi-word-key value` → `{"multi_word_key": "value"}`

## Output Format

All scripts use **pure JSON output** without special markers:

```python
import json

result = {
    "success": True,
    "asset_path": "/Game/BP_Test",
    "asset_name": "BP_Test"
}

# Output as last line - MCP parses last valid JSON
print(json.dumps(result))
```

**Parsing on MCP Side:**
```python
def _parse_json_result(exec_result):
    """Extract last valid JSON from output."""
    output = exec_result.get("output", [])

    # Find last line starting with { or [
    for line in reversed(output):
        if line.startswith("{") or line.startswith("["):
            return json.loads(line)

    return {"success": False, "error": "No JSON found"}
```

## Script Development Guide

### Template Structure

```python
"""
Script description and usage examples.

Parameters:
    param1: Description (required)
    param2: Description (optional)
"""

import json
import unreal
from ue_mcp_capture.utils import get_params

# Parameter defaults and requirements
DEFAULTS = {
    "param2": None,
}
REQUIRED = ["param1"]


def main():
    """Main entry point."""
    # Get parameters
    params = get_params(defaults=DEFAULTS, required=REQUIRED)
    param1 = params["param1"]
    param2 = params.get("param2")

    # Implement logic
    try:
        # ... do work ...
        result = {
            "success": True,
            "data": data
        }
    except Exception as e:
        result = {
            "success": False,
            "error": str(e)
        }

    # Output result as pure JSON
    print(json.dumps(result))


if __name__ == "__main__":
    main()
```

### Best Practices

1. **Keep scripts simple**: Complex logic should go in `site-packages` modules
2. **Use descriptive parameter names**: `asset_path` not `path`, `target_x` not `x`
3. **Provide defaults**: Make parameters optional when possible
4. **Validate inputs**: Check required parameters early
5. **Error handling**: Always output `{"success": False, "error": "..."}` on failure
6. **Structured output**: Return detailed, parseable results
7. **Add docstrings**: Include usage examples for CLI mode

### Testing Scripts

**Quick Test (Hot-Reload Verification):**
```bash
# 1. Add print statement to script
echo 'print("TEST VERSION 1")' >> asset_open.py

# 2. Run test
pytest tests/test_asset_open.py -k test_basic

# 3. Modify script
sed -i 's/VERSION 1/VERSION 2/' asset_open.py

# 4. Run test again (no restart!)
pytest tests/test_asset_open.py -k test_basic
# → Should see "TEST VERSION 2"
```

**Full Integration Test:**
```bash
# Test all tools with hot-reload
pytest tests/test_hot_reload.py -v
```

## Common Use Cases

### Example 1: Add Debug Output

```python
# Edit asset_open.py
def main():
    params = get_params(defaults=DEFAULTS, required=REQUIRED)

    # ADD: Debug logging
    print(f"[DEBUG] Opening {params['asset_path']}")
    print(f"[DEBUG] Tab requested: {params.get('tab_id')}")

    # ... existing code ...
```

Save → Call tool → See debug output immediately!

### Example 2: Add New Parameter

```python
# Edit pie_control.py
DEFAULTS = {
    "delay_seconds": 0.0,  # NEW: Add startup delay
}

def main():
    params = get_params(defaults=DEFAULTS, required=REQUIRED)
    command = params["command"]
    delay = params.get("delay_seconds", 0.0)  # NEW

    if delay > 0:  # NEW
        import time
        time.sleep(delay)

    # ... rest of code ...
```

Update MCP tool to accept new parameter → Test immediately!

### Example 3: Test API Before Integration

```python
# Create temporary test script
import sys
sys.argv = ['test.py', '--test-value', '123']

# In UE5 console:
import unreal
api_to_test = unreal.SomeNewLibrary
result = api_to_test.some_new_method()
print(json.dumps({"result": str(result)}))

# See result → Refine → Integrate into main script
```

## Troubleshooting

### Script Changes Not Taking Effect

**Problem**: Modified script but see old behavior

**Solutions**:
1. **Check file save**: Ensure you actually saved the file (look for unsaved indicator in editor)
2. **Check correct file**: Verify you're editing the right script path
3. **Check syntax errors**: Script with syntax errors may fail silently, use CLI mode to test
4. **Check UE crash**: If editor crashed, hot-reload won't work (restart editor)

### Parameter Not Found

**Problem**: `KeyError: 'my_param'`

**Solutions**:
1. **Use `params.get()`**: `params.get("my_param")` instead of `params["my_param"]`
2. **Add to DEFAULTS**: `DEFAULTS = {"my_param": None}`
3. **Check parameter name**: MCP uses snake_case, CLI uses kebab-case (auto-converted)

### Import Errors

**Problem**: `ModuleNotFoundError: No module named 'some_module'`

**Solutions**:
1. **Auto-install**: MCP auto-installs missing packages, but may need retry
2. **Manual install**: `editor_pip_install(["package-name"])`
3. **Check bundled modules**: `editor_capture` and `asset_diagnostic` are pre-bundled

## Advanced: State Isolation

**Q: Do global variables persist between calls?**

**A: Yes, within the same editor session!**

```python
# test_state.py
import builtins

# First call: set state
if not hasattr(builtins, 'call_count'):
    builtins.call_count = 0

builtins.call_count += 1
print(json.dumps({"count": builtins.call_count}))

# First call → {"count": 1}
# Second call → {"count": 2}
# Third call → {"count": 3}
```

**Use Cases:**
- Cache expensive computations across calls
- Track tool usage statistics
- Maintain temporary state during iteration

**Cleanup:**
```python
# Reset state when needed
import builtins
if hasattr(builtins, 'call_count'):
    delattr(builtins, 'call_count')
```

## Migration Notes

### From Inline Code to Scripts

**Before (Inline in server.py):**
```python
@mcp.tool()
def my_tool():
    code = """
import unreal
# ... 50 lines of inline code ...
print("RESULT:" + json.dumps(data))
"""
    result = manager.execute(code)
    # ... parse result with string splitting ...
```

**After (Standalone Script):**
```python
# my_script.py
import json
import unreal

def main():
    # ... 50 lines (now editable with hot-reload) ...
    print(json.dumps({"success": True, "data": data}))

if __name__ == "__main__":
    main()
```

```python
# server.py
@mcp.tool()
def my_tool():
    result = execute_script_from_path(manager, "my_script.py", params)
    return _parse_json_result(result)
```

**Benefits:**
- ✅ Hot-reload: Edit script without MCP restart
- ✅ Testable: Can test script independently
- ✅ Reusable: Can call from CLI or other tools
- ✅ Cleaner: No string escaping, proper syntax highlighting
- ✅ Debuggable: Add print statements anytime

## See Also

- [UE5 Python API Search](../../CLAUDE.md#python-api-search) - Finding APIs at runtime
- [Hot-Reload Architecture](../../../docs/architecture.md) - Technical deep dive
- [Testing Guide](../../../tests/README.md) - Writing tests for scripts
