"""Unit tests for ToolManifest."""

import json
import tempfile
import unittest
from pathlib import Path

from appliers.manifest import ToolManifest, _sha256


class TestToolManifest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.manifest_path = Path(self.tmpdir) / "claude.json"

    def _make_manifest(self) -> ToolManifest:
        return ToolManifest("claude", path=self.manifest_path)

    # -- empty / first sync ---------------------------------------------------

    def test_empty_manifest_creation(self):
        m = self._make_manifest()
        self.assertEqual(m.tool, "claude")
        self.assertEqual(m.managed_skill_names(), [])
        self.assertEqual(m.managed_linked_skill_names(), [])
        self.assertEqual(m.managed_mcp_names(), [])
        self.assertEqual(m.memory_entry_ids(), [])
        self.assertTrue(m.is_first_sync)

    # -- skills CRUD ----------------------------------------------------------

    def test_record_and_list_skills(self):
        m = self._make_manifest()
        m.record_skill("pdf", file_path="/tmp/pdf.md", content="# PDF skill")
        m.record_skill("git", file_path="/tmp/git.md", content="# Git skill")

        self.assertEqual(sorted(m.managed_skill_names()), ["git", "pdf"])

    def test_get_skill_checksum(self):
        m = self._make_manifest()
        m.record_skill("pdf", file_path="/tmp/pdf.md", content="hello")
        checksum = m.get_skill_checksum("pdf")
        self.assertTrue(checksum.startswith("sha256:"))
        self.assertEqual(checksum, _sha256("hello"))

    def test_get_skill_checksum_missing(self):
        m = self._make_manifest()
        self.assertIsNone(m.get_skill_checksum("nonexistent"))

    def test_remove_skill(self):
        m = self._make_manifest()
        m.record_skill("pdf", file_path="/tmp/pdf.md", content="x")
        m.remove_skill("pdf")
        self.assertEqual(m.managed_skill_names(), [])

    def test_remove_nonexistent_skill(self):
        m = self._make_manifest()
        m.remove_skill("ghost")  # should not raise

    # -- linked skills CRUD ---------------------------------------------------

    def test_record_and_list_linked_skills(self):
        m = self._make_manifest()
        m.record_linked_skill("pdf", link_path="/a/pdf", target="/b/pdf")
        self.assertEqual(m.managed_linked_skill_names(), ["pdf"])

    def test_remove_linked_skill(self):
        m = self._make_manifest()
        m.record_linked_skill("pdf", link_path="/a", target="/b")
        m.remove_linked_skill("pdf")
        self.assertEqual(m.managed_linked_skill_names(), [])

    # -- mcp servers CRUD -----------------------------------------------------

    def test_record_and_list_mcp_servers(self):
        m = self._make_manifest()
        m.record_mcp_server("filesystem")
        m.record_mcp_server("github")
        self.assertEqual(sorted(m.managed_mcp_names()), ["filesystem", "github"])

    def test_remove_mcp_server(self):
        m = self._make_manifest()
        m.record_mcp_server("filesystem")
        m.remove_mcp_server("filesystem")
        self.assertEqual(m.managed_mcp_names(), [])

    # -- memory CRUD ----------------------------------------------------------

    def test_record_memory(self):
        m = self._make_manifest()
        m.record_memory(
            file_path="/tmp/CLAUDE.md",
            entry_ids=["e1", "e2"],
            content="# My memory",
        )
        self.assertEqual(m.memory_entry_ids(), ["e1", "e2"])

    def test_clear_memory(self):
        m = self._make_manifest()
        m.record_memory(file_path="/tmp/X.md", entry_ids=["e1"], content="x")
        m.clear_memory()
        self.assertEqual(m.memory_entry_ids(), [])

    # -- persistence ----------------------------------------------------------

    def test_save_and_reload(self):
        m = self._make_manifest()
        m.record_skill("pdf", file_path="/tmp/pdf.md", content="body")
        m.record_mcp_server("fs")
        m.record_memory(file_path="/tmp/M.md", entry_ids=["e1"], content="mem")
        m.save()

        self.assertTrue(self.manifest_path.exists())

        m2 = ToolManifest("claude", path=self.manifest_path)
        self.assertEqual(m2.managed_skill_names(), ["pdf"])
        self.assertEqual(m2.managed_mcp_names(), ["fs"])
        self.assertEqual(m2.memory_entry_ids(), ["e1"])
        self.assertFalse(m2.is_first_sync)  # has last_sync_at now

    def test_reload_corrupt_json_creates_empty(self):
        self.manifest_path.write_text("NOT JSON", encoding="utf-8")
        m = ToolManifest("claude", path=self.manifest_path)
        self.assertEqual(m.managed_skill_names(), [])
        self.assertTrue(m.is_first_sync)

    def test_reload_wrong_schema_version_creates_empty(self):
        self.manifest_path.write_text(
            json.dumps({"schema_version": 999, "tool": "claude"}),
            encoding="utf-8",
        )
        m = ToolManifest("claude", path=self.manifest_path)
        self.assertEqual(m.managed_skill_names(), [])

    # -- is_first_sync --------------------------------------------------------

    def test_is_first_sync_false_after_save(self):
        m = self._make_manifest()
        self.assertTrue(m.is_first_sync)
        m.save()

        m2 = ToolManifest("claude", path=self.manifest_path)
        self.assertFalse(m2.is_first_sync)


if __name__ == "__main__":
    unittest.main()
