"""apc memory commands — add, list, and show from local cache.

No login required. No network calls.

Supports both the legacy per-line entry format (entry_id, category, content)
and the new raw-file format (id, source_tool, source_file, content).
"""

import hashlib
from datetime import datetime, timezone

import click

from cache import load_memory, merge_memory, save_memory
from sync_helpers import resolve_target_tools
from sync_helpers import sync_memory as _sync_memory


def _is_raw_file_entry(entry: dict) -> bool:
    """Detect new raw-file format entries (have 'source_file' key)."""
    return "source_file" in entry


def _is_manual_entry(entry: dict) -> bool:
    """Detect manually-added entries (source_tool == 'manual')."""
    return entry.get("source_tool") == "manual"


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
    # Use the new schema (id + source_tool) so that:
    # 1. The same text added twice is idempotent — content-hash id is stable (#45)
    # 2. merge_memory deduplicates via 'id', not a timestamp-based entry_id
    content_id = hashlib.sha256(f"manual:{category}:{text}".encode()).hexdigest()[:16]
    now = datetime.now(timezone.utc).isoformat()

    new_entry = {
        "id": content_id,
        "source_tool": "manual",
        "source_file": "memory_add",
        "label": f"Manual [{category}]",
        "category": category,
        "content": text,
        "collected_at": now,
    }

    existing = load_memory()
    merged = merge_memory(existing, [new_entry])
    save_memory(merged)

    click.echo(f"Memory added: [{category}] {text}")


@memory.command("list")
@click.option("--tool", default=None, help="Filter by source tool name.")
def list_entries(tool):
    """List all memory entries from local cache as rich tables. (#21)"""
    from rich.console import Console
    from rich.table import Table
    from rich.text import Text

    entries = load_memory()
    if not entries:
        click.echo("No memory entries found. Run 'apc collect' or 'apc memory add \"...\"' first.")
        return

    if tool:
        entries = [e for e in entries if e.get("source_tool") == tool]
        if not entries:
            click.echo(f"No memory entries for tool '{tool}'.")
            return

    console = Console()

    # Separate entries into groups
    manual = [e for e in entries if _is_raw_file_entry(e) and _is_manual_entry(e)]
    raw_files = [e for e in entries if _is_raw_file_entry(e) and not _is_manual_entry(e)]
    legacy = [e for e in entries if not _is_raw_file_entry(e)]

    # Collected file entries table
    if raw_files:
        tbl = Table(
            title=f"Collected Files ({len(raw_files)})",
            show_header=True,
            header_style="bold cyan",
            show_lines=False,
        )
        tbl.add_column("ID", style="dim", width=10)
        tbl.add_column("Source Tool", style="green")
        tbl.add_column("File", style="blue")
        tbl.add_column("Size", justify="right")

        for entry in raw_files:
            entry_id = (entry.get("id") or entry.get("entry_id", ""))[:8]
            t = entry.get("source_tool", "?")
            fname = entry.get("source_file", "?")
            size_bytes = len(entry.get("content", "").encode("utf-8"))
            if size_bytes >= 1024:
                size_str = f"{size_bytes / 1024:.1f} KB"
            else:
                size_str = f"{size_bytes} B"
            tbl.add_row(entry_id, t, fname, size_str)

        console.print(tbl)

    # Manually-added entries table
    if manual:
        mtbl = Table(
            title=f"Manual Entries ({len(manual)})",
            show_header=True,
            header_style="bold magenta",
            show_lines=False,
        )
        mtbl.add_column("ID", style="dim", width=10)
        mtbl.add_column("Category", style="yellow")
        mtbl.add_column("Content")

        for entry in manual:
            entry_id = (entry.get("id") or entry.get("entry_id", ""))[:8]
            cat = entry.get("category", "manual")
            content = entry.get("content", "")
            preview = (content[:80] + "…") if len(content) > 80 else content
            mtbl.add_row(entry_id, cat, Text(preview))

        console.print(mtbl)

    # Legacy entries table
    if legacy:
        ltbl = Table(
            title=f"Legacy Entries ({len(legacy)})",
            show_header=True,
            header_style="bold",
            show_lines=False,
        )
        ltbl.add_column("Category", style="yellow")
        ltbl.add_column("Source", style="dim")
        ltbl.add_column("Content")

        for entry in legacy:
            cat = entry.get("category", "unknown")
            source = entry.get("source", "")
            content = entry.get("content", "")
            preview = (content[:80] + "…") if len(content) > 80 else content
            ltbl.add_row(cat, source, Text(preview))

        console.print(ltbl)

    total = len(entries)
    console.print(f"\n[dim]{total} total entries[/dim]")


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

    from ui import paged_print

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
        from ui import memory_detail

        renderables.extend(memory_detail(legacy))

    if not renderables:
        renderables = [Text("No memory entries found.", style="dim")]

    paged_print(renderables)


