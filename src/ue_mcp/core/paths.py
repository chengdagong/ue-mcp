"""
Path utilities for UE-MCP.

Provides functions to locate bundled scripts and resources.
"""

from pathlib import Path


def get_extra_dir() -> Path:
    """Get the extra directory (contains scripts, site-packages, plugin)."""
    return Path(__file__).parent.parent / "extra"


def get_scripts_dir() -> Path:
    """Get the scripts root directory."""
    return get_extra_dir() / "scripts"


def get_capture_scripts_dir() -> Path:
    """Get the capture scripts directory (ue_mcp_capture package)."""
    return get_scripts_dir() / "ue_mcp_capture"


def get_diagnostic_scripts_dir() -> Path:
    """Get the diagnostic scripts directory."""
    return get_scripts_dir() / "diagnostic"


def get_site_packages_dir() -> Path:
    """Get the bundled site-packages directory."""
    return get_extra_dir() / "site-packages"


def get_plugin_dir() -> Path:
    """Get the ExtraPythonAPIs plugin directory."""
    return get_extra_dir() / "plugin" / "ExtraPythonAPIs"
