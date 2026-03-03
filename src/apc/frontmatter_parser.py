"""Safe YAML frontmatter parsing for skill markdown files."""

import re
from typing import Any, Dict, Tuple

import yaml


def parse_frontmatter(content: str) -> Tuple[Dict[str, Any], str]:
    """Parse YAML frontmatter from a markdown file.

    Returns:
        (metadata_dict, body_content)
    """
    pattern = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)", re.DOTALL)
    match = pattern.match(content)

    if not match:
        return {}, content

    try:
        metadata = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        metadata = {}

    body = match.group(2)
    return metadata, body


def render_frontmatter(metadata: Dict[str, Any], body: str) -> str:
    """Render a markdown file with YAML frontmatter.

    Returns:
        Complete markdown string with frontmatter header
    """
    if not metadata:
        return body

    yaml_str = yaml.dump(metadata, default_flow_style=False, sort_keys=False).strip()
    return f"---\n{yaml_str}\n---\n\n{body}"
