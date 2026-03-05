"""apc install and apc marketplace commands."""

import click

from cache import load_skills, merge_skills, save_skills
from marketplace import (
    add_marketplace,
    delete_marketplace,
    is_local_path,
    load_marketplaces,
    save_skill_file,
    search_skill,
)


@click.command()
@click.argument("skill_name")
@click.option(
    "--repo",
    default=None,
    help="Specific marketplace source (owner/repo or local path) to fetch from",
)
@click.option("--branch", default="main", help="Git branch to fetch from (default: main)")
def install(skill_name, repo, branch):
    """Install a skill from a marketplace. Usage: apc install <skill-name>"""
    repos = [repo] if repo else None

    click.echo(f"Searching for '{skill_name}'...")
    skill = search_skill(skill_name, repos=repos, branch=branch)

    if not skill:
        source = repo if repo else "configured marketplaces"
        click.echo(f"Skill '{skill_name}' not found in {source}.", err=True)
        return

    click.echo(f"Found '{skill['name']}' in {skill['source_repo']}")

    # Save raw SKILL.md to source-of-truth directory (~/.apc/skills/<name>/SKILL.md)
    raw_content = skill.pop("_raw_content", skill.get("body", ""))
    save_skill_file(skill["name"], raw_content)

    # Save metadata to local cache
    existing = load_skills()
    merged = merge_skills(existing, [skill])
    save_skills(merged)

    click.echo(f"✓ Skill '{skill['name']}' saved. Run 'apc sync' to apply to your tools.")


# --- Marketplace management commands ---


@click.group()
def marketplace():
    """Manage skill marketplaces (GitHub repos or local directories)."""
    pass


@marketplace.command("list")
def marketplace_list():
    """Show configured marketplaces."""
    sources = load_marketplaces()
    if not sources:
        click.echo("No marketplaces configured.")
        return
    for i, s in enumerate(sources):
        priority = " (highest priority)" if i == 0 else ""
        click.echo(f"  {s}{priority}")


@marketplace.command("add")
@click.argument("source")
def marketplace_add(source):
    """Add a marketplace (owner/repo or local directory path). Added at highest priority."""
    if not is_local_path(source):
        parts = source.split("/")
        if len(parts) != 2:
            click.echo(
                "Invalid format. Use: apc marketplace add <owner/repo> or a local path", err=True
            )
            return
    add_marketplace(source)
    click.echo(f"Added '{source}' (highest priority)")


@marketplace.command("delete")
@click.argument("source")
def marketplace_delete(source):
    """Remove a marketplace."""
    delete_marketplace(source)
    click.echo(f"Removed '{source}'")
