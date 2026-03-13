"""Shared sync logic for applying cached configs to target tools.

Used by `apc sync`, `apc skill sync`, `apc memory sync`, and `apc mcp sync`.
"""

from typing import Dict, List, Optional, Tuple

from appliers import get_applier
from cache import load_local_bundle, load_mcp_servers
from extractors import detect_installed_tools
from secrets_manager import retrieve_secret
from skills import get_skills_dir
from ui import error, numbered_selection, success, warning


def _resolve_all_mcp_secrets(mcp_servers: List[Dict]) -> Dict[str, str]:
    """Collect all secret_placeholders from MCP servers and resolve from keychain."""
    secrets: Dict[str, str] = {}
    for srv in mcp_servers:
        for key in srv.get("secret_placeholders", []):
            if key not in secrets:
                value = retrieve_secret("local", key)
                if value:
                    secrets[key] = value
    return secrets


def _discover_installed_skills() -> List[dict]:
    """Find installed skills from ~/.apc/skills/ (directories with SKILL.md)."""
    skills_dir = get_skills_dir()
    if not skills_dir.exists():
        return []
    return [
        {"name": d.name}
        for d in sorted(skills_dir.iterdir())
        if d.is_dir() and (d / "SKILL.md").exists()
    ]


def count_installed_skills() -> int:
    """Count installed skills in ~/.apc/skills/. Used for summary display."""
    return len(_discover_installed_skills())


def resolve_target_tools(tools_flag: Optional[str], apply_all: bool) -> List[str]:
    """Resolve target tools from --tools flag, --all flag, or interactive selection."""
    if tools_flag is not None:
        tool_list = [t.strip() for t in tools_flag.split(",") if t.strip()]
        if not tool_list:
            warning("--tools requires at least one tool name (e.g. --tools cursor,gemini)")
            return []
        return tool_list

    if apply_all:
        tool_list = detect_installed_tools()
        if not tool_list:
            warning("No AI tools detected on this machine.")
        return tool_list

    # Interactive selection
    detected = detect_installed_tools()
    if not detected:
        warning("No AI tools detected on this machine.")
        return []

    indices = numbered_selection(detected, "Select tools to apply to")
    return [detected[i] for i in indices]


def sync_skills(tool_list: List[str]) -> Tuple[int, int]:
    """Establish skill links for all tools. Returns (dir_linked_count, skill_linked_count).

    ~/.apc/skills/ is the single source of truth for all skills (installed and collected).
    Three strategies depending on the tool:

    - Dir-symlink (OpenClaw, Claude Code, Gemini, Cursor): replace the tool's skills
      dir with a single symlink → ~/.apc/skills/. Future installs are live immediately.
    - Injection (Windsurf): maintain an APC Skills block in global_rules.md.
    - Per-file symlinks (Copilot): create <name>.instructions.md → SKILL.md symlinks.
    """
    skills_dir = get_skills_dir()

    total_dir = 0

    for tool_name in tool_list:
        try:
            applier = get_applier(tool_name)
            manifest = applier.get_manifest()

            if applier.sync_skills_dir():
                if applier.SKILL_DIR is not None:
                    # Dir-symlink tools: record the symlink target
                    manifest.record_dir_sync(str(applier.SKILL_DIR), str(skills_dir))
                    success(f"{tool_name}: skills dir symlinked → ~/.apc/skills/")
                else:
                    # Tool-specific sync (injection or per-file symlinks)
                    manifest.record_tool_sync(applier.SYNC_METHOD)
                    success(f"{tool_name}: skills synced ({applier.SYNC_METHOD})")
                manifest.save()
                total_dir += 1
            else:
                success(f"{tool_name}: no skills dir configured — skipping")

        except Exception as e:
            error(f"Failed to sync skills to {tool_name}: {e}")

    return total_dir, 0


def sync_mcp(tool_list: List[str], override: bool = False) -> int:
    """Apply MCP servers from cache to tools. Returns count.

    Only servers whose ``source_tool`` matches the target tool (or that have
    no ``source_tool``, meaning they are shared) are synced to each tool.
    This prevents tool-specific MCP servers from being broadcast to every
    tool during a full sync (#44).
    """
    mcp_servers = load_mcp_servers()

    if not mcp_servers:
        warning("No MCP servers in cache. Run 'apc collect' first.")
        return 0

    # Warn once if any server has secrets that will be written to disk (#32)
    servers_with_secrets = [s for s in mcp_servers if s.get("secret_placeholders")]
    if servers_with_secrets:
        warning(
            f"{len(servers_with_secrets)} MCP server(s) have secrets that will be resolved "
            "and written to tool config files (chmod 600). "
            "Ensure those files are excluded from version control."
        )

    total = 0

    for tool_name in tool_list:
        try:
            # Only sync servers that originated from this tool or have no source
            # (i.e. explicitly shared / user-added without a source_tool tag).
            tool_servers = [
                s for s in mcp_servers
                if not s.get("source_tool") or s.get("source_tool") == tool_name
            ]
            current_tool_mcp_names = [s.get("name", "unnamed") for s in tool_servers]

            applier = get_applier(tool_name)
            manifest = applier.get_manifest()

            secrets = _resolve_all_mcp_secrets(tool_servers)
            m = applier.apply_mcp_servers(tool_servers, secrets, manifest, override=override)
            # Prune orphaned MCP servers (keep skill names empty — not our concern)
            applier.prune([], current_tool_mcp_names, manifest)
            manifest.save()

            total += m
            success(f"{tool_name}: {m} MCP servers")
        except Exception as e:
            error(f"Failed to sync MCP to {tool_name}: {e}")

    return total


