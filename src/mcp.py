"""apc mcp commands — list, sync, and remove MCP server configurations.

No login required. No network calls.
"""

import click

from cache import load_mcp_servers, save_mcp_servers
from sync_helpers import resolve_target_tools, sync_mcp
from ui import header, info, mcp_list, success, warning


@click.group()
def mcp():
    """Manage MCP server configurations."""
    pass


@mcp.command("list")
def mcp_list_cmd():
    """List cached MCP servers."""
    servers = load_mcp_servers()
    mcp_list(servers)


@mcp.command("sync")
@click.option("--tools", default=None, help="Comma-separated list of target tools")
@click.option("--all", "apply_all", is_flag=True, help="Apply to all detected tools")
@click.option("--override", is_flag=True, help="Replace existing MCP servers instead of merging")
@click.option(
    "--all-sources",
    "all_sources",
    is_flag=True,
    help="Sync ALL cached servers to every tool, ignoring source_tool origin.",
)
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
def mcp_sync(tools, apply_all, override, all_sources, yes):
    """Sync MCP servers to target tools.

    By default each server is only applied to the tool it was originally
    collected from (source_tool). Use --all-sources to broadcast every
    cached server to every target tool regardless of origin.
    """
    header("MCP Sync")

    tool_list = resolve_target_tools(tools, apply_all)
    if not tool_list:
        return

    if not yes:
        if not override:
            override = click.confirm(
                "Override existing MCP servers? (No = append/merge)", default=False
            )
        if not click.confirm(f"Sync MCP servers to {', '.join(tool_list)}?"):
            click.echo("Cancelled.")
            return

    sync_mcp(tool_list, override=override, all_sources=all_sources)


@mcp.command("remove")
@click.argument("name")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
def mcp_remove(name, yes):
    """Remove an MCP server from the cache by name.

    The server will be pruned from target tools on next 'apc sync'.
    """
    servers = load_mcp_servers()
    matches = [s for s in servers if s.get("name") == name]

    if not matches:
        warning(f"No MCP server named '{name}' in cache.")
        info("Run 'apc mcp list' to see cached servers.")
        return

    if not yes:
        for m in matches:
            source = m.get("source_tool", "unknown")
            info(f"  {name} (from {source})")
        if not click.confirm(f"\nRemove {len(matches)} server(s)?"):
            info("Cancelled.")
            return

    remaining = [s for s in servers if s.get("name") != name]
    save_mcp_servers(remaining)
    success(f"Removed '{name}' from cache ({len(matches)} entry/entries).")
    info("Run 'apc sync' to propagate the removal to target tools.")
