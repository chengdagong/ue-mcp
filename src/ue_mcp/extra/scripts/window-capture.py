#!/usr/bin/env python3
"""
Window Capture Wrapper for remote-execute.py

A CLI wrapper for Windows API window capturing using the editor_capture
window_capture module. Captures screenshots of UE5 editor windows and asset editors.

Note: This script is Windows-only and uses Windows API for window manipulation.

Usage:
    window-capture.py window --output-file PATH [--tab NUM]
    window-capture.py asset --asset-path PATH --output-file PATH [--tab NUM]
    window-capture.py batch --asset-list PATH1,PATH2,... --output-dir PATH

Examples:
    # Capture UE5 window
    window-capture.py window --output-file C:/Screenshots/editor.png

    # Capture with specific tab active
    window-capture.py window --output-file C:/Screenshots/tab1.png --tab 1

    # Open asset and capture
    window-capture.py asset --asset-path /Game/BP_Test --output-file C:/Screenshots/bp.png

    # Batch capture multiple assets
    window-capture.py batch --asset-list /Game/BP1,/Game/BP2 --output-dir C:/Screenshots

Via remote-execute.py:
    remote-execute.py --file window-capture.py \\
        --args "command=window,output_file=C:/Screenshots/editor.png"

    remote-execute.py --file window-capture.py \\
        --args "command=window,output_file=C:/Screenshots/tab1.png,tab=1"

    remote-execute.py --file window-capture.py \\
        --args "command=asset,asset_path=/Game/BP_Test,output_file=C:/Screenshots/bp.png"
"""

import sys
import argparse


