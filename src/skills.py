"""Skill installation — fetch skills from GitHub repos.

Skills are stored in ~/.apc/skills/<name>/SKILL.md and linked into each
tool's skill directory on sync.
"""

import hashlib
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from config import get_config_dir
from frontmatter_parser import parse_frontmatter

DEFAULT_BRANCH = "main"
_GITHUB_TREE_API = "https://api.github.com/repos/{repo}/git/trees/{branch}?recursive=1"
_GITHUB_RAW = "https://raw.githubusercontent.com/{repo}/{branch}/skills/{skill}/SKILL.md"
_GITHUB_COMMITS_API = (
    "https://api.github.com/repos/{repo}/commits?path=skills/{skill}/SKILL.md&per_page=1"
)

_SKILL_NAME_SAFE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_\-]{0,63}$")


def sanitize_skill_name(name: str) -> str:
    """Return a safe skill name or raise ValueError.

    Rules:
    - Basename only (strips directory components).
    - No path separators, no '..' traversal.
    - Must match [A-Za-z0-9][A-Za-z0-9_\\-]{0,63}.
    """
    # Take basename — eliminates leading paths like "../../etc"
    safe = Path(name).name
    # Reject anything that still looks path-like after basename
    if not safe or safe in (".", ".."):
        raise ValueError(f"Invalid skill name (empty or dot): {name!r}")
    if not _SKILL_NAME_SAFE.match(safe):
        raise ValueError(
            f"Skill name {safe!r} contains invalid characters. "
            "Only letters, digits, hyphens, and underscores are allowed."
        )
    return safe


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
    skill_name = sanitize_skill_name(skill_name)  # raises ValueError on traversal
    skill_dir = get_skills_dir() / skill_name
    skill_dir.mkdir(exist_ok=True)
    path = skill_dir / "SKILL.md"
    path.write_text(raw_content, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# GitHub helpers
# ---------------------------------------------------------------------------


def _safe_get(url: str, timeout: int = 15) -> httpx.Response:
    """Perform a GET request with redirects disabled to prevent SSRF.

    Only follows redirects that stay on the same host (api.github.com or
    raw.githubusercontent.com) by not following redirects at all and letting
    the caller handle non-200 responses.  This prevents open-redirect /
    SSRF attacks where a malicious server could redirect requests to internal
    services.
    """
    return httpx.get(url, follow_redirects=False, timeout=timeout)


def list_skills_in_repo(repo: str, branch: str = DEFAULT_BRANCH) -> List[str]:
    """Return names of all skills available in a GitHub repo.

    Expects skills under skills/<name>/SKILL.md in the repo tree.
    Returns an empty list on network error or if no skills found.
    """
    url = _GITHUB_TREE_API.format(repo=repo, branch=branch)
    try:
        resp = _safe_get(url)
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


def _fetch_skill_commit_sha(repo: str, skill_name: str) -> Optional[str]:
    """Return the latest commit SHA for a skill file, or None on error.

    Uses the GitHub Commits API with a path filter so we get the SHA of the
    commit that last touched skills/<skill_name>/SKILL.md.  This is
    displayed at install-time so users can audit the exact version (#29).
    """
    url = _GITHUB_COMMITS_API.format(repo=repo, skill=skill_name)
    try:
        resp = _safe_get(url)
        if resp.status_code != 200:
            return None
        data = resp.json()
        if isinstance(data, list) and data:
            return data[0].get("sha")
    except (httpx.HTTPError, Exception):
        pass
    return None


def fetch_skill_from_repo(
    repo: str,
    skill_name: str,
    branch: str = DEFAULT_BRANCH,
) -> Optional[Dict[str, Any]]:
    """Fetch and parse a single skill from a GitHub repo.

    Returns a skill dict (with _raw_content and _commit_sha) or None if not found.
    The _commit_sha field contains the SHA of the last commit that touched the
    skill file — callers should display this so users can audit the download (#29).
    """
    url = _GITHUB_RAW.format(repo=repo, branch=branch, skill=skill_name)
    try:
        resp = _safe_get(url)
        if resp.status_code != 200:
            return None
    except httpx.HTTPError:
        return None

    metadata, body = parse_frontmatter(resp.text)
    # Sanitize the name from frontmatter — it comes from an untrusted source.
    raw_name = metadata.get("name", skill_name)
    try:
        safe_name = sanitize_skill_name(raw_name)
    except ValueError:
        # Fall back to the URL-path component (already validated by list_skills_in_repo)
        safe_name = sanitize_skill_name(skill_name)

    # Compute content checksum and fetch commit SHA for integrity display (#29)
    content_checksum = "sha256:" + hashlib.sha256(resp.text.encode()).hexdigest()
    commit_sha = _fetch_skill_commit_sha(repo, skill_name)

    return {
        "name": safe_name,
        "description": metadata.get("description", ""),
        "body": body.strip(),
        "tags": metadata.get("tags", []),
        "targets": [],
        "version": metadata.get("version", ""),
        "source_tool": "github",
        "source_repo": repo,
        "_raw_content": resp.text,
        "_content_checksum": content_checksum,
        "_commit_sha": commit_sha,
    }
