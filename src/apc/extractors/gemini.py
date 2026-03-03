"""Gemini CLI extractor — MCP servers and settings."""

import json
from pathlib import Path
from typing import Dict, List, Optional

from apc.extractors.base import BaseExtractor

GEMINI_DIR = Path.home() / ".gemini"
GEMINI_SETTINGS = GEMINI_DIR / "settings.json"


class GeminiExtractor(BaseExtractor):
    def extract_skills(self) -> List[Dict]:
        return []

    def extract_mcp_servers(self) -> List[Dict]:
        servers = []
        if not GEMINI_SETTINGS.exists():
            return servers

        try:
            data = json.loads(GEMINI_SETTINGS.read_text(encoding="utf-8"))
            for name, cfg in data.get("mcpServers", {}).items():
                servers.append(
                    {
                        "name": name,
                        "transport": cfg.get("type", "stdio"),
                        "command": cfg.get("command"),
                        "args": cfg.get("args", []),
                        "env": cfg.get("env", {}),
                        "source_tool": "gemini",
                        "targets": [],
                    }
                )
        except (json.JSONDecodeError, IOError):
            pass

        return servers

    def extract_memory(self) -> List[Dict]:
        return []

    def extract_settings(self) -> Optional[Dict]:
        if not GEMINI_SETTINGS.exists():
            return None
        try:
            raw = json.loads(GEMINI_SETTINGS.read_text(encoding="utf-8"))
            # Exclude mcpServers from settings — they're handled separately
            settings = {k: v for k, v in raw.items() if k != "mcpServers"}
            if not settings:
                return None
            return {
                "gemini": {
                    "raw_json": settings,
                    "source_path": str(GEMINI_SETTINGS),
                }
            }
        except (json.JSONDecodeError, IOError):
            return None
