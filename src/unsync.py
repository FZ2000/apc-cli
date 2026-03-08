"""apc unsync command — remove skill sync for one or all tools."""

import click

from appliers import get_applier
from appliers.manifest import ToolManifest
from extractors import detect_installed_tools
from ui import error, header, info, success, warning


@click.command()
@click.argument("tools", nargs=-1, metavar="[TOOL]...")
@click.option("--all", "all_tools", is_flag=True, help="Unsync all synced tools.")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt.")
def unsync(tools: tuple, all_tools: bool, yes: bool) -> None:
    """Remove skill sync for one or more tools.

    Undoes the effect of `apc sync` for the given TOOL(s):

    \b
    - Dir-symlink tools (Claude Code, OpenClaw, Gemini CLI, Cursor):
        Removes the symlink and recreates an empty directory.
    - Windsurf:
        Removes the APC Skills section from global_rules.md.
    - GitHub Copilot:
        Removes per-skill .instructions.md symlinks from ~/.github/instructions/.

    Run `apc sync` again to re-establish sync for a tool.
    """
    if all_tools:
        target_list = detect_installed_tools()
    elif tools:
        target_list = list(tools)
    else:
        click.echo("Specify a tool name or --all. Run `apc unsync --help` for usage.", err=True)
        raise SystemExit(1)

    # Filter to only synced tools
    synced = [t for t in target_list if not ToolManifest(t).is_first_sync]
    if not synced:
        info("No synced tools found. Nothing to do.")
        return

    header("Unsync")
    info(f"Tools to unsync: {', '.join(synced)}")

    if not yes:
        if not click.confirm("\nProceed?"):
            info("Cancelled.")
            return

    for tool_name in synced:
        try:
            applier = get_applier(tool_name)
            undone = applier.unsync_skills()
            manifest = applier.get_manifest()
            # Clear dir_sync record from manifest
            manifest._data.pop("dir_sync", None)
            manifest.save()
            if undone:
                success(f"{tool_name}: unsynced")
            else:
                info(f"{tool_name}: nothing to undo (already clean)")
        except Exception as e:
            error(f"{tool_name}: {e}")

    warning("\nSkill sync removed. Run `apc sync` to re-establish sync for a tool.")
