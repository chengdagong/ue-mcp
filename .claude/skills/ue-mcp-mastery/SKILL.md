---
name: ue-mcp-mastery
description: Master UE-MCP tools and UE5 Python programming patterns. Use when working with UE5 projects via MCP, writing Python scripts for Unreal Editor, or debugging UE5 Python code.
---
# UE-MCP Mastery

## Recommended Workflows

### Starting a Session

1. Set project path (if not auto-detected): `ue-mcp:project_set_path`
2. Launch editor: `ue-mcp:editor_launch` with `wait: true`
3. If result contains `requires_build: true`, run `ue-mcp:project_build` first, then launch again
4. Load level: `ue-mcp:editor_load_level`

### Script Hot-Reload

Scripts support hot-reload:

- Edit script → Save → Call `ue-mcp:editor_execute_script` → Changes take effect immediately
- No MCP server or editor restart needed

### Asset Inspection & Diagnostics

- `ue-mcp:editor_asset_inspect` returns components, properties, metadata, and screenshot
- `ue-mcp:editor_asset_diagnostic` returns issues (errors, warnings), suggestions

### API Discovery

Use `ue-mcp:python_api_search` to find UE5 Python APIs:

- `mode: "search"` + `query: "spawn"` - fuzzy search
- `mode: "list_functions"` + `query: "Actor.*location*"` - list methods
- `mode: "class_info"` + `query: "StaticMeshComponent"` - full class info

### Test Project

Use `tests/fixtures/ThirdPersonTemplate/` for testing code snippets and scripts safely.

---

## References

- **UE5 Python patterns**: See [references/ue5-python-patterns.md](references/ue5-python-patterns.md) for best practices (subsystems, memory management, physics setup)
- **ExtraPythonAPIs & Diagnostics**: See [references/extra-apis.md](references/extra-apis.md) for plugin APIs and diagnostic system
