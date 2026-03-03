"""apc mcp commands — list and sync MCP server configurations.

No login required. No network calls.
"""

import click

from apc.cache import load_mcp_servers
from apc.sync_helpers import resolve_target_tools, sync_mcp
from apc.ui import header, mcp_list


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
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
def mcp_sync(tools, apply_all, yes):
    """Sync MCP servers to target tools."""
    header("MCP Sync")

    tool_list = resolve_target_tools(tools, apply_all)
    if not tool_list:
        return

    if not yes:
        if not click.confirm(f"Sync MCP servers to {', '.join(tool_list)}?"):
            click.echo("Cancelled.")
            return

    sync_mcp(tool_list)
