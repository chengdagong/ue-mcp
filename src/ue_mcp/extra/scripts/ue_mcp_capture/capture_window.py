"""
Window capture script for UE Editor.

Supports three modes:
- "window": Capture the main UE5 editor window
- "asset": Open an asset editor and capture it
- "batch": Capture multiple assets to a directory

Usage (CLI):
    # Window mode (default):
    python capture_window.py --level=/Game/Maps/TestLevel --output-file=screenshot.png

    # Asset mode:
    python capture_window.py --level=/Game/Maps/TestLevel --mode=asset \\
        --asset-path=/Game/Blueprints/BP_Test --output-file=asset.png

    # Batch mode:
    python capture_window.py --level=/Game/Maps/TestLevel --mode=batch \\
        --asset-list='["/Game/BP1", "/Game/BP2"]' --output-dir=/path/to/output

    Optional arguments:
        --tab=<n>             Tab number to switch to (1-9)

MCP mode (__PARAMS__):
    level: str - Level path to load
    mode: str - "window", "asset", or "batch"
    output_file: str - Output file path (for window/asset modes)
    output_dir: str - Output directory (for batch mode)
    asset_path: str - Asset path (for asset mode)
    asset_list: list[str] - Asset paths (for batch mode)
    tab: int | None - Tab number to switch to (for window/asset modes)
"""

import time
import editor_capture

from module_reload_utils import reload_recursive
reload_recursive(editor_capture)

from ue_mcp_capture.utils import get_params, ensure_level_loaded, output_result

# Default parameter values for CLI mode
DEFAULTS = {
    "mode": "window",
    "output_file": None,
    "output_dir": None,
    "asset_path": None,
    "asset_list": None,
    "tab": None,
}

# Required parameters (level is always required, others depend on mode)
REQUIRED = ["level"]


def capture_mode_window(params):
    output_file = params["output_file"]
    tab = params.get("tab")

    if tab is not None:
        hwnd = editor_capture.find_ue5_window()
        if hwnd:
            editor_capture.switch_to_tab(tab, hwnd)
            time.sleep(0.5)

    result = editor_capture.capture_ue5_window(output_file)

    # Handle both old (bool) and new (dict) return formats for compatibility
    if isinstance(result, dict):
        captured = result.get("success", False)
        error = result.get("error")
        output = {"file": output_file, "captured": captured}
        if error:
            output["error"] = error
        output_result(output)
    else:
        # Legacy bool return
        output_result({"file": output_file, "captured": result})


def capture_mode_asset(params):
    asset_path = params["asset_path"]
    output_file = params["output_file"]
    tab = params.get("tab")

    # Prepare arguments for open_asset_and_screenshot
    kwargs = {"asset_path": asset_path, "output_path": output_file, "delay": 3.0}
    if tab is not None:
        kwargs["tab_number"] = tab

    result = editor_capture.open_asset_and_screenshot(**kwargs)

    output_result(
        {
            "file": output_file,
            "opened": result["opened"],
            "captured": result["screenshot"],
        }
    )


def capture_mode_batch(params):
    asset_list = params["asset_list"]
    output_dir = params["output_dir"]

    results = editor_capture.batch_asset_screenshots(
        asset_paths=asset_list,
        output_dir=output_dir,
        delay=3.0,
        close_after=True,
    )

    # batch_asset_screenshots returns {"success": [(path, screenshot_path)], "failed": [path]}
    files = [screenshot_path for _, screenshot_path in results.get("success", [])]
    success_count = len(files)
    failed_count = len(results.get("failed", []))
    total_count = len(asset_list)

    output_result(
        {
            "files": files,
            "success_count": success_count,
            "failed_count": failed_count,
            "total_count": total_count,
        }
    )


def main():
    params = get_params(defaults=DEFAULTS, required=REQUIRED)

    # Validate mode-specific required parameters
    mode = params.get("mode", "window")
    if mode in ("window", "asset") and not params.get("output_file"):
        raise RuntimeError(
            f"Mode '{mode}' requires --output-file parameter.\n"
            f"Example: python capture_window.py --level=/Game/Maps/Test --output-file=screenshot.png"
        )
    if mode == "asset" and not params.get("asset_path"):
        raise RuntimeError(
            "Mode 'asset' requires --asset-path parameter.\n"
            "Example: python capture_window.py --mode=asset --asset-path=/Game/BP_Test --output-file=out.png"
        )
    if mode == "batch":
        if not params.get("asset_list"):
            raise RuntimeError(
                "Mode 'batch' requires --asset-list parameter.\n"
                'Example: python capture_window.py --mode=batch --asset-list=\'["/Game/BP1"]\' --output-dir=./out'
            )
        if not params.get("output_dir"):
            raise RuntimeError(
                "Mode 'batch' requires --output-dir parameter.\n"
                'Example: python capture_window.py --mode=batch --asset-list=\'["/Game/BP1"]\' --output-dir=./out'
            )

    # Ensure correct level is loaded
    ensure_level_loaded(params["level"])

    if mode == "window":
        capture_mode_window(params)
    elif mode == "asset":
        capture_mode_asset(params)
    elif mode == "batch":
        capture_mode_batch(params)
    else:
        # Should be caught by server validation, but good to have
        raise ValueError(f"Unknown mode: {mode}")


if __name__ == "__main__":
    main()
