"""Gemini CLI applier — writes MCP server configs and settings."""

import json
from pathlib import Path
from typing import Dict, List

from apc.appliers.base import BaseApplier
from apc.appliers.manifest import ToolManifest

GEMINI_DIR = Path.home() / ".gemini"
GEMINI_SETTINGS = GEMINI_DIR / "settings.json"


class GeminiApplier(BaseApplier):
    TOOL_NAME = "gemini"

    def apply_skills(self, skills: List[Dict], manifest: ToolManifest) -> int:
        return 0  # Gemini doesn't have a skills format

    def apply_mcp_servers(
        self, servers: List[Dict], secrets: Dict[str, str], manifest: ToolManifest
    ) -> int:
        if GEMINI_SETTINGS.exists():
            try:
                data = json.loads(GEMINI_SETTINGS.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                data = {}
        else:
            data = {}

        mcp_servers = data.get("mcpServers", {})

        # Prune orphaned MCP servers
        if not manifest.is_first_sync:
            current_names = {
                s.get("name", "unnamed")
                for s in servers
                if not s.get("targets") or "gemini" in s.get("targets", [])
            }
            for orphan in set(manifest.managed_mcp_names()) - current_names:
                mcp_servers.pop(orphan, None)
                manifest.remove_mcp_server(orphan)

        count = 0
        for server in servers:
            targets = server.get("targets", [])
            if targets and "gemini" not in targets:
                continue
            name = server.get("name", "unnamed")

            env = server.get("env", {}).copy()
            for key, value in env.items():
                if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
                    secret_name = value[2:-1]
                    if secret_name in secrets:
                        env[key] = secrets[secret_name]

            mcp_servers[name] = {
                "type": server.get("transport", "stdio"),
                "command": server.get("command", ""),
                "args": server.get("args", []),
            }
            if env:
                mcp_servers[name]["env"] = env
            manifest.record_mcp_server(name)
            count += 1

        data["mcpServers"] = mcp_servers
        GEMINI_DIR.mkdir(parents=True, exist_ok=True)
        GEMINI_SETTINGS.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return count

    def apply_memory(self, entries: List[Dict], manifest: ToolManifest) -> int:
        return 0

    def apply_settings(self, settings: Dict) -> bool:
        gemini_settings = settings.get("gemini", {})
        raw_json = gemini_settings.get("raw_json")
        if not raw_json:
            return False

        if GEMINI_SETTINGS.exists():
            try:
                existing = json.loads(GEMINI_SETTINGS.read_text(encoding="utf-8"))
                # Preserve mcpServers
                mcp = existing.get("mcpServers")
                existing.update(raw_json)
                if mcp:
                    existing["mcpServers"] = mcp
                raw_json = existing
            except json.JSONDecodeError:
                pass

        GEMINI_DIR.mkdir(parents=True, exist_ok=True)
        GEMINI_SETTINGS.write_text(json.dumps(raw_json, indent=2), encoding="utf-8")
        return True
