"""GitHub Copilot extractor — instructions and MCP servers."""

import hashlib
import json
from pathlib import Path
from typing import Dict, List

from extractors.base import BaseExtractor

COPILOT_INSTRUCTIONS = Path(".github") / "copilot-instructions.md"
VSCODE_MCP_JSON = Path(".vscode") / "mcp.json"


class CopilotExtractor(BaseExtractor):
    def extract_skills(self) -> List[Dict]:
        skills = []
        if not COPILOT_INSTRUCTIONS.exists():
            return skills

        try:
            content = COPILOT_INSTRUCTIONS.read_text(encoding="utf-8")
            checksum = f"sha256:{hashlib.sha256(content.encode()).hexdigest()[:16]}"
            skills.append(
                {
                    "name": "copilot-instructions",
                    "description": "GitHub Copilot custom instructions",
                    "body": content,
                    "tags": ["copilot", "instructions"],
                    "targets": [],
                    "version": "1.0.0",
                    "source_tool": "copilot",
                    "source_path": str(COPILOT_INSTRUCTIONS),
                    "checksum": checksum,
                }
            )
        except IOError:
            pass

        return skills

    def extract_mcp_servers(self) -> List[Dict]:
        servers = []
        if not VSCODE_MCP_JSON.exists():
            return servers

        try:
            data = json.loads(VSCODE_MCP_JSON.read_text(encoding="utf-8"))
            for name, cfg in data.get("servers", {}).items():
                servers.append(
                    {
                        "name": name,
                        "transport": cfg.get("type", "stdio"),
                        "command": cfg.get("command"),
                        "args": cfg.get("args", []),
                        "env": cfg.get("env", {}),
                        "source_tool": "copilot",
                        "targets": [],
                    }
                )
        except (json.JSONDecodeError, IOError):
            pass

        return servers

    def extract_memory(self) -> List[Dict]:
        return []
