"""apc skill commands — view and manage skills from local cache.

No login required. No network calls.
"""

import click

from cache import load_skills, save_skills
from install import propagate_remove_to_synced_tools
from skills import delete_skill_file, get_skills_dir
from sync_helpers import resolve_target_tools, sync_skills
from ui import dim, error, header, paged_print, skill_detail, skills_list, success, warning


@click.group()
def skill():
    """View and manage skills (local cache)."""
    pass


@skill.command("show")
@click.argument("name", required=False, default=None)
def show(name):
    """Show full detail of all skills (or one by name), with pagination."""
    skills = load_skills()

    if not skills:
        dim("No skills found. Run 'apc collect' or 'apc install <skill>' first.")
        return

    if name:
        matched = [s for s in skills if s.get("name", "").lower() == name.lower()]
        if not matched:
            dim(f"Skill '{name}' not found.")
            return
        panels = [skill_detail(s) for s in matched]
    else:
        panels = [skill_detail(s) for s in skills]

    paged_print(panels)


@skill.command("list")
def list_skills():
    """Brief summary table of all skills."""
    skills = load_skills()
    skills_list(skills)


@skill.command("sync")
@click.option("--tools", default=None, help="Comma-separated list of target tools")
@click.option("--all", "apply_all", is_flag=True, help="Apply to all detected tools")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
def skill_sync(tools, apply_all, yes):
    """Sync skills to target tools."""
    header("Skill Sync")

    tool_list = resolve_target_tools(tools, apply_all)
    if not tool_list:
        return

    if not yes:
        if not click.confirm(f"Sync skills to {', '.join(tool_list)}?"):
            click.echo("Cancelled.")
            return

    sync_skills(tool_list)


@skill.command("remove")
@click.argument("names", nargs=-1, required=True, metavar="NAME [NAME...]")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt.")
def remove(names: tuple, yes: bool) -> None:
    """Remove one or more installed skills.

    Deletes the skill from ~/.apc/skills/ and cleans up any tool-specific
    state left behind:

    \b
    - Dir-symlink tools (Claude Code, OpenClaw, Gemini, Cursor): automatic —
      the skill dir disappears from the symlink immediately.
    - Windsurf: regenerates global_rules.md to drop the removed skill.
    - Copilot: removes the now-dangling .instructions.md symlink.

    \b
    Examples:
      apc skill remove pdf
      apc skill remove pdf skill-creator -y
    """
    skills_dir = get_skills_dir()
    existing = [n for n in names if (skills_dir / n).exists()]
    missing = [n for n in names if n not in existing]

    if missing:
        for m in missing:
            warning(f"Skill '{m}' not found in ~/.apc/skills/ — skipping.")

    if not existing:
        dim("Nothing to remove.")
        return

    if not yes:
        click.echo(f"\nRemove skill(s): {', '.join(existing)}")
        if not click.confirm("Proceed?"):
            click.echo("Cancelled.")
            return

    removed = []
    for name in existing:
        if delete_skill_file(name):
            # Update the metadata cache
            cached = [s for s in load_skills() if s.get("name") != name]
            save_skills(cached)
            # Notify synced tools
            propagate_remove_to_synced_tools(name)
            success(f"Removed: {name}")
            removed.append(name)
        else:
            error(f"Failed to remove: {name}")