def sync_memory(tool_list: List[str]) -> int:
    """Apply memory via LLM transformation to tools. Returns count."""
    bundle = load_local_bundle()
    memory_entries = bundle["memory"]

    if not memory_entries:
        warning("No memory entries in cache. Run 'apc collect' or 'apc memory add' first.")
        return 0

    total = 0

    for tool_name in tool_list:
        try:
            applier = get_applier(tool_name)
            manifest = applier.get_manifest()

            mem = applier.apply_memory_via_llm(memory_entries, manifest)
            manifest.save()

            total += mem
            success(f"{tool_name}: {mem} memory files")
        except Exception as e:
            error(f"Failed to sync memory to {tool_name}: {e}")

    # Warn if entries exist but none were synced — likely an LLM config issue (#43)
    if memory_entries and total == 0:
        warning(
            f"\n⚠  {len(memory_entries)} memory entries in cache — 0 synced "
            "(LLM unavailable or not configured). "
            "Run 'apc configure' to enable memory sync."
        )

    return total


def sync_all(tool_list: List[str], no_memory: bool = False, override_mcp: bool = False) -> bool:
    """Apply everything (skills + MCP + memory). Used by `apc sync`.

    Returns True if at least one tool was synced successfully, False otherwise.
    """
    bundle = load_local_bundle()
    mcp_servers = bundle["mcp_servers"]
    memory_entries = bundle["memory"] if not no_memory else []

    skills_dir = get_skills_dir()
    current_mcp_names = [s.get("name", "unnamed") for s in mcp_servers]

    total_skills = 0
    total_mcp = 0
    total_memory = 0
    failed_tools = []

    for tool_name in tool_list:
        try:
            # Only sync servers that originated from this tool or have no source
            # (i.e. explicitly shared / user-added without a source_tool tag).
            tool_servers = [
                s for s in mcp_servers
                if not s.get("source_tool") or s.get("source_tool") == tool_name
            ]
            current_tool_mcp_names = [s.get("name", "unnamed") for s in tool_servers]

            applier = get_applier(tool_name)
            manifest = applier.get_manifest()

            # Establish dir-level symlink: SKILL_DIR → ~/.apc/skills/
            if applier.sync_skills_dir():
                manifest.record_dir_sync(str(applier.SKILL_DIR), str(skills_dir))
            s, lk = (1, 0) if applier.SKILL_DIR is not None else (0, 0)

            # MCP servers (filtered to this tool only — #44)
            secrets = _resolve_all_mcp_secrets(tool_servers)
            m = applier.apply_mcp_servers(tool_servers, secrets, manifest, override=override_mcp)

            # Memory
            mem = 0
            if memory_entries:
                mem = applier.apply_memory_via_llm(memory_entries, manifest)

            # Prune MCP orphans (skills are managed via dir symlink — no pruning needed)
            applier.prune([], current_tool_mcp_names, manifest)
            manifest.save()

            total_skills += s + lk
            total_mcp += m
            total_memory += mem

            success(f"{tool_name}: {s + lk} skills, {m} MCP servers, {mem} memory files")
        except Exception as e:
            error(f"Failed to apply to {tool_name}: {e}")
            failed_tools.append(tool_name)

    any_success = len(failed_tools) < len(tool_list)
    if any_success:
        success(
            f"\nSynced: {total_skills} skills, {total_mcp} MCP servers, {total_memory} memory files"
        )
    elif failed_tools:
        warning(f"\nSync failed for all tools: {', '.join(failed_tools)}")

    # Warn if memory entries exist but none were synced — likely an LLM config issue (#43)
    if memory_entries and total_memory == 0:
        warning(
            f"\n⚠  {len(memory_entries)} memory entries in cache — 0 synced "
            "(LLM unavailable or not configured). "
            "Run 'apc configure' to enable memory sync."
        )

    return any_success
