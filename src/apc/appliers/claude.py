"""Claude Code applier — writes skills, MCP, memory, settings."""

import json
from pathlib import Path
from typing import Dict, List

from apc.appliers.base import BaseApplier
from apc.appliers.manifest import ToolManifest
from apc.appliers.memory_section import write_memory_file
from apc.frontmatter_parser import render_frontmatter

CLAUDE_DIR = Path.home() / ".claude"
CLAUDE_JSON = Path.home() / ".claude.json"
CLAUDE_COMMANDS_DIR = CLAUDE_DIR / "commands"
CLAUDE_SKILLS_DIR = CLAUDE_DIR / "skills"
CLAUDE_MD = CLAUDE_DIR / "CLAUDE.md"
CLAUDE_SETTINGS = CLAUDE_DIR / "settings.json"

CATEGORY_HEADERS = {
    "preference": "Preferences",
    "workflow": "Workflow",
    "project_context": "Project Context",
    "personal": "Personal",
    "tool_config": "Tool Configuration",
    "constraint": "Constraints",
}

CLAUDE_MEMORY_SCHEMA = """
Claude Code reads instructions from ~/.claude/CLAUDE.md.
This is a plain Markdown file with no special schema.
It contains project instructions, coding preferences, workflow rules, and constraints.
Structure: Use headings (##) to organize sections. Use bullet points for individual rules.
Example sections: Project Context, Standards, Git Workflow, Architecture Notes.
Do NOT include personal information like name/timezone — Claude Code is a coding assistant.
"""


class ClaudeApplier(BaseApplier):
    SKILL_DIR = CLAUDE_SKILLS_DIR
    TOOL_NAME = "claude"
    MEMORY_SCHEMA = CLAUDE_MEMORY_SCHEMA

    def apply_skills(self, skills: List[Dict], manifest: ToolManifest) -> int:
        CLAUDE_COMMANDS_DIR.mkdir(parents=True, exist_ok=True)
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
            path = CLAUDE_COMMANDS_DIR / f"{name}.md"
            path.write_text(content, encoding="utf-8")
            manifest.record_skill(name, file_path=str(path), content=content)
            count += 1
        return count

    def apply_mcp_servers(
        self, servers: List[Dict], secrets: Dict[str, str], manifest: ToolManifest
    ) -> int:
        # Read existing claude.json or start fresh
        if CLAUDE_JSON.exists():
            try:
                data = json.loads(CLAUDE_JSON.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                data = {}
        else:
            data = {}

        mcp_servers = data.get("mcpServers", {})

        # Prune orphaned MCP servers that APC previously managed
        if not manifest.is_first_sync:
            current_names = {
                s.get("name", "unnamed")
                for s in servers
                if not s.get("targets") or "claude" in s.get("targets", [])
            }
            for orphan in set(manifest.managed_mcp_names()) - current_names:
                mcp_servers.pop(orphan, None)
                manifest.remove_mcp_server(orphan)

        count = 0
        for server in servers:
            targets = server.get("targets", [])
            if targets and "claude" not in targets:
                continue
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
        CLAUDE_JSON.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return count

    def apply_memory(self, entries: List[Dict], manifest: ToolManifest) -> int:
        """Legacy direct apply (used as fallback when LLM is not configured)."""
        if not entries:
            return 0

        CLAUDE_DIR.mkdir(parents=True, exist_ok=True)

        inner = write_memory_file(
            CLAUDE_MD,
            entries,
            CATEGORY_HEADERS,
            title="AI Context — Synced by apc",
        )

        entry_ids = [e.get("entry_id") or e.get("id", "") for e in entries if e.get("content")]
        manifest.record_memory(
            file_path=str(CLAUDE_MD),
            entry_ids=entry_ids,
            content=inner,
        )

        # Count actual entries written
        return sum(1 for e in entries if e.get("content"))

    def _read_existing_memory_files(self) -> Dict[str, str]:
        """Return {file_path: content} for Claude's memory files."""
        result = {}
        if CLAUDE_MD.exists():
            try:
                result[str(CLAUDE_MD)] = CLAUDE_MD.read_text(encoding="utf-8")
            except IOError:
                pass
        return result

    def apply_settings(self, settings: Dict) -> bool:
        claude_settings = settings.get("claude", {})
        raw_json = claude_settings.get("raw_json")
        if not raw_json:
            return False

        # Merge with existing settings
        if CLAUDE_SETTINGS.exists():
            try:
                existing = json.loads(CLAUDE_SETTINGS.read_text(encoding="utf-8"))
                existing.update(raw_json)
                raw_json = existing
            except json.JSONDecodeError:
                pass

        CLAUDE_DIR.mkdir(parents=True, exist_ok=True)
        CLAUDE_SETTINGS.write_text(json.dumps(raw_json, indent=2), encoding="utf-8")
        return True
