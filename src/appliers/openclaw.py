"""OpenClaw applier — writes skills, memory, settings."""

from pathlib import Path
from typing import Dict, List

from appliers.base import BaseApplier
from appliers.manifest import ToolManifest
from frontmatter_parser import render_frontmatter

OPENCLAW_MEMORY_SCHEMA = """
OpenClaw uses these files in ~/.openclaw/workspace/:
1. USER.md — Personal context about the user (name, timezone, pronouns, preferences).
   Uses bold labels: **What to call them:** Name, **Timezone:** TZ, **Pronouns:** they/them
   Sections: ## Personal, ## Preferences, ## Workflow, etc.
2. MEMORY.md — Long-term curated memory (AI observations about the user).
   Free-form markdown with bullet points.
3. IDENTITY.md — Assistant persona definition (name, creature type, vibe, emoji, avatar).
4. SOUL.md — Core values and working style principles for the assistant.
5. TOOLS.md — User's infrastructure config (SSH hosts, devices, TTS voices, etc.).
"""


def _openclaw_dir() -> Path:
    return Path.home() / ".openclaw"


def _openclaw_skills_dir() -> Path:
    return Path.home() / ".openclaw/skills"


def _openclaw_workspace() -> Path:
    return Path.home() / ".openclaw/workspace"


def _openclaw_user_md() -> Path:
    return Path.home() / ".openclaw/workspace/USER.md"


def _openclaw_memory_md() -> Path:
    return Path.home() / ".openclaw/workspace/MEMORY.md"


def _openclaw_identity_md() -> Path:
    return Path.home() / ".openclaw/workspace/IDENTITY.md"


def _openclaw_soul_md() -> Path:
    return Path.home() / ".openclaw/workspace/SOUL.md"


def _openclaw_tools_md() -> Path:
    return Path.home() / ".openclaw/workspace/TOOLS.md"


class OpenClawApplier(BaseApplier):
    @property
    def SKILL_DIR(self):
        return getattr(self, "_skill_dir_override", None) or _openclaw_skills_dir()

    @SKILL_DIR.setter
    def SKILL_DIR(self, value):
        self._skill_dir_override = value

    TOOL_NAME = "openclaw"
    MEMORY_SCHEMA = OPENCLAW_MEMORY_SCHEMA

    @property  # type: ignore[override]
    def MEMORY_ALLOWED_BASE(self) -> "Path":  # noqa: N802
        return _openclaw_workspace()

    def apply_skills(self, skills: List[Dict], manifest: ToolManifest) -> int:
        _openclaw_skills_dir().mkdir(parents=True, exist_ok=True)
        count = 0
        for skill in skills:
            name = skill.get("name", "unnamed")
            metadata = {"name": name}
            if skill.get("description"):
                metadata["description"] = skill["description"]
            if skill.get("tags"):
                metadata["tags"] = skill["tags"]
            if skill.get("version"):
                metadata["version"] = skill["version"]

            content = render_frontmatter(metadata, skill.get("body", ""))

            # OpenClaw uses directory-based skills: <name>/SKILL.md
            skill_dir = _openclaw_skills_dir() / name
            # If a previous `apc install` left a symlink here, remove it before
            # calling mkdir — Path.mkdir(exist_ok=True) raises FileExistsError
            # (errno 17) on symlinks even when the link points to a directory (#33).
            if skill_dir.is_symlink():
                skill_dir.unlink()
            skill_dir.mkdir(parents=True, exist_ok=True)
            path = skill_dir / "SKILL.md"
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
        # OpenClaw does not support MCP servers — it uses its own skill/tool system
        return 0

    def _read_existing_memory_files(self) -> Dict[str, str]:
        """Return {file_path: content} for OpenClaw's memory files."""
        result = {}
        for path in [
            _openclaw_user_md(),
            _openclaw_memory_md(),
            _openclaw_identity_md(),
            _openclaw_soul_md(),
            _openclaw_tools_md(),
        ]:
            if path.exists():
                try:
                    result[str(path)] = path.read_text(encoding="utf-8")
                except IOError:
                    pass
        return result
