"""Applier registry — maps tool names to specialized appliers."""

import importlib

from appliers.base import BaseApplier

_SPECIALIZED = {
    "claude-code": "appliers.claude:ClaudeApplier",
    "cursor": "appliers.cursor:CursorApplier",
    "gemini-cli": "appliers.gemini:GeminiApplier",
    "github-copilot": "appliers.copilot:CopilotApplier",
    "windsurf": "appliers.windsurf:WindsurfApplier",
    "openclaw": "appliers.openclaw:OpenClawApplier",
}

_ALIASES = {
    "claude": "claude-code",
    "gemini": "gemini-cli",
    "copilot": "github-copilot",
}


def get_applier(tool_name: str) -> BaseApplier:
    """Get the applier for a supported tool.

    Raises ValueError if the tool is not supported.
    """
    resolved = _ALIASES.get(tool_name, tool_name)

    if resolved not in _SPECIALIZED:
        raise ValueError(f"Unsupported tool: {tool_name}")

    module_path, cls_name = _SPECIALIZED[resolved].split(":")
    mod = importlib.import_module(module_path)
    cls = getattr(mod, cls_name)
    return cls()


def supported_tools() -> list[str]:
    """Return list of all supported tool names."""
    return list(_SPECIALIZED.keys())
