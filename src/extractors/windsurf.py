"""Windsurf (Codeium) extractor — MCP servers."""

import json
from pathlib import Path
from typing import Dict, List

from extractors.base import BaseExtractor

WINDSURF_MCP_CONFIG = Path.home() / ".codeium" / "windsurf" / "mcp_config.json"


class WindsurfExtractor(BaseExtractor):
    def extract_skills(self) -> List[Dict]:
        return []

    def extract_mcp_servers(self) -> List[Dict]:
        servers = []
        if not WINDSURF_MCP_CONFIG.exists():
            return servers

        try:
            data = json.loads(WINDSURF_MCP_CONFIG.read_text(encoding="utf-8"))
            for name, cfg in data.get("mcpServers", {}).items():
                servers.append(
                    {
                        "name": name,
                        "transport": cfg.get("type", "stdio"),
                        "command": cfg.get("command"),
                        "args": cfg.get("args", []),
                        "env": cfg.get("env", {}),
                        "source_tool": "windsurf",
                        "targets": [],
                    }
                )
        except (json.JSONDecodeError, IOError):
            pass

        return servers

    def extract_memory(self) -> List[Dict]:
        return []
