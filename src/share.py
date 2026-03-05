"""apc install command — fetch and install a skill from a repo or local path."""

import click

from cache import load_skills, merge_skills, save_skills
from skills import save_skill_file, search_skill


@click.command()
@click.argument("skill_name")
@click.option(
    "--repo",
    default=None,
    help="GitHub repo (owner/repo) or local path to fetch from",
)
@click.option("--branch", default="main", help="Git branch to fetch from (default: main)")
def install(skill_name, repo, branch):
    """Install a skill from a GitHub repo or local directory.

    By default fetches from anthropics/skills. Use --repo to specify a source.

    Usage: apc install <skill-name> [--repo owner/repo]
    """
    repos = [repo] if repo else None

    click.echo(f"Searching for '{skill_name}'...")
    skill = search_skill(skill_name, repos=repos, branch=branch)

    if not skill:
        source = repo if repo else "anthropics/skills"
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

    click.echo(f"✓ Skill '{skill['name']}' installed. Run 'apc sync' to apply to your tools.")
