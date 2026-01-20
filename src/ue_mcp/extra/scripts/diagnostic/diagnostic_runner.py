"""
Asset diagnostic runner script for MCP.

Runs asset_diagnostic.diagnose() on the specified asset path
and outputs structured JSON result for the MCP server to parse.

Expected __PARAMS__:
    asset_path: str - Asset path to diagnose (e.g., /Game/Maps/TestLevel)
"""
import json

import asset_diagnostic


def get_params() -> dict:
    """Get parameters injected by MCP server."""
    import builtins
    if hasattr(builtins, "__PARAMS__"):
        return builtins.__PARAMS__
    raise RuntimeError(
        "__PARAMS__ not found. If testing manually, set builtins.__PARAMS__ = {...} first."
    )


def output_result(data: dict) -> None:
    """Output result in format expected by MCP server."""
    print("__DIAGNOSTIC_RESULT__" + json.dumps(data))


def main():
    params = get_params()
    asset_path = params["asset_path"]

    # Run diagnostic - asset_diagnostic handles type detection internally
    result = asset_diagnostic.diagnose(asset_path, verbose=True)

    if result is None:
        output_result({
            "success": False,
            "error": f"No diagnostic available for asset: {asset_path}"
        })
        return

    # Use to_dict() method for full serialization including report text
    result_dict = result.to_dict()
    result_dict["success"] = True
    output_result(result_dict)


if __name__ == "__main__":
    main()