@memory.command("remove")
@click.argument("entry_id", required=False)
@click.option("--tool", default=None, help="Remove all entries from a specific source tool.")
@click.option("--all", "remove_all", is_flag=True, help="Remove ALL memory entries.")
@click.option("-y", "--yes", is_flag=True, help="Skip confirmation prompt.")
def remove(entry_id, tool, remove_all, yes):
    """Remove memory entries from the cache. (#48)

    \b
    Examples:
      apc memory remove abc12345          # by ID prefix
      apc memory remove --tool openclaw   # all entries from a tool
      apc memory remove --all             # clear entire cache
    """
    entries = load_memory()
    if not entries:
        click.echo("No memory entries in cache.")
        return

    if remove_all:
        count = len(entries)
        if not yes and not click.confirm(f"Remove ALL {count} memory entries?", default=False):
            click.echo("Cancelled.")
            return
        save_memory([])
        click.echo(f"✓ Removed {count} memory entries.")
        return

    if tool:
        to_remove = [e for e in entries if e.get("source_tool") == tool]
        if not to_remove:
            click.echo(f"No entries found for tool '{tool}'.")
            return
        if not yes and not click.confirm(
            f"Remove {len(to_remove)} entries from '{tool}'?", default=False
        ):
            click.echo("Cancelled.")
            return
        remaining = [e for e in entries if e.get("source_tool") != tool]
        save_memory(remaining)
        click.echo(f"✓ Removed {len(to_remove)} entries from '{tool}'.")
        return

    if entry_id:
        # Match by ID prefix
        matched = [
            e for e in entries if (e.get("id") or e.get("entry_id", "")).startswith(entry_id)
        ]
        if not matched:
            click.echo(f"No entry found with ID starting with '{entry_id}'.")
            return
        if len(matched) > 1:
            click.echo(f"Ambiguous: {len(matched)} entries match '{entry_id}':")
            for e in matched:
                eid = e.get("id") or e.get("entry_id", "?")
                click.echo(f"  {eid[:16]}  {e.get('source_tool', '')}  {e.get('content', '')[:60]}")
            return
        e = matched[0]
        eid = e.get("id") or e.get("entry_id", "?")
        preview = e.get("content", e.get("source_file", ""))[:60]
        if not yes and not click.confirm(f"Remove entry {eid[:16]}: {preview!r}?", default=False):
            click.echo("Cancelled.")
            return
        target_id = e.get("id") or e.get("entry_id", "")
        remaining = [x for x in entries if (x.get("id") or x.get("entry_id", "")) != target_id]
        save_memory(remaining)
        click.echo(f"✓ Removed entry {eid[:16]}.")
        return

    # Interactive selection (no args)
    from rich.console import Console
    from rich.table import Table

    console = Console()
    tbl = Table(title="Memory Entries", show_header=True, header_style="bold cyan")
    tbl.add_column("#", style="dim", width=4)
    tbl.add_column("ID", style="dim", width=12)
    tbl.add_column("Source", style="green")
    tbl.add_column("Content/File")

    for i, e in enumerate(entries, 1):
        eid = (e.get("id") or e.get("entry_id", ""))[:12]
        src = e.get("source_tool", "?")
        content = e.get("content", e.get("source_file", ""))[:60]
        tbl.add_row(str(i), eid, src, content)

    console.print(tbl)
    raw = click.prompt("Entry # to remove (or 'q' to cancel)", default="q")
    if raw.strip().lower() == "q" or not raw.strip():
        click.echo("Cancelled.")
        return

    try:
        idx = int(raw.strip()) - 1
        if not (0 <= idx < len(entries)):
            raise ValueError
    except ValueError:
        click.echo("Invalid selection.")
        return

    e = entries[idx]
    eid = (e.get("id") or e.get("entry_id", "?"))[:16]
    preview = e.get("content", e.get("source_file", ""))[:60]
    if not yes and not click.confirm(f"Remove entry {eid}: {preview!r}?", default=False):
        click.echo("Cancelled.")
        return

    remaining = [x for x in entries if x is not e]
    save_memory(remaining)
    click.echo(f"✓ Removed entry {eid}.")


@memory.command("sync")
@click.option("--tools", default=None, help="Comma-separated list of target tools")
@click.option("--all", "apply_all", is_flag=True, help="Apply to all detected tools")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
def memory_sync(tools, apply_all, yes):
    """Sync memory to target tools."""
    from ui import header

    header("Memory Sync")

    tool_list = resolve_target_tools(tools, apply_all)
    if not tool_list:
        return

    if not yes:
        if not click.confirm(f"Sync memory to {', '.join(tool_list)}?"):
            click.echo("Cancelled.")
            return

    _sync_memory(tool_list)
