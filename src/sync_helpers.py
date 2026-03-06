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
    """Apply all skills to tools. Returns (copy_count, link_count).

    Two skill sources:
    1. Collected skills (from cache, have body inline) -> apply_skills() copy mode
    2. Installed skills (from ~/.apc/skills/, have SKILL.md files) -> link_skills() symlink mode
    """
    bundle = load_local_bundle()
    collected_skills = bundle["skills"]
    skills_dir = get_skills_dir()
    installed_skills = _discover_installed_skills()

    total_copy = 0
    total_link = 0

    # Build combined name list for pruning
    all_skill_names = list(
        {s.get("name", "unnamed") for s in collected_skills}
        | {s.get("name", "unnamed") for s in installed_skills}
    )

    for tool_name in tool_list:
        try:
            applier = get_applier(tool_name)
            manifest = applier.get_manifest()

            # Per-tool counts (reset each iteration)
            tool_copy = 0
            tool_link = 0

            # Copy collected skills
            if collected_skills:
                tool_copy = applier.apply_skills(collected_skills, manifest)
                total_copy += tool_copy

            # Link installed skills
            if installed_skills:
                tool_link = applier.link_skills(installed_skills, skills_dir, manifest)
                total_link += tool_link

            # Prune orphaned skills (keep MCP names empty — not our concern)
            applier.prune(all_skill_names, [], manifest)
            manifest.save()

            success(f"{tool_name}: {tool_copy} copied, {tool_link} linked")
        except Exception as e:
            error(f"Failed to sync skills to {tool_name}: {e}")

    return total_copy, total_link


def sync_mcp(tool_list: List[str], override: bool = False) -> int:
    """Apply MCP servers from cache to tools. Returns count."""
    mcp_servers = load_mcp_servers()

    if not mcp_servers:
        warning("No MCP servers in cache. Run 'apc collect' first.")
        return 0

    current_mcp_names = [s.get("name", "unnamed") for s in mcp_servers]
    total = 0

    for tool_name in tool_list:
        try:
            applier = get_applier(tool_name)
            manifest = applier.get_manifest()

            secrets = _resolve_all_mcp_secrets(mcp_servers)
            m = applier.apply_mcp_servers(mcp_servers, secrets, manifest, override=override)
            # Prune orphaned MCP servers (keep skill names empty — not our concern)
            applier.prune([], current_mcp_names, manifest)
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

    return total


def sync_all(tool_list: List[str], no_memory: bool = False, override_mcp: bool = False) -> bool:
    """Apply everything (skills + MCP + memory). Used by `apc sync`.

    Returns True if at least one tool was synced successfully, False otherwise.
    """
    bundle = load_local_bundle()
    collected_skills = bundle["skills"]
    mcp_servers = bundle["mcp_servers"]
    memory_entries = bundle["memory"] if not no_memory else []

    skills_dir = get_skills_dir()
    installed_skills = _discover_installed_skills()

    # Build combined name lists for pruning
    all_skill_names = list(
        {s.get("name", "unnamed") for s in collected_skills}
        | {s.get("name", "unnamed") for s in installed_skills}
    )
    current_mcp_names = [s.get("name", "unnamed") for s in mcp_servers]

    total_skills = 0
    total_mcp = 0
    total_memory = 0
    failed_tools = []

    for tool_name in tool_list:
        try:
            applier = get_applier(tool_name)
            manifest = applier.get_manifest()

            # Copy collected skills
            s = applier.apply_skills(collected_skills, manifest)

            # Link installed skills
            lk = applier.link_skills(installed_skills, skills_dir, manifest)

            # MCP servers
            secrets = _resolve_all_mcp_secrets(mcp_servers)
            m = applier.apply_mcp_servers(mcp_servers, secrets, manifest, override=override_mcp)

            # Memory
            mem = 0
            if memory_entries:
                mem = applier.apply_memory_via_llm(memory_entries, manifest)

            # Prune orphans
            applier.prune(all_skill_names, current_mcp_names, manifest)
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

    return any_success
