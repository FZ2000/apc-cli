"""apc install command — install skills from a GitHub repository.

Handles the `apc install owner/repo` command and all its options.
"""

import re

import click

from appliers import get_applier
from cache import load_skills, merge_skills, save_skills
from extractors import detect_installed_tools
from skills import (
    fetch_skill_from_repo,
    get_skills_dir,
    list_skills_in_repo,
    sanitize_skill_name,
    save_skill_file,
)

# Allowlist patterns for GitHub owner/repo and branch names
# owner/repo: letters, digits, hyphens, underscores, dots — no leading dots/hyphens
_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$")
# branch: letters, digits, hyphens, underscores, dots, slashes — no path traversal
_BRANCH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/\-]{0,253}$")


def _validate_repo(repo: str) -> None:
    """Raise UsageError if repo is not a safe owner/repo string."""
    if not _REPO_RE.match(repo):
        raise click.UsageError(
            f"Invalid repo format {repo!r}. "
            "Must be 'owner/repo' with only letters, digits, hyphens, underscores, and dots."
        )
    # Reject obvious traversal attempts even if regex passes
    if ".." in repo or repo.startswith(".") or repo.endswith("."):
        raise click.UsageError(f"Repo name {repo!r} contains disallowed sequences.")


def _validate_branch(branch: str) -> None:
    """Raise UsageError if branch contains unsafe characters."""
    if not _BRANCH_RE.match(branch):
        raise click.UsageError(
            f"Invalid branch name {branch!r}. "
            "Only letters, digits, hyphens, underscores, dots, and slashes are allowed."
        )
    if ".." in branch:
        raise click.UsageError(f"Branch name {branch!r} contains disallowed path traversal.")


_AGENTS = ["claude-code", "cursor", "gemini-cli", "github-copilot", "openclaw", "windsurf"]


def propagate_remove_to_synced_tools(skill_name: str) -> None:
    """Notify all synced tools that a skill has been uninstalled.

    - Dir-symlink tools: no-op — the skill dir is already gone from the symlink.
    - Windsurf: regenerates global_rules.md block (deleted skill won't appear).
    - Copilot: removes the now-dangling .instructions.md symlink.
    """
    from appliers.manifest import ToolManifest
    from extractors import detect_installed_tools

    for tool_name in detect_installed_tools():
        manifest = ToolManifest(tool_name)
        if manifest.is_first_sync:
            continue
        try:
            applier = get_applier(tool_name)
            applier.remove_installed_skill(skill_name)
        except Exception:
            pass


def _propagate_to_synced_tools(skill_name: str) -> None:
    """Push a newly installed skill to every tool that has been synced.

    Skills always land in ~/.apc/skills/ regardless of --tool flags.
    This function ensures all synced tools see the new skill:

    - Dir-symlink tools (Claude Code, OpenClaw, Gemini, Cursor): no-op —
      the dir symlink already makes the new skill live immediately.
    - Windsurf: regenerates the ## APC Skills block in global_rules.md.
    - Copilot: creates ~/.github/instructions/<name>.instructions.md symlink.
    """
    from appliers.manifest import ToolManifest

    for tool_name in detect_installed_tools():
        manifest = ToolManifest(tool_name)
        if manifest.is_first_sync:
            continue  # never synced — skip
        try:
            applier = get_applier(tool_name)
            applier.apply_installed_skill(skill_name)
        except Exception:
            pass


@click.command()
@click.argument("repo")
@click.option(
    "--skill", "-s", "skills", multiple=True, help="Skill name(s) to install. Use '*' for all."
)
@click.option("--all", "install_all", is_flag=True, help="Install all skills from the repo.")
@click.option("--branch", default="main", show_default=True, help="Git branch to fetch from.")
@click.option(
    "--list",
    "list_only",
    is_flag=True,
    help="List available skills in the repo without installing.",
)
@click.option("-y", "--yes", is_flag=True, help="Non-interactive: skip all confirmation prompts.")
def install(repo, skills, install_all, branch, list_only, yes):
    """Install skills from a GitHub repository.

    Skills are saved to ~/.apc/skills/ and automatically propagated to every
    tool that has been synced via `apc sync`.

    \b
    Examples:
      apc install owner/repo --list
      apc install owner/repo --skill frontend-design
      apc install owner/repo --skill frontend-design --skill skill-creator
      apc install owner/repo --skill '*'
      apc install owner/repo --all
      apc install owner/repo --all -y
    """
    # Validate: repo must look like owner/repo with safe characters
    if repo.startswith("http"):
        raise click.UsageError(
            "REPO must be a GitHub repository name in owner/repo format"
            " (e.g. vercel-labs/target-skills), not a full URL."
        )
    _validate_repo(repo)
    _validate_branch(branch)

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

    # Confirm plan
    if not yes:
        click.echo(f"\nInstall {len(skill_names)} skill(s) from {repo}")
        click.echo(f"  Skills: {', '.join(skill_names)}")
        if not click.confirm("\nProceed?", default=True):
            click.echo("Cancelled.")
            return

    # Ensure ~/.apc/skills/ exists before any skill is fetched.
    # This guarantees the directory is present even if all fetches fail,
    # so callers can safely call iterdir() or exist() on it after install.
    get_skills_dir()

    # Fetch and install
    installed_skills = []
    for skill_name in skill_names:
        click.echo(f"  Fetching {skill_name}...", nl=False)
        skill = fetch_skill_from_repo(repo, skill_name, branch)
        if not skill:
            click.echo(f" not found in {repo}")
            continue

        # Validate name once more before writing to disk (save_skill_file also validates)
        try:
            sanitize_skill_name(skill["name"])
        except ValueError as exc:
            click.echo(f" skipped — invalid name: {exc}", err=True)
            continue

        # Save to ~/.apc/skills/<name>/SKILL.md
        raw_content = skill.pop("_raw_content", skill.get("body", ""))
        save_skill_file(skill["name"], raw_content)

        # Apply directly to each target target
        _propagate_to_synced_tools(skill["name"])

        # Save metadata to local cache
        existing = load_skills()
        merged = merge_skills(existing, [skill])
        save_skills(merged)

        installed_skills.append(skill["name"])
        click.echo(" ✓")

    if installed_skills:
        click.echo(f"\n✓ Installed {len(installed_skills)} skill(s) to ~/.apc/skills/")
    else:
        click.echo("\nNo skills were installed.")
