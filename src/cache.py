"""Local JSON cache layer for offline-first operation.

All data lives in ~/.apc/cache/*.json. No network, no login required.
"""

import json
from typing import Any, Dict, List

from config import get_cache_dir


def _load_json(filename: str, default: Any = None) -> Any:
    """Load a JSON file from the cache directory."""
    path = get_cache_dir() / filename
    if not path.exists():
        return default if default is not None else []
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return default if default is not None else []


def _save_json(filename: str, data: Any) -> None:
    """Save data as JSON to the cache directory."""
    path = get_cache_dir() / filename
    path.write_text(json.dumps(data, indent=2, default=str))


# --- Skills ---


def load_skills() -> List[Dict]:
    return _load_json("skills.json", [])


def save_skills(skills: List[Dict]) -> None:
    _save_json("skills.json", skills)


# --- MCP Servers ---


def load_mcp_servers() -> List[Dict]:
    return _load_json("mcp_servers.json", [])


def save_mcp_servers(servers: List[Dict]) -> None:
    _save_json("mcp_servers.json", servers)


# --- Memory ---


def load_memory() -> List[Dict]:
    return _load_json("memory.json", [])


def save_memory(entries: List[Dict]) -> None:
    _save_json("memory.json", entries)


# --- Bundle ---


def load_local_bundle() -> Dict:
    """Load the full local bundle from cache."""
    return {
        "skills": load_skills(),
        "mcp_servers": load_mcp_servers(),
        "memory": load_memory(),
    }


# --- Merge helpers (upsert, never delete) ---


def merge_skills(existing: List[Dict], new: List[Dict]) -> List[Dict]:
    """Merge new skills into existing by name. Upsert only."""
    index = {s.get("name", ""): s for s in existing}
    for s in new:
        index[s.get("name", "")] = s
    return list(index.values())


def merge_mcp_servers(existing: List[Dict], new: List[Dict]) -> List[Dict]:
    """Merge new MCP servers into existing by (source_tool, name) key. Upsert only."""
    index = {(_key_mcp(s)): s for s in existing}
    for s in new:
        index[_key_mcp(s)] = s
    return list(index.values())


def merge_memory(existing: List[Dict], new: List[Dict]) -> List[Dict]:
    """Merge new memory entries into existing by id (content-hash). Upsert only.

    Supports both old format (entry_id key) and new format (id key based on
    content hash of source_tool:source_file:content).

    The fallback key is a SHA-256 of the entry content — never str(id(e)) which
    changes every Python process invocation and would cause duplication (#36).
    """
    import hashlib

    def _stable_fallback(e: Dict) -> str:
        """Deterministic key for entries that lack an explicit id field."""
        # Use content + source fields to build a stable hash so that the
        # same entry loaded from disk on two different runs gets the same key.
        raw = "|".join(
            [
                str(e.get("content", "")),
                str(e.get("source_tool", "")),
                str(e.get("source_file", "")),
                str(e.get("category", "")),
            ]
        )
        return "fallback:" + hashlib.sha256(raw.encode()).hexdigest()[:16]

    def _key(e: Dict) -> str:
        # New format uses "id" (content-hash), old format uses "entry_id".
        # Fallback to a stable content hash — never str(id(e)) (#36).
        return e.get("id") or e.get("entry_id") or _stable_fallback(e)

    index = {_key(e): e for e in existing}
    for e in new:
        index[_key(e)] = e
    return list(index.values())


def _key_mcp(s: Dict) -> str:
    """Deduplicate MCP servers by (source_tool, name) composite key.

    Using a composite key preserves the correct source attribution for each
    server.  When the same server name appears in multiple tools (e.g. after
    a full sync), each tool's entry is kept as a distinct record with its
    original source_tool intact instead of the last-collected tool winning
    (#47).
    """
    return f"{s.get('source_tool', '')}:{s.get('name', '')}"
