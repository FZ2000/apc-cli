"""Extractor registry — maps tool names to specialized extractors."""

import importlib
from pathlib import Path
from typing import List

from extractors.base import BaseExtractor

_SPECIALIZED = {
    "claude-code": "extractors.claude:ClaudeExtractor",
    "cursor": "extractors.cursor:CursorExtractor",
    "gemini-cli": "extractors.gemini:GeminiExtractor",
    "github-copilot": "extractors.copilot:CopilotExtractor",
    "windsurf": "extractors.windsurf:WindsurfExtractor",
    "openclaw": "extractors.openclaw:OpenClawExtractor",
}

# Filesystem paths used to detect if a tool is installed
_DETECT_PATHS = {
    "claude-code": [Path.home() / ".claude", Path.home() / ".claude.json"],
    "cursor": [Path.home() / ".cursor"],
    "gemini-cli": [Path.home() / ".gemini"],
    "github-copilot": [Path.home() / ".copilot", Path.home() / ".github"],
    "windsurf": [Path.home() / ".codeium" / "windsurf"],
    "openclaw": [Path.home() / ".openclaw"],
}


def detect_installed_tools() -> List[str]:
    """Detect which supported AI tools are installed on this machine."""
    found = []
    for name, paths in _DETECT_PATHS.items():
        if any(p.exists() for p in paths):
            found.append(name)
    return sorted(found)


def get_extractor(tool_name: str) -> BaseExtractor:
    """Get the extractor for a supported tool.

    Raises ValueError if the tool is not supported.
    """
    if tool_name not in _SPECIALIZED:
        raise ValueError(f"Unsupported tool: {tool_name!r}. Valid tools: {', '.join(_SPECIALIZED)}")

    module_path, cls_name = _SPECIALIZED[tool_name].split(":")
    mod = importlib.import_module(module_path)
    cls = getattr(mod, cls_name)
    return cls()
