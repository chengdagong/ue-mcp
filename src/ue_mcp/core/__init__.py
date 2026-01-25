"""
UE-MCP Core Module

Core utilities including path discovery, pip installation, port allocation,
and shared constants.
"""

from .constants import (
    ENV_VAR_CALL,
    ENV_VAR_MODE,
    INJECT_TIME_MAX_AGE,
    MARKER_ACTOR_SNAPSHOT_RESULT,
    MARKER_CURRENT_LEVEL_PATH,
    MARKER_SNAPSHOT_RESULT,
)
from .pip_install import (
    BUNDLED_MODULES,
    MODULE_TO_PACKAGE,
    extract_bundled_module_imports,
    extract_import_statements,
    extract_missing_module,
    generate_module_unload_code,
    get_missing_module_from_result,
    is_import_error,
    module_to_package,
    pip_install,
    pip_list,
)
from .port_allocator import (
    PORT_RANGE_END,
    PORT_RANGE_START,
    find_available_port,
)
from .utils import (
    find_ue5_build_batch_file,
    find_ue5_editor,
    find_ue5_editor_for_project,
    find_ue5_project_root,
    find_ue5_python,
    find_ue5_python_for_editor,
    find_ue5_runuat,
    find_uproject_file,
    get_project_name,
    get_ue5_engine_root,
)

__all__ = [
    # Constants
    "ENV_VAR_MODE",
    "ENV_VAR_CALL",
    "INJECT_TIME_MAX_AGE",
    "MARKER_SNAPSHOT_RESULT",
    "MARKER_ACTOR_SNAPSHOT_RESULT",
    "MARKER_CURRENT_LEVEL_PATH",
    # Utils
    "find_ue5_project_root",
    "find_uproject_file",
    "get_project_name",
    "find_ue5_editor",
    "find_ue5_editor_for_project",
    "find_ue5_python",
    "find_ue5_python_for_editor",
    "find_ue5_build_batch_file",
    "find_ue5_runuat",
    "get_ue5_engine_root",
    # Pip install
    "MODULE_TO_PACKAGE",
    "BUNDLED_MODULES",
    "extract_missing_module",
    "module_to_package",
    "extract_import_statements",
    "extract_bundled_module_imports",
    "generate_module_unload_code",
    "pip_install",
    "pip_list",
    "is_import_error",
    "get_missing_module_from_result",
    # Port allocator
    "PORT_RANGE_START",
    "PORT_RANGE_END",
    "find_available_port",
]
