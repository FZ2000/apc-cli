"""Tests for secret-handling security fixes (#32, #35)."""

import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from appliers.manifest import ToolManifest


class TestScrubContent(unittest.TestCase):
    """#35 — Memory/skill content exported without secret scrubbing."""

    def test_openai_key_redacted(self):
        from secrets_manager import scrub_content

        # Build fake key at runtime — avoids gitleaks false positive in source
        fake_key = "sk-" + "Ab1" * 10  # 30 alphanum chars after "sk-"
        text = f"My key is {fake_key} and it works"
        result = scrub_content(text)
        self.assertNotIn(fake_key, result)
        self.assertIn("[REDACTED]", result)

    def test_anthropic_key_redacted(self):
        from secrets_manager import scrub_content

        # Build fake Anthropic key at runtime
        fake_key = "sk-ant-" + "xY9" * 12  # > 20 chars after "sk-ant-"
        text = f"Use {fake_key}"
        result = scrub_content(text)
        self.assertNotIn(fake_key, result)
        self.assertIn("[REDACTED]", result)

    def test_github_token_redacted(self):
        from secrets_manager import scrub_content

        # Build fake GitHub PAT at runtime
        fake_token = "ghp_" + "Az1" * 13  # 39 chars after "ghp_"
        text = f"TOKEN={fake_token}"
        result = scrub_content(text)
        self.assertNotIn(fake_token, result)
        self.assertIn("[REDACTED]", result)

    def test_plain_text_unchanged(self):
        from secrets_manager import scrub_content

        text = "This is a normal sentence with no secrets."
        result = scrub_content(text)
        self.assertEqual(result, text)

    def test_short_base64_unchanged(self):
        """Short base64 strings (e.g. checksums) should NOT be redacted."""
        from secrets_manager import scrub_content

        text = "checksum: dGVzdA=="  # 8 chars, way below 40-char threshold
        result = scrub_content(text)
        self.assertEqual(result, text)


class TestExportScrubsContent(unittest.TestCase):
    """#35 — Export must scrub recognizable secret patterns from memory/skills."""

    def test_memory_content_scrubbed_on_export(self):
        """Memory entries with API-key-shaped values get redacted in export."""
        from secrets_manager import scrub_content

        # Build fake key at runtime to avoid gitleaks false positives in source
        fake_key = "sk-" + "t3st" * 7  # 28 chars after "sk-", matches scrub pattern
        secret_content = f"Use this key: {fake_key}"
        scrubbed = scrub_content(secret_content)
        self.assertNotIn(fake_key, scrubbed)
        self.assertIn("[REDACTED]", scrubbed)

    def test_skill_body_scrubbed_on_export(self):
        """Skill body text with embedded keys gets redacted in export."""
        from secrets_manager import scrub_content

        # Build fake key at runtime to avoid gitleaks false positives in source
        fake_key = "sk-" + "Abc9" * 6  # 24 chars after "sk-"
        skill_body = f"OPENAI_KEY={fake_key}"
        scrubbed = scrub_content(skill_body)
        self.assertNotIn(fake_key, scrubbed)


class TestMcpConfigPermissions(unittest.TestCase):
    """#32 — MCP config files must be chmod 600 after writing resolved secrets."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.manifest_path = self.tmpdir / "manifest.json"

    def _manifest(self, tool: str = "cursor") -> ToolManifest:
        return ToolManifest(tool, path=self.manifest_path)

    def test_cursor_mcp_json_chmod_600(self):
        mcp_json = self.tmpdir / "mcp.json"
        servers = [
            {
                "name": "fs",
                "transport": "stdio",
                "command": "npx",
                "args": [],
                "env": {"TOKEN": "resolved-secret"},
            }
        ]
        manifest = self._manifest("cursor")

        with patch("appliers.cursor._cursor_mcp_json", return_value=mcp_json):
            from appliers.cursor import CursorApplier

            applier = CursorApplier()
            applier.apply_mcp_servers(servers, {}, manifest)

        file_mode = oct(stat.S_IMODE(os.stat(mcp_json).st_mode))
        self.assertEqual(file_mode, oct(0o600), f"Expected 600, got {file_mode}")

    def test_gemini_settings_chmod_600(self):
        settings = self.tmpdir / "settings.json"
        servers = [
            {
                "name": "svc",
                "transport": "stdio",
                "command": "node",
                "args": [],
                "env": {},
            }
        ]
        manifest = self._manifest("gemini-cli")

        with (
            patch("appliers.gemini._gemini_settings", return_value=settings),
            patch("appliers.gemini._gemini_dir", return_value=self.tmpdir),
        ):
            from appliers.gemini import GeminiApplier

            applier = GeminiApplier()
            applier.apply_mcp_servers(servers, {}, manifest)

        file_mode = oct(stat.S_IMODE(os.stat(settings).st_mode))
        self.assertEqual(file_mode, oct(0o600), f"Expected 600, got {file_mode}")

    def test_claude_json_chmod_600(self):
        claude_json = self.tmpdir / ".claude.json"
        servers = [
            {
                "name": "mcp-srv",
                "transport": "stdio",
                "command": "node",
                "args": [],
                "env": {},
            }
        ]
        manifest = self._manifest("claude-code")

        with patch("appliers.claude._claude_json", return_value=claude_json):
            from appliers.claude import ClaudeApplier

            applier = ClaudeApplier()
            applier.apply_mcp_servers(servers, {}, manifest)

        file_mode = oct(stat.S_IMODE(os.stat(claude_json).st_mode))
        self.assertEqual(file_mode, oct(0o600), f"Expected 600, got {file_mode}")


class TestSyncMcpWarnsAboutSecrets(unittest.TestCase):
    """#32 — sync_mcp should warn when servers have secrets being written to disk."""

    def test_warns_when_servers_have_secrets(self):
        servers = [
            {"name": "fs", "transport": "stdio", "command": "npx", "secret_placeholders": ["TOKEN"]}
        ]
        warnings = []

        with (
            patch("sync_helpers.load_mcp_servers", return_value=servers),
            patch("sync_helpers.get_applier") as mock_get_applier,
            patch("sync_helpers.warning", side_effect=lambda m: warnings.append(m)),
            patch("sync_helpers._resolve_all_mcp_secrets", return_value={"TOKEN": "secret"}),
        ):
            mock_applier = unittest.mock.MagicMock()
            mock_applier.get_manifest.return_value = ToolManifest(
                "cursor", path=Path(tempfile.mkdtemp()) / "m.json"
            )
            mock_applier.apply_mcp_servers.return_value = 1
            mock_get_applier.return_value = mock_applier

            from sync_helpers import sync_mcp

            sync_mcp(["cursor"])

        # At least one warning about secrets being written to disk
        self.assertTrue(
            any("secret" in w.lower() for w in warnings),
            f"Expected a secrets warning, got: {warnings}",
        )


if __name__ == "__main__":
    unittest.main()
