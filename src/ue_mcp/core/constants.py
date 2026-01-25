"""
Shared constants for UE-MCP.

This module contains constants that are shared across the MCP server
and the scripts executed in UE5's Python environment.

IMPORTANT: These constants must be kept in sync with the corresponding
values in extra/scripts/ue_mcp_capture/utils.py since scripts run in
a separate Python environment (UE5's embedded Python).
"""

# Environment variable names for script parameter passing
# Used by _helpers.py (MCP server side) and utils.py (UE5 script side)
ENV_VAR_MODE = "UE_MCP_MODE"  # "1" when running via MCP (vs CLI)
ENV_VAR_CALL = "UE_MCP_CALL"  # "<checksum>:<timestamp>:<json_params>" script call info

# Maximum allowed age for injected parameters (in seconds)
# Increased to 5s to account for UE5's Python execution lag between
# parameter injection (EXECUTE_STATEMENT) and script file execution (EXECUTE_FILE)
INJECT_TIME_MAX_AGE = 5.0

# Output markers for script results (legacy, prefer pure JSON output)
# These are kept for backward compatibility but new scripts should
# output pure JSON as the last line of output
MARKER_SNAPSHOT_RESULT = "SNAPSHOT_RESULT:"
MARKER_ACTOR_SNAPSHOT_RESULT = "ACTOR_SNAPSHOT_RESULT:"
MARKER_CURRENT_LEVEL_PATH = "CURRENT_LEVEL_PATH:"
