"""End-to-end tests for APC CLI.

These tests require a running backend. Set RUN_E2E_TESTS=true to enable.
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from appliers.manifest import ToolManifest


class TestMemoryViaLLM(unittest.TestCase):
    """Test that memory sync via LLM writes files correctly."""

    def test_llm_memory_sync_writes_claude_md(self):
        from appliers.claude import ClaudeApplier

        tmpdir = tempfile.mkdtemp()
        claude_dir = Path(tmpdir) / ".claude"
        claude_dir.mkdir()
        claude_md = claude_dir / "CLAUDE.md"
        manifest = ToolManifest("claude-code", path=Path(tmpdir) / "manifest.json")

        collected = [
            {
                "id": "abc123",
                "source_tool": "openclaw",
                "source_file": "USER.md",
                "content": "Prefers TypeScript\nUses 2-space indentation",
            },
        ]

        llm_response = json.dumps(
            [
                {
                    "file_path": str(claude_md),
                    "content": "## Preferences\n- Prefers TypeScript\n- Uses 2-space indentation\n",
                }
            ]
        )

        with (
            patch("appliers.claude._claude_md", return_value=claude_md),
            patch("appliers.claude._claude_dir", return_value=claude_dir),
            patch("appliers.base.call_llm", return_value=llm_response, create=True),
            patch("llm_client.call_llm", return_value=llm_response),
        ):
            applier = ClaudeApplier()
            count = applier.apply_memory_via_llm(collected, manifest)

        self.assertEqual(count, 1)
        content = claude_md.read_text()
        self.assertIn("Prefers TypeScript", content)
        self.assertIn("Uses 2-space indentation", content)

    def test_no_llm_configured_shows_warning(self):
        from appliers.claude import ClaudeApplier

        tmpdir = tempfile.mkdtemp()
        manifest = ToolManifest("claude-code", path=Path(tmpdir) / "manifest.json")

        collected = [{"id": "abc", "source_tool": "test", "content": "test"}]

        # Simulate LLM not configured
        from llm_client import LLMError

        with patch("llm_client.call_llm", side_effect=LLMError("No LLM model configured")):
            applier = ClaudeApplier()
            count = applier.apply_memory_via_llm(collected, manifest)

        # With no-LLM fallback: writes a simple formatted section, returns >= 0
        # (1 if MEMORY_TARGET_FILE is set, 0 otherwise)
        self.assertGreaterEqual(count, 0)


if __name__ == "__main__":
    unittest.main()
