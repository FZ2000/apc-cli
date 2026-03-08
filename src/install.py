"""apc install command — install skills from a GitHub repository.

Handles the `apc install owner/repo` command and all its options.
"""

import re
from typing import List

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


def _resolve_targets(target_args: tuple, yes: bool) -> List[str]:
    """Resolve target targets from -a flags, '*', or interactive selection."""
    if not target_args:
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

    targets = list(target_args)
    if "*" in targets:
        return detect_installed_tools()
    return targets


def _note_per_skill_tools(target_list: list) -> None:
    """Warn if any synced target uses per-skill symlinks (not dir-level).

    For tools with SKILL_DIR set, the dir symlink is already live after
    apc sync — new skills in ~/.apc/skills/ appear immediately.
    For Copilot (no SKILL_DIR), re-run `apc sync` to pick up new skills.
    """
    needs_sync = []
    for target_name in target_list:
        try:
            applier = get_applier(target_name)
            if applier.SKILL_DIR is None:
                needs_sync.append(target_name)
        except Exception:
            pass
    if needs_sync:
        click.echo(
            f"  ℹ {', '.join(needs_sync)}: run `apc sync` to link this skill "
            "(per-skill symlinks — dir-level not supported for mixed skill dirs)",
            err=True,
        )


@click.command()
@click.argument("repo")
@click.option(
    "--skill", "-s", "skills", multiple=True, help="Skill name(s) to install. Use '*' for all."
)
@click.option("--all", "install_all", is_flag=True, help="Install all skills from the repo.")
@click.option(
    "--target",
    "-t",
    "targets",
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
def install(repo, skills, install_all, targets, branch, list_only, yes):
    """Install skills from a GitHub repository.

    \b
    Examples:
      apc install owner/repo --list
      apc install owner/repo --skill frontend-design
      apc install owner/repo --skill frontend-design --skill skill-creator
      apc install owner/repo --skill '*'
      apc install owner/repo --all
      apc install owner/repo --skill frontend-design -t claude-code -t cursor
      apc install owner/repo --all -t claude-code -y
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

    # Resolve target targets
    target_list = _resolve_targets(targets, yes)
    if not target_list:
        return

    # Confirm plan
    if not yes:
        click.echo(f"\nInstall {len(skill_names)} skill(s) from {repo}")
        click.echo(f"  Skills: {', '.join(skill_names)}")
        click.echo(f"  To:     {', '.join(target_list)}")
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
        _note_per_skill_tools(target_list)

        # Save metadata to local cache
        existing = load_skills()
        merged = merge_skills(existing, [skill])
        save_skills(merged)

        installed_skills.append(skill["name"])
        click.echo(" ✓")

    if installed_skills:
        click.echo(f"\n✓ Installed {len(installed_skills)} skill(s) to {', '.join(target_list)}")
    else:
        click.echo("\nNo skills were installed.")
