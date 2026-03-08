"""GitHub Copilot applier — writes instructions and MCP configs."""

import json
import os
import stat
from pathlib import Path
from typing import Dict, List

from appliers.base import BaseApplier
from appliers.manifest import ToolManifest


def _copilot_instructions() -> Path:
    return Path.cwd() / ".github" / "copilot-instructions.md"


def _copilot_instructions_dir() -> Path:
    return Path.cwd() / ".github" / "instructions"


def _copilot_global_instructions_dir() -> Path:
    """User-global instructions dir — applies across all projects via VS Code."""
    return Path.home() / ".github" / "instructions"


def _vscode_mcp_json() -> Path:
    return Path.cwd() / ".vscode" / "mcp.json"


# Module-level aliases kept for backward compatibility with extractors
# (evaluated lazily through the functions above inside the class methods)
COPILOT_INSTRUCTIONS = Path(".github") / "copilot-instructions.md"
COPILOT_INSTRUCTIONS_DIR = Path(".github") / "instructions"
VSCODE_MCP_JSON = Path(".vscode") / "mcp.json"

COPILOT_MEMORY_SCHEMA = """
GitHub Copilot reads custom instructions from two locations:

1. .github/copilot-instructions.md — Repository-wide instructions.
   - Plain Markdown, no frontmatter required.
   - Automatically attached to every Copilot Chat request in the repository.
   - Does NOT affect inline code completion (autocomplete).
   - Use headings (##) to organize sections, bullet points for individual rules.
   - Keep instructions concise and actionable.
   - Example content:
     ## Project Standards
     - Use TypeScript strict mode for all new files
     - Follow PEP 8 for Python files
     - All API endpoints must include error handling

2. .github/instructions/*.instructions.md — Path-specific instructions.
   - Markdown files with YAML frontmatter containing an `applyTo` glob pattern.
   - Only included when Copilot is working on files matching the pattern.
   - Frontmatter format:
     ---
     applyTo: "**/*.py"
     ---
   - Glob patterns: "**/*.py" (all Python files), "src/**/*.ts" (TS under src/),
     "**/*.ts,**/*.tsx" (comma-separated for multiple patterns).
   - Name files descriptively: python.instructions.md, testing.instructions.md.
   - Example:
     ---
     applyTo: "**/*.py"
     ---
     ## Python Conventions
     - Use type hints for all function parameters and return values
     - Use pytest for all test files

WHAT TO PUT IN INSTRUCTIONS:
- Coding style preferences (language, formatting, naming conventions)
- Architecture decisions and patterns
- Framework-specific guidance
- Testing conventions
- Things to avoid

WHAT NOT TO PUT IN INSTRUCTIONS:
- Personal information (name, timezone)
- Entire style guides — use a linter
- Common tool commands — Copilot already knows these

GUIDELINES:
- Put universal project rules in copilot-instructions.md.
- Put language/path-specific rules in .github/instructions/ with applyTo globs.
- Both are combined when both match — they don't replace each other.
- Keep each file focused on one topic.

OUTPUT: Write files as described above. Use copilot-instructions.md for general rules.
Use .github/instructions/<topic>.instructions.md with applyTo frontmatter for
language or path-specific rules.
"""


