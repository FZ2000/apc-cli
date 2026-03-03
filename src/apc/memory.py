"""apc memory commands — add, list, and show from local cache.

No login required. No network calls.

Supports both the legacy per-line entry format (entry_id, category, content)
and the new raw-file format (id, source_tool, source_file, content).
"""

import hashlib
from datetime import datetime, timezone

import click

from apc.cache import load_memory, merge_memory, save_memory
from apc.sync_helpers import resolve_target_tools
from apc.sync_helpers import sync_memory as _sync_memory


def _is_raw_file_entry(entry: dict) -> bool:
    """Detect new raw-file format entries (have 'source_file' key)."""
    return "source_file" in entry


@click.group()
def memory():
    """Manage AI memory entries (local cache)."""
    pass


@memory.command("add")
@click.argument("text")
@click.option(
    "--category",
    default="preference",
    type=click.Choice(
        ["preference", "workflow", "project_context", "personal", "tool_config", "constraint"]
    ),
    help="Memory category",
)
def add(text, category):
    """Add a memory entry to local cache. Usage: apc memory add "your text" """
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    short_hash = hashlib.md5(text.encode()).hexdigest()[:6]
    entry_id = f"{ts}_{short_hash}"

    new_entry = {
        "entry_id": entry_id,
        "category": category,
        "content": text,
        "source": "manual_add",
    }

    existing = load_memory()
    merged = merge_memory(existing, [new_entry])
    save_memory(merged)

    click.echo(f"Memory added: [{category}] {text}")


@memory.command("list")
def list_entries():
    """List all memory entries from local cache."""
    entries = load_memory()
    if not entries:
        click.echo("No memory entries found. Run 'apc collect' or 'apc memory add \"...\"' first.")
        return

    # Separate raw-file entries from legacy entries
    raw_files = [e for e in entries if _is_raw_file_entry(e)]
    legacy = [e for e in entries if not _is_raw_file_entry(e)]

    # Display raw-file entries
    if raw_files:
        click.echo("\n[Collected Files]")
        for entry in raw_files:
            tool = entry.get("source_tool", "?")
            fname = entry.get("source_file", "?")
            size = len(entry.get("content", "").encode("utf-8"))
            if size >= 1024:
                size_str = f"{size / 1024:.1f} KB"
            else:
                size_str = f"{size} bytes"
            click.echo(f"  - {tool}/{fname}  ({size_str})")

    # Display legacy entries grouped by category
    if legacy:
        by_category = {}
        for entry in legacy:
            cat = entry.get("category", "unknown")
            by_category.setdefault(cat, []).append(entry)

        for cat, items in sorted(by_category.items()):
            click.echo(f"\n[{cat}]")
            for item in items:
                source = item.get("source", "")
                click.echo(f"  - {item.get('content', '')}  ({source})")


@memory.command("show")
@click.option(
    "--category",
    default=None,
    type=click.Choice(
        ["preference", "workflow", "project_context", "personal", "tool_config", "constraint"]
    ),
    help="Filter by category (legacy entries only)",
)
def show(category):
    """Show full detail of all memory entries, with pagination."""
    from rich.panel import Panel
    from rich.text import Text

    from apc.ui import paged_print

    entries = load_memory()

    if not entries:
        click.echo("No memory entries found.")
        return

    raw_files = [e for e in entries if _is_raw_file_entry(e)]
    legacy = [e for e in entries if not _is_raw_file_entry(e)]

    if category:
        legacy = [e for e in legacy if e.get("category") == category]

    renderables = []

    # Raw-file entries
    if raw_files:
        for entry in raw_files:
            tool = entry.get("source_tool", "?")
            fname = entry.get("source_file", "?")
            label = entry.get("label", fname)
            content = entry.get("content", "")
            collected = entry.get("collected_at", "")

            # Truncate very long content for display
            display_content = content
            if len(display_content) > 2000:
                display_content = display_content[:2000] + "\n... (truncated)"

            meta = f"[dim]tool: {tool} | file: {fname}"
            if collected:
                meta += f" | collected: {collected}"
            meta += f" | id: {entry.get('id', '?')}[/dim]"

            body = f"{meta}\n\n{display_content}"
            panel = Panel(
                body,
                title=f"[bold cyan]{tool}/{fname}[/bold cyan] — {label}",
                border_style="cyan",
                padding=(0, 1),
            )
            renderables.append(panel)

    # Legacy entries
    if legacy:
        from apc.ui import memory_detail

        renderables.extend(memory_detail(legacy))

    if not renderables:
        renderables = [Text("No memory entries found.", style="dim")]

    paged_print(renderables)


@memory.command("sync")
@click.option("--tools", default=None, help="Comma-separated list of target tools")
@click.option("--all", "apply_all", is_flag=True, help="Apply to all detected tools")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
def memory_sync(tools, apply_all, yes):
    """Sync memory to target tools."""
    from apc.ui import header

    header("Memory Sync")

    tool_list = resolve_target_tools(tools, apply_all)
    if not tool_list:
        return

    if not yes:
        if not click.confirm(f"Sync memory to {', '.join(tool_list)}?"):
            click.echo("Cancelled.")
            return

    _sync_memory(tool_list)
