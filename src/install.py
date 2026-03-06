"""apc install command — install skills from a GitHub repository.

Handles the `apc install owner/repo` command and all its options.
"""

from typing import List

import click

from appliers import get_applier
from cache import load_skills, merge_skills, save_skills
from extractors import detect_installed_tools
from skills import fetch_skill_from_repo, list_skills_in_repo, save_skill_file

_AGENTS = ["claude-code", "cursor", "gemini-cli", "github-copilot", "openclaw", "windsurf"]


def _resolve_agents(agent_args: tuple, yes: bool) -> List[str]:
    """Resolve target agents from -a flags, '*', or interactive selection."""
    if not agent_args:
        detected = detect_installed_tools()
        if not detected:
            click.echo("No AI tools detected on this machine.", err=True)
            return []
        if yes:
            return detected
        click.echo("\nDetected tools:")
        for i, t in enumerate(detected, 1):
            click.echo(f"  {i}. {t}")
        raw = click.prompt("Install to (e.g. 1,3 or 'all')", default="all")
        if raw.strip().lower() == "all":
            return detected
        indices = []
        for part in raw.split(","):
            part = part.strip()
            if "-" in part:
                a, b = part.split("-", 1)
                indices.extend(range(int(a) - 1, int(b)))
            elif part.isdigit():
                indices.append(int(part) - 1)
        return [detected[i] for i in indices if 0 <= i < len(detected)]

    agents = list(agent_args)
    if "*" in agents:
        return detect_installed_tools()
    return agents


def _apply_skill_to_agents(skill: dict, agent_list: list) -> int:
    """Write a skill directly to each agent's skill directory. Returns applied count."""

    count = 0
    for agent_name in agent_list:
        try:
            applier = get_applier(agent_name)
            manifest = applier.get_manifest()
            applied = applier.apply_skills([skill], manifest)
            manifest.save()
            count += applied
        except Exception as e:
            click.echo(f"  ! {agent_name}: {e}", err=True)
    return count


@click.command()
@click.argument("repo")
@click.option(
    "--skill", "-s", "skills", multiple=True, help="Skill name(s) to install. Use '*' for all."
)
@click.option("--all", "install_all", is_flag=True, help="Install all skills from the repo.")
@click.option(
    "--agent",
    "-a",
    "agents",
    multiple=True,
    help="Target tool(s) to install to. Use '*' for all detected.",
)
@click.option("--branch", default="main", show_default=True, help="Git branch to fetch from.")
@click.option(
    "--list",
    "list_only",
    is_flag=True,
    help="List available skills in the repo without installing.",
)
@click.option("-y", "--yes", is_flag=True, help="Non-interactive: skip all confirmation prompts.")
def install(repo, skills, install_all, agents, branch, list_only, yes):
    """Install skills from a GitHub repository.

    \b
    Examples:
      apc install owner/repo --list
      apc install owner/repo --skill frontend-design
      apc install owner/repo --skill frontend-design --skill skill-creator
      apc install owner/repo --skill '*'
      apc install owner/repo --all
      apc install owner/repo --skill frontend-design -a claude-code -a cursor
      apc install owner/repo --all -a claude-code -y
    """
    # Validate: repo must look like owner/repo
    if "/" not in repo or repo.startswith("http"):
        raise click.UsageError(
            "REPO must be a GitHub repository name in owner/repo format (e.g. vercel-labs/agent-skills)"
        )

    # --list: just show available skills and exit
    if list_only:
        click.echo(f"Fetching skill list from {repo}...")
        available = list_skills_in_repo(repo, branch)
        if not available:
            click.echo(f"No skills found in {repo} (branch: {branch}).", err=True)
            return
        click.echo(f"\nAvailable skills in {repo}:\n")
        for name in available:
            click.echo(f"  • {name}")
        click.echo(f"\n{len(available)} skill(s) found.")
        return

    # Resolve which skills to install
    if install_all or ("*" in skills):
        click.echo(f"Fetching skill list from {repo}...")
        skill_names = list_skills_in_repo(repo, branch)
        if not skill_names:
            click.echo(f"No skills found in {repo}.", err=True)
            return
    elif skills:
        skill_names = list(skills)
    else:
        # No --skill or --all: show list and prompt
        click.echo(f"Fetching skill list from {repo}...")
        available = list_skills_in_repo(repo, branch)
        if not available:
            click.echo(f"No skills found in {repo}.", err=True)
            return
        click.echo(f"\nAvailable skills in {repo}:\n")
        for i, name in enumerate(available, 1):
            click.echo(f"  {i}. {name}")
        raw = click.prompt("\nWhich skills? (e.g. 1,3 or 'all')", default="all")
        if raw.strip().lower() == "all":
            skill_names = available
        else:
            indices = []
            for part in raw.split(","):
                part = part.strip()
                if "-" in part:
                    a, b = part.split("-", 1)
                    indices.extend(range(int(a) - 1, int(b)))
                elif part.isdigit():
                    indices.append(int(part) - 1)
            skill_names = [available[i] for i in indices if 0 <= i < len(available)]

    if not skill_names:
        click.echo("No skills selected.", err=True)
        return

    # Resolve target agents
    agent_list = _resolve_agents(agents, yes)
    if not agent_list:
        return

    # Confirm plan
    if not yes:
        click.echo(f"\nInstall {len(skill_names)} skill(s) from {repo}")
        click.echo(f"  Skills: {', '.join(skill_names)}")
        click.echo(f"  To:     {', '.join(agent_list)}")
        if not click.confirm("\nProceed?", default=True):
            click.echo("Cancelled.")
            return

    # Fetch and install
    installed_skills = []
    for skill_name in skill_names:
        click.echo(f"  Fetching {skill_name}...", nl=False)
        skill = fetch_skill_from_repo(repo, skill_name, branch)
        if not skill:
            click.echo(f" not found in {repo}")
            continue

        # Save to ~/.apc/skills/<name>/SKILL.md
        raw_content = skill.pop("_raw_content", skill.get("body", ""))
        save_skill_file(skill["name"], raw_content)

        # Apply directly to each target agent
        _apply_skill_to_agents(skill, agent_list)

        # Save metadata to local cache
        existing = load_skills()
        merged = merge_skills(existing, [skill])
        save_skills(merged)

        installed_skills.append(skill["name"])
        click.echo(" ✓")

    if installed_skills:
        click.echo(f"\n✓ Installed {len(installed_skills)} skill(s) to {', '.join(agent_list)}")
    else:
        click.echo("\nNo skills were installed.")
