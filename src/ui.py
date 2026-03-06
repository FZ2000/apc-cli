"""Shared rich UI helpers for APC CLI commands.

All rich imports are isolated here — commands never import rich directly.
"""

from typing import Dict, List, Optional

import click
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

console = Console()


# --- Spinner ---


def spinner(message: str):
    """Return a rich Status context manager that shows a spinner with a message.

    Usage:
        with spinner("Syncing memory via LLM..."):
            do_slow_thing()
    """
    return console.status(f"[bold cyan]{message}[/bold cyan]", spinner="dots")


# --- Styled single-line output ---


def header(title: str) -> None:
    """Print a styled section header with separator."""
    console.print()
    console.print(f"[bold cyan]{title}[/bold cyan]")
    console.print("[dim]" + "─" * min(len(title) + 4, 60) + "[/dim]")


def success(msg: str) -> None:
    console.print(f"[bold green]✓[/bold green] {msg}")


def warning(msg: str) -> None:
    console.print(f"[bold yellow]![/bold yellow] {msg}")


def error(msg: str) -> None:
    console.print(f"[bold red]✗[/bold red] {msg}")


def info(msg: str) -> None:
    console.print(f"[bold blue]ℹ[/bold blue] {msg}")


def dim(msg: str) -> None:
    console.print(f"[dim]{msg}[/dim]")


# --- Tables ---


def scan_results_table(tool_results: Dict[str, Dict[str, int]]) -> None:
    """Display extraction results per tool.

    tool_results: {tool_name: {"skills": N, "mcp": N, "memory": N}}
    """
    table = Table(title="Scan Results", show_lines=False)
    table.add_column("Tool", style="cyan", no_wrap=True)
    table.add_column("Skills", justify="right")
    table.add_column("MCP Servers", justify="right")
    table.add_column("Memory", justify="right")

    total_s, total_m, total_mem = 0, 0, 0
    for tool, counts in tool_results.items():
        s = counts.get("skills", 0)
        m = counts.get("mcp", 0)
        mem = counts.get("memory", 0)
        total_s += s
        total_m += m
        total_mem += mem
        table.add_row(tool, str(s), str(m), str(mem))

    table.add_section()
    table.add_row(
        "[bold]Total[/bold]",
        f"[bold]{total_s}[/bold]",
        f"[bold]{total_m}[/bold]",
        f"[bold]{total_mem}[/bold]",
    )

    console.print()
    console.print(table)


def cache_summary_table(skills: int, mcp: int, memory: int, title: str = "Cache Summary") -> None:
    """Simple 3-row count table for cache contents."""
    table = Table(title=title, show_lines=False)
    table.add_column("Category", style="cyan")
    table.add_column("Count", justify="right")

    table.add_row("Skills", str(skills))
    table.add_row("MCP Servers", str(mcp))
    table.add_row("Memory", str(memory))

    console.print()
    console.print(table)


def tools_status_table(tools: List[Dict[str, str]]) -> None:
    """Display tool status with sync badges.

    tools: [{"name": "claude-code", "status": "synced"}, ...]
    """
    table = Table(title="Detected Tools", show_lines=False)
    table.add_column("Tool", style="cyan", no_wrap=True)
    table.add_column("Status", justify="center")

    for tool in tools:
        name = tool["name"]
        st = tool.get("status", "detected")
        if st == "synced":
            badge = Text("● synced", style="bold green")
        elif st == "not synced":
            badge = Text("○ not synced", style="yellow")
        else:
            badge = Text("◌ detected", style="dim")
        table.add_row(name, badge)

    console.print()
    console.print(table)


# --- Detail lists ---


