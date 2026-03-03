"""Cursor applier — writes rules/skills and MCP server configs."""

import json
import os
from pathlib import Path
from typing import Dict, List

from appliers.base import BaseApplier
from appliers.manifest import ToolManifest
from frontmatter_parser import render_frontmatter

CURSOR_DIR = Path.home() / ".cursor"
CURSOR_RULES_DIR = Path(".cursor") / "rules"
CURSOR_MCP_JSON = CURSOR_DIR / "mcp.json"


class CursorApplier(BaseApplier):
    SKILL_DIR = CURSOR_RULES_DIR
    TOOL_NAME = "cursor"

    def link_skills(self, skills: List[Dict], source_dir: Path, manifest: ToolManifest) -> int:
        """Cursor uses flat .mdc files, so symlink SKILL.md as <name>.mdc."""
        if self.SKILL_DIR is None:
            return 0

        self.SKILL_DIR.mkdir(parents=True, exist_ok=True)
        count = 0

        for skill in skills:
            name = skill.get("name", "unnamed")
            source = source_dir / name / "SKILL.md"
            if not source.exists():
                continue

            link_path = self.SKILL_DIR / f"{name}.mdc"

            if link_path.is_symlink() or link_path.exists():
                link_path.unlink()

            os.symlink(source, link_path)
            manifest.record_linked_skill(
                name,
                link_path=str(link_path.resolve()),
                target=str(source.resolve()),
            )
            count += 1

        return count

    def apply_skills(self, skills: List[Dict], manifest: ToolManifest) -> int:
        CURSOR_RULES_DIR.mkdir(parents=True, exist_ok=True)
        count = 0
        for skill in skills:
            name = skill.get("name", "unnamed")
            metadata = {}
            if skill.get("description"):
                metadata["description"] = skill["description"]
            if skill.get("tags"):
                metadata["tags"] = skill["tags"]

            content = render_frontmatter(metadata, skill.get("body", ""))
            path = CURSOR_RULES_DIR / f"{name}.mdc"
            path.write_text(content, encoding="utf-8")
            manifest.record_skill(name, file_path=str(path.resolve()), content=content)
            count += 1
        return count

    def apply_mcp_servers(
        self, servers: List[Dict], secrets: Dict[str, str], manifest: ToolManifest
    ) -> int:
        if CURSOR_MCP_JSON.exists():
            try:
                data = json.loads(CURSOR_MCP_JSON.read_text(encoding="utf-8"))
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
                if not s.get("targets") or "cursor" in s.get("targets", [])
            }
            for orphan in set(manifest.managed_mcp_names()) - current_names:
                mcp_servers.pop(orphan, None)
                manifest.remove_mcp_server(orphan)

        count = 0
        for server in servers:
            targets = server.get("targets", [])
            if targets and "cursor" not in targets:
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
        CURSOR_MCP_JSON.parent.mkdir(parents=True, exist_ok=True)
        CURSOR_MCP_JSON.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return count

    def apply_memory(self, entries: List[Dict], manifest: ToolManifest) -> int:
        return 0  # Cursor doesn't have a memory file

    def apply_settings(self, settings: Dict) -> bool:
        return False  # Cursor settings not synced
