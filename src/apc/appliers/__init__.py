"""Applier registry."""

from apc.appliers.base import BaseApplier


def get_applier(tool_name: str) -> BaseApplier:
    """Get the appropriate applier for a tool."""
    from apc.appliers.claude import ClaudeApplier
    from apc.appliers.copilot import CopilotApplier
    from apc.appliers.cursor import CursorApplier
    from apc.appliers.gemini import GeminiApplier
    from apc.appliers.openclaw import OpenClawApplier
    from apc.appliers.windsurf import WindsurfApplier

    appliers = {
        "claude": ClaudeApplier,
        "cursor": CursorApplier,
        "gemini": GeminiApplier,
        "copilot": CopilotApplier,
        "windsurf": WindsurfApplier,
        "openclaw": OpenClawApplier,
    }
    cls = appliers.get(tool_name)
    if not cls:
        raise ValueError(f"Unknown tool: {tool_name}")
    return cls()