def skills_list(skills: List[Dict]) -> None:
    """Table: # | Name | Source | Description | Tags"""
    if not skills:
        dim("  No skills found.")
        return

    table = Table(show_lines=False)
    table.add_column("#", style="dim", justify="right", width=4)
    table.add_column("Name", style="cyan", no_wrap=True)
    table.add_column("Source", style="dim")
    table.add_column("Description", max_width=50)
    table.add_column("Tags", style="dim")

    for i, s in enumerate(skills, 1):
        tags = ", ".join(s.get("tags", [])) if s.get("tags") else ""
        table.add_row(
            str(i),
            s.get("name", "—"),
            s.get("source_tool", "—"),
            (s.get("description", "") or "")[:50],
            tags,
        )

    console.print()
    console.print(table)


def mcp_list(servers: List[Dict]) -> None:
    """Table: # | Name | Transport | Command | Source"""
    if not servers:
        dim("  No MCP servers found.")
        return

    table = Table(show_lines=False)
    table.add_column("#", style="dim", justify="right", width=4)
    table.add_column("Name", style="cyan", no_wrap=True)
    table.add_column("Transport", style="dim")
    table.add_column("Command", max_width=40)
    table.add_column("Source", style="dim")

    for i, srv in enumerate(servers, 1):
        cmd = srv.get("command", "")
        if isinstance(cmd, list):
            cmd = " ".join(cmd)
        table.add_row(
            str(i),
            srv.get("name", "—"),
            srv.get("transport", "stdio"),
            (cmd or "")[:40],
            srv.get("source_tool", "—"),
        )

    console.print()
    console.print(table)


def display_memory_files(memory_files: List[Dict]) -> List[Dict]:
    """Display memory files from multiple tools and let the user pick which to collect.

    Args:
        memory_files: List of raw file dicts with id, source_tool, source_file,
                      source_path, label, content.

    Returns:
        Subset of memory_files selected by the user.
    """
    console.print()
    warning("Memory files detected in multiple tools:")
    console.print()

    for i, mf in enumerate(memory_files, 1):
        size = len(mf.get("content", "").encode("utf-8"))
        if size >= 1024:
            size_str = f"{size / 1024:.1f} KB"
        else:
            size_str = f"{size} bytes"
        console.print(
            f"  [bold cyan]{i}.[/bold cyan] "
            f"[bold]{mf['source_tool']}[/bold] — {mf.get('label', mf['source_file'])} "
            f"[dim]({size_str})[/dim]"
        )
        console.print(f"     [dim]{mf.get('source_path', '')}[/dim]")

    console.print()
    indices = numbered_selection(
        [f"{m['source_tool']}/{m.get('source_file', '?')}" for m in memory_files],
        "Select files to collect",
    )
    return [memory_files[i] for i in indices]


def memory_display(entries: List[Dict]) -> None:
    """Tree grouped by category with dim source/confidence metadata."""
    if not entries:
        dim("  No memory entries found.")
        return

    # Group by category
    by_category: Dict[str, List[Dict]] = {}
    for e in entries:
        cat = e.get("category", "uncategorized")
        by_category.setdefault(cat, []).append(e)

    tree = Tree("[bold]Memory[/bold]")
    for category, items in sorted(by_category.items()):
        branch = tree.add(f"[bold cyan]{category}[/bold cyan] ({len(items)})")
        for item in items:
            content = item.get("content", item.get("text", "—"))
            if len(content) > 80:
                content = content[:77] + "..."
            meta_parts = []
            if item.get("source_tool"):
                meta_parts.append(f"source: {item['source_tool']}")
            if item.get("confidence"):
                meta_parts.append(f"confidence: {item['confidence']}")
            meta = f" [dim]({', '.join(meta_parts)})[/dim]" if meta_parts else ""
            branch.add(f"{content}{meta}")

    console.print()
    console.print(tree)


# --- Paginated output ---


def paged_print(renderables: list) -> None:
    """Print a list of Rich renderables; use a pager if output exceeds terminal height."""
    # Measure total height
    total_lines = 0
    for r in renderables:
        with console.capture() as capture:
            console.print(r)
        total_lines += capture.get().count("\n")

    term_height = console.size.height

    if total_lines > term_height:
        with console.pager(styles=True):
            for r in renderables:
                console.print(r)
    else:
        for r in renderables:
            console.print(r)


