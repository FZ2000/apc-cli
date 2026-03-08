"""GitHub Copilot extractor — instructions and MCP servers."""

import hashlib
import json
from pathlib import Path
from typing import Dict, List

from extractors.base import BaseExtractor


def _copilot_instructions() -> Path:
    """Absolute path to copilot-instructions.md, resolved at call-time from CWD (#42)."""
    return Path.cwd().resolve() / ".github" / "copilot-instructions.md"


def _vscode_mcp_json() -> Path:
    """Absolute path to .vscode/mcp.json, resolved at call-time from CWD (#42)."""
    return Path.cwd().resolve() / ".vscode" / "mcp.json"


class CopilotExtractor(BaseExtractor):
    def extract_skills(self) -> List[Dict]:
        skills = []
        instructions = _copilot_instructions()
        if not instructions.exists():
            return skills

        try:
            content = instructions.read_text(encoding="utf-8")
            checksum = f"sha256:{hashlib.sha256(content.encode()).hexdigest()[:16]}"
            skills.append(
                {
                    "name": "copilot-instructions",
                    "description": "GitHub Copilot custom instructions",
                    "body": content,
                    "tags": ["copilot", "instructions"],
                    "targets": [],
                    "version": "1.0.0",
                    "source_tool": "github-copilot",
                    "source_path": str(instructions),
                    "checksum": checksum,
                }
            )
        except IOError:
            pass

        return skills

    def extract_mcp_servers(self) -> List[Dict]:
        servers = []
        vscode_mcp = _vscode_mcp_json()
        if not vscode_mcp.exists():
            return servers

        try:
            data = json.loads(vscode_mcp.read_text(encoding="utf-8"))
            for name, cfg in data.get("servers", {}).items():
                servers.append(
                    {
                        "name": name,
                        "transport": cfg.get("type", "stdio"),
                        "command": cfg.get("command"),
                        "args": cfg.get("args", []),
                        "env": cfg.get("env", {}),
                        "source_tool": "github-copilot",
                        "targets": [],
                    }
                )
        except (json.JSONDecodeError, IOError):
            pass

        return servers

    def extract_memory(self) -> List[Dict]:
        return []
