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

CURSOR_MEMORY_SCHEMA = """
Cursor uses Project Rules in .cursor/rules/ to provide persistent context to its AI.
Rules are markdown files (.md or .mdc). Files with .mdc extension support YAML frontmatter.

FRONTMATTER FORMAT (for .mdc files):
---
description: "Short description of what this rule covers"
globs:                  # omit for rules that aren't file-specific
alwaysApply: true       # true = always included; false = agent decides based on description
---

RULE TYPES (controlled by frontmatter):
- Always Apply (alwaysApply: true): included in every chat session. Use for universal
  preferences like code style, language choices, communication style.
- Agent-decided (alwaysApply: false, description set): included when the agent decides
  the rule is relevant based on its description. Use for domain-specific rules.
- File-scoped (globs set, e.g. "*.py"): included only when matching files are in context.
- Manual (@-mention only): no alwaysApply, no globs, no description.

WHAT TO PUT IN RULES:
- Coding style preferences (language, formatting, naming conventions)
- Architecture decisions and patterns used in the project
- Workflow conventions (testing, git, review process)
- Framework-specific guidance and project structure
- Constraints and things to avoid

WHAT NOT TO PUT IN RULES:
- Personal information (name, timezone) — Cursor is a coding assistant
- Entire style guides — use a linter instead
- Common tool commands (npm, git, pytest) — Cursor already knows these
- Edge cases that rarely apply

GUIDELINES FOR CREATING RULES:
- Keep each rule file focused on ONE topic (e.g., "react-patterns", "api-conventions")
- Keep rules under 500 lines; split large rules into composable files
- Use concrete examples rather than vague guidance
- Reference files with @filename instead of copying their contents
- Use bullet points for individual rules, headings (##) to organize sections
- Name files descriptively: coding-style.mdc, git-workflow.mdc, architecture.mdc

ORGANIZATION:
Rules live in .cursor/rules/ and can be organized in subdirectories:
  .cursor/rules/coding-style.mdc
  .cursor/rules/architecture.mdc
  .cursor/rules/frontend/components.mdc

OUTPUT: Write rules as .mdc files in .cursor/rules/. Organize collected memory into
focused, topic-based rule files. Merge related items from different source tools into
the same rule file when they cover the same topic.
"""


class CursorApplier(BaseApplier):
    SKILL_DIR = CURSOR_RULES_DIR
    TOOL_NAME = "cursor"
    MEMORY_SCHEMA = CURSOR_MEMORY_SCHEMA

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
        self,
        servers: List[Dict],
        secrets: Dict[str, str],
        manifest: ToolManifest,
        override: bool = False,
    ) -> int:
        if CURSOR_MCP_JSON.exists():
            try:
                data = json.loads(CURSOR_MCP_JSON.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                data = {}
        else:
            data = {}

        if override:
            mcp_servers = {}
        else:
            mcp_servers = data.get("mcpServers", {})

            # Prune orphaned MCP servers
            if not manifest.is_first_sync:
                current_names = {s.get("name", "unnamed") for s in servers}
                for orphan in set(manifest.managed_mcp_names()) - current_names:
                    mcp_servers.pop(orphan, None)
                    manifest.remove_mcp_server(orphan)

        count = 0
        for server in servers:
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

    def _read_existing_memory_files(self) -> Dict[str, str]:
        """Return {file_path: content} for Cursor's rule files."""
        result = {}
        if CURSOR_RULES_DIR.exists():
            for path in CURSOR_RULES_DIR.rglob("*.md*"):
                if path.is_file():
                    try:
                        result[str(path)] = path.read_text(encoding="utf-8")
                    except IOError:
                        pass
        return result

