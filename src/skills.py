"""Skill installation — fetch skills from GitHub repos.

Skills are stored in ~/.apc/skills/<name>/SKILL.md and linked into each
tool's skill directory on sync.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from config import get_config_dir
from frontmatter_parser import parse_frontmatter

DEFAULT_BRANCH = "main"
_GITHUB_TREE_API = "https://api.github.com/repos/{repo}/git/trees/{branch}?recursive=1"
_GITHUB_RAW = "https://raw.githubusercontent.com/{repo}/{branch}/skills/{skill}/SKILL.md"


# ---------------------------------------------------------------------------
# Skills directory
# ---------------------------------------------------------------------------


def get_skills_dir() -> Path:
    """Get or create the ~/.apc/skills/ directory (source of truth for installed skills)."""
    skills_dir = get_config_dir() / "skills"
    skills_dir.mkdir(exist_ok=True)
    return skills_dir


def save_skill_file(skill_name: str, raw_content: str) -> Path:
    """Save raw SKILL.md to ~/.apc/skills/<name>/SKILL.md. Returns the path."""
    skill_dir = get_skills_dir() / skill_name
    skill_dir.mkdir(exist_ok=True)
    path = skill_dir / "SKILL.md"
    path.write_text(raw_content, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# GitHub helpers
# ---------------------------------------------------------------------------


def list_skills_in_repo(repo: str, branch: str = DEFAULT_BRANCH) -> List[str]:
    """Return names of all skills available in a GitHub repo.

    Expects skills under skills/<name>/SKILL.md in the repo tree.
    Returns an empty list on network error or if no skills found.
    """
    url = _GITHUB_TREE_API.format(repo=repo, branch=branch)
    try:
        resp = httpx.get(url, follow_redirects=True, timeout=15)
        if resp.status_code != 200:
            return []
        tree = resp.json().get("tree", [])
    except (httpx.HTTPError, ValueError):
        return []

    names = []
    for item in tree:
        path = item.get("path", "")
        # Match: skills/<name>/SKILL.md
        parts = path.split("/")
        if len(parts) == 3 and parts[0] == "skills" and parts[2] == "SKILL.md":
            names.append(parts[1])
    return sorted(names)


def fetch_skill_from_repo(
    repo: str,
    skill_name: str,
    branch: str = DEFAULT_BRANCH,
) -> Optional[Dict[str, Any]]:
    """Fetch and parse a single skill from a GitHub repo.

    Returns a skill dict (with _raw_content) or None if not found.
    """
    url = _GITHUB_RAW.format(repo=repo, branch=branch, skill=skill_name)
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
        "source_repo": repo,
        "_raw_content": resp.text,
    }
