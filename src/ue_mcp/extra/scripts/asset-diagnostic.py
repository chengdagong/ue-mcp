#!/usr/bin/env python3
"""
Asset Diagnostic Wrapper for remote-execute.py

A simple CLI wrapper for the asset_diagnostic module that makes it easy to
diagnose UE5 assets through remote execution.

Usage:
    asset-diagnostic.py ASSET_PATH

Examples:
    # Diagnose a level
    asset-diagnostic.py /Game/Maps/TestLevel

    # Diagnose a blueprint
    asset-diagnostic.py /Game/Blueprints/BP_MyActor

Via remote-execute.py:
    remote-execute.py --file asset-diagnostic.py \\
        --args "asset_path=/Game/Maps/TestLevel"
"""

import sys
import argparse
from pathlib import Path

# Add site-packages to Python path for asset_diagnostic module
# Handle both direct execution and remote execution (where __file__ is not defined)
if '__file__' in globals():
    # Direct execution: use relative path from script location
    site_packages = Path(__file__).parent.parent.parent / "skills" / "ue5-python" / "site-packages"
else:
    # Remote execution: try to find site-packages by searching common locations
    possible_paths = [
        Path("d:/Code/ue5-dev-tools/ue5-dev-tools/skills/ue5-python/site-packages"),
        Path.cwd() / "ue5-dev-tools" / "skills" / "ue5-python" / "site-packages",
    ]
    site_packages = None
    for path in possible_paths:
        if path.exists():
            site_packages = path
            break

    if not site_packages:
        # Last resort: try to import directly (may already be in path)
        site_packages = Path.cwd()

sys.path.insert(0, str(site_packages))


def main():
    """Main entry point for the wrapper script."""
    parser = argparse.ArgumentParser(
        description="Diagnose UE5 assets for common issues",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s /Game/Maps/TestLevel
  %(prog)s /Game/Blueprints/BP_MyActor

Via remote-execute.py:
  remote-execute.py --file %(prog)s --args "asset_path=/Game/Maps/TestLevel"

For diagnosing current level or selected assets, use Python API directly:
  import asset_diagnostic
  asset_diagnostic.diagnose_current_level()
  asset_diagnostic.diagnose_selected()
        """
    )

    parser.add_argument(
        "--asset-path",
        required=True,
        dest="asset_path",
        help="Path to the asset to diagnose (e.g., /Game/Maps/TestLevel)"
    )

    args = parser.parse_args()

    # Import asset_diagnostic module (must be done in UE5 Python environment)
    import asset_diagnostic

    # Run diagnostic
    try:
        result = asset_diagnostic.diagnose(args.asset_path)

        # Exit with error code if diagnostic found issues
        if result and result.has_errors:
            sys.exit(1)

    except Exception as e:
        print(f"Error running diagnostic: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