def _skill_panel_content(skill: Dict) -> str:
    """Build the inner content string for a skill panel."""
    parts = []
    description = skill.get("description", "")
    tags = ", ".join(skill.get("tags", [])) if skill.get("tags") else ""
    source = skill.get("source_tool", "—")
    version = skill.get("version", "")

    if description:
        parts.append(f"[bold]Description:[/bold] {description}")
    if tags:
        parts.append(f"[bold]Tags:[/bold] {tags}")
    if source:
        parts.append(f"[bold]Source:[/bold] {source}")
    if version:
        parts.append(f"[bold]Version:[/bold] {version}")

    body = skill.get("body", "")
    if body:
        if parts:
            parts.append("")
        parts.append(escape(body))

    return "\n".join(parts) if parts else "[dim]No content[/dim]"


def skill_detail(skill: Dict) -> Panel:
    """Render a single skill as a Rich Panel with full body and metadata."""
    name = skill.get("name", "unnamed")
    content = _skill_panel_content(skill)
    return Panel(
        content, title=f"[bold cyan]{name}[/bold cyan]", border_style="cyan", padding=(1, 2)
    )


def memory_detail(entries: List[Dict]) -> list:
    """Render memory entries grouped by category with full content and metadata.

    Returns a list of Rich renderables suitable for paged_print().
    """
    if not entries:
        return [Text("No memory entries found.", style="dim")]

    by_category: Dict[str, List[Dict]] = {}
    for e in entries:
        cat = e.get("category", "uncategorized")
        by_category.setdefault(cat, []).append(e)

    renderables = []
    for category, items in sorted(by_category.items()):
        rows = []
        for item in items:
            content = item.get("content", item.get("text", "—"))
            entry_id = item.get("entry_id", "")
            source = item.get("source", item.get("source_tool", "—"))
            confidence = item.get("confidence", "")

            meta_parts = []
            if source:
                meta_parts.append(f"source: {source}")
            if item.get("source_tool"):
                meta_parts.append(f"tool: {item['source_tool']}")
            if confidence:
                meta_parts.append(f"confidence: {confidence}")
            if entry_id:
                meta_parts.append(f"id: {entry_id}")

            meta = f"  [dim]({', '.join(meta_parts)})[/dim]" if meta_parts else ""
            rows.append(f"  • {content}{meta}")

        body = "\n".join(rows)
        panel = Panel(
            body,
            title=f"[bold cyan]{category}[/bold cyan] ({len(items)})",
            border_style="cyan",
            padding=(0, 1),
        )
        renderables.append(panel)

    return renderables


# --- Interactive selection ---


def numbered_selection(items: List[str], prompt_text: str = "Select items") -> List[int]:
    """Show a numbered list, return 0-based indices.

    Accepts "1,3", "1-3", "all". Retries on bad input.
    """
    console.print()
    for i, item in enumerate(items, 1):
        console.print(f"  [bold cyan]{i}.[/bold cyan] {item}")
    console.print()

    while True:
        raw = click.prompt(prompt_text + ' (e.g. 1,3 or 1-3 or "all")')
        raw = raw.strip().lower()

        if raw == "all":
            return list(range(len(items)))

        indices = _parse_selection(raw, len(items))
        if indices is not None:
            return indices

        error(f"Invalid selection: {raw!r}. Try again.")


def _parse_selection(raw: str, count: int) -> Optional[List[int]]:
    """Parse a selection string into 0-based indices. Returns None on failure."""
    indices = set()
    for part in raw.split(","):
        part = part.strip()
        if "-" in part:
            try:
                lo, hi = part.split("-", 1)
                lo_i, hi_i = int(lo), int(hi)
                if lo_i < 1 or hi_i > count or lo_i > hi_i:
                    return None
                indices.update(range(lo_i - 1, hi_i))
            except ValueError:
                return None
        else:
            try:
                n = int(part)
                if n < 1 or n > count:
                    return None
                indices.add(n - 1)
            except ValueError:
                return None

    if not indices:
        return None
    return sorted(indices)
