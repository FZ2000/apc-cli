"""apc status command — brief summary of detected tools and cache contents.

No login required. No network calls.
"""

import click

from apc.cache import load_local_bundle
from apc.extractors import detect_installed_tools
from apc.ui import (
    cache_summary_table,
    dim,
    header,
    info,
    tools_status_table,
    warning,
)


def _build_tools_status(tool_list, bundle):
    """Build tool status list with basic sync detection."""
    tools = []
    for name in tool_list:
        has_skills = any(s.get("source_tool") == name for s in bundle["skills"])
        has_mcp = any(s.get("source_tool") == name for s in bundle["mcp_servers"])
        has_data = has_skills or has_mcp
        tools.append(
            {
                "name": name,
                "status": "synced" if has_data else "not synced",
            }
        )
    return tools


@click.command()
def status():
    """Show detected tools and local cache summary."""
    header("Status")

    # Detect tools and show status table
    tool_list = detect_installed_tools()
    bundle = load_local_bundle()

    if tool_list:
        tools = _build_tools_status(tool_list, bundle)
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
        from apc.llm_config import get_default_model, load_auth_profiles

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
