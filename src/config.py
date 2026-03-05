"""Manages ~/.apc/ directory and cache paths."""

from pathlib import Path


def get_config_dir() -> Path:
    """Get or create the ~/.apc/ configuration directory."""
    config_dir = Path.home() / ".apc"
    config_dir.mkdir(exist_ok=True)
    return config_dir


def get_cache_dir() -> Path:
    """Get or create the ~/.apc/cache/ directory for local JSON cache."""
    cache_dir = get_config_dir() / "cache"
    cache_dir.mkdir(exist_ok=True)
    return cache_dir


def get_skills_dir() -> Path:
    """Get or create the ~/.apc/skills/ directory for installed skills."""
    skills_dir = get_config_dir() / "skills"
    skills_dir.mkdir(exist_ok=True)
    return skills_dir
