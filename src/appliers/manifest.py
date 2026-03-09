"""Manifest-based tracking for APC appliers.

Stores per-tool manifests at ~/.apc/manifests/<tool>.json so that APC
knows exactly which items it manages.  On subsequent syncs, only managed
items are touched — everything the user added by hand is left alone.
"""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from config import get_config_dir

SCHEMA_VERSION = 1


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(content: str) -> str:
    return "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest()


def _manifests_dir() -> Path:
    d = get_config_dir() / "manifests"
    d.mkdir(parents=True, exist_ok=True)
    return d


class ToolManifest:
    """Tracks every item APC wrote for a single tool."""

    def __init__(self, tool: str, path: Optional[Path] = None):
        self.tool = tool
        self.path = path or (_manifests_dir() / f"{tool}.json")
        self._data: dict = self._load()

    # -- persistence ----------------------------------------------------------

    def _load(self) -> dict:
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                if data.get("schema_version") == SCHEMA_VERSION:
                    return data
            except (json.JSONDecodeError, KeyError):
                pass
        return self._empty()

    def _empty(self) -> dict:
        return {
            "schema_version": SCHEMA_VERSION,
            "tool": self.tool,
            "last_sync_at": None,
            "skills": {},
            "linked_skills": {},
            "dir_sync": None,
            "mcp_servers": {},
            "memory": {},
        }

    def record_dir_sync(self, skill_dir: str, target: str) -> None:
        """Record a dir-level symlink: skill_dir → target (~/.apc/skills/)."""
        self._data["dir_sync"] = {
            "skill_dir": skill_dir,
            "target": target,
            "sync_method": "dir-symlink",
            "synced_at": _now_iso(),
        }

    def record_tool_sync(self, sync_method: str) -> None:
        """Record a tool-specific sync (injection or per-file symlinks)."""
        self._data["dir_sync"] = {
            "sync_method": sync_method,
            "synced_at": _now_iso(),
        }

    @property
    def sync_method(self) -> str | None:
        """Return the sync method recorded for this tool, or None if never synced."""
        return (self._data.get("dir_sync") or {}).get("sync_method")

    @property
    def is_first_sync(self) -> bool:
        """True when no manifest existed on disk before this run."""
        return self._data.get("last_sync_at") is None

    def save(self) -> None:
        self._data["last_sync_at"] = _now_iso()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._data, indent=2), encoding="utf-8")

    # -- skills ---------------------------------------------------------------

    def managed_skill_names(self) -> List[str]:
        return list(self._data["skills"].keys())

    def record_skill(self, name: str, file_path: str, content: str) -> None:
        self._data["skills"][name] = {
            "file_path": file_path,
            "checksum": _sha256(content),
            "synced_at": _now_iso(),
        }

    def remove_skill(self, name: str) -> None:
        self._data["skills"].pop(name, None)

    def get_skill_checksum(self, name: str) -> Optional[str]:
        entry = self._data["skills"].get(name)
        return entry["checksum"] if entry else None

    # -- linked skills --------------------------------------------------------

    def managed_linked_skill_names(self) -> List[str]:
        return list(self._data["linked_skills"].keys())

    def record_linked_skill(self, name: str, link_path: str, target: str) -> None:
        self._data["linked_skills"][name] = {
            "link_path": link_path,
            "target": target,
            "synced_at": _now_iso(),
        }

    def remove_linked_skill(self, name: str) -> None:
        self._data["linked_skills"].pop(name, None)

    # -- mcp servers ----------------------------------------------------------

    def managed_mcp_names(self) -> List[str]:
        return list(self._data["mcp_servers"].keys())

    def record_mcp_server(self, name: str) -> None:
        self._data["mcp_servers"][name] = {
            "synced_at": _now_iso(),
        }

    def remove_mcp_server(self, name: str) -> None:
        self._data["mcp_servers"].pop(name, None)

    # -- memory ---------------------------------------------------------------

    def memory_entry_ids(self) -> List[str]:
        return list(self._data["memory"].get("entry_ids", []))

    def record_memory(
        self,
        file_path: str,
        entry_ids: List[str],
        content: str,
        section_marker: str = "## APC Synced Context",
    ) -> None:
        self._data["memory"] = {
            "section_marker": section_marker,
            "file_path": file_path,
            "entry_ids": entry_ids,
            "checksum": _sha256(content),
            "synced_at": _now_iso(),
        }

    def clear_memory(self) -> None:
        self._data["memory"] = {}
