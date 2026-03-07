"""Base applier ABC for all tool-specific appliers."""

import json
import os
import shutil
import sys
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, List, Optional

from appliers.manifest import ToolManifest, _sha256
from ui import spinner, warning

# Prompt template for LLM-based memory sync
SYNC_PROMPT = """You are transforming user memory/context for an AI tool.

TARGET TOOL: {tool_name}
TOOL SCHEMA:
{tool_schema}

EXISTING FILES IN THIS TOOL:
{existing_files}

COLLECTED MEMORY FROM ALL TOOLS:
{collected_memory}

INSTRUCTIONS:
- Merge ALL collected memory into the target tool's format
- Preserve any existing content that is NOT between APC markers
- Follow the tool's native format exactly
- You MUST always output at least one file with the merged result
- Never return an empty array — always produce the full merged file

OUTPUT FORMAT (JSON array):
[
  {{"file_path": "/absolute/path/to/file", "content": "full file content"}}
]

Output valid JSON only, no markdown fencing."""


def _format_existing(existing: Dict[str, str]) -> str:
    """Format existing file contents for the prompt."""
    if not existing:
        return "(no existing files)"
    parts = []
    for path, content in existing.items():
        parts.append(f"--- {path} ---\n{content}\n")
    return "\n".join(parts)


def _format_collected(collected: List[Dict]) -> str:
    """Format collected memory entries for the prompt."""
    if not collected:
        return "(no collected memory)"
    parts = []
    for entry in collected:
        source = f"{entry.get('source_tool', '?')}/{entry.get('source_file', '?')}"
        parts.append(f"--- Source: {source} ---\n{entry.get('content', '')}\n")
    return "\n".join(parts)


