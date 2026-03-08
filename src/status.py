"""apc status command — brief summary of detected tools and cache contents.

No login required. No network calls.
"""

from pathlib import Path

import click

from appliers.manifest import ToolManifest
from cache import load_local_bundle
from extractors import detect_installed_tools
from ui import (
    cache_summary_table,
    dim,
    header,
    info,
    tools_status_table,
    warning,
)


def _tool_sync_status(name: str) -> str:
    """Return sync status for a tool by comparing manifest records to disk.

    - "not synced"  — apc has never synced to this tool
    - "synced"      — all manifest-recorded files exist on disk
    - "out of sync" — manifest exists but one or more recorded files are missing

    Manifests are keyed by the detected tool name (e.g. "claude-code"),
    matching TOOL_NAME on every applier.
    """
    manifest = ToolManifest(name)

    if manifest.is_first_sync:
        return "not synced"

    # If the last sync recorded an error, surface it immediately (#34)
    if manifest.last_sync_failed:
        return "error"

    # Gather all file paths APC last wrote for this tool
    recorded_paths: list[str] = []

    for info_dict in manifest._data.get("skills", {}).values():
        if fp := info_dict.get("file_path"):
            recorded_paths.append(fp)

    for info_dict in manifest._data.get("linked_skills", {}).values():
        if fp := info_dict.get("link_path"):
            recorded_paths.append(fp)

    # memory is a flat dict {file_path, checksum, ...}, not a dict-of-dicts.
    if fp := manifest._data.get("memory", {}).get("file_path"):
        recorded_paths.append(fp)

    # If nothing was recorded (e.g. only MCP servers were synced), trust the timestamp
    if not recorded_paths:
        return "synced"

    # Check every recorded file still exists on disk
    all_present = all(Path(fp).exists() for fp in recorded_paths)
    return "synced" if all_present else "out of sync"


def _build_tools_status(tool_list):
    """Build tool status list with real consistency check against disk."""
    return [{"name": name, "status": _tool_sync_status(name)} for name in tool_list]


@click.command()
def status():
    """Show detected tools and local cache summary."""
    header("Status")

    # Detect tools and show status table
    tool_list = detect_installed_tools()
    bundle = load_local_bundle()

    if tool_list:
        tools = _build_tools_status(tool_list)
        tools_status_table(tools)
    else:
        warning("No AI tools detected on this machine.")

    # Local cache summary
    cache_skills = len(bundle["skills"])
    cache_mcp = len(bundle["mcp_servers"])
    cache_memory = len(bundle["memory"])
    cache_summary_table(cache_skills, cache_mcp, cache_memory, title="Local Cache")

    if not cache_skills and not cache_mcp and not cache_memory:
        info("Cache is empty. Run 'apc collect' to extract from local tools.")

    # LLM provider status
    try:
        from llm_config import get_default_model, load_auth_profiles

        default_model = get_default_model()
        profiles = load_auth_profiles()
        profile_count = len(profiles.get("profiles", {}))

        if default_model:
            info(f"LLM: {default_model} ({profile_count} auth profile(s))")
        else:
            dim("\nNo LLM configured. Run 'apc configure' for LLM-based memory sync.")
    except ImportError:
        pass

    dim("\nRun 'apc skill show' or 'apc memory show' for details.")
