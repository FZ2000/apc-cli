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
from frontmatter_parser import render_frontmatter
from secrets_manager import detect_and_redact, store_secrets_batch
from skills import save_skill_file
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


def _resolve_mcp_conflicts(
    all_servers: List[Dict],
    yes: bool,
) -> List[Dict]:
    """Detect MCP server name collisions across tools and let the user resolve them.

    A collision occurs when two or more tools provide an MCP server with the
    same name (e.g. both claude-code and cursor have a server called "my-mcp").

    For each collision the user may:
      - overwrite  → keep only one entry; the last-collected one is the default
      - rename     → keep both, but suffix the non-default one with its source
                     tool name (e.g. "my-mcp-cursor")

    When --yes / non-interactive: last-collected wins (overwrite silently).
    """
    if not all_servers:
        return []

    # Group by server name to detect collisions
    from collections import defaultdict

    by_name: Dict[str, List[Dict]] = defaultdict(list)
    for server in all_servers:
        by_name[server.get("name", "")].append(server)

    collisions = {name: entries for name, entries in by_name.items() if len(entries) > 1}

    if not collisions or yes:
        # No conflicts, or --yes: last-collected wins (standard merge behaviour)
        return all_servers

    # Interactive resolution
    from rich.console import Console
    from rich.table import Table

    console = Console()
    resolved: List[Dict] = []
    # Start with non-conflicting servers
    for name, entries in by_name.items():
        if len(entries) == 1:
            resolved.append(entries[0])

    for name, entries in collisions.items():
        console.print(
            f"\n[bold yellow]⚠ MCP server name conflict:[/bold yellow] [bold]{name!r}[/bold]"
        )

        tbl = Table(show_header=True, header_style="bold cyan", show_lines=False)
        tbl.add_column("#", style="dim", width=3)
        tbl.add_column("Source Tool", style="green")
        tbl.add_column("Command")
        tbl.add_column("Args")

        for i, entry in enumerate(entries, 1):
            cmd = entry.get("command") or ""
            args = " ".join(str(a) for a in entry.get("args", []))
            tbl.add_row(str(i), entry.get("source_tool", "?"), cmd, args)

        console.print(tbl)
        console.print(
            "[dim]Options: overwrite (keep one) or rename (keep both with tool suffix)[/dim]"
        )

        # Pick which entry to keep as canonical
        default_idx = len(entries)  # last-collected
        raw = click.prompt(
            f"  Keep which as {name!r}? [1-{len(entries)}]",
            default=str(default_idx),
        ).strip()
        try:
            keep_idx = int(raw) - 1
            if not (0 <= keep_idx < len(entries)):
                raise ValueError
        except ValueError:
            info(f"  Invalid choice — keeping last-collected entry for {name!r}")
            keep_idx = len(entries) - 1

        canonical = entries[keep_idx]
        others = [e for i, e in enumerate(entries) if i != keep_idx]

        resolved.append(canonical)

        # Ask about the others: rename or discard
        for other in others:
            src = other.get("source_tool", "other")
            new_name = f"{name}-{src}"
            choice = (
                click.prompt(
                    f"  Entry from {src!r}: [r]ename to {new_name!r} or [d]iscard?",
                    default="r",
                )
                .strip()
                .lower()
            )
            if choice.startswith("r"):
                renamed = dict(other)
                renamed["name"] = new_name
                resolved.append(renamed)
                info(f"  ✓ Renamed to {new_name!r}")
            else:
                info(f"  ✓ Discarded {src!r} entry for {name!r}")

    return resolved


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
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be collected without writing to cache. (#25)",
)
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
def collect(tools, no_memory, dry_run, yes):
    """Extract from installed AI tools and save to local cache.

    No login or network required.
    Use --dry-run to preview what would be collected without writing.
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
    all_mcp_raw: List[Dict] = []
    all_memory_raw: List[Dict] = []
    for data in tool_extractions.values():
        all_mcp_raw.extend(data["mcp_servers"])
        all_memory_raw.extend(data["memory"])

    resolved_mcp = _resolve_mcp_conflicts(all_mcp_raw, yes)

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
    for data in tool_extractions.values():
        new_skills.extend(data["skills"])

    new_mcp_servers = resolved_mcp

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

    # --- Dry-run: preview without writing (#25) ---
    if dry_run:
        from cache import get_cache_dir

        cache_dir = get_cache_dir()
        info("\n[dry-run] Would write to cache:")
        info(f"  {cache_dir / 'skills.json'}   ({len(new_skills)} skills)")
        info(f"  {cache_dir / 'mcp.json'}       ({len(new_mcp_servers)} MCP servers)")
        info(f"  {cache_dir / 'memory.json'}    ({len(selected_memory)} memory entries)")

        if new_skills:
            info("\n  Skills:")
            for s in new_skills:
                info(f"    • {s.get('name', '?')}  ({s.get('source_tool', '')})")

        if new_mcp_servers:
            info("\n  MCP Servers:")
            for sv in new_mcp_servers:
                info(f"    • {sv.get('name', '?')}  ({sv.get('source_tool', '')})")

        if selected_memory:
            info("\n  Memory files:")
            for e in selected_memory:
                label = e.get("label") or e.get("source_file") or e.get("content", "")[:40]
                info(f"    • {e.get('source_tool', '?')}/{label}")

        info("\n[dry-run] No files written.")
        return

    # Write collected skills to ~/.apc/skills/<name>/SKILL.md (source of truth)
    # Skills are never stored inline in the cache — ~/.apc/skills/ is canonical.
    for skill in new_skills:
        name = skill.get("name", "unnamed")
        metadata = {k: skill[k] for k in ("name", "description", "tags", "version") if skill.get(k)}
        raw_content = render_frontmatter(metadata, skill.get("body", ""))
        try:
            save_skill_file(name, raw_content)
        except ValueError as exc:
            warning(f"Skipping skill {name!r}: {exc}")

    merged_mcp = merge_mcp_servers(load_mcp_servers(), new_mcp_servers)
    merged_memory = merge_memory(load_memory(), selected_memory)
    # Keep skills.json as a metadata index (name, description, tags — no body)
    # so `apc skill list` and other commands can enumerate skills without
    # reading every SKILL.md. Body lives in ~/.apc/skills/<name>/SKILL.md.
    skill_index = [
        {k: s[k] for k in ("name", "description", "tags", "version", "source_tool") if k in s}
        for s in new_skills
    ]
    merged_index = merge_skills(load_skills(), skill_index)

    save_mcp_servers(merged_mcp)
    save_memory(merged_memory)
    save_skills(merged_index)

    cache_summary_table(
        len(new_skills), len(merged_mcp), len(merged_memory), title="Local Cache Updated"
    )
    success("Collection complete.")