class BaseApplier(ABC):
    # Subclasses that support skills should set this to their skill directory
    # and the target name used in frontmatter filtering.
    SKILL_DIR: Optional[Path] = None
    TOOL_NAME: str = ""

    # Subclasses that support LLM-based memory sync should override this
    # with a description of how the tool expects its memory files.
    MEMORY_SCHEMA: str = ""

    # Subclasses MUST override this with the directory the LLM is allowed to
    # write memory files into.  apply_memory_via_llm() rejects any path that
    # does not resolve inside this directory.  Defaults to Path.home() as a
    # minimum guard; narrow it in each applier.
    MEMORY_ALLOWED_BASE: Optional[Path] = None

    def get_manifest(self) -> ToolManifest:
        """Return (or create) the manifest for this tool."""
        return ToolManifest(self.TOOL_NAME)

    @abstractmethod
    def apply_skills(self, skills: List[Dict], manifest: ToolManifest) -> int:
        """Write skills to the tool's config files (copy mode).
        Returns number of skills applied."""
        pass

    def link_skills(self, skills: List[Dict], source_dir: Path, manifest: ToolManifest) -> int:
        """Symlink skill directories from source_dir into the tool's skill directory.

        Creates directory symlinks: <SKILL_DIR>/<name> -> <source_dir>/<name>
        This way the entire skill directory (SKILL.md + supporting files) is linked.
        If the target already exists (file, dir, or broken symlink), it is replaced.
        Returns number of skills linked.
        """
        if self.SKILL_DIR is None:
            return 0

        self.SKILL_DIR.mkdir(parents=True, exist_ok=True)
        count = 0

        for skill in skills:
            raw_name = skill.get("name", "unnamed")
            try:
                from skills import sanitize_skill_name

                name = sanitize_skill_name(raw_name)
            except (ValueError, ImportError):
                warning(f"Skipping skill with invalid name: {raw_name!r}")
                continue

            source = source_dir / name
            if not source.exists():
                continue

            link_path = self.SKILL_DIR / name

            # Remove existing file, directory, or broken symlink
            if link_path.is_symlink():
                link_path.unlink()
            elif link_path.exists():
                if link_path.is_dir():
                    shutil.rmtree(link_path)
                else:
                    link_path.unlink()

            os.symlink(source, link_path)
            manifest.record_linked_skill(
                name,
                link_path=str(link_path.resolve()),
                target=str(source.resolve()),
            )
            count += 1

        return count

    @abstractmethod
    def apply_mcp_servers(
        self,
        servers: List[Dict],
        secrets: Dict[str, str],
        manifest: ToolManifest,
        override: bool = False,
    ) -> int:
        """Write MCP server configurations, injecting resolved secrets.

        If override is True, replace all existing MCP servers with the given list.
        If False (default), merge/append into existing servers.
        Returns number of servers applied.
        """
        pass

    def apply_memory_via_llm(self, collected_memory: List[Dict], manifest: ToolManifest) -> int:
        """Use LLM to transform collected memory into tool-native format.

        Requires an LLM to be configured via 'apc configure'.
        Returns number of files written.
        """
        if not self.MEMORY_SCHEMA:
            return 0

        if not collected_memory:
            return 0

        # Try to import and call LLM
        try:
            from llm_client import call_llm
        except ImportError:
            warning(
                f"LLM not available for memory sync to {self.TOOL_NAME}. "
                "Run 'apc configure' to set up an LLM provider."
            )
            return 0

        # Read existing files
        existing = self._read_existing_memory_files()

        # Build prompt
        prompt = SYNC_PROMPT.format(
            tool_name=self.TOOL_NAME,
            tool_schema=self.MEMORY_SCHEMA,
            existing_files=_format_existing(existing),
            collected_memory=_format_collected(collected_memory),
        )

        try:
            with spinner(f"Syncing memory to {self.TOOL_NAME} via LLM..."):
                response = call_llm(
                    prompt,
                    system="You are a JSON-only function. Return ONLY a valid JSON array. "
                    "Do not wrap in markdown fences. Do not include commentary or explanation.",
                )
        except Exception as e:
            error_msg = str(e)
            if "No LLM model configured" in error_msg:
                warning(
                    f"No LLM configured for memory sync to {self.TOOL_NAME}. "
                    "Run 'apc configure' to set up an LLM provider."
                )
            else:
                warning(f"LLM call failed ({e}), skipping memory sync for {self.TOOL_NAME}")
            return 0

        # Parse structured output
        try:
            # Strip potential markdown fencing
            text = response.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1] if "\n" in text else text[3:]
                if text.endswith("```"):
                    text = text[:-3]
                text = text.strip()
            file_ops = json.loads(text)
        except (json.JSONDecodeError, ValueError) as e:
            warning(f"Failed to parse LLM response for {self.TOOL_NAME}: {e}")
            warning(f"Raw LLM response (first 500 chars): {response[:500]}")
            return 0

        if not isinstance(file_ops, list):
            warning(f"LLM returned non-list type ({type(file_ops).__name__}) for {self.TOOL_NAME}")
            return 0

        if not file_ops:
            warning(f"LLM returned empty file list for {self.TOOL_NAME}")
            warning(f"Raw LLM response: {response[:500]}")
            return 0

        # Determine the allowed write root for this applier.
        # Resolving at call-time so tests can monkeypatch Path.home().
        allowed_base = (self.MEMORY_ALLOWED_BASE or Path.home()).resolve()

        # Write files
        count = 0
        for op in file_ops:
            if not isinstance(op, dict):
                continue
            file_path = op.get("file_path")
            content = op.get("content")
            if not file_path or content is None:
                continue

            # Security: resolve the path (collapses `..`) and assert it lands
            # inside the allowed base directory.  Rejects prompt-injection or
            # hallucinated paths like /etc/cron.d/evil.
            resolved = Path(file_path).resolve()
            if not str(resolved).startswith(str(allowed_base) + "/") and resolved != allowed_base:
                warning(
                    f"[security] Rejecting LLM-suggested write outside allowed path: "
                    f"{file_path!r} (resolved: {resolved}, allowed base: {allowed_base})"
                )
                continue

            resolved.parent.mkdir(parents=True, exist_ok=True)
            resolved.write_text(content, encoding="utf-8")
            manifest.record_memory(
                file_path=str(resolved),
                content=content,
                entry_ids=[e.get("entry_id") or e.get("id", "") for e in collected_memory],
            )
            count += 1

        return count

    def _read_existing_memory_files(self) -> Dict[str, str]:
        """Return {file_path: content} for this tool's memory files.

        Subclasses with MEMORY_SCHEMA should override this.
        """
        return {}

    def prune(
        self,
        current_skill_names: List[str],
        current_mcp_names: List[str],
        manifest: ToolManifest,
    ) -> None:
        """Delete orphaned managed files, preserve user files.

        An item is "orphaned" when it was recorded in the manifest from a
        previous sync but is no longer in the current bundle.
        """
        # -- prune skills -----------------------------------------------------
        current_set = set(current_skill_names)
        for name in manifest.managed_skill_names():
            if name not in current_set:
                entry = manifest._data["skills"].get(name, {})
                file_path = entry.get("file_path")
                if file_path:
                    p = Path(file_path)
                    if p.exists():
                        # Check if user modified the file
                        on_disk_checksum = _sha256(p.read_text(encoding="utf-8"))
                        manifest_checksum = manifest.get_skill_checksum(name)
                        if manifest_checksum and on_disk_checksum != manifest_checksum:
                            print(
                                f"[apc] Warning: skipping prune of modified skill '{name}' "
                                f"({file_path})",
                                file=sys.stderr,
                            )
                            continue
                        p.unlink()
                manifest.remove_skill(name)

        # -- prune linked skills ----------------------------------------------
        current_set_linked = set(current_skill_names)
        for name in manifest.managed_linked_skill_names():
            if name not in current_set_linked:
                entry = manifest._data["linked_skills"].get(name, {})
                link_path = entry.get("link_path")
                if link_path:
                    p = Path(link_path)
                    if p.is_symlink():
                        p.unlink()
                    elif p.exists():
                        if p.is_dir():
                            shutil.rmtree(p)
                        else:
                            p.unlink()
                manifest.remove_linked_skill(name)

        # -- prune MCP servers ------------------------------------------------
        # On first sync we skip MCP pruning — we don't know what's user-added
        if manifest.is_first_sync:
            return

        current_mcp_set = set(current_mcp_names)
        for name in manifest.managed_mcp_names():
            if name not in current_mcp_set:
                manifest.remove_mcp_server(name)
                # Actual removal from the JSON config is handled by each
                # applier's apply_mcp_servers (they should call
                # _prune_mcp_from_config).
