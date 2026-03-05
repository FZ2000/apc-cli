"""GitHub Copilot applier — writes instructions and MCP configs."""

import json
from pathlib import Path
from typing import Dict, List

from appliers.base import BaseApplier
from appliers.manifest import ToolManifest

COPILOT_INSTRUCTIONS = Path(".github") / "copilot-instructions.md"
VSCODE_MCP_JSON = Path(".vscode") / "mcp.json"


class CopilotApplier(BaseApplier):
    TOOL_NAME = "copilot"

    def apply_skills(self, skills: List[Dict], manifest: ToolManifest) -> int:
        count = 0
        for skill in skills:
            if skill.get("name") == "copilot-instructions":
                COPILOT_INSTRUCTIONS.parent.mkdir(parents=True, exist_ok=True)
                content = skill.get("body", "")
                COPILOT_INSTRUCTIONS.write_text(content, encoding="utf-8")
                manifest.record_skill(
                    "copilot-instructions",
                    file_path=str(COPILOT_INSTRUCTIONS.resolve()),
                    content=content,
                )
                count += 1
        return count

    def apply_mcp_servers(
        self, servers: List[Dict], secrets: Dict[str, str], manifest: ToolManifest
    ) -> int:
        if VSCODE_MCP_JSON.exists():
            try:
                data = json.loads(VSCODE_MCP_JSON.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                data = {}
        else:
            data = {}

        vscode_servers = data.get("servers", {})

        # Prune orphaned MCP servers
        if not manifest.is_first_sync:
            current_names = {
                s.get("name", "unnamed")
                for s in servers
                if not s.get("targets") or "copilot" in s.get("targets", [])
            }
            for orphan in set(manifest.managed_mcp_names()) - current_names:
                vscode_servers.pop(orphan, None)
                manifest.remove_mcp_server(orphan)

        count = 0
        for server in servers:
            targets = server.get("targets", [])
            if targets and "copilot" not in targets:
                continue
            name = server.get("name", "unnamed")

            env = server.get("env", {}).copy()
            for key, value in env.items():
                if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
                    secret_name = value[2:-1]
                    if secret_name in secrets:
                        env[key] = secrets[secret_name]

            vscode_servers[name] = {
                "type": server.get("transport", "stdio"),
                "command": server.get("command", ""),
                "args": server.get("args", []),
            }
            if env:
                vscode_servers[name]["env"] = env
            manifest.record_mcp_server(name)
            count += 1

        data["servers"] = vscode_servers
        VSCODE_MCP_JSON.parent.mkdir(parents=True, exist_ok=True)
        VSCODE_MCP_JSON.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return count

    def apply_memory(self, entries: List[Dict], manifest: ToolManifest) -> int:
        return 0

    def apply_settings(self, settings: Dict) -> bool:
        return False
