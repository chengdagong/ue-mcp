"""
Editor initialization script - applies monkey patches after editor launch.

This script is automatically executed by launch_manager.py after the editor
connection is established. It applies monkey patches to enhance UE5 behavior.

Current patches:
1. LevelEditorSubsystem.load_level - calls RefreshSlateView after level load
   to ensure the Slate UI updates properly.

Usage:
    # Via MCP (automatically after editor launch):
    Executed by launch_manager.py after connection

    # Via UE Python console (for testing):
    exec(open(r'D:\\path\\to\\editor_init.py').read())
"""

import json

import unreal


def patch_load_level() -> dict:
    """
    Patch LevelEditorSubsystem.load_level to call RefreshSlateView after load.

    This ensures Slate UI updates properly after level load operations,
    replacing the manual open_output_log/close_output_log pattern.

    Returns:
        dict with success status and message
    """
    subsystem_class = unreal.LevelEditorSubsystem

    # Idempotency check - skip if already patched
    if getattr(subsystem_class, "__ue_mcp_load_level_patched__", False):
        return {"success": True, "message": "already patched", "patched": False}

    # Store the original method
    original_load_level = subsystem_class.load_level

    def patched_load_level(self, level_path: str) -> bool:
        """Wrapped load_level that calls RefreshSlateView after loading."""
        # Call original method
        result = original_load_level(self, level_path)

        # Call RefreshSlateView to ensure UI updates
        try:
            unreal.ExSlateTabLibrary.refresh_slate_view()
        except Exception as e:
            # Log warning but don't fail - the level load still succeeded
            unreal.log_warning(f"RefreshSlateView failed after load_level: {e}")

        return result

    # Apply the patch
    subsystem_class.load_level = patched_load_level

    # Mark as patched (for idempotency check)
    subsystem_class.__ue_mcp_load_level_patched__ = True

    # Store original for potential restoration
    subsystem_class.__ue_mcp_original_load_level__ = original_load_level

    return {"success": True, "message": "patched successfully", "patched": True}


def main():
    """Main entry point - apply all initialization patches."""
    results = {}

    # Apply load_level patch
    try:
        results["load_level_patch"] = patch_load_level()
    except Exception as e:
        results["load_level_patch"] = {"success": False, "error": str(e)}

    # Overall success if all patches succeeded
    all_success = all(r.get("success", False) for r in results.values())

    output = {"success": all_success, "patches": results}

    print(json.dumps(output))


if __name__ == "__main__":
    main()
