"""Tests for memory schema and deduplication fixes (#36, #45)."""

import unittest
from unittest.mock import patch


class TestMergeMemoryDedup(unittest.TestCase):
    """#36 — Memory entries duplicate on every apc collect."""

    def test_same_content_no_id_not_duplicated(self):
        """Entries lacking id/entry_id are deduplicated by stable content hash."""
        from cache import merge_memory

        entry = {"content": "hello", "source_tool": "test", "category": "pref"}
        # Same logical entry as two separate dict instances (simulates load from disk)
        entry1 = dict(entry)
        entry2 = dict(entry)

        result = merge_memory([entry1], [entry2])
        self.assertEqual(len(result), 1, "Same content must not create a duplicate")

    def test_different_content_creates_two_entries(self):
        """Different content creates two separate entries."""
        from cache import merge_memory

        e1 = {"content": "hello", "source_tool": "test", "category": "pref"}
        e2 = {"content": "world", "source_tool": "test", "category": "pref"}
        result = merge_memory([e1], [e2])
        self.assertEqual(len(result), 2)

    def test_stable_id_deduplicates_correctly(self):
        """Entries with an explicit 'id' are deduplicated by that id."""
        from cache import merge_memory

        e1 = {"id": "abc123", "content": "old", "source_tool": "t"}
        e2 = {"id": "abc123", "content": "new", "source_tool": "t"}
        result = merge_memory([e1], [e2])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["content"], "new", "New entry should win (upsert)")

    def test_entry_id_key_stable_across_runs(self):
        """entry_id (old format) provides a stable dedup key across reloads."""
        from cache import merge_memory

        e = {"entry_id": "20260307_abc123", "content": "hello", "category": "pref"}
        # Same entry reloaded = new Python object, but same entry_id
        e_reloaded = dict(e)
        result = merge_memory([e], [e_reloaded])
        self.assertEqual(len(result), 1)

    def test_no_id_same_source_tool_file_deduplicates(self):
        """Fallback hash uses source_tool + source_file + content for stable keying."""
        from cache import merge_memory

        base = {"content": "data", "source_tool": "openclaw", "source_file": "MEMORY.md"}
        result = merge_memory([dict(base)], [dict(base)])
        self.assertEqual(len(result), 1, "Same source+content should deduplicate")


class TestMemoryAddNewSchema(unittest.TestCase):
    """#45 — apc memory add uses legacy schema vs collect's new schema."""

    def test_memory_add_uses_id_not_entry_id(self):
        """memory add now creates entries with 'id' field (new schema)."""
        from click.testing import CliRunner

        from memory import memory

        runner = CliRunner()
        saved = []

        with (
            patch("memory.load_memory", return_value=[]),
            patch("memory.save_memory", side_effect=lambda entries: saved.extend(entries)),
            patch("memory.merge_memory", side_effect=lambda existing, new: new),
        ):
            result = runner.invoke(memory, ["add", "test memory text"])

        self.assertEqual(result.exit_code, 0)
        self.assertEqual(len(saved), 1)
        entry = saved[0]
        # New schema: must have 'id', not 'entry_id'
        self.assertIn("id", entry, "New schema requires 'id' field")
        self.assertNotIn("entry_id", entry, "'entry_id' is legacy — must not appear")
        self.assertIn("source_tool", entry)
        self.assertEqual(entry["source_tool"], "manual")
        self.assertIn("source_file", entry)

    def test_memory_add_same_text_same_id(self):
        """Adding the same text twice produces the same id (idempotent)."""
        from click.testing import CliRunner

        from memory import memory

        runner = CliRunner()
        ids = []

        def capture_save(entries):
            ids.extend(e["id"] for e in entries)

        with (
            patch("memory.load_memory", return_value=[]),
            patch("memory.save_memory", side_effect=capture_save),
            patch("memory.merge_memory", side_effect=lambda existing, new: new),
        ):
            runner.invoke(memory, ["add", "repeated text"])
            runner.invoke(memory, ["add", "repeated text"])

        self.assertEqual(len(ids), 2)
        self.assertEqual(ids[0], ids[1], "Same text must produce the same id")

    def test_memory_add_different_category_different_id(self):
        """Same text with different category produces a different id."""
        from click.testing import CliRunner

        from memory import memory

        runner = CliRunner()
        ids = []

        def capture_save(entries):
            ids.extend(e["id"] for e in entries)

        with (
            patch("memory.load_memory", return_value=[]),
            patch("memory.save_memory", side_effect=capture_save),
            patch("memory.merge_memory", side_effect=lambda existing, new: new),
        ):
            runner.invoke(memory, ["add", "same text", "--category", "preference"])
            runner.invoke(memory, ["add", "same text", "--category", "workflow"])

        self.assertEqual(len(ids), 2)
        self.assertNotEqual(ids[0], ids[1], "Different categories should produce different ids")

    def test_memory_add_preserves_category(self):
        """Category is still stored in the new schema entry."""
        from click.testing import CliRunner

        from memory import memory

        runner = CliRunner()
        saved = []

        with (
            patch("memory.load_memory", return_value=[]),
            patch("memory.save_memory", side_effect=lambda e: saved.extend(e)),
            patch("memory.merge_memory", side_effect=lambda existing, new: new),
        ):
            runner.invoke(memory, ["add", "some text", "--category", "workflow"])

        self.assertEqual(saved[0]["category"], "workflow")
        self.assertEqual(saved[0]["content"], "some text")


if __name__ == "__main__":
    unittest.main()
