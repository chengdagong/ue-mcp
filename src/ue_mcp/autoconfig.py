"""
UE-MCP Auto Configuration

Automatically detect and fix UE5 project configuration for Python remote execution.
"""

import json
import logging
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# INI file section for Python plugin settings
PYTHON_PLUGIN_SECTION = "[/Script/PythonScriptPlugin.PythonScriptPluginSettings]"


def check_python_plugin(
    uproject_path: Path, auto_fix: bool = False
) -> tuple[bool, bool, str]:
    """
    Check and optionally fix Python-related plugins in .uproject.

    Args:
        uproject_path: Path to .uproject file
        auto_fix: Whether to automatically fix issues

    Returns:
        (enabled, modified, message)
    """
    required_plugins = ["PythonScriptPlugin", "PythonAutomationTest"]

    try:
        with open(uproject_path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except json.JSONDecodeError as e:
        return False, False, f"JSON Parse Error: {e}"
    except Exception as e:
        return False, False, f"Read Failed: {e}"

    plugins = config.get("Plugins", [])
    modified = False
    messages = []
    all_enabled = True

    for plugin_name in required_plugins:
        plugin = next((p for p in plugins if p.get("Name") == plugin_name), None)

        if plugin is None:
            if auto_fix:
                plugins.append({"Name": plugin_name, "Enabled": True})
                modified = True
                messages.append(f"Added {plugin_name}")
            else:
                all_enabled = False
                messages.append(f"{plugin_name} not in Plugins array")
        elif not plugin.get("Enabled", False):
            if auto_fix:
                plugin["Enabled"] = True
                modified = True
                messages.append(f"Enabled {plugin_name}")
            else:
                all_enabled = False
                messages.append(f"{plugin_name} exists but disabled")

    if modified:
        config["Plugins"] = plugins
        try:
            with open(uproject_path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent="\t")
            return True, True, "; ".join(messages)
        except Exception as e:
            return False, False, f"Write Failed: {e}"

    if not messages:
        messages.append("Python plugins correctly configured")

    return all_enabled, False, "; ".join(messages)


def _read_ini_file(
    ini_path: Path,
) -> tuple[Optional[str], Optional[list[str]], Optional[str]]:
    """
    Read INI file content and lines.

    Returns:
        (content, lines, error_message) - error_message is None on success
    """
    try:
        with open(ini_path, "r", encoding="utf-8") as f:
            content = f.read()
        return content, content.splitlines(keepends=True), None
    except Exception as e:
        return None, None, f"Read Failed: {e}"


def _section_exists(lines: list[str], section: str) -> bool:
    """Check if a section exists in INI file lines (case-insensitive)."""
    section_lower = section.lower()
    return any(section_lower in line.lower() for line in lines)


def _insert_into_section(lines: list[str], section: str, entries: list[str]) -> str:
    """
    Insert entries into the specified section.
    Entries are inserted at the end of the section, before the next section starts.

    Returns:
        Modified content as a string
    """
    section_lower = section.lower()
    new_lines = []
    in_target_section = False
    entries_added = False

    for line in lines:
        new_lines.append(line)

        if section_lower in line.lower():
            in_target_section = True
            continue

        if (
            in_target_section
            and line.strip().startswith("[")
            and section_lower not in line.lower()
        ):
            # Entering a new section - insert entries before it
            if not entries_added:
                for entry in entries:
                    new_lines.insert(-1, f"{entry}\n")
                entries_added = True
            in_target_section = False

    # If still in target section at end of file, append entries
    if in_target_section and not entries_added:
        if new_lines and not new_lines[-1].endswith("\n"):
            new_lines[-1] += "\n"
        for entry in entries:
            new_lines.append(f"{entry}\n")

    return "".join(new_lines)


def check_remote_execution(
    ini_path: Path, auto_fix: bool = False
) -> tuple[bool, bool, list[str]]:
    """
    Check and optionally fix Remote Execution settings in DefaultEngine.ini.

    Args:
        ini_path: Path to DefaultEngine.ini
        auto_fix: Whether to automatically fix issues

    Returns:
        (enabled, modified, changes_list)
    """
    required_settings = {
        "bRemoteExecution": "True",
        "bDeveloperMode": "True",
        "RemoteExecutionMulticastBindAddress": "0.0.0.0",
    }

    if not ini_path.exists():
        if not auto_fix:
            return False, False, ["DefaultEngine.ini does not exist"]

        ini_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            lines = ["\n", f"{PYTHON_PLUGIN_SECTION}\n"]
            lines.extend(f"{k}={v}\n" for k, v in required_settings.items())
            with open(ini_path, "w", encoding="utf-8") as f:
                f.writelines(lines)
            changes = ["Created DefaultEngine.ini"]
            changes.extend(f"Set {k}={v}" for k, v in required_settings.items())
            return True, True, changes
        except Exception as e:
            return False, False, [f"Write Failed: {e}"]

    content, lines, error = _read_ini_file(ini_path)
    if error:
        return False, False, [error]

    section_exists = _section_exists(lines, PYTHON_PLUGIN_SECTION)
    changes = []
    missing_settings = {}

    if not section_exists:
        missing_settings = required_settings.copy()
        changes.append(f"Missing section {PYTHON_PLUGIN_SECTION}")
    else:
        for key, expected_value in required_settings.items():
            key_lower = key.lower()
            found_correct = False

            for line in lines:
                line_stripped = line.strip().lower()
                if line_stripped.startswith(key_lower) and "=" in line_stripped:
                    _, _, value = line.partition("=")
                    value = value.strip()
                    if value.lower() == expected_value.lower():
                        found_correct = True
                    else:
                        changes.append(f"{key} needs {expected_value} (is: {value})")
                    break

            if not found_correct and key not in [c.split()[0] for c in changes]:
                missing_settings[key] = expected_value
                changes.append(f"{key} needs {expected_value} (is: None)")

    needs_fix = bool(missing_settings)

    if auto_fix and needs_fix:
        try:
            if not section_exists:
                if not content.endswith("\n"):
                    content += "\n"
                content += f"\n{PYTHON_PLUGIN_SECTION}\n"
                content += "".join(f"{k}={v}\n" for k, v in required_settings.items())
                changes = [f"Added section {PYTHON_PLUGIN_SECTION}"]
                changes.extend(f"Set {k}={v}" for k, v in required_settings.items())
            else:
                entries = [f"{k}={v}" for k, v in missing_settings.items()]
                content = _insert_into_section(lines, PYTHON_PLUGIN_SECTION, entries)
                changes = [
                    f"Set {k}={v} (was: None)" for k, v in missing_settings.items()
                ]

            with open(ini_path, "w", encoding="utf-8") as f:
                f.write(content)
            needs_fix = False
        except Exception as e:
            return False, False, [f"Write Failed: {e}"]

    if not changes:
        changes = ["Remote execution config correct"]

    enabled = not needs_fix or auto_fix
    modified = auto_fix and bool(missing_settings)
    return enabled, modified, changes


def check_additional_paths(
    ini_path: Path, paths: list[str], auto_fix: bool = False
) -> tuple[bool, bool, list[str]]:
    """
    Check and optionally add AdditionalPaths settings in DefaultEngine.ini.

    Args:
        ini_path: Path to DefaultEngine.ini
        paths: List of paths to add
        auto_fix: Whether to automatically fix issues

    Returns:
        (configured, modified, changes_list)
    """
    if not paths:
        return True, False, ["No additional paths requested"]

    if not ini_path.exists():
        return False, False, [
            "DefaultEngine.ini does not exist (will be created by remote_execution check)"
        ]

    content, lines, error = _read_ini_file(ini_path)
    if error:
        return False, False, [error]

    if not _section_exists(lines, PYTHON_PLUGIN_SECTION):
        return False, False, ["Section missing"]

    # Check which paths are already configured
    missing_paths = []
    for path in paths:
        path_normalized = path.replace("\\", "/")
        found = False
        for line in lines:
            if (
                "additionalpaths" in line.lower()
                and path_normalized.lower() in line.lower().replace("\\", "/")
            ):
                found = True
                break
        if not found:
            missing_paths.append(path_normalized)

    if not missing_paths:
        return True, False, ["All AdditionalPaths correctly configured"]

    if not auto_fix:
        return False, False, [f"AdditionalPaths missing: {', '.join(missing_paths)}"]

    try:
        entries = [f'+AdditionalPaths=(Path="{p}")' for p in missing_paths]
        content = _insert_into_section(lines, PYTHON_PLUGIN_SECTION, entries)
        with open(ini_path, "w", encoding="utf-8") as f:
            f.write(content)
        return True, True, [f"Added AdditionalPaths: {', '.join(missing_paths)}"]
    except Exception as e:
        return False, False, [f"Write Failed: {e}"]


def _update_status(result: dict[str, Any], modified: bool, success: bool) -> None:
    """Update result status based on check outcome."""
    if modified:
        result["restart_needed"] = True
        result["status"] = "fixed"
    elif not success and result["status"] != "fixed":
        result["status"] = "needs_fix"


def run_config_check(
    project_root: Path,
    auto_fix: bool = True,
    additional_paths: Optional[list[str]] = None,
) -> dict[str, Any]:
    """
    Run full config check and fix.

    Args:
        project_root: Path to project root directory
        auto_fix: Whether to automatically fix issues
        additional_paths: Optional list of additional Python paths to add

    Returns:
        Result dictionary with status, check results, and summary
    """
    additional_paths = additional_paths or []

    result: dict[str, Any] = {
        "status": "ok",
        "python_plugin": {
            "path": None,
            "enabled": False,
            "modified": False,
            "message": "",
        },
        "remote_execution": {
            "path": None,
            "enabled": False,
            "modified": False,
            "message": "",
        },
        "additional_paths": {
            "paths": additional_paths,
            "configured": False,
            "modified": False,
            "message": "",
        },
        "restart_needed": False,
        "summary": "",
    }

    # Find .uproject file
    uproject_files = list(project_root.glob("*.uproject"))
    if not uproject_files:
        result["status"] = "error"
        result["summary"] = f"No .uproject found in {project_root}"
        return result

    uproject_path = uproject_files[0]

    # Check Python Plugin
    result["python_plugin"]["path"] = str(uproject_path.name)
    enabled, modified, message = check_python_plugin(uproject_path, auto_fix)
    result["python_plugin"].update(enabled=enabled, modified=modified, message=message)
    _update_status(result, modified, enabled)

    # Check Remote Execution
    ini_path = project_root / "Config" / "DefaultEngine.ini"
    result["remote_execution"]["path"] = str(ini_path.relative_to(project_root))
    enabled, modified, changes = check_remote_execution(ini_path, auto_fix)
    result["remote_execution"].update(
        enabled=enabled, modified=modified, message="; ".join(changes)
    )
    _update_status(result, modified, enabled)

    # Check Additional Paths (only if requested)
    if additional_paths:
        configured, modified, changes = check_additional_paths(
            ini_path, additional_paths, auto_fix
        )
        result["additional_paths"].update(
            configured=configured, modified=modified, message="; ".join(changes)
        )
        _update_status(result, modified, configured)
    else:
        result["additional_paths"]["configured"] = True
        result["additional_paths"]["message"] = "No additional paths requested"

    # Generate summary
    if result["status"] == "fixed":
        fix_count = sum(
            [
                result["python_plugin"]["modified"],
                result["remote_execution"]["modified"],
                result["additional_paths"]["modified"],
            ]
        )
        result["summary"] = f"Fixed {fix_count} issue(s)."
    elif result["status"] == "needs_fix":
        result["summary"] = "Issues found. Auto-fix required."
    elif result["status"] == "ok":
        result["summary"] = "All configurations correct."

    return result
