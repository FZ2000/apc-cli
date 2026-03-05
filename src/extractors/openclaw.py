"""OpenClaw extractor — skills, memory, settings."""

import hashlib
from pathlib import Path
from typing import Dict, List

from extractors.base import BaseExtractor
from frontmatter_parser import parse_frontmatter

OPENCLAW_DIR = Path.home() / ".openclaw"
OPENCLAW_SKILLS_DIR = OPENCLAW_DIR / "skills"
OPENCLAW_WORKSPACE = OPENCLAW_DIR / "workspace"
OPENCLAW_USER_MD = OPENCLAW_WORKSPACE / "USER.md"
OPENCLAW_MEMORY_MD = OPENCLAW_WORKSPACE / "MEMORY.md"
OPENCLAW_IDENTITY_MD = OPENCLAW_WORKSPACE / "IDENTITY.md"
OPENCLAW_SOUL_MD = OPENCLAW_WORKSPACE / "SOUL.md"
OPENCLAW_TOOLS_MD = OPENCLAW_WORKSPACE / "TOOLS.md"

# Registry of portable memory files (excludes Claw-specific: AGENTS.md, BOOTSTRAP.md, HEARTBEAT.md)
MEMORY_FILES = [
    {"path": OPENCLAW_USER_MD, "label": "Personal context (USER.md)"},
    {"path": OPENCLAW_MEMORY_MD, "label": "Long-term memory (MEMORY.md)"},
    {"path": OPENCLAW_IDENTITY_MD, "label": "Assistant persona (IDENTITY.md)"},
    {"path": OPENCLAW_SOUL_MD, "label": "Values & working style (SOUL.md)"},
    {"path": OPENCLAW_TOOLS_MD, "label": "Infrastructure & device config (TOOLS.md)"},
]


def _content_hash_id(source_tool: str, source_file: str, content: str) -> str:
    """Generate a content-hash based ID for deduplication."""
    raw = f"{source_tool}:{source_file}:{content}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


class OpenClawExtractor(BaseExtractor):
    def extract_skills(self) -> List[Dict]:
        """Extract user-local skills only (not bundled ones from the npm package)."""
        skills = []
        if not OPENCLAW_SKILLS_DIR.exists():
            return skills

        for skill_dir in OPENCLAW_SKILLS_DIR.iterdir():
            if not skill_dir.is_dir():
                continue
            skill_md = skill_dir / "SKILL.md"
            if not skill_md.exists():
                continue

            try:
                content = skill_md.read_text(encoding="utf-8")
                metadata, body = parse_frontmatter(content)
                name = metadata.get("name", skill_dir.name)
                checksum = f"sha256:{hashlib.sha256(content.encode()).hexdigest()[:16]}"

                skills.append(
                    {
                        "name": name,
                        "description": metadata.get("description", ""),
                        "body": body,
                        "tags": metadata.get("tags", []),
                        "targets": [],
                        "version": metadata.get("version", "1.0.0"),
                        "source_tool": "openclaw",
                        "source_path": str(skill_md),
                        "checksum": checksum,
                    }
                )
            except Exception:
                continue

        return skills

    def extract_mcp_servers(self) -> List[Dict]:
        # OpenClaw does not support MCP servers — it uses its own skill/tool system
        return []

    def extract_memory(self) -> List[Dict]:
        """Extract memory as raw file contents with content-hash IDs."""
        entries = []
        for mf in MEMORY_FILES:
            path = mf["path"]
            if not path.exists():
                continue
            try:
                content = path.read_text(encoding="utf-8").strip()
                if not content:
                    continue
                entries.append(
                    {
                        "id": _content_hash_id("openclaw", path.name, content),
                        "source_tool": "openclaw",
                        "source_file": path.name,
                        "source_path": str(path),
                        "label": mf["label"],
                        "content": content,
                    }
                )
            except IOError:
                continue
        return entries
