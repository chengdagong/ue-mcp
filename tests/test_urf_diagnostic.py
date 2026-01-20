"""
Manual test script for editor.asset.diagnostic using URF project.
"""
import asyncio
import json
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from mcp import ClientSession, StdioServerParameters, stdio_client


async def test_diagnostic():
    """Test diagnostic on PunchingBagLevel in URF project."""
    
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "ue_mcp.server"],
        cwd=r"D:\Code\URF",
        env={
            "PYTHONPATH": str(Path(__file__).parent.parent / "src"),
        },
    )

    print("Connecting to MCP server...")
    async with stdio_client(params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            print("Session initialized")

            # Launch editor
            print("\nLaunching editor (this may take a few minutes)...")
            result = await session.call_tool(
                "editor.launch",
                {"wait": True, "wait_timeout": 180},
                read_timeout_seconds=timedelta(seconds=240),
            )
            
            for c in result.content:
                if hasattr(c, "text"):
                    data = json.loads(c.text)
                    print(f"Launch result: success={data.get('success')}")
                    if not data.get("success"):
                        print(f"Error: {data.get('error')}")
                        return

            # Run diagnostic on PunchingBagLevel
            print("\nRunning diagnostic on /Game/Maps/PunchingBagLevel...")
            result = await session.call_tool(
                "editor.asset.diagnostic",
                {"asset_path": "/Game/Maps/PunchingBagLevel"},
                read_timeout_seconds=timedelta(seconds=120),
            )

            print("\n" + "=" * 60)
            print("DIAGNOSTIC RESULT")
            print("=" * 60)
            
            for c in result.content:
                if hasattr(c, "text"):
                    data = json.loads(c.text)
                    # Print report text first
                    if "report" in data:
                        print("\n--- FORMATTED REPORT ---")
                        print(data["report"])
                        print("--- END REPORT ---\n")
                        # Remove report from dict to avoid duplication
                        del data["report"]
                    print("\n--- JSON DATA ---")
                    print(json.dumps(data, indent=2, ensure_ascii=False))

            # Stop editor
            print("\nStopping editor...")
            await session.call_tool(
                "editor.stop",
                read_timeout_seconds=timedelta(seconds=30),
            )
            print("Done!")


if __name__ == "__main__":
    asyncio.run(test_diagnostic())
