# UE-MCP

MCP server for Unreal Editor interaction.

## Overview

UE-MCP is a [FastMCP](https://github.com/jlowin/fastmcp)-based MCP server that enables AI assistants to interact with Unreal Editor through the Python remote execution protocol.

## Features

- **Project Isolation**: Each MCP server instance is bound to a single UE5 project (auto-detected from working directory)
- **Managed Editor Lifecycle**: Server manages the editor process and ensures cleanup on exit
- **Auto Configuration**: Automatically configures Python plugin and remote execution settings
- **Remote Execution**: Execute Python code in the editor via socket protocol

## Installation

```bash
pip install -e .
```

## Usage

Run the server from a UE5 project directory:

```bash
cd /path/to/your/ue5/project
ue-mcp
```

Or use with FastMCP:

```bash
fastmcp run ue_mcp.server:mcp
```

## MCP Tools

- `editor.launch()` - Start the Unreal Editor
- `editor.status()` - Get editor status
- `editor.stop()` - Stop the editor
- `editor.execute(code)` - Execute Python code in the editor
- `editor.configure()` - Check/fix project configuration

## Claude Code Configuration

Add to your `.claude/settings.json`:

```json
{
  "mcpServers": {
    "ue-mcp": {
      "command": "ue-mcp"
    }
  }
}
```

## Requirements

- Python >= 3.10
- Unreal Engine 5.x with Python plugin
- FastMCP >= 2.0.0

## License

MIT
