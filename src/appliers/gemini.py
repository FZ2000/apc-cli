"""Gemini CLI applier — writes MCP server configs and settings."""

import json
from pathlib import Path
from typing import Dict, List

from appliers.base import BaseApplier
from appliers.manifest import ToolManifest

GEMINI_MEMORY_SCHEMA = """
Gemini CLI reads instructions from ~/.gemini/GEMINI.md (global) and ./GEMINI.md (per-project).
This applier targets the GLOBAL file at ~/.gemini/GEMINI.md.

FORMAT:
- Plain Markdown. No special schema or frontmatter required.
- Use headings (##) to organize sections. Use bullet points for rules.
- Free-form — whatever you write is sent as-is to the model as system context.

SPECIAL SECTION:
- "## Gemini Added Memories" — Gemini CLI's save_memory tool appends facts here.
  If this section exists, preserve it and append new items below existing ones.
  If it doesn't exist, create it at the bottom of the file.

IMPORT SYNTAX:
- Gemini supports @path/to/file.md imports on their own line.
  Do NOT use this syntax — write content directly in the file.

WHAT TO PUT IN GEMINI.MD:
- Coding style preferences (language, formatting, naming)
- Architecture decisions and project patterns
- Framework-specific guidance
- Testing conventions and workflow rules
- Constraints and things to avoid

WHAT NOT TO PUT:
- Personal information unrelated to coding (Gemini CLI is a coding assistant)
- Entire style guides — use a linter
- Common tool commands — Gemini already knows these

STRUCTURE EXAMPLE:
  ## Project Context
  - Python 3.12 project using FastAPI
  - PostgreSQL with SQLAlchemy ORM

  ## Coding Standards
  - Use type hints for all functions
  - Prefer composition over inheritance

  ## Testing
  - Use pytest with fixtures
  - Aim for >80% coverage

  ## Gemini Added Memories
  - Prefers TypeScript over JavaScript
  - Uses 2-space indentation for YAML

OUTPUT: Write a single file at the GEMINI.md path. Merge collected memory into
organized sections. Preserve any existing "## Gemini Added Memories" content.
"""


def _gemini_dir() -> Path:
    return Path.home() / ".gemini"


def _gemini_settings() -> Path:
    return Path.home() / ".gemini/settings.json"


def _gemini_md() -> Path:
    return Path.home() / ".gemini/GEMINI.md"


class GeminiApplier(BaseApplier):
    TOOL_NAME = "gemini-cli"
    MEMORY_SCHEMA = GEMINI_MEMORY_SCHEMA

    def apply_skills(self, skills: List[Dict], manifest: ToolManifest) -> int:
        return 0  # Gemini doesn't have a skills format

    def apply_mcp_servers(
        self,
        servers: List[Dict],
        secrets: Dict[str, str],
        manifest: ToolManifest,
        override: bool = False,
    ) -> int:
        if _gemini_settings().exists():
            try:
                data = json.loads(_gemini_settings().read_text(encoding="utf-8"))
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
        _gemini_dir().mkdir(parents=True, exist_ok=True)
        _gemini_settings().write_text(json.dumps(data, indent=2), encoding="utf-8")
        return count

    def _read_existing_memory_files(self) -> Dict[str, str]:
        """Return {file_path: content} for Gemini's memory files."""
        result = {}
        if _gemini_md().exists():
            try:
                result[str(_gemini_md())] = _gemini_md().read_text(encoding="utf-8")
            except IOError:
                pass
        return result
