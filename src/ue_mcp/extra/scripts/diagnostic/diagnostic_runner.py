"""
Asset diagnostic runner script for MCP.

Runs asset_diagnostic.diagnose() on the specified asset path
and outputs structured JSON result for the MCP server to parse.

Usage (CLI):
    python diagnostic_runner.py --asset-path=/Game/Maps/TestLevel

MCP mode (sys.argv):
    asset_path: str - Asset path to diagnose (e.g., /Game/Maps/TestLevel)
"""
import argparse
import json
import sys

# Force reload asset_diagnostic module to ensure latest version
# This is critical because UE5 caches Python modules between executions
# Must be done BEFORE importing asset_diagnostic
modules_to_remove = [k for k in list(sys.modules.keys()) if k.startswith("asset_diagnostic")]
for mod_name in modules_to_remove:
    del sys.modules[mod_name]

import asset_diagnostic

# Flag to track if running in MCP mode (vs CLI mode)
_mcp_mode = None


def _is_mcp_mode() -> bool:
    """Check if running in MCP mode (vs CLI mode)."""
    global _mcp_mode
    if _mcp_mode is None:
        import os
        _mcp_mode = os.environ.get('UE_MCP_MODE') == '1'
    return _mcp_mode


def output_result(data: dict) -> None:
    """
    Output result as pure JSON (last line of output).

    The MCP server will parse the last valid JSON object from the output.
    This enables clean output without special markers.

    In MCP mode: Outputs compact JSON for parsing
    In CLI mode: Outputs formatted JSON for readability
    """
    if _is_mcp_mode():
        # MCP mode: compact JSON (will be parsed as last line)
        print(json.dumps(data))
    else:
        # CLI mode: human-readable formatted output
        print("\n" + "=" * 60)
        print("DIAGNOSTIC RESULT")
        print("=" * 60)
        print(json.dumps(data, indent=2))
        print("=" * 60)


def serialize_result(result) -> dict:
    """Serialize DiagnosticResult to dict, with fallback for older versions."""
    # Try to_dict() method first
    if hasattr(result, "to_dict"):
        return result.to_dict()

    # Fallback manual serialization for older cached modules
    issues = []
    for issue in result.issues:
        issues.append({
            "severity": issue.severity.value if hasattr(issue.severity, "value") else str(issue.severity),
            "category": issue.category,
            "message": issue.message,
            "actor": issue.actor,
            "details": issue.details,
            "suggestion": issue.suggestion,
        })

    return {
        "asset_path": result.asset_path,
        "asset_type": result.asset_type.value if hasattr(result.asset_type, "value") else str(result.asset_type),
        "asset_name": result.asset_name,
        "errors": result.error_count if hasattr(result, "error_count") else 0,
        "warnings": result.warning_count if hasattr(result, "warning_count") else 0,
        "issues": issues,
        "metadata": result.metadata if hasattr(result, "metadata") else {},
        "summary": result.summary if hasattr(result, "summary") else None,
        "report": result.get_report(verbose=True) if hasattr(result, "get_report") else "",
    }


def main():
    parser = argparse.ArgumentParser(
        description="Run diagnostics on a UE5 asset"
    )
    parser.add_argument(
        "--asset-path",
        required=True,
        help="Asset path to diagnose (e.g., /Game/Maps/TestLevel)"
    )
    args = parser.parse_args()

    asset_path = args.asset_path

    # Run diagnostic - asset_diagnostic handles type detection internally
    result = asset_diagnostic.diagnose(asset_path, verbose=True)

    if result is None:
        output_result({
            "success": False,
            "error": f"No diagnostic available for asset: {asset_path}"
        })
        return

    # Serialize result with fallback for older cached modules
    result_dict = serialize_result(result)
    result_dict["success"] = True
    output_result(result_dict)


if __name__ == "__main__":
    main()