class CopilotApplier(BaseApplier):
    TOOL_NAME = "github-copilot"
    SYNC_METHOD = "per-file-symlink"
    MEMORY_SCHEMA = COPILOT_MEMORY_SCHEMA

    @property  # type: ignore[override]
    def MEMORY_ALLOWED_BASE(self) -> "Path":  # noqa: N802
        # Copilot writes to .github/ / .vscode/ in the current project directory.
        # Using the resolved CWD ensures a stable absolute path even if the
        # calling process later changes directory (#42).
        return Path.cwd().resolve()

    def _global_instructions_dir(self) -> Path:
        return _copilot_global_instructions_dir()

    def sync_skills_dir(self) -> bool:  # type: ignore[override]
        """Create per-skill .instructions.md symlinks in ~/.github/instructions/.

        Copilot reads each <name>.instructions.md in the instructions dir.
        We symlink: ~/.github/instructions/<name>.instructions.md →
                    ~/.apc/skills/<name>/SKILL.md
        so each skill's content is served as a Copilot instruction.
        """
        from skills import get_skills_dir

        instr_dir = self._global_instructions_dir()
        instr_dir.mkdir(parents=True, exist_ok=True)
        skills_dir = get_skills_dir()

        if not skills_dir.exists():
            return True  # nothing to link yet; will populate on first apc install

        for skill_path in skills_dir.iterdir():
            skill_md = skill_path / "SKILL.md"
            if not skill_md.exists():
                continue
            self._link_skill(skill_path.name, skill_md, instr_dir)

        return True

    def apply_installed_skill(self, name: str) -> bool:  # type: ignore[override]
        """Create a symlink for a newly installed skill."""
        from skills import get_skills_dir

        skill_md = get_skills_dir() / name / "SKILL.md"
        if not skill_md.exists():
            return False
        instr_dir = self._global_instructions_dir()
        instr_dir.mkdir(parents=True, exist_ok=True)
        self._link_skill(name, skill_md, instr_dir)
        return True

    def remove_installed_skill(self, name: str) -> bool:  # type: ignore[override]
        """Remove the dangling .instructions.md symlink for an uninstalled skill."""
        link = self._global_instructions_dir() / f"{name}.instructions.md"
        if link.is_symlink():
            link.unlink()
            return True
        return False

    def unsync_skills(self) -> bool:  # type: ignore[override]
        """Remove all apc-managed .instructions.md symlinks from ~/.github/instructions/."""
        instr_dir = self._global_instructions_dir()
        if not instr_dir.exists():
            return False
        removed = 0
        for link in instr_dir.glob("*.instructions.md"):
            if link.is_symlink():
                link.unlink()
                removed += 1
        return removed > 0

    @staticmethod
    def _link_skill(name: str, skill_md: Path, instr_dir: Path) -> None:
        link_path = instr_dir / f"{name}.instructions.md"
        if link_path.is_symlink() or link_path.exists():
            link_path.unlink()
        os.symlink(skill_md.resolve(), link_path)

    def apply_skills(self, skills: List[Dict], manifest: ToolManifest) -> int:
        count = 0
        instructions = _copilot_instructions()
        for skill in skills:
            if skill.get("name") == "copilot-instructions":
                instructions.parent.mkdir(parents=True, exist_ok=True)
                content = skill.get("body", "")
                instructions.write_text(content, encoding="utf-8")
                manifest.record_skill(
                    "copilot-instructions",
                    file_path=str(instructions.resolve()),
                    content=content,
                )
                count += 1
        return count

    def apply_mcp_servers(
        self,
        servers: List[Dict],
        secrets: Dict[str, str],
        manifest: ToolManifest,
        override: bool = False,
    ) -> int:
        vscode_mcp = _vscode_mcp_json()
        if vscode_mcp.exists():
            try:
                data = json.loads(vscode_mcp.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                data = {}
        else:
            data = {}

        if override:
            vscode_servers = {}
        else:
            vscode_servers = data.get("servers", {})

            # Prune orphaned MCP servers
            if not manifest.is_first_sync:
                current_names = {s.get("name", "unnamed") for s in servers}
                for orphan in set(manifest.managed_mcp_names()) - current_names:
                    vscode_servers.pop(orphan, None)
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
        vscode_mcp.parent.mkdir(parents=True, exist_ok=True)
        vscode_mcp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        # Restrict to owner-only since the file may contain resolved API keys (#32)
        os.chmod(vscode_mcp, stat.S_IRUSR | stat.S_IWUSR)
        return count

    def _read_existing_memory_files(self) -> Dict[str, str]:
        """Return {file_path: content} for Copilot's instruction files."""
        result = {}
        instructions = _copilot_instructions()
        instructions_dir = _copilot_instructions_dir()
        if instructions.exists():
            try:
                result[str(instructions.resolve())] = instructions.read_text(encoding="utf-8")
            except IOError:
                pass
        if instructions_dir.exists():
            for path in instructions_dir.glob("*.instructions.md"):
                if path.is_file():
                    try:
                        result[str(path.resolve())] = path.read_text(encoding="utf-8")
                    except IOError:
                        pass
        return result
