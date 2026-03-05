"""GitHub repository management for skill installation.

Manages a list of GitHub repos (like conda channels) and fetches
SKILL.md files from raw.githubusercontent.com. No auth required.

Skills are stored as source-of-truth files in ~/.apc/skills/<name>/SKILL.md
and symlinked into each tool's directory.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from config import get_config_dir
from frontmatter_parser import parse_frontmatter

DEFAULT_REPOS = ["anthropics/skills"]
REPOS_FILENAME = "repositories.json"
DEFAULT_BRANCH = "main"


def _repos_path() -> Path:
    return get_config_dir() / REPOS_FILENAME


def load_repositories() -> List[str]:
    """Load the list of configured GitHub repos. Defaults to ['anthropics/skills']."""
    path = _repos_path()
    if not path.exists():
        return list(DEFAULT_REPOS)
    try:
        data = json.loads(path.read_text())
        if isinstance(data, list) and data:
            return data
        return list(DEFAULT_REPOS)
    except (json.JSONDecodeError, TypeError):
        return list(DEFAULT_REPOS)


def save_repositories(repos: List[str]) -> None:
    """Save the list of configured GitHub repos."""
    path = _repos_path()
    path.write_text(json.dumps(repos, indent=2))


def add_repository(repo: str) -> List[str]:
    """Add a repo at highest priority (index 0). Returns updated list."""
    repos = load_repositories()
    if repo in repos:
        repos.remove(repo)
    repos.insert(0, repo)
    save_repositories(repos)
    return repos


def remove_repository(repo: str) -> List[str]:
    """Remove a repo from the list. Returns updated list."""
    repos = load_repositories()
    if repo in repos:
        repos.remove(repo)
    save_repositories(repos)
    return repos


def _build_skill_url(repo_slug: str, skill_name: str, branch: str = DEFAULT_BRANCH) -> str:
    """Build the raw GitHub URL for a SKILL.md file."""
    return f"https://raw.githubusercontent.com/{repo_slug}/{branch}/skills/{skill_name}/SKILL.md"


def get_skills_dir() -> Path:
    """Get or create the ~/.apc/skills/ directory (source of truth for installed skills)."""
    skills_dir = get_config_dir() / "skills"
    skills_dir.mkdir(exist_ok=True)
    return skills_dir


def save_skill_file(skill_name: str, raw_content: str) -> Path:
    """Save raw SKILL.md content to ~/.apc/skills/<name>/SKILL.md.

    Returns the path to the saved file.
    """
    skill_dir = get_skills_dir() / skill_name
    skill_dir.mkdir(exist_ok=True)
    path = skill_dir / "SKILL.md"
    path.write_text(raw_content, encoding="utf-8")
    return path


def get_skill_source_path(skill_name: str) -> Path:
    """Get the source-of-truth path for a skill."""
    return get_skills_dir() / skill_name / "SKILL.md"


def fetch_skill_from_repo(
    repo_slug: str,
    skill_name: str,
    branch: str = DEFAULT_BRANCH,
) -> Optional[Dict[str, Any]]:
    """Fetch and parse a SKILL.md from a GitHub repo.

    Returns a skill dict compatible with the local cache format, or None if not found.
    The raw content is included under the '_raw_content' key for saving to disk.
    """
    url = _build_skill_url(repo_slug, skill_name, branch)
    try:
        resp = httpx.get(url, follow_redirects=True, timeout=15)
        if resp.status_code != 200:
            return None
    except httpx.HTTPError:
        return None

    metadata, body = parse_frontmatter(resp.text)

    return {
        "name": metadata.get("name", skill_name),
        "description": metadata.get("description", ""),
        "body": body.strip(),
        "tags": metadata.get("tags", []),
        "targets": [],
        "version": metadata.get("version", ""),
        "source_tool": "github",
        "source_repo": repo_slug,
        "_raw_content": resp.text,
    }


def search_skill(
    skill_name: str,
    repos: Optional[List[str]] = None,
    branch: str = DEFAULT_BRANCH,
) -> Optional[Dict[str, Any]]:
    """Search for a skill across repos in priority order. Returns first match."""
    if repos is None:
        repos = load_repositories()

    for repo in repos:
        skill = fetch_skill_from_repo(repo, skill_name, branch)
        if skill is not None:
            return skill

    return None
