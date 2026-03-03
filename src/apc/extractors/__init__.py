"""Tool auto-detection and extractor registry."""

from pathlib import Path
from typing import List

from apc.extractors.base import BaseExtractor

TOOL_MARKERS = {
    "claude": [Path.home() / ".claude", Path.home() / ".claude.json"],
    "cursor": [Path.home() / ".cursor"],
    "gemini": [Path.home() / ".gemini"],
    "copilot": [Path(".github") / "copilot-instructions.md"],
    "windsurf": [Path.home() / ".codeium" / "windsurf"],
    "openclaw": [Path.home() / ".openclaw"],
}


def detect_installed_tools() -> List[str]:
    """Detect which AI tools are installed on this machine."""
    return [name for name, markers in TOOL_MARKERS.items() if any(m.exists() for m in markers)]


def get_extractor(tool_name: str) -> BaseExtractor:
    """Get the appropriate extractor for a tool."""
    from apc.extractors.claude import ClaudeExtractor
    from apc.extractors.copilot import CopilotExtractor
    from apc.extractors.cursor import CursorExtractor
    from apc.extractors.gemini import GeminiExtractor
    from apc.extractors.openclaw import OpenClawExtractor
    from apc.extractors.windsurf import WindsurfExtractor

    extractors = {
        "claude": ClaudeExtractor,
        "cursor": CursorExtractor,
        "gemini": GeminiExtractor,
        "copilot": CopilotExtractor,
        "windsurf": WindsurfExtractor,
        "openclaw": OpenClawExtractor,
    }
    cls = extractors.get(tool_name)
    if not cls:
        raise ValueError(f"Unknown tool: {tool_name}")
    return cls()
