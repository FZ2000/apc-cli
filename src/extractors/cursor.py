"""Cursor extractor — rules/skills and MCP servers."""

import hashlib
import json
from pathlib import Path
from typing import Dict, List

from extractors.base import BaseExtractor
from frontmatter_parser import parse_frontmatter

CURSOR_DIR = Path.home() / ".cursor"
CURSOR_RULES_DIR = Path(".cursor") / "rules"
CURSOR_MCP_JSON = CURSOR_DIR / "mcp.json"


class CursorExtractor(BaseExtractor):
    def extract_skills(self) -> List[Dict]:
        skills = []
        if not CURSOR_RULES_DIR.exists():
            return skills

        for mdc_file in CURSOR_RULES_DIR.glob("*.mdc"):
            try:
                content = mdc_file.read_text(encoding="utf-8")
                metadata, body = parse_frontmatter(content)
                name = metadata.get("name", mdc_file.stem)
                checksum = f"sha256:{hashlib.sha256(content.encode()).hexdigest()[:16]}"

                skills.append(
                    {
                        "name": name,
                        "description": metadata.get("description", ""),
                        "body": body,
                        "tags": metadata.get("tags", []),
                        "targets": [],
                        "version": metadata.get("version", "1.0.0"),
                        "source_tool": "cursor",
                        "source_path": str(mdc_file),
                        "checksum": checksum,
                    }
                )
            except Exception:
                continue

        return skills

    def extract_mcp_servers(self) -> List[Dict]:
        servers = []
        if not CURSOR_MCP_JSON.exists():
            return servers

        try:
            data = json.loads(CURSOR_MCP_JSON.read_text(encoding="utf-8"))
            for name, cfg in data.get("mcpServers", {}).items():
                servers.append(
                    {
                        "name": name,
                        "transport": cfg.get("type", "stdio"),
                        "command": cfg.get("command"),
                        "args": cfg.get("args", []),
                        "env": cfg.get("env", {}),
                        "source_tool": "cursor",
                        "targets": [],
                    }
                )
        except (json.JSONDecodeError, IOError):
            pass

        return servers

    def extract_memory(self) -> List[Dict]:
        return []
