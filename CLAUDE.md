# Development Guildelines

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
