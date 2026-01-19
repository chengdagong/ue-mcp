"""
UE-MCP: MCP Server for Unreal Editor Interaction

This package provides a FastMCP-based server that enables AI assistants
to interact with Unreal Editor through the Python remote execution protocol.
"""

__version__ = "0.1.0"

from .autoconfig import get_bundled_site_packages
from .editor_manager import EditorInstance, EditorManager
from .remote_client import RemoteExecutionClient

__all__ = [
    "EditorManager",
    "EditorInstance",
    "RemoteExecutionClient",
    "get_bundled_site_packages",
]
