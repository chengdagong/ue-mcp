"""
Window capture script for UE Editor.

Supports three modes:
- "window": Capture the main UE5 editor window
- "asset": Open an asset editor and capture it
- "batch": Capture multiple assets to a directory

Expected __PARAMS__:
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

from capture.utils import get_params, ensure_level_loaded, output_result, error_handler


def capture_mode_window(params):
    output_file = params["output_file"]
    tab = params.get("tab")

    if tab is not None:
        hwnd = editor_capture.find_ue5_window()
        if hwnd:
            editor_capture.switch_to_tab(tab, hwnd)
            time.sleep(0.5)

    success = editor_capture.capture_ue5_window(output_file)
    output_result({
        "file": output_file,
        "captured": success
    })


def capture_mode_asset(params):
    asset_path = params["asset_path"]
    output_file = params["output_file"]
    tab = params.get("tab")

    # Prepare arguments for open_asset_and_screenshot
    kwargs = {
        "asset_path": asset_path,
        "output_path": output_file,
        "delay": 3.0
    }
    if tab is not None:
        kwargs["tab_number"] = tab

    result = editor_capture.open_asset_and_screenshot(**kwargs)
    
    output_result({
        "file": output_file,
        "opened": result["opened"],
        "captured": result["screenshot"],
    })


def capture_mode_batch(params):
    asset_list = params["asset_list"]
    output_dir = params["output_dir"]

    results = editor_capture.batch_asset_screenshots(
        asset_paths=asset_list,
        output_dir=output_dir,
        delay=3.0,
        close_after=True,
    )

    files = [r.get("screenshot_path") for r in results if r.get("screenshot")]
    success_count = len(files)
    total_count = len(asset_list)

    output_result({
        "files": files,
        "success_count": success_count,
        "total_count": total_count,
    })


def main():
    params = get_params()

    # Ensure correct level is loaded
    ensure_level_loaded(params["level"])

    mode = params.get("mode", "window")

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
