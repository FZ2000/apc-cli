"""Unit tests for tool extractors."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class TestClaudeExtractor(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.claude_dir = Path(self.tmpdir) / ".claude"
        self.claude_dir.mkdir()
        self.commands_dir = self.claude_dir / "commands"
        self.commands_dir.mkdir()
        self.claude_json = Path(self.tmpdir) / ".claude.json"
        self.claude_md = self.claude_dir / "CLAUDE.md"

    def test_extract_skills_from_markdown(self):
        skill_content = """---
name: test-skill
description: A test skill
tags:
  - testing
---

# Instructions
Do something useful.
"""
        (self.commands_dir / "test-skill.md").write_text(skill_content)

        with patch("apc.extractors.claude.CLAUDE_COMMANDS_DIR", self.commands_dir):
            from apc.extractors.claude import ClaudeExtractor

            extractor = ClaudeExtractor()
            skills = extractor.extract_skills()

        self.assertEqual(len(skills), 1)
        self.assertEqual(skills[0]["name"], "test-skill")
        self.assertEqual(skills[0]["description"], "A test skill")
        self.assertIn("testing", skills[0]["tags"])
        self.assertIn("Do something useful.", skills[0]["body"])

    def test_extract_mcp_servers(self):
        mcp_data = {
            "mcpServers": {
                "filesystem": {
                    "type": "stdio",
                    "command": "npx",
                    "args": ["-y", "@mcp/server-filesystem"],
                    "env": {"TOKEN": "secret123"},
                }
            }
        }
        self.claude_json.write_text(json.dumps(mcp_data))

        with patch("apc.extractors.claude.CLAUDE_JSON", self.claude_json):
            from apc.extractors.claude import ClaudeExtractor

            extractor = ClaudeExtractor()
            servers = extractor.extract_mcp_servers()

        self.assertEqual(len(servers), 1)
        self.assertEqual(servers[0]["name"], "filesystem")
        self.assertEqual(servers[0]["command"], "npx")
        self.assertEqual(servers[0]["env"]["TOKEN"], "secret123")

    def test_extract_memory_raw_file_format(self):
        """Memory extraction now returns raw file content dicts."""
        content = """# My AI Context

## Preferences
- Always use TypeScript for new projects
- Prefer functional programming patterns

