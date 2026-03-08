"""Claude Code applier — writes skills, MCP, memory, settings."""

import json
import os
import stat
from pathlib import Path
from typing import Dict, List

from appliers.base import BaseApplier
from appliers.manifest import ToolManifest
from frontmatter_parser import render_frontmatter

CLAUDE_MEMORY_SCHEMA = """
Claude Code reads instructions from ~/.claude/CLAUDE.md.
This is a plain Markdown file with no special schema.
It contains project instructions, coding preferences, workflow rules, and constraints.
Structure: Use headings (##) to organize sections. Use bullet points for individual rules.
Example sections: Project Context, Standards, Git Workflow, Architecture Notes.
Do NOT include personal information like name/timezone — Claude Code is a coding assistant.
"""


def _claude_dir() -> Path:
    return Path.home() / ".claude"


def _claude_json() -> Path:
    return Path.home() / ".claude.json"


def _claude_commands_dir() -> Path:
    return Path.home() / ".claude/commands"


def _claude_skills_dir() -> Path:
    return Path.home() / ".claude/skills"


def _claude_md() -> Path:
    return Path.home() / ".claude/CLAUDE.md"


class ClaudeApplier(BaseApplier):
    @property
    def SKILL_DIR(self):
        return getattr(self, "_skill_dir_override", None) or _claude_skills_dir()

    @SKILL_DIR.setter
    def SKILL_DIR(self, value):
        self._skill_dir_override = value

    TOOL_NAME = "claude-code"
    MEMORY_SCHEMA = CLAUDE_MEMORY_SCHEMA

    @property  # type: ignore[override]
    def MEMORY_ALLOWED_BASE(self) -> "Path":  # noqa: N802
        return _claude_dir()

    def apply_skills(self, skills: List[Dict], manifest: ToolManifest) -> int:
        _claude_commands_dir().mkdir(parents=True, exist_ok=True)
        count = 0
        for skill in skills:
            name = skill.get("name", "unnamed")
            metadata = {}
            if skill.get("description"):
                metadata["description"] = skill["description"]
            if skill.get("tags"):
                metadata["tags"] = skill["tags"]
            if skill.get("version"):
                metadata["version"] = skill["version"]

            content = render_frontmatter(metadata, skill.get("body", ""))
            path = _claude_commands_dir() / f"{name}.md"
            path.write_text(content, encoding="utf-8")
            manifest.record_skill(name, file_path=str(path), content=content)
            count += 1
        return count

    def apply_mcp_servers(
        self,
        servers: List[Dict],
        secrets: Dict[str, str],
        manifest: ToolManifest,
        override: bool = False,
    ) -> int:
        # Read existing claude.json or start fresh
        if _claude_json().exists():
            try:
                data = json.loads(_claude_json().read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                data = {}
        else:
            data = {}

        if override:
            mcp_servers = {}
        else:
            mcp_servers = data.get("mcpServers", {})

            # Prune orphaned MCP servers that APC previously managed
            if not manifest.is_first_sync:
                current_names = {s.get("name", "unnamed") for s in servers}
                for orphan in set(manifest.managed_mcp_names()) - current_names:
                    mcp_servers.pop(orphan, None)
                    manifest.remove_mcp_server(orphan)

        count = 0
        for server in servers:
            name = server.get("name", "unnamed")

            # Resolve secret placeholders in env
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
        target = _claude_json()
        target.write_text(json.dumps(data, indent=2), encoding="utf-8")
        # Restrict to owner-only since the file may contain resolved API keys (#32)
        os.chmod(target, stat.S_IRUSR | stat.S_IWUSR)
        return count

    def _read_existing_memory_files(self) -> Dict[str, str]:
        """Return {file_path: content} for Claude's memory files."""
        result = {}
        if _claude_md().exists():
            try:
                result[str(_claude_md())] = _claude_md().read_text(encoding="utf-8")
            except IOError:
                pass
        return result
