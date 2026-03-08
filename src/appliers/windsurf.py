"""Windsurf (Codeium) applier — writes MCP server configs and rules."""

import json
import os
import stat
from pathlib import Path
from typing import Dict, List

from appliers.base import BaseApplier
from appliers.manifest import ToolManifest

WINDSURF_RULES_DIR = Path(".windsurf") / "rules"

WINDSURF_MEMORY_SCHEMA = """
Windsurf (Cascade) reads rules from two locations:

1. ~/.codeium/windsurf/memories/global_rules.md — Global rules for all projects.
   - Plain Markdown file. No YAML frontmatter.
   - Applied to every workspace/project automatically ("Always On").
   - Use for personal coding preferences and universal standards.

2. .windsurf/rules/*.md — Project-specific rules.
   - Plain Markdown files (one per topic). No YAML frontmatter.
   - Windsurf does NOT use frontmatter for metadata (unlike Cursor).
   - Activation mode (Always On, Manual, Model Decision, Glob-based) is
     configured through the Windsurf GUI, not in the file itself.
   - Name files descriptively: general.md, api-conventions.md, testing.md.
   - These files are committed to git and shared with the team.

FORMAT:
- Plain Markdown. Use headings (##) to organize sections.
- Use bullet points for individual rules.
- Keep each file under 12,000 characters (Windsurf truncates beyond this).
- XML tags (e.g., <coding_guidelines>) can be used for semantic grouping.
- Keep rules concise and specific — vague guidance is less effective.

WHAT TO PUT IN RULES:
- Coding style preferences (language, formatting, naming conventions)
- Architecture decisions and patterns
- Framework-specific guidance and project structure
- Testing conventions and workflow rules
- Build system and tooling preferences
- Constraints and things to avoid

WHAT NOT TO PUT:
- Personal information unrelated to coding
- Entire style guides — use a linter
- Common tool commands — Cascade already knows these

STRUCTURE EXAMPLE (global_rules.md):
  ## Coding Standards
  - Use early returns when possible
  - Always add documentation for new functions
  - Prefer simple solutions over complex ones

  ## Architecture
  - Follow existing project patterns and conventions
  - Prefer composition over inheritance

STRUCTURE EXAMPLE (.windsurf/rules/python.md):
  ## Python Conventions
  - Use type hints for all function parameters
  - Use pytest with fixtures for testing
  - Follow PEP 8 naming conventions

NOTE: There is also a legacy .windsurfrules file at the project root (single file,
plain text or numbered list). This format still works but is deprecated in favor
of .windsurf/rules/*.md. Do NOT create .windsurfrules — use the rules directory.

OUTPUT: Write global_rules.md for universal preferences. Write .windsurf/rules/<topic>.md
files for project-specific or topic-specific rules. Merge related items from different
source tools into the same rule file when they cover the same topic.
"""


def _windsurf_dir() -> Path:
    return Path.home() / ".codeium/windsurf"


def _windsurf_mcp_config() -> Path:
    return Path.home() / ".codeium/windsurf/mcp_config.json"


def _windsurf_memories_dir() -> Path:
    return Path.home() / ".codeium/windsurf/memories"


def _windsurf_global_rules() -> Path:
    return Path.home() / ".codeium/windsurf/memories/global_rules.md"


class WindsurfApplier(BaseApplier):
    TOOL_NAME = "windsurf"
    MEMORY_SCHEMA = WINDSURF_MEMORY_SCHEMA

    @property  # type: ignore[override]
    def MEMORY_ALLOWED_BASE(self) -> "Path":  # noqa: N802
        return _windsurf_dir()

    def apply_skills(self, skills: List[Dict], manifest: ToolManifest) -> int:
        return 0

    def apply_mcp_servers(
        self,
        servers: List[Dict],
        secrets: Dict[str, str],
        manifest: ToolManifest,
        override: bool = False,
    ) -> int:
        if _windsurf_mcp_config().exists():
            try:
                data = json.loads(_windsurf_mcp_config().read_text(encoding="utf-8"))
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
        _windsurf_dir().mkdir(parents=True, exist_ok=True)
        mcp_config_path = _windsurf_mcp_config()
        mcp_config_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        # Restrict to owner-only since the file may contain resolved API keys (#32)
        os.chmod(mcp_config_path, stat.S_IRUSR | stat.S_IWUSR)
        return count

    def _read_existing_memory_files(self) -> Dict[str, str]:
        """Return {file_path: content} for Windsurf's rule/memory files."""
        result = {}
        # Global rules
        if _windsurf_global_rules().exists():
            try:
                result[str(_windsurf_global_rules())] = _windsurf_global_rules().read_text(
                    encoding="utf-8"
                )
            except IOError:
                pass
        # Project rules
        if WINDSURF_RULES_DIR.exists():
            for path in WINDSURF_RULES_DIR.glob("*.md"):
                if path.is_file():
                    try:
                        result[str(path)] = path.read_text(encoding="utf-8")
                    except IOError:
                        pass
        return result