## Workflow
- Run tests before committing code
"""
        self.claude_md.write_text(content)

        with patch(
            "apc.extractors.claude.MEMORY_FILES",
            [{"path": self.claude_md, "label": "Instructions (CLAUDE.md)"}],
        ):
            from apc.extractors.claude import ClaudeExtractor

            extractor = ClaudeExtractor()
            entries = extractor.extract_memory()

        self.assertEqual(len(entries), 1)
        entry = entries[0]
        # New format fields
        self.assertIn("id", entry)
        self.assertEqual(entry["source_tool"], "claude")
        self.assertEqual(entry["source_file"], "CLAUDE.md")
        self.assertIn("content", entry)
        self.assertIn("TypeScript", entry["content"])
        self.assertEqual(entry["label"], "Instructions (CLAUDE.md)")

    def test_extract_memory_content_hash_dedup(self):
        """Same content from same file always gets same ID."""
        content = "# Test content\n- Some preference"
        self.claude_md.write_text(content)

        with patch(
            "apc.extractors.claude.MEMORY_FILES", [{"path": self.claude_md, "label": "test"}]
        ):
            from apc.extractors.claude import ClaudeExtractor

            extractor = ClaudeExtractor()
            entries1 = extractor.extract_memory()
            entries2 = extractor.extract_memory()

        self.assertEqual(entries1[0]["id"], entries2[0]["id"])

    def test_extract_memory_different_content_different_id(self):
        """Different content gets different IDs."""
        from apc.extractors.claude import _content_hash_id

        id1 = _content_hash_id("claude", "CLAUDE.md", "content A")
        id2 = _content_hash_id("claude", "CLAUDE.md", "content B")

        self.assertNotEqual(id1, id2)

    def test_extract_memory_empty_file_skipped(self):
        """Empty files should be skipped."""
        self.claude_md.write_text("")

        with patch(
            "apc.extractors.claude.MEMORY_FILES", [{"path": self.claude_md, "label": "test"}]
        ):
            from apc.extractors.claude import ClaudeExtractor

            extractor = ClaudeExtractor()
            entries = extractor.extract_memory()

        self.assertEqual(len(entries), 0)

    def test_extract_memory_nonexistent_file_skipped(self):
        """Non-existent files should be skipped."""
        fake_path = Path(self.tmpdir) / "nonexistent.md"

        with patch("apc.extractors.claude.MEMORY_FILES", [{"path": fake_path, "label": "test"}]):
            from apc.extractors.claude import ClaudeExtractor

            extractor = ClaudeExtractor()
            entries = extractor.extract_memory()

        self.assertEqual(len(entries), 0)

    def test_extract_skills_no_directory(self):
        with patch("apc.extractors.claude.CLAUDE_COMMANDS_DIR", Path("/nonexistent")):
            from apc.extractors.claude import ClaudeExtractor

            extractor = ClaudeExtractor()
            skills = extractor.extract_skills()

        self.assertEqual(len(skills), 0)


class TestOpenClawExtractor(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.workspace = Path(self.tmpdir) / "workspace"
        self.workspace.mkdir()
        self.user_md = self.workspace / "USER.md"
        self.memory_md = self.workspace / "MEMORY.md"

    def test_extract_memory_raw_file_format(self):
        """OpenClaw memory extraction returns raw file content dicts."""
        self.user_md.write_text("# USER.md\n## Personal\n- **Name:** Zhiyan\n")
        self.memory_md.write_text("# Memory\n- User prefers TypeScript\n")

        with patch(
            "apc.extractors.openclaw.MEMORY_FILES",
            [
                {"path": self.user_md, "label": "Personal context (USER.md)"},
                {"path": self.memory_md, "label": "Long-term memory (MEMORY.md)"},
            ],
        ):
            from apc.extractors.openclaw import OpenClawExtractor

            extractor = OpenClawExtractor()
            entries = extractor.extract_memory()

        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0]["source_tool"], "openclaw")
        self.assertEqual(entries[0]["source_file"], "USER.md")
        self.assertEqual(entries[1]["source_file"], "MEMORY.md")
        self.assertIn("Zhiyan", entries[0]["content"])
        self.assertIn("TypeScript", entries[1]["content"])

    def test_extract_memory_content_hash_dedup(self):
        """Same content always gets same ID."""
        content = "# Some content"
        self.user_md.write_text(content)

        with patch(
            "apc.extractors.openclaw.MEMORY_FILES",
            [
                {"path": self.user_md, "label": "test"},
            ],
        ):
            from apc.extractors.openclaw import OpenClawExtractor

            extractor = OpenClawExtractor()
            entries1 = extractor.extract_memory()
            entries2 = extractor.extract_memory()

        self.assertEqual(entries1[0]["id"], entries2[0]["id"])

    def test_extract_memory_empty_file_skipped(self):
        self.user_md.write_text("   \n  ")

        with patch(
            "apc.extractors.openclaw.MEMORY_FILES",
            [
                {"path": self.user_md, "label": "test"},
            ],
        ):
            from apc.extractors.openclaw import OpenClawExtractor

            extractor = OpenClawExtractor()
            entries = extractor.extract_memory()

        self.assertEqual(len(entries), 0)


class TestCursorExtractor(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.cursor_dir = Path(self.tmpdir) / ".cursor"
        self.cursor_dir.mkdir()
        self.mcp_json = self.cursor_dir / "mcp.json"

    def test_extract_mcp_servers(self):
        mcp_data = {
            "mcpServers": {
                "test-server": {
                    "type": "stdio",
                    "command": "node",
                    "args": ["server.js"],
                }
            }
        }
        self.mcp_json.write_text(json.dumps(mcp_data))

        with patch("apc.extractors.cursor.CURSOR_MCP_JSON", self.mcp_json):
            from apc.extractors.cursor import CursorExtractor

            extractor = CursorExtractor()
            servers = extractor.extract_mcp_servers()

        self.assertEqual(len(servers), 1)
        self.assertEqual(servers[0]["name"], "test-server")


class TestSecretsModule(unittest.TestCase):
    def test_detect_and_redact(self):
        from apc.secrets import detect_and_redact

        env = {
            "GITHUB_TOKEN": "ghp_abc123",
            "API_KEY": "sk-test",
            "SOME_FLAG": "true",
            "DATABASE_URL": "mongodb://localhost",
        }
        redacted, secrets = detect_and_redact(env)

        self.assertEqual(redacted["GITHUB_TOKEN"], "${GITHUB_TOKEN}")
        self.assertEqual(redacted["API_KEY"], "${API_KEY}")
        self.assertEqual(redacted["SOME_FLAG"], "true")
        self.assertEqual(redacted["DATABASE_URL"], "mongodb://localhost")
        self.assertEqual(secrets["GITHUB_TOKEN"], "ghp_abc123")
        self.assertEqual(secrets["API_KEY"], "sk-test")

    def test_already_redacted_not_double_redacted(self):
        from apc.secrets import detect_and_redact

        env = {"GITHUB_TOKEN": "${GITHUB_TOKEN}"}
        redacted, secrets = detect_and_redact(env)

        self.assertEqual(redacted["GITHUB_TOKEN"], "${GITHUB_TOKEN}")
        self.assertEqual(len(secrets), 0)


class TestFrontmatterParser(unittest.TestCase):
    def test_parse_with_frontmatter(self):
        from apc.frontmatter_parser import parse_frontmatter

        content = "---\nname: test\ntags:\n  - a\n  - b\n---\n\n# Body\nHello"
        metadata, body = parse_frontmatter(content)

        self.assertEqual(metadata["name"], "test")
        self.assertEqual(metadata["tags"], ["a", "b"])
        self.assertIn("Hello", body)

    def test_parse_without_frontmatter(self):
        from apc.frontmatter_parser import parse_frontmatter

        content = "# Just markdown\nNo frontmatter here"
        metadata, body = parse_frontmatter(content)

        self.assertEqual(metadata, {})
        self.assertEqual(body, content)

    def test_render_frontmatter(self):
        from apc.frontmatter_parser import render_frontmatter

        metadata = {"name": "test", "tags": ["a"]}
        body = "# Hello"
        result = render_frontmatter(metadata, body)

        self.assertIn("---", result)
        self.assertIn("name: test", result)
        self.assertIn("# Hello", result)


class TestCacheMergeMemory(unittest.TestCase):
    def test_merge_memory_new_format(self):
        """Content-hash IDs deduplicate across runs."""
        from apc.cache import merge_memory

        existing = [
            {"id": "abc123", "source_tool": "claude", "source_file": "CLAUDE.md", "content": "old"},
        ]
        new = [
            {
                "id": "abc123",
                "source_tool": "claude",
                "source_file": "CLAUDE.md",
                "content": "updated",
            },
        ]
        merged = merge_memory(existing, new)

        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["content"], "updated")

    def test_merge_memory_different_ids(self):
        """Different IDs are kept as separate entries."""
        from apc.cache import merge_memory

        existing = [
            {"id": "aaa", "source_tool": "claude", "content": "A"},
        ]
        new = [
            {"id": "bbb", "source_tool": "openclaw", "content": "B"},
        ]
        merged = merge_memory(existing, new)

        self.assertEqual(len(merged), 2)

    def test_merge_memory_legacy_format(self):
        """Old entry_id format still works."""
        from apc.cache import merge_memory

        existing = [
            {"entry_id": "20250301_abc123", "category": "preference", "content": "old"},
        ]
        new = [
            {"entry_id": "20250301_abc123", "category": "preference", "content": "updated"},
        ]
        merged = merge_memory(existing, new)

        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["content"], "updated")


if __name__ == "__main__":
    unittest.main()
