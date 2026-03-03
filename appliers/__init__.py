"""Applier registry."""

from appliers.base import BaseApplier


def get_applier(tool_name: str) -> BaseApplier:
    """Get the appropriate applier for a tool."""
    from appliers.claude import ClaudeApplier
    from appliers.copilot import CopilotApplier
    from appliers.cursor import CursorApplier
    from appliers.gemini import GeminiApplier
    from appliers.openclaw import OpenClawApplier
    from appliers.windsurf import WindsurfApplier

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
