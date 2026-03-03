"""End-to-end tests for APC CLI.

These tests require a running backend. Set RUN_E2E_TESTS=true to enable.
"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from apc.appliers.manifest import ToolManifest


class TestMemoryReconstruction(unittest.TestCase):
    """Test that CLAUDE.md is properly rebuilt from memory entries."""

    def test_rebuild_claude_md(self):
        from apc.appliers.claude import ClaudeApplier

        tmpdir = tempfile.mkdtemp()
        claude_dir = Path(tmpdir) / ".claude"
        claude_dir.mkdir()
        claude_md = claude_dir / "CLAUDE.md"
        manifest = ToolManifest("claude", path=Path(tmpdir) / "manifest.json")

        entries = [
            {"category": "preference", "content": "Prefers TypeScript"},
            {"category": "preference", "content": "Uses 2-space indentation"},
            {"category": "workflow", "content": "Always runs tests before committing"},
            {"category": "constraint", "content": "Never use deprecated APIs"},
        ]

        with (
            patch("apc.appliers.claude.CLAUDE_MD", claude_md),
            patch("apc.appliers.claude.CLAUDE_DIR", claude_dir),
        ):
            applier = ClaudeApplier()
            count = applier.apply_memory(entries, manifest)

        self.assertEqual(count, 4)
        content = claude_md.read_text()

        # Verify structure
        self.assertIn("# AI Context", content)
        self.assertIn("## Preferences", content)
        self.assertIn("- Prefers TypeScript", content)
        self.assertIn("- Uses 2-space indentation", content)
        self.assertIn("## Workflow", content)
        self.assertIn("- Always runs tests before committing", content)
        self.assertIn("## Constraints", content)
        self.assertIn("- Never use deprecated APIs", content)


if __name__ == "__main__":
    unittest.main()
