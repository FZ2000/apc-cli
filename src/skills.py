"""Skill installation — fetch skills from GitHub repos or local directories.

No auth required. Skills are stored in ~/.apc/skills/<name>/SKILL.md
and linked into each tool's skill directory on sync.
"""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from config import get_config_dir
from frontmatter_parser import parse_frontmatter

DEFAULT_BRANCH = "main"


def is_local_path(source: str) -> bool:
    """Return True if the source looks like a local directory path."""
    return (
        source.startswith("/")
        or source.startswith("./")
        or source.startswith("../")
        or source.startswith("~")
    )


def fetch_skill_from_local(directory_path: str, skill_name: str) -> Optional[Dict[str, Any]]:
    """Fetch and parse a SKILL.md from a local directory.

    Expects the file at <directory_path>/skills/<skill_name>/SKILL.md.
    Returns a skill dict compatible with the cache format, or None if not found.
    """
    path = Path(os.path.expanduser(directory_path)) / "skills" / skill_name / "SKILL.md"
    if not path.is_file():
        return None

    raw_content = path.read_text(encoding="utf-8")
    metadata, body = parse_frontmatter(raw_content)

    return {
        "name": metadata.get("name", skill_name),
        "description": metadata.get("description", ""),
        "body": body.strip(),
        "tags": metadata.get("tags", []),
        "targets": [],
        "version": metadata.get("version", ""),
        "source_tool": "local",
        "source_repo": directory_path,
        "_raw_content": raw_content,
    }


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


DEFAULT_REPO = "anthropics/skills"


def search_skill(
    skill_name: str,
    repos: Optional[List[str]] = None,
    branch: str = DEFAULT_BRANCH,
) -> Optional[Dict[str, Any]]:
    """Search for a skill across repos in priority order. Returns first match."""
    if repos is None:
        repos = [DEFAULT_REPO]

    for source in repos:
        if is_local_path(source):
            skill = fetch_skill_from_local(source, skill_name)
        else:
            skill = fetch_skill_from_repo(source, skill_name, branch)
        if skill is not None:
            return skill

    return None
