"""apc CLI entry point — wires all commands into a Click group."""

import click

from cache import load_local_bundle
from collect import collect
from doctor import doctor
from export_import import export_cmd, import_cmd
from install import install
from llm_config import configure_cmd, models_cmd
from mcp import mcp
from memory import memory
from skill import skill
from status import status
from sync_helpers import count_installed_skills, resolve_target_tools, sync_all
from ui import (
    cache_summary_table,
    header,
    info,
    warning,
)


@click.group()
@click.version_option(version="0.1.1", prog_name="apc")
def cli():
    """apc — AI Personal Context manager.

    Collect, manage, and sync AI agent configs (skills, MCP servers, memory,
    settings) across tools (Claude, Cursor, Gemini, Copilot, Windsurf).

    Quick start:

      apc collect        Extract from installed tools → local cache

      apc status         Show what's in your cache

      apc sync           Sync cached configs to target tools

      apc skill show     View skill details

      apc memory show    View memory details
    """
    pass


# Local operations
cli.add_command(collect)
cli.add_command(status)

# Skills
cli.add_command(skill)

# Memory
cli.add_command(memory)


# Install
cli.add_command(install)

# MCP
cli.add_command(mcp)

# LLM configuration
cli.add_command(configure_cmd)
cli.add_command(models_cmd)
cli.add_command(doctor)

# Export / Import
cli.add_command(export_cmd)
cli.add_command(import_cmd)


@cli.command()
@click.option(
    "--tools", default=None, help="Comma-separated list of target tools (e.g., cursor,gemini)"
)
@click.option(
    "--all", "apply_all", is_flag=True, help="Apply to all detected tools without selection"
)
@click.option("--no-memory", is_flag=True, help="Skip applying memory entries")
@click.option(
    "--override-mcp", is_flag=True, help="Replace existing MCP servers instead of merging"
)
@click.option("--dry-run", is_flag=True, help="Show what would be applied without writing")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
def sync(tools, apply_all, no_memory, override_mcp, dry_run, yes):
    """Sync local cache contents to target AI tools.

    No login or network required.
    """
    header("Sync")

    # Load from local cache for summary display
    bundle = load_local_bundle()
    collected_skills = bundle["skills"]
    mcp_servers = bundle["mcp_servers"]
    memory_entries = bundle["memory"] if not no_memory else []
    installed_count = count_installed_skills()
    total_skills = len(collected_skills) + installed_count

    if not total_skills and not mcp_servers and not memory_entries:
        warning("Local cache is empty. Run 'apc collect' first.")
        return

    tool_list = resolve_target_tools(tools, apply_all)
    if not tool_list:
        return

    # Show plan
    info(f"Target tools: {', '.join(tool_list)}")
    cache_summary_table(
        total_skills, len(mcp_servers), len(memory_entries), title="Applying from Cache"
    )
    if collected_skills and installed_count:
        info(f"Skills: {len(collected_skills)} collected + {installed_count} installed")

    if dry_run:
        info("[dry-run] No files written.")
        return

    # Confirm
    if not yes:
        if mcp_servers and not override_mcp:
            override_mcp = click.confirm(
                "Override existing MCP servers? (No = append/merge)", default=False
            )
        if not click.confirm("\nProceed?"):
            info("Cancelled.")
            return

    ok = sync_all(tool_list, no_memory=no_memory, override_mcp=override_mcp)
    if not ok:
        raise SystemExit(1)


def main():
    cli()


if __name__ == "__main__":
    main()
