"""Marketplace management for skill installation.

Manages a list of skill sources — GitHub repos (owner/repo) and local
directories — and fetches SKILL.md files from them. No auth required.

Skills are stored as source-of-truth files in ~/.apc/skills/<name>/SKILL.md
and symlinked into each tool's directory.
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from apc.config import get_config_dir
from apc.frontmatter_parser import parse_frontmatter

DEFAULT_MARKETPLACES = ["anthropics/skills"]
MARKETPLACES_FILENAME = "marketplaces.json"
DEFAULT_BRANCH = "main"


def _marketplaces_path() -> Path:
    return get_config_dir() / MARKETPLACES_FILENAME


def load_marketplaces() -> List[str]:
    """Load the list of configured marketplaces. Defaults to ['anthropics/skills']."""
    path = _marketplaces_path()
    if not path.exists():
        return list(DEFAULT_MARKETPLACES)
    try:
        data = json.loads(path.read_text())
        if isinstance(data, list) and data:
            return data
        return list(DEFAULT_MARKETPLACES)
    except (json.JSONDecodeError, TypeError):
        return list(DEFAULT_MARKETPLACES)


def save_marketplaces(marketplaces: List[str]) -> None:
    """Save the list of configured marketplaces."""
    path = _marketplaces_path()
    path.write_text(json.dumps(marketplaces, indent=2))


def add_marketplace(source: str) -> List[str]:
    """Add a marketplace at highest priority (index 0). Returns updated list."""
    marketplaces = load_marketplaces()
    if source in marketplaces:
        marketplaces.remove(source)
    marketplaces.insert(0, source)
    save_marketplaces(marketplaces)
    return marketplaces


def delete_marketplace(source: str) -> List[str]:
    """Remove a marketplace from the list. Returns updated list."""
    marketplaces = load_marketplaces()
    if source in marketplaces:
        marketplaces.remove(source)
    save_marketplaces(marketplaces)
    return marketplaces


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


def search_skill(
    skill_name: str,
    repos: Optional[List[str]] = None,
    branch: str = DEFAULT_BRANCH,
) -> Optional[Dict[str, Any]]:
    """Search for a skill across marketplaces in priority order. Returns first match."""
    if repos is None:
        repos = load_marketplaces()

    for source in repos:
        if is_local_path(source):
            skill = fetch_skill_from_local(source, skill_name)
        else:
            skill = fetch_skill_from_repo(source, skill_name, branch)
        if skill is not None:
            return skill

    return None
