"""OpenClaw applier — writes skills, memory, settings."""

import json
from pathlib import Path
from typing import Dict, List

from appliers.base import BaseApplier
from appliers.manifest import ToolManifest
from appliers.memory_section import write_memory_file
from frontmatter_parser import render_frontmatter

OPENCLAW_DIR = Path.home() / ".openclaw"
OPENCLAW_CONFIG = OPENCLAW_DIR / "openclaw.json"
OPENCLAW_SKILLS_DIR = OPENCLAW_DIR / "skills"
OPENCLAW_WORKSPACE = OPENCLAW_DIR / "workspace"
OPENCLAW_USER_MD = OPENCLAW_WORKSPACE / "USER.md"
OPENCLAW_MEMORY_MD = OPENCLAW_WORKSPACE / "MEMORY.md"
OPENCLAW_IDENTITY_MD = OPENCLAW_WORKSPACE / "IDENTITY.md"
OPENCLAW_SOUL_MD = OPENCLAW_WORKSPACE / "SOUL.md"
OPENCLAW_TOOLS_MD = OPENCLAW_WORKSPACE / "TOOLS.md"

# Keys that are safe to merge into openclaw.json from synced settings.
# OpenClaw uses strict schema validation — unknown keys crash the gateway.
_SAFE_SETTINGS_KEYS = {
    "agents",
    "commands",
    "hooks",
    "messages",
    "session",
    "channels",
    "skills",
    "plugins",
    "memory",
    "sandbox",
    "env",
}

CATEGORY_HEADERS = {
    "personal": "About You",
    "preference": "Preferences",
    "workflow": "Workflow",
    "project_context": "Project Context",
    "tool_config": "Tool Configuration",
    "constraint": "Constraints",
}

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


class OpenClawApplier(BaseApplier):
    SKILL_DIR = OPENCLAW_SKILLS_DIR
    TOOL_NAME = "openclaw"
    MEMORY_SCHEMA = OPENCLAW_MEMORY_SCHEMA

    def apply_skills(self, skills: List[Dict], manifest: ToolManifest) -> int:
        OPENCLAW_SKILLS_DIR.mkdir(parents=True, exist_ok=True)
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
            skill_dir = OPENCLAW_SKILLS_DIR / name
            skill_dir.mkdir(parents=True, exist_ok=True)
            path = skill_dir / "SKILL.md"
            path.write_text(content, encoding="utf-8")
            manifest.record_skill(name, file_path=str(path), content=content)
            count += 1
        return count

    def apply_mcp_servers(
        self, servers: List[Dict], secrets: Dict[str, str], manifest: ToolManifest
    ) -> int:
        # OpenClaw does not support MCP servers — it uses its own skill/tool system
        return 0

    def apply_memory(self, entries: List[Dict], manifest: ToolManifest) -> int:
        """Legacy direct apply (used as fallback when LLM is not configured)."""
        if not entries:
            return 0

        OPENCLAW_WORKSPACE.mkdir(parents=True, exist_ok=True)

        inner = write_memory_file(
            OPENCLAW_USER_MD,
            entries,
            CATEGORY_HEADERS,
            title="USER.md - About Your Human",
        )

        entry_ids = [e.get("entry_id") or e.get("id", "") for e in entries if e.get("content")]
        manifest.record_memory(
            file_path=str(OPENCLAW_USER_MD),
            entry_ids=entry_ids,
            content=inner,
        )

        return sum(1 for e in entries if e.get("content"))

    def _read_existing_memory_files(self) -> Dict[str, str]:
        """Return {file_path: content} for OpenClaw's memory files."""
        result = {}
        for path in [
            OPENCLAW_USER_MD,
            OPENCLAW_MEMORY_MD,
            OPENCLAW_IDENTITY_MD,
            OPENCLAW_SOUL_MD,
            OPENCLAW_TOOLS_MD,
        ]:
            if path.exists():
                try:
                    result[str(path)] = path.read_text(encoding="utf-8")
                except IOError:
                    pass
        return result

    def apply_settings(self, settings: Dict) -> bool:
        openclaw_settings = settings.get("openclaw", {})
        raw_json = openclaw_settings.get("raw_json")
        if not raw_json:
            return False

        if OPENCLAW_CONFIG.exists():
            try:
                existing = json.loads(OPENCLAW_CONFIG.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                existing = {}
        else:
            existing = {}

        # Only merge keys that OpenClaw's schema recognises
        for key, value in raw_json.items():
            if key in _SAFE_SETTINGS_KEYS:
                existing[key] = value

        OPENCLAW_DIR.mkdir(parents=True, exist_ok=True)
        OPENCLAW_CONFIG.write_text(json.dumps(existing, indent=2), encoding="utf-8")
        return True
