"""Unit tests for non-destructive memory section writing."""

import tempfile
import unittest
from pathlib import Path

from apc.appliers.memory_section import (
    BEGIN_MARKER,
    END_MARKER,
    build_memory_section,
    read_and_split,
    remove_memory_section,
    write_memory_file,
)

HEADERS = {
    "preference": "Preferences",
    "workflow": "Workflow",
    "constraint": "Constraints",
}


class TestBuildMemorySection(unittest.TestCase):
    def test_basic_build(self):
        entries = [
            {"category": "preference", "content": "Uses TypeScript"},
            {"category": "workflow", "content": "Runs tests first"},
        ]
        result = build_memory_section(entries, HEADERS)
        self.assertIn("## Preferences", result)
        self.assertIn("- Uses TypeScript", result)
        self.assertIn("## Workflow", result)
        self.assertIn("- Runs tests first", result)

    def test_empty_entries(self):
        result = build_memory_section([], HEADERS)
        self.assertIn("# AI Context", result)
        self.assertNotIn("## Preferences", result)

    def test_skips_empty_content(self):
        entries = [
            {"category": "preference", "content": ""},
            {"category": "preference", "content": "Valid"},
        ]
        result = build_memory_section(entries, HEADERS)
        self.assertIn("- Valid", result)
        # Only one bullet
        self.assertEqual(result.count("- "), 1)


class TestReadAndSplit(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def _path(self, name="test.md"):
        return Path(self.tmpdir) / name

    def test_nonexistent_file(self):
        before, section, after = read_and_split(self._path("missing.md"))
        self.assertEqual(before, "")
        self.assertIsNone(section)
        self.assertEqual(after, "")

    def test_file_without_markers(self):
        p = self._path()
        p.write_text("# My notes\nSome content\n", encoding="utf-8")
        before, section, after = read_and_split(p)
        self.assertEqual(before, "# My notes\nSome content\n")
        self.assertIsNone(section)
        self.assertEqual(after, "")

    def test_file_with_markers(self):
        content = (
            "# User notes\n\n"
            f"{BEGIN_MARKER}\n## APC Section\n- item\n{END_MARKER}\n"
            "\n# More user notes\n"
        )
        p = self._path()
        p.write_text(content, encoding="utf-8")

        before, section, after = read_and_split(p)
        self.assertEqual(before, "# User notes\n\n")
        self.assertIn(BEGIN_MARKER, section)
        self.assertIn(END_MARKER, section)
        self.assertEqual(after, "\n\n# More user notes\n")

    def test_malformed_begin_without_end(self):
        content = f"# User\n{BEGIN_MARKER}\n## Orphan section\n"
        p = self._path()
        p.write_text(content, encoding="utf-8")

        before, section, after = read_and_split(p)
        self.assertEqual(before, "# User\n")
        self.assertIn(BEGIN_MARKER, section)
        self.assertEqual(after, "")


class TestWriteMemoryFile(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def _path(self, name="CLAUDE.md"):
        return Path(self.tmpdir) / name

    def _entries(self):
        return [
            {"category": "preference", "content": "Prefers TypeScript"},
            {"category": "workflow", "content": "Runs tests first"},
        ]

    def test_creates_new_file(self):
        p = self._path()
        write_memory_file(p, self._entries(), HEADERS)

        content = p.read_text(encoding="utf-8")
        self.assertIn(BEGIN_MARKER, content)
        self.assertIn(END_MARKER, content)
        self.assertIn("Prefers TypeScript", content)

    def test_appends_to_existing_file_without_section(self):
        p = self._path()
        p.write_text("# My personal notes\n\nI like cats.\n", encoding="utf-8")

        write_memory_file(p, self._entries(), HEADERS)

        content = p.read_text(encoding="utf-8")
        # User content preserved
        self.assertIn("# My personal notes", content)
        self.assertIn("I like cats.", content)
        # APC section appended
        self.assertIn(BEGIN_MARKER, content)
        self.assertIn("Prefers TypeScript", content)

    def test_replaces_existing_section(self):
        p = self._path()
        # First write
        p.write_text(
            f"# User stuff\n\n{BEGIN_MARKER}\nOLD CONTENT\n{END_MARKER}\n\n# Footer\n",
            encoding="utf-8",
        )

        write_memory_file(p, self._entries(), HEADERS)

        content = p.read_text(encoding="utf-8")
        self.assertIn("# User stuff", content)
        self.assertIn("# Footer", content)
        self.assertNotIn("OLD CONTENT", content)
        self.assertIn("Prefers TypeScript", content)
        # Only one begin marker
        self.assertEqual(content.count(BEGIN_MARKER), 1)

    def test_preserves_user_content_across_syncs(self):
        p = self._path()
        p.write_text("# My notes\n", encoding="utf-8")

        # First sync
        write_memory_file(p, self._entries(), HEADERS)
        # Second sync with different entries
        new_entries = [{"category": "constraint", "content": "Never use eval"}]
        write_memory_file(p, new_entries, HEADERS)

        content = p.read_text(encoding="utf-8")
        self.assertIn("# My notes", content)
        self.assertIn("Never use eval", content)
        # Old APC entries should be gone
        self.assertNotIn("Prefers TypeScript", content)

    def test_returns_inner_content(self):
        p = self._path()
        inner = write_memory_file(p, self._entries(), HEADERS)
        self.assertIn("Prefers TypeScript", inner)
        self.assertNotIn(BEGIN_MARKER, inner)


class TestRemoveMemorySection(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def _path(self, name="CLAUDE.md"):
        return Path(self.tmpdir) / name

    def test_remove_from_file_with_section(self):
        p = self._path()
        p.write_text(
            f"# User stuff\n\n{BEGIN_MARKER}\n## APC\n- item\n{END_MARKER}\n\n# Footer\n",
            encoding="utf-8",
        )
        result = remove_memory_section(p)
        self.assertTrue(result)

        content = p.read_text(encoding="utf-8")
        self.assertIn("# User stuff", content)
        self.assertIn("# Footer", content)
        self.assertNotIn(BEGIN_MARKER, content)
        self.assertNotIn("- item", content)

    def test_remove_from_file_without_section(self):
        p = self._path()
        p.write_text("# Just user content\n", encoding="utf-8")
        result = remove_memory_section(p)
        self.assertFalse(result)

        content = p.read_text(encoding="utf-8")
        self.assertIn("# Just user content", content)

    def test_remove_from_nonexistent_file(self):
        result = remove_memory_section(self._path("ghost.md"))
        self.assertFalse(result)

    def test_remove_leaves_clean_user_content(self):
        p = self._path()
        p.write_text(
            f"# My notes\n{BEGIN_MARKER}\nstuff\n{END_MARKER}\n",
            encoding="utf-8",
        )
        remove_memory_section(p)
        content = p.read_text(encoding="utf-8")
        self.assertIn("# My notes", content)
        # File should end cleanly
        self.assertTrue(content.endswith("\n"))


if __name__ == "__main__":
    unittest.main()
