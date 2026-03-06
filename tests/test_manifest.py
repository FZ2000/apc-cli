"""Unit tests for ToolManifest."""

import json
import tempfile
import unittest
import unittest.mock
from pathlib import Path

from appliers.manifest import ToolManifest, _sha256


class TestToolManifest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.manifest_path = Path(self.tmpdir) / "claude-code.json"

    def _make_manifest(self) -> ToolManifest:
        return ToolManifest("claude-code", path=self.manifest_path)

    # -- empty / first sync ---------------------------------------------------

    def test_empty_manifest_creation(self):
        m = self._make_manifest()
        self.assertEqual(m.tool, "claude-code")
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

        m2 = ToolManifest("claude-code", path=self.manifest_path)
        self.assertEqual(m2.managed_skill_names(), ["pdf"])
        self.assertEqual(m2.managed_mcp_names(), ["fs"])
        self.assertEqual(m2.memory_entry_ids(), ["e1"])
        self.assertFalse(m2.is_first_sync)  # has last_sync_at now

    def test_reload_corrupt_json_creates_empty(self):
        self.manifest_path.write_text("NOT JSON", encoding="utf-8")
        m = ToolManifest("claude-code", path=self.manifest_path)
        self.assertEqual(m.managed_skill_names(), [])
        self.assertTrue(m.is_first_sync)

    def test_reload_wrong_schema_version_creates_empty(self):
        self.manifest_path.write_text(
            json.dumps({"schema_version": 999, "tool": "claude"}),
            encoding="utf-8",
        )
        m = ToolManifest("claude-code", path=self.manifest_path)
        self.assertEqual(m.managed_skill_names(), [])

    # -- is_first_sync --------------------------------------------------------

    def test_is_first_sync_false_after_save(self):
        m = self._make_manifest()
        self.assertTrue(m.is_first_sync)
        m.save()

        m2 = ToolManifest("claude-code", path=self.manifest_path)
        self.assertFalse(m2.is_first_sync)


if __name__ == "__main__":
    unittest.main()


class TestToolSyncStatus(unittest.TestCase):
    """Unit tests for status._tool_sync_status — file-system consistency check."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.manifest_path = self.tmpdir / "cursor.json"

    def _make_manifest(self) -> ToolManifest:
        return ToolManifest("cursor", path=self.manifest_path)

    def test_not_synced_when_no_manifest(self):
        from status import _tool_sync_status

        with unittest.mock.patch(
            "status.ToolManifest",
            side_effect=lambda name: ToolManifest(name, path=self.manifest_path),
        ):
            assert _tool_sync_status("cursor") == "not synced"

    def test_synced_when_all_files_present(self):
        from status import _tool_sync_status

        skill_file = self.tmpdir / "pdf.mdc"
        skill_file.write_text("# pdf skill")

        m = self._make_manifest()
        m.record_skill("pdf", file_path=str(skill_file), content="# pdf skill")
        m.save()

        with unittest.mock.patch(
            "status.ToolManifest",
            side_effect=lambda name: ToolManifest(name, path=self.manifest_path),
        ):
            assert _tool_sync_status("cursor") == "synced"

    def test_out_of_sync_when_file_deleted(self):
        from status import _tool_sync_status

        skill_file = self.tmpdir / "pdf.mdc"
        skill_file.write_text("# pdf skill")

        m = self._make_manifest()
        m.record_skill("pdf", file_path=str(skill_file), content="# pdf skill")
        m.save()

        skill_file.unlink()  # simulate deletion

        with unittest.mock.patch(
            "status.ToolManifest",
            side_effect=lambda name: ToolManifest(name, path=self.manifest_path),
        ):
            assert _tool_sync_status("cursor") == "out of sync"

    def test_synced_when_only_mcp_synced(self):
        """If only MCP servers were synced (no skill files recorded), trust the timestamp."""
        from status import _tool_sync_status

        m = self._make_manifest()
        m.record_mcp_server("filesystem")
        m.save()

        with unittest.mock.patch(
            "status.ToolManifest",
            side_effect=lambda name: ToolManifest(name, path=self.manifest_path),
        ):
            assert _tool_sync_status("cursor") == "synced"

    def test_out_of_sync_when_linked_skill_missing(self):
        """Linked skill symlink removed → out of sync."""
        from status import _tool_sync_status

        link_path = self.tmpdir / "pdf.mdc"
        # Don't create the symlink — it's missing

        m = self._make_manifest()
        m.record_linked_skill("pdf", link_path=str(link_path), target="/source/SKILL.md")
        m.save()

        with unittest.mock.patch(
            "status.ToolManifest",
            side_effect=lambda name: ToolManifest(name, path=self.manifest_path),
        ):
            assert _tool_sync_status("cursor") == "out of sync"

    def test_partial_files_missing_is_out_of_sync(self):
        """One skill file present, one missing → out of sync."""
        from status import _tool_sync_status

        present = self.tmpdir / "skill-a.mdc"
        present.write_text("# skill a")
        missing = self.tmpdir / "skill-b.mdc"
        # skill-b not created

        m = self._make_manifest()
        m.record_skill("skill-a", file_path=str(present), content="# skill a")
        m.record_skill("skill-b", file_path=str(missing), content="# skill b")
        m.save()

        with unittest.mock.patch(
            "status.ToolManifest",
            side_effect=lambda name: ToolManifest(name, path=self.manifest_path),
        ):
            assert _tool_sync_status("cursor") == "out of sync"
