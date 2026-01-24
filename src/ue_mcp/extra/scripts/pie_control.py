"""
PIE (Play-In-Editor) control script.

Provides unified control for starting and stopping PIE sessions.

Usage:
    # Via MCP (parameters auto-injected):
    MCP tool calls this script automatically

    # Via UE Python console:
    import sys
    sys.argv = ['pie_control.py', '--command', 'start']
    # exec(open(r'C:\\path\\to\\pie_control.py').read())

Parameters:
    command: "start" or "stop"
"""

import argparse
import json
import sys

# Import from bundled package
import editor_capture.pie_capture as pie_capture

# Defaults: {}
# Required: ["command"]


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Control PIE (Play-In-Editor) sessions - start or stop."
    )
    parser.add_argument(
        "--command",
        required=True,
        choices=["start", "stop"],
        help="Command to execute: 'start' to begin PIE session, 'stop' to end it",
    )
    args = parser.parse_args()
    command = args.command.lower()

    if command not in ("start", "stop"):
        result = {
            "success": False,
            "error": f"Invalid command: {command}. Use 'start' or 'stop'.",
        }
        print(json.dumps(result))
        return

    is_running = pie_capture.is_pie_running()

    if command == "start":
        if is_running:
            result = {
                "success": False,
                "message": "PIE is already running",
                "command": "start",
            }
        else:
            success = pie_capture.start_pie_session()
            if success:
                result = {
                    "success": True,
                    "message": "PIE session started",
                    "command": "start",
                }
            else:
                result = {
                    "success": False,
                    "error": "Failed to start PIE session",
                    "command": "start",
                }
    else:  # stop
        if not is_running:
            result = {
                "success": False,
                "message": "PIE is not running",
                "command": "stop",
            }
        else:
            success = pie_capture.stop_pie_session()
            if success:
                result = {
                    "success": True,
                    "message": "PIE session stopped",
                    "command": "stop",
                }
            else:
                result = {
                    "success": False,
                    "error": "Failed to stop PIE session",
                    "command": "stop",
                }

    # Output result as pure JSON
    print(json.dumps(result))


if __name__ == "__main__":
    main()
