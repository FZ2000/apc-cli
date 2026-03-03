"""Windsurf (Codeium) applier — writes MCP server configs."""

import json
from pathlib import Path
from typing import Dict, List

from appliers.base import BaseApplier
from appliers.manifest import ToolManifest

WINDSURF_DIR = Path.home() / ".codeium" / "windsurf"
WINDSURF_MCP_CONFIG = WINDSURF_DIR / "mcp_config.json"


class WindsurfApplier(BaseApplier):
    TOOL_NAME = "windsurf"

    def apply_skills(self, skills: List[Dict], manifest: ToolManifest) -> int:
        return 0

    def apply_mcp_servers(
        self, servers: List[Dict], secrets: Dict[str, str], manifest: ToolManifest
    ) -> int:
        if WINDSURF_MCP_CONFIG.exists():
            try:
                data = json.loads(WINDSURF_MCP_CONFIG.read_text(encoding="utf-8"))
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
                if not s.get("targets") or "windsurf" in s.get("targets", [])
            }
            for orphan in set(manifest.managed_mcp_names()) - current_names:
                mcp_servers.pop(orphan, None)
                manifest.remove_mcp_server(orphan)

        count = 0
        for server in servers:
            targets = server.get("targets", [])
            if targets and "windsurf" not in targets:
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
        WINDSURF_DIR.mkdir(parents=True, exist_ok=True)
        WINDSURF_MCP_CONFIG.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return count

    def apply_memory(self, entries: List[Dict], manifest: ToolManifest) -> int:
        return 0

    def apply_settings(self, settings: Dict) -> bool:
        return False
