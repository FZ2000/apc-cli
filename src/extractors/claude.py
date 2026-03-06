"""Claude Code extractor — skills, MCP servers, memory, settings."""

import hashlib
import json
from pathlib import Path
from typing import Dict, List

from extractors.base import BaseExtractor
from frontmatter_parser import parse_frontmatter

CLAUDE_DIR = Path.home() / ".claude"
CLAUDE_JSON = Path.home() / ".claude.json"
CLAUDE_COMMANDS_DIR = CLAUDE_DIR / "commands"
CLAUDE_MD = CLAUDE_DIR / "CLAUDE.md"
# Registry of memory files this tool declares
MEMORY_FILES = [
    {"path": CLAUDE_MD, "label": "Instructions (CLAUDE.md)"},
]


def _content_hash_id(source_tool: str, source_file: str, content: str) -> str:
    """Generate a content-hash based ID for deduplication."""
    raw = f"{source_tool}:{source_file}:{content}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


class ClaudeExtractor(BaseExtractor):
    def extract_skills(self) -> List[Dict]:
        skills = []
        if not CLAUDE_COMMANDS_DIR.exists():
            return skills

        for md_file in CLAUDE_COMMANDS_DIR.glob("*.md"):
            try:
                content = md_file.read_text(encoding="utf-8")
                metadata, body = parse_frontmatter(content)
                name = metadata.get("name", md_file.stem)
                checksum = f"sha256:{hashlib.sha256(content.encode()).hexdigest()[:16]}"

                skills.append(
                    {
                        "name": name,
                        "description": metadata.get("description", ""),
                        "body": body,
                        "tags": metadata.get("tags", []),
                        "targets": [],
                        "version": metadata.get("version", "1.0.0"),
                        "source_tool": "claude-code",
                        "source_path": str(md_file),
                        "checksum": checksum,
                    }
                )
            except Exception:
                continue

        return skills

    def extract_mcp_servers(self) -> List[Dict]:
        servers = []
        if not CLAUDE_JSON.exists():
            return servers

        try:
            data = json.loads(CLAUDE_JSON.read_text(encoding="utf-8"))
            for name, cfg in data.get("mcpServers", {}).items():
                servers.append(
                    {
                        "name": name,
                        "transport": cfg.get("type", "stdio"),
                        "command": cfg.get("command"),
                        "args": cfg.get("args", []),
                        "env": cfg.get("env", {}),
                        "source_tool": "claude-code",
                        "targets": [],
                    }
                )
        except (json.JSONDecodeError, IOError):
            pass

        return servers

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
                        "id": _content_hash_id("claude-code", path.name, content),
                        "source_tool": "claude-code",
                        "source_file": path.name,
                        "source_path": str(path),
                        "label": mf["label"],
                        "content": content,
                    }
                )
            except IOError:
                continue
        return entries
