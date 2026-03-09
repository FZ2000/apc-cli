"""Unit tests for tool appliers."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from appliers.manifest import ToolManifest
from appliers.memory_section import BEGIN_MARKER, END_MARKER  # noqa: F401


class TestClaudeApplier(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.claude_dir = Path(self.tmpdir) / ".claude"
        self.claude_dir.mkdir()
        self.commands_dir = self.claude_dir / "commands"
        self.commands_dir.mkdir()
        self.claude_json = Path(self.tmpdir) / ".claude.json"
        self.claude_md = self.claude_dir / "CLAUDE.md"
        self.claude_settings = self.claude_dir / "settings.json"
        self.manifest_path = Path(self.tmpdir) / "manifest.json"

    def _manifest(self) -> ToolManifest:
        return ToolManifest("claude-code", path=self.manifest_path)

    def test_apply_skills(self):
        skills = [
            {
                "name": "test-skill",
                "description": "A test",
                "body": "# Instructions\nDo things.",
                "tags": ["test"],
                "targets": [],
                "version": "1.0.0",
            }
        ]
        manifest = self._manifest()

        with patch("appliers.claude._claude_commands_dir", return_value=self.commands_dir):
            from appliers.claude import ClaudeApplier

            applier = ClaudeApplier()
            count = applier.apply_skills(skills, manifest)

        self.assertEqual(count, 1)
        skill_file = self.commands_dir / "test-skill.md"
        self.assertTrue(skill_file.exists())
        content = skill_file.read_text()
        self.assertIn("Do things.", content)
        # Manifest should track the skill
        self.assertIn("test-skill", manifest.managed_skill_names())

    def test_apply_mcp_servers(self):
        servers = [
            {
                "name": "filesystem",
                "transport": "stdio",
                "command": "npx",
                "args": ["-y", "@mcp/server"],
                "env": {"TOKEN": "${TOKEN}"},
                "targets": [],
            }
        ]
        secrets = {"TOKEN": "actual_value"}
        manifest = self._manifest()

        with patch("appliers.claude._claude_json", return_value=self.claude_json):
            from appliers.claude import ClaudeApplier

            applier = ClaudeApplier()
            count = applier.apply_mcp_servers(servers, secrets, manifest)

        self.assertEqual(count, 1)
        data = json.loads(self.claude_json.read_text())
        self.assertIn("filesystem", data["mcpServers"])
        self.assertEqual(data["mcpServers"]["filesystem"]["env"]["TOKEN"], "actual_value")
        # Manifest should track the MCP server
        self.assertIn("filesystem", manifest.managed_mcp_names())

    def test_apply_mcp_servers_merges_existing(self):
        # Pre-existing config
        existing = {"mcpServers": {"existing-server": {"type": "stdio", "command": "old"}}}
        self.claude_json.write_text(json.dumps(existing))

        servers = [
            {
                "name": "new-server",
                "transport": "stdio",
                "command": "new",
                "args": [],
                "env": {},
                "targets": [],
            }
        ]
        manifest = self._manifest()

        with patch("appliers.claude._claude_json", return_value=self.claude_json):
            from appliers.claude import ClaudeApplier

            applier = ClaudeApplier()
            count = applier.apply_mcp_servers(servers, {}, manifest)

        self.assertEqual(count, 1)
        data = json.loads(self.claude_json.read_text())
        self.assertIn("existing-server", data["mcpServers"])
        self.assertIn("new-server", data["mcpServers"])

    def test_apply_memory_via_llm(self):
        """LLM-based memory sync writes files from LLM response."""
        collected = [
            {
                "id": "abc123",
                "source_tool": "openclaw",
                "source_file": "USER.md",
                "content": "# USER.md\n- **Name:** Zhiyan\n",
            }
        ]
        manifest = self._manifest()

        # Mock LLM response
        llm_response = json.dumps(
            [
                {
                    "file_path": str(self.claude_md),
                    "content": "# AI Context\n\n## Preferences\n- Prefers TypeScript\n",
                }
            ]
        )

        with (
            patch("appliers.claude._claude_md", return_value=self.claude_md),
            patch("appliers.claude._claude_dir", return_value=self.claude_dir),
            patch("llm_client.call_llm", return_value=llm_response),
        ):
            from appliers.claude import ClaudeApplier

            applier = ClaudeApplier()
            count = applier.apply_memory_via_llm(collected, manifest)

        self.assertEqual(count, 1)
        content = self.claude_md.read_text()
        self.assertIn("Prefers TypeScript", content)

    def test_apply_memory_via_llm_returns_negative_on_failure(self):
        """When LLM fails, returns -1 to signal failure (not 0 which looks like success)."""
        collected = [
            {"id": "abc", "source_tool": "openclaw", "content": "test"},
        ]
        manifest = self._manifest()

        with (
            patch("appliers.claude._claude_md", return_value=self.claude_md),
            patch("llm_client.call_llm", side_effect=Exception("No LLM")),
        ):
            from appliers.claude import ClaudeApplier

            applier = ClaudeApplier()
            count = applier.apply_memory_via_llm(collected, manifest)

        self.assertEqual(count, -1)  # -1 signals LLM failure, not zero-files-written

    def test_apply_memory_via_llm_handles_markdown_fencing(self):
        """LLM sometimes wraps response in markdown code blocks."""
        collected = [{"id": "abc", "source_tool": "test", "content": "test"}]
        manifest = self._manifest()

        llm_response = (
            "```json\n"
            + json.dumps(
                [
                    {
                        "file_path": str(self.claude_md),
                        "content": "# From LLM\n",
                    }
                ]
            )
            + "\n```"
        )

        with (
            patch("appliers.claude._claude_md", return_value=self.claude_md),
            patch("appliers.claude._claude_dir", return_value=self.claude_dir),
            patch("llm_client.call_llm", return_value=llm_response),
        ):
            from appliers.claude import ClaudeApplier

            applier = ClaudeApplier()
            count = applier.apply_memory_via_llm(collected, manifest)

        self.assertEqual(count, 1)
        self.assertIn("From LLM", self.claude_md.read_text())

    def test_apply_memory_via_llm_no_schema_returns_zero(self):
        """Appliers without MEMORY_SCHEMA should return 0."""
        from appliers.base import BaseApplier

        class NoSchemaApplier(BaseApplier):
            TOOL_NAME = "noop"
            MEMORY_SCHEMA = ""

            def apply_skills(self, skills, manifest):
                return 0

            def apply_mcp_servers(self, servers, secrets, manifest):
                return 0

            def apply_settings(self, settings):
                return False

        applier = NoSchemaApplier()
        manifest = self._manifest()
        collected = [{"id": "abc", "content": "test"}]

        count = applier.apply_memory_via_llm(collected, manifest)
        self.assertEqual(count, 0)

    def test_apply_mcp_prunes_orphaned_server(self):
        """MCP servers removed from bundle should be pruned from config."""
        # First sync: add two servers
        manifest = self._manifest()

        servers_v1 = [
            {
                "name": "fs",
                "transport": "stdio",
                "command": "fs-cmd",
                "args": [],
                "env": {},
                "targets": [],
            },
            {
                "name": "github",
                "transport": "stdio",
                "command": "gh-cmd",
                "args": [],
                "env": {},
                "targets": [],
            },
        ]

        with patch("appliers.claude._claude_json", return_value=self.claude_json):
            from appliers.claude import ClaudeApplier

            applier = ClaudeApplier()
            applier.apply_mcp_servers(servers_v1, {}, manifest)
        manifest.save()

        # Second sync: only "fs" remains
        manifest2 = ToolManifest("claude-code", path=self.manifest_path)
        servers_v2 = [
            {
                "name": "fs",
                "transport": "stdio",
                "command": "fs-cmd",
                "args": [],
                "env": {},
                "targets": [],
            },
        ]

        with patch("appliers.claude._claude_json", return_value=self.claude_json):
            applier = ClaudeApplier()
            applier.apply_mcp_servers(servers_v2, {}, manifest2)

        data = json.loads(self.claude_json.read_text())
        self.assertIn("fs", data["mcpServers"])
        self.assertNotIn("github", data["mcpServers"])

    def test_prune_removes_orphaned_skill(self):
        """Skills removed from bundle should be deleted from disk."""
        # Create a managed skill file
        skill_file = self.commands_dir / "old-skill.md"
        skill_content = "# Old skill"
        skill_file.write_text(skill_content, encoding="utf-8")

        manifest = self._manifest()
        manifest.record_skill("old-skill", file_path=str(skill_file), content=skill_content)

        with patch("appliers.claude._claude_commands_dir", return_value=self.commands_dir):
            from appliers.claude import ClaudeApplier

            applier = ClaudeApplier()
            # Current skills don't include "old-skill"
            applier.prune(["new-skill"], [], manifest)

        self.assertFalse(skill_file.exists())
        self.assertNotIn("old-skill", manifest.managed_skill_names())

    def test_prune_skips_modified_skill(self):
        """Skills modified by user since last sync should not be pruned."""
        skill_file = self.commands_dir / "edited.md"
        original_content = "# Original"
        skill_file.write_text(original_content, encoding="utf-8")

        manifest = self._manifest()
        manifest.record_skill("edited", file_path=str(skill_file), content=original_content)

        # User edits the file
        skill_file.write_text("# User modified this!", encoding="utf-8")

        with patch("appliers.claude._claude_commands_dir", return_value=self.commands_dir):
            from appliers.claude import ClaudeApplier

            applier = ClaudeApplier()
            applier.prune([], [], manifest)

        # File should still exist because checksum differs
        self.assertTrue(skill_file.exists())


class TestCursorApplier(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.cursor_dir = Path(self.tmpdir) / ".cursor"
        self.cursor_dir.mkdir()
        self.rules_dir = Path(self.tmpdir) / ".cursor" / "rules"
        self.mcp_json = self.cursor_dir / "mcp.json"
        self.manifest_path = Path(self.tmpdir) / "manifest.json"

    def _manifest(self) -> ToolManifest:
        return ToolManifest("cursor", path=self.manifest_path)

    def test_apply_skills(self):
        skills = [
            {
                "name": "test-rule",
                "description": "A test",
                "body": "# Rule\nDo cursor things.",
                "targets": [],
            }
        ]
        manifest = self._manifest()

        with patch("appliers.cursor._cursor_rules_dir", return_value=self.rules_dir):
            from appliers.cursor import CursorApplier

            applier = CursorApplier()
            count = applier.apply_skills(skills, manifest)

        self.assertEqual(count, 1)
        rule_file = self.rules_dir / "test-rule.mdc"
        self.assertTrue(rule_file.exists())
        self.assertIn("test-rule", manifest.managed_skill_names())

    def test_apply_mcp_servers(self):
        servers = [
            {
                "name": "test",
                "transport": "stdio",
                "command": "node",
                "args": [],
                "env": {},
                "targets": [],
            }
        ]
        manifest = self._manifest()

        with patch("appliers.cursor._cursor_mcp_json", return_value=self.mcp_json):
            from appliers.cursor import CursorApplier

            applier = CursorApplier()
            count = applier.apply_mcp_servers(servers, {}, manifest)

        self.assertEqual(count, 1)
        data = json.loads(self.mcp_json.read_text())
        self.assertIn("test", data["mcpServers"])
        self.assertIn("test", manifest.managed_mcp_names())


class TestReadExistingMemoryFiles(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def test_claude_reads_existing_memory(self):
        claude_md = Path(self.tmpdir) / "CLAUDE.md"
        claude_md.write_text("# My context\n- test", encoding="utf-8")

        with patch("appliers.claude._claude_md", return_value=claude_md):
            from appliers.claude import ClaudeApplier

            applier = ClaudeApplier()
            result = applier._read_existing_memory_files()

        self.assertIn(str(claude_md), result)
        self.assertIn("My context", result[str(claude_md)])

    def test_claude_no_existing_files(self):
        with patch("appliers.claude._claude_md", return_value=Path(self.tmpdir) / "nonexistent.md"):
            from appliers.claude import ClaudeApplier

            applier = ClaudeApplier()
            result = applier._read_existing_memory_files()

        self.assertEqual(result, {})

    def test_openclaw_reads_existing_memory(self):
        user_md = Path(self.tmpdir) / "USER.md"
        memory_md = Path(self.tmpdir) / "MEMORY.md"
        identity_md = Path(self.tmpdir) / "IDENTITY.md"
        soul_md = Path(self.tmpdir) / "SOUL.md"
        tools_md = Path(self.tmpdir) / "TOOLS.md"
        user_md.write_text("# User", encoding="utf-8")
        memory_md.write_text("# Memory", encoding="utf-8")
        identity_md.write_text("# Identity", encoding="utf-8")
        soul_md.write_text("# Soul", encoding="utf-8")
        tools_md.write_text("# Tools", encoding="utf-8")

        with (
            patch("appliers.openclaw._openclaw_user_md", return_value=user_md),
            patch("appliers.openclaw._openclaw_memory_md", return_value=memory_md),
            patch("appliers.openclaw._openclaw_identity_md", return_value=identity_md),
            patch("appliers.openclaw._openclaw_soul_md", return_value=soul_md),
            patch("appliers.openclaw._openclaw_tools_md", return_value=tools_md),
        ):
            from appliers.openclaw import OpenClawApplier

            applier = OpenClawApplier()
            result = applier._read_existing_memory_files()

        self.assertEqual(len(result), 5)


if __name__ == "__main__":
    unittest.main()