def cmd_window(args):
    """Handle the 'window' command - capture UE5 window."""
    import unreal
    import editor_capture

    unreal.log("")
    unreal.log("=" * 60)
    unreal.log("WINDOW CAPTURE")
    unreal.log("=" * 60)
    unreal.log(f"Output file: {args.output_file}")
    if args.tab:
        unreal.log(f"Tab: {args.tab}")
    unreal.log("")

    try:
        # Switch to tab if specified
        if args.tab:
            hwnd = editor_capture.find_ue5_window()
            if hwnd:
                unreal.log(f"[INFO] Switching to tab {args.tab}...")
                editor_capture.switch_to_tab(args.tab, hwnd)
                import time
                time.sleep(0.5)  # Brief delay for tab switch

        # Capture window
        success = editor_capture.capture_ue5_window(args.output_file)

        if success:
            unreal.log("[SUCCESS] Window capture completed")
            unreal.log("")
        else:
            unreal.log_error("[ERROR] Window capture failed")
            sys.exit(1)

    except Exception as e:
        print(f"Error during window capture: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


def cmd_asset(args):
    """Handle the 'asset' command - open asset editor and capture."""
    import unreal
    import editor_capture

    unreal.log("")
    unreal.log("=" * 60)
    unreal.log("ASSET CAPTURE")
    unreal.log("=" * 60)
    unreal.log(f"Asset: {args.asset_path}")
    unreal.log(f"Output file: {args.output_file}")
    if args.tab:
        unreal.log(f"Tab: {args.tab}")
    unreal.log("")

    try:
        result = editor_capture.open_asset_and_screenshot(
            asset_path=args.asset_path,
            output_path=args.output_file,
            tab_number=args.tab,
            delay=3.0,
        )

        if result["opened"] and result["screenshot"]:
            unreal.log("[SUCCESS] Asset capture completed")
            unreal.log("")
        elif result["opened"]:
            unreal.log_error("[ERROR] Asset opened but screenshot failed")
            sys.exit(1)
        else:
            unreal.log_error("[ERROR] Failed to open asset editor")
            sys.exit(1)

    except Exception as e:
        print(f"Error during asset capture: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


def cmd_batch(args):
    """Handle the 'batch' command - batch capture multiple assets."""
    import unreal
    import editor_capture

    # Parse asset list
    asset_paths = [path.strip() for path in args.asset_list.split(',')]

    unreal.log("")
    unreal.log("=" * 60)
    unreal.log("BATCH ASSET CAPTURE")
    unreal.log("=" * 60)
    unreal.log(f"Asset count: {len(asset_paths)}")
    unreal.log(f"Output directory: {args.output_dir}")
    unreal.log("")

    try:
        results = editor_capture.batch_asset_screenshots(
            asset_paths=asset_paths,
            output_dir=args.output_dir,
            delay=3.0,
            close_after=True,
        )

        # Print summary
        success_count = sum(1 for r in results if r["screenshot"])
        unreal.log("")
        unreal.log("=" * 60)
        unreal.log(f"BATCH CAPTURE COMPLETE: {success_count}/{len(asset_paths)} successful")
        unreal.log("=" * 60)

        # Print details
        for i, result in enumerate(results):
            asset_path = asset_paths[i]
            if result["screenshot"]:
                unreal.log(f"[OK] {asset_path} -> {result['screenshot_path']}")
            else:
                unreal.log(f"[FAIL] {asset_path}")

        unreal.log("")

        # Exit with error if any failed
        if success_count < len(asset_paths):
            sys.exit(1)

    except Exception as e:
        print(f"Error during batch capture: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


def main():
    """Main entry point for the wrapper script."""
    parser = argparse.ArgumentParser(
        description="Capture screenshots of UE5 editor windows (Windows only)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Commands:
  window    Capture the UE5 editor window
  asset     Open asset editor and capture screenshot
  batch     Batch capture multiple assets

Examples via remote-execute.py:
  remote-execute.py --file %(prog)s --args "command=window,output_file=C:/Screenshots/editor.png"
  remote-execute.py --file %(prog)s --args "command=window,output_file=C:/Screenshots/tab1.png,tab=1"
  remote-execute.py --file %(prog)s --args "command=asset,asset_path=//Game/BP_Test,output_file=C:/Screenshots/bp.png"
        """
    )

    parser.add_argument(
        "--command",
        type=str,
        required=True,
        choices=["window", "asset", "batch"],
        help="Command to execute: window, asset, or batch"
    )

    parser.add_argument(
        "--output-file",
        type=str,
        default=None,
        dest="output_file",
        help="Output file path for screenshot (required for window/asset)"
    )

    parser.add_argument(
        "--asset-path",
        type=str,
        default=None,
        dest="asset_path",
        help="Asset path to open (required for asset command)"
    )

    parser.add_argument(
        "--asset-list",
        type=str,
        default=None,
        dest="asset_list",
        help="Comma-separated asset paths (required for batch command)"
    )

    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        dest="output_dir",
        help="Output directory (required for batch command)"
    )

    parser.add_argument(
        "--tab",
        type=int,
        default=None,
        help="Tab number to switch to (1-9, optional)"
    )

    args = parser.parse_args()

    # Import modules (must be done in UE5 Python environment)
    # Note: editor_capture should be available via AdditionalPaths configured by ue-mcp
    try:
        import unreal
        import editor_capture
    except ImportError as e:
        print("=" * 60, file=sys.stderr)
        print("ERROR: Failed to import required modules", file=sys.stderr)
        print("=" * 60, file=sys.stderr)
        print(f"Import error: {e}", file=sys.stderr)
        print("", file=sys.stderr)
        print("This script must run in a UE5 Python environment.", file=sys.stderr)
        print("Ensure editor_capture is available via AdditionalPaths.", file=sys.stderr)
        print("=" * 60, file=sys.stderr)
        sys.exit(1)

    # Check if running on Windows
    if sys.platform != "win32":
        print("Error: This script is Windows-only (uses Windows API)", file=sys.stderr)
        sys.exit(1)

    # Execute command
    if args.command == "window":
        if not args.output_file:
            parser.error("--output-file is required for 'window' command")
        cmd_window(args)
    elif args.command == "asset":
        if not args.asset_path or not args.output_file:
            parser.error("--asset-path and --output-file are required for 'asset' command")
        cmd_asset(args)
    elif args.command == "batch":
        if not args.asset_list or not args.output_dir:
            parser.error("--asset-list and --output-dir are required for 'batch' command")
        cmd_batch(args)


if __name__ == "__main__":
    main()
