"""
Asset diagnostic runner script for MCP.

Runs asset_diagnostic.diagnose() on the specified asset path
and outputs structured JSON result for the MCP server to parse.

Usage (CLI):
    python diagnostic_runner.py --asset-path=/Game/Maps/TestLevel

MCP mode (__PARAMS__):
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

# Flag to track if running in MCP mode (vs CLI mode)
_mcp_mode = None


def _is_mcp_mode() -> bool:
    """Check if running in MCP mode (vs CLI mode)."""
    global _mcp_mode
    if _mcp_mode is None:
        import builtins
        _mcp_mode = hasattr(builtins, "__PARAMS__")
    return _mcp_mode


def _parse_cli_value(value_str: str):
    """Parse a CLI argument value string to appropriate Python type."""
    if value_str.lower() in ("none", "null"):
        return None
    if value_str.lower() in ("true", "yes", "1"):
        return True
    if value_str.lower() in ("false", "no", "0"):
        return False
    try:
        return int(value_str)
    except ValueError:
        pass
    try:
        return float(value_str)
    except ValueError:
        pass
    return value_str


def get_params() -> dict:
    """
    Get parameters from MCP server or CLI arguments.

    The MCP server injects __PARAMS__ into builtins before executing the script.
    For direct execution, parameters are parsed from sys.argv.
    """
    import builtins

    # Check MCP mode first
    if hasattr(builtins, "__PARAMS__"):
        return builtins.__PARAMS__

    # CLI mode: parse arguments
    params = {}
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        arg = args[i]
        if arg.startswith("--"):
            arg = arg[2:]
            if "=" in arg:
                key, value = arg.split("=", 1)
                params[key.replace("-", "_")] = _parse_cli_value(value)
            elif i + 1 < len(args) and not args[i + 1].startswith("--"):
                key = arg.replace("-", "_")
                params[key] = _parse_cli_value(args[i + 1])
                i += 1
            else:
                params[arg.replace("-", "_")] = True
        i += 1

    # Validate required parameters
    if "asset_path" not in params:
        raise RuntimeError(
            "Missing required parameter: asset_path\n"
            "Usage: python diagnostic_runner.py --asset-path=/Game/Maps/TestLevel"
        )

    return params


def output_result(data: dict) -> None:
    """
    Output result in format appropriate for current mode.

    In MCP mode: Outputs JSON with special prefix for parsing.
    In CLI mode: Outputs human-readable formatted JSON.
    """
    if _is_mcp_mode():
        print("__DIAGNOSTIC_RESULT__" + json.dumps(data))
    else:
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
