"""
Asset diagnostic runner script for MCP.

Runs asset_diagnostic.diagnose() on the specified asset path
and outputs structured JSON result for the MCP server to parse.

Expected __PARAMS__:
    asset_path: str - Asset path to diagnose (e.g., /Game/Maps/TestLevel)
"""
import json
import sys

# Force reload asset_diagnostic module to ensure latest version
# This is critical because UE5 caches Python modules between executions
# Must be done BEFORE importing asset_diagnostic
modules_to_remove = [k for k in list(sys.modules.keys()) if k.startswith("asset_diagnostic")]
for mod_name in modules_to_remove:
    del sys.modules[mod_name]

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

    # Serialize result with fallback for older cached modules
    result_dict = serialize_result(result)
    result_dict["success"] = True
    output_result(result_dict)


if __name__ == "__main__":
    main()
