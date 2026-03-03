"""apc skill commands — view and manage skills from local cache.

No login required. No network calls.
"""

import click

from apc.cache import load_skills
from apc.sync_helpers import resolve_target_tools, sync_skills
from apc.ui import dim, header, paged_print, skill_detail, skills_list


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
