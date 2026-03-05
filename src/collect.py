"""apc collect command — extract from local tools into local cache.

No login required. No network calls.
Four-phase flow: scan → conflict resolution → confirm → collect.
"""

from datetime import datetime, timezone
from typing import Dict, List

import click

from cache import (
    load_mcp_servers,
    load_memory,
    load_skills,
    merge_mcp_servers,
    merge_memory,
    merge_skills,
    save_mcp_servers,
    save_memory,
    save_skills,
)
from extractors import detect_installed_tools, get_extractor
from secrets_manager import detect_and_redact, store_secrets_batch
from ui import (
    cache_summary_table,
    display_memory_files,
    error,
    header,
    info,
    scan_results_table,
    success,
    warning,
)


def _resolve_memory_conflicts(
    all_memory: List[Dict],
    yes: bool,
) -> List[Dict]:
    """File-level conflict detection and resolution.

    If multiple tools have non-empty memory files, present them for user
    selection.  If only one tool has memory files (or --yes), collect all.
    """
    if not all_memory:
        return []

    # Group by source tool
    tools_with_memory = set(m["source_tool"] for m in all_memory)

    # No conflict if only one tool has memory files
    if len(tools_with_memory) <= 1 or yes:
        return all_memory

    # Multiple tools have memory files — show conflict UI
    return display_memory_files(all_memory)


@click.command()
@click.option(
    "--tools",
    default=None,
    help="Comma-separated list of tools to collect from (e.g., claude,cursor)",
)
@click.option("--no-memory", is_flag=True, help="Skip collecting memory entries")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
def collect(tools, no_memory, yes):
    """Extract from installed AI tools and save to local cache.

    No login or network required.
    """
    # --- Phase 1: Scan ---
    header("Scanning")

    if tools is not None:
        tool_list = [t.strip() for t in tools.split(",") if t.strip()]
        if not tool_list:
            error("--tools requires at least one tool name (e.g. --tools claude,cursor)")
            return
    else:
        tool_list = detect_installed_tools()

    if not tool_list:
        warning("No AI tools detected on this machine.")
        return

    info(f"Detected tools: {', '.join(tool_list)}")

    # Extract from all tools, hold results in memory
    tool_extractions = {}
    tool_counts = {}

    for tool_name in tool_list:
        try:
            extractor = get_extractor(tool_name)
            skills = extractor.extract_skills()
            mcp_servers = extractor.extract_mcp_servers()
            memory = extractor.extract_memory() if not no_memory else []

            tool_extractions[tool_name] = {
                "skills": skills,
                "mcp_servers": mcp_servers,
                "memory": memory,
            }
            tool_counts[tool_name] = {
                "skills": len(skills),
                "mcp": len(mcp_servers),
                "memory": len(memory),
            }
        except Exception as e:
            error(f"Failed to extract from {tool_name}: {e}")

    if not tool_extractions:
        error("No data extracted from any tool.")
        return

    scan_results_table(tool_counts)

    # --- Phase 2: Conflict Resolution ---
    all_memory_raw: List[Dict] = []
    for data in tool_extractions.values():
        all_memory_raw.extend(data["memory"])

    if all_memory_raw and not no_memory:
        selected_memory = _resolve_memory_conflicts(all_memory_raw, yes)
    else:
        selected_memory = []

    # --- Phase 3: Confirm ---
    if not yes:
        if not click.confirm("\nProceed with collection?"):
            info("Cancelled.")
            return

    # --- Phase 4: Collect ---
    header("Collecting")

    new_skills = []
    new_mcp_servers = []

    for tool_name, data in tool_extractions.items():
        new_skills.extend(data["skills"])
        new_mcp_servers.extend(data["mcp_servers"])

    # Add collected_at timestamp to selected memory entries
    now = datetime.now(timezone.utc).isoformat()
    for entry in selected_memory:
        entry["collected_at"] = now

    # Redact secrets from MCP servers and store in keychain
    all_secrets = {}
    for server in new_mcp_servers:
        env = server.get("env", {})
        if env:
            redacted_env, secrets = detect_and_redact(env)
            server["env"] = redacted_env
            if secrets:
                server["secret_placeholders"] = list(secrets.keys())
                all_secrets.update(secrets)

    if all_secrets:
        store_secrets_batch("local", all_secrets)
        success(f"Stored {len(all_secrets)} secret(s) in OS keychain")

    # Merge into existing cache (upsert, never delete)
    merged_skills = merge_skills(load_skills(), new_skills)
    merged_mcp = merge_mcp_servers(load_mcp_servers(), new_mcp_servers)
    merged_memory = merge_memory(load_memory(), selected_memory)

    save_skills(merged_skills)
    save_mcp_servers(merged_mcp)
    save_memory(merged_memory)

    cache_summary_table(
        len(merged_skills), len(merged_mcp), len(merged_memory), title="Local Cache Updated"
    )
    success("Collection complete.")
