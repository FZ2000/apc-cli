"""Unit tests for GitHub repository management, skill fetching, and symlink installation."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from apc.repositories import (
    DEFAULT_REPOS,
    _build_skill_url,
    add_repository,
    fetch_skill_from_repo,
    get_skills_dir,
    load_repositories,
    remove_repository,
    save_repositories,
    save_skill_file,
    search_skill,
)

SAMPLE_SKILL_MD = """\
---
name: pdf
description: Extract and analyze PDF files
tags:
  - utility
version: "1.0.0"
---

Use this skill to handle PDF files. Read them with the Read tool.
"""


class TestRepoConfig(unittest.TestCase):
    """Tests for repository CRUD operations."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.config_dir = Path(self.tmpdir)
        self.patcher = patch(
            "apc.repositories.get_config_dir",
            return_value=self.config_dir,
        )
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()

    def test_load_defaults_when_no_file(self):
        repos = load_repositories()
        self.assertEqual(repos, list(DEFAULT_REPOS))

    def test_save_and_load(self):
        save_repositories(["myorg/skills", "anthropics/skills"])
        repos = load_repositories()
        self.assertEqual(repos, ["myorg/skills", "anthropics/skills"])

    def test_load_falls_back_on_invalid_json(self):
        (self.config_dir / "repositories.json").write_text("not json")
        repos = load_repositories()
        self.assertEqual(repos, list(DEFAULT_REPOS))

    def test_load_falls_back_on_empty_list(self):
        (self.config_dir / "repositories.json").write_text("[]")
        repos = load_repositories()
        self.assertEqual(repos, list(DEFAULT_REPOS))

    def test_add_repository_inserts_at_front(self):
        save_repositories(["anthropics/skills"])
        repos = add_repository("myorg/tools")
        self.assertEqual(repos[0], "myorg/tools")
        self.assertIn("anthropics/skills", repos)

    def test_add_existing_repo_moves_to_front(self):
        save_repositories(["a/b", "c/d"])
        repos = add_repository("c/d")
        self.assertEqual(repos, ["c/d", "a/b"])

    def test_remove_repository(self):
        save_repositories(["a/b", "c/d"])
        repos = remove_repository("a/b")
        self.assertEqual(repos, ["c/d"])

    def test_remove_nonexistent_is_safe(self):
        save_repositories(["a/b"])
        repos = remove_repository("x/y")
        self.assertEqual(repos, ["a/b"])


class TestUrlBuilding(unittest.TestCase):
    """Tests for raw GitHub URL construction."""

    def test_default_branch(self):
        url = _build_skill_url("anthropics/skills", "pdf")
        self.assertEqual(
            url,
            "https://raw.githubusercontent.com/anthropics/skills/main/skills/pdf/SKILL.md",
        )

    def test_custom_branch(self):
        url = _build_skill_url("myorg/tools", "commit", branch="develop")
        self.assertEqual(
            url,
            "https://raw.githubusercontent.com/myorg/tools/develop/skills/commit/SKILL.md",
        )


class TestFetchSkill(unittest.TestCase):
    """Tests for fetching and parsing SKILL.md from GitHub."""

    @patch("apc.repositories.httpx.get")
    def test_fetch_success(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = SAMPLE_SKILL_MD
        mock_get.return_value = mock_resp

        skill = fetch_skill_from_repo("anthropics/skills", "pdf")

        self.assertIsNotNone(skill)
        self.assertEqual(skill["name"], "pdf")
        self.assertEqual(skill["description"], "Extract and analyze PDF files")
        self.assertIn("PDF files", skill["body"])
        self.assertEqual(skill["tags"], ["utility"])
        self.assertEqual(skill["targets"], [])
        self.assertEqual(skill["version"], "1.0.0")
        self.assertEqual(skill["source_tool"], "github")
        self.assertEqual(skill["source_repo"], "anthropics/skills")
        self.assertEqual(skill["_raw_content"], SAMPLE_SKILL_MD)

        mock_get.assert_called_once_with(
            "https://raw.githubusercontent.com/anthropics/skills/main/skills/pdf/SKILL.md",
            follow_redirects=True,
            timeout=15,
        )

    @patch("apc.repositories.httpx.get")
    def test_fetch_not_found(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_get.return_value = mock_resp

        skill = fetch_skill_from_repo("anthropics/skills", "nonexistent")
        self.assertIsNone(skill)

    @patch("apc.repositories.httpx.get")
    def test_fetch_network_error(self, mock_get):
        import httpx

        mock_get.side_effect = httpx.ConnectError("connection refused")

        skill = fetch_skill_from_repo("anthropics/skills", "pdf")
        self.assertIsNone(skill)

    @patch("apc.repositories.httpx.get")
    def test_fetch_no_frontmatter(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "Just plain markdown content."
        mock_get.return_value = mock_resp

        skill = fetch_skill_from_repo("anthropics/skills", "simple")
        self.assertIsNotNone(skill)
        self.assertEqual(skill["name"], "simple")  # falls back to skill_name arg
        self.assertEqual(skill["body"], "Just plain markdown content.")


class TestSearchSkill(unittest.TestCase):
    """Tests for searching across multiple repos."""

    @patch("apc.repositories.fetch_skill_from_repo")
    def test_search_returns_first_match(self, mock_fetch):
        skill_a = {"name": "pdf", "source_repo": "a/skills"}
        skill_b = {"name": "pdf", "source_repo": "b/skills"}
        mock_fetch.side_effect = [skill_a, skill_b]

        result = search_skill("pdf", repos=["a/skills", "b/skills"])
        self.assertEqual(result["source_repo"], "a/skills")
        # Should only call once since first repo matched
        mock_fetch.assert_called_once_with("a/skills", "pdf", "main")

    @patch("apc.repositories.fetch_skill_from_repo")
    def test_search_falls_through_to_second_repo(self, mock_fetch):
        mock_fetch.side_effect = [None, {"name": "pdf", "source_repo": "b/skills"}]

        result = search_skill("pdf", repos=["a/skills", "b/skills"])
        self.assertEqual(result["source_repo"], "b/skills")
        self.assertEqual(mock_fetch.call_count, 2)

    @patch("apc.repositories.fetch_skill_from_repo")
    def test_search_returns_none_when_not_found(self, mock_fetch):
        mock_fetch.return_value = None

        result = search_skill("pdf", repos=["a/skills"])
        self.assertIsNone(result)

    @patch("apc.repositories.fetch_skill_from_repo")
    def test_search_uses_custom_branch(self, mock_fetch):
        mock_fetch.return_value = {"name": "pdf", "source_repo": "a/skills"}

        search_skill("pdf", repos=["a/skills"], branch="develop")
        mock_fetch.assert_called_once_with("a/skills", "pdf", "develop")

    @patch("apc.repositories.load_repositories", return_value=["anthropics/skills"])
    @patch("apc.repositories.fetch_skill_from_repo")
    def test_search_uses_default_repos(self, mock_fetch, mock_load):
        mock_fetch.return_value = {"name": "pdf", "source_repo": "anthropics/skills"}

        search_skill("pdf")
        mock_load.assert_called_once()
        mock_fetch.assert_called_once_with("anthropics/skills", "pdf", "main")


class TestSkillStorage(unittest.TestCase):
    """Tests for saving skill files to source-of-truth directory."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.config_dir = Path(self.tmpdir)
        self.patcher = patch(
            "apc.repositories.get_config_dir",
            return_value=self.config_dir,
        )
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()

    def test_get_skills_dir_creates_directory(self):
        skills_dir = get_skills_dir()
        self.assertTrue(skills_dir.exists())
        self.assertEqual(skills_dir, self.config_dir / "skills")

    def test_save_skill_file(self):
        path = save_skill_file("pdf", SAMPLE_SKILL_MD)
        self.assertTrue(path.exists())
        self.assertEqual(path, self.config_dir / "skills" / "pdf" / "SKILL.md")
        self.assertEqual(path.read_text(), SAMPLE_SKILL_MD)

    def test_save_skill_file_overwrites(self):
        save_skill_file("pdf", "old content")
        path = save_skill_file("pdf", "new content")
        self.assertEqual(path.read_text(), "new content")


class TestLinkSkills(unittest.TestCase):
    """Tests for symlink-based skill installation via appliers."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        # Source of truth directory (~/.apc/skills/)
        self.source_dir = Path(self.tmpdir) / "skills"
        self.source_dir.mkdir()
        # Create a sample skill source directory with SKILL.md + supporting file
        skill_dir = self.source_dir / "pdf"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(SAMPLE_SKILL_MD)
        (skill_dir / "REFERENCE.md").write_text("# Reference\nExtra docs.")
        # Target directories for tools
        self.claude_skills = Path(self.tmpdir) / "claude_skills"
        self.claude_skills.mkdir()
        self.cursor_rules = Path(self.tmpdir) / "cursor_rules"
        self.cursor_rules.mkdir()

    def _manifest(self, tool="claude"):
        from apc.appliers.manifest import ToolManifest

        return ToolManifest(tool, path=Path(self.tmpdir) / f"{tool}_manifest.json")

    def test_claude_link_skills_directory_symlink(self):
        """Claude creates directory symlinks: ~/.claude/skills/pdf -> source/pdf"""
        from apc.appliers.claude import ClaudeApplier

        applier = ClaudeApplier()
        applier.SKILL_DIR = self.claude_skills
        skills = [{"name": "pdf", "targets": []}]
        count = applier.link_skills(skills, self.source_dir, self._manifest())

        self.assertEqual(count, 1)
        link = self.claude_skills / "pdf"
        self.assertTrue(link.is_symlink())
        # Should point to the source directory, not the file
        self.assertEqual(link.resolve(), (self.source_dir / "pdf").resolve())
        # SKILL.md and supporting files should be accessible through the link
        self.assertTrue((link / "SKILL.md").exists())
        self.assertTrue((link / "REFERENCE.md").exists())

    def test_cursor_link_skills_file_symlink(self):
        """Cursor creates file symlinks: .cursor/rules/pdf.mdc -> source/pdf/SKILL.md"""
        from apc.appliers.cursor import CursorApplier

        applier = CursorApplier()
        applier.SKILL_DIR = self.cursor_rules
        skills = [{"name": "pdf", "targets": []}]
        count = applier.link_skills(skills, self.source_dir, self._manifest("cursor"))

        self.assertEqual(count, 1)
        link = self.cursor_rules / "pdf.mdc"
        self.assertTrue(link.is_symlink())
        # Should point to the SKILL.md file directly
        self.assertEqual(link.resolve(), (self.source_dir / "pdf" / "SKILL.md").resolve())

    def test_link_skills_replaces_existing_directory(self):
        """Replaces a pre-existing real directory with a symlink."""
        existing_dir = self.claude_skills / "pdf"
        existing_dir.mkdir()
        (existing_dir / "old.md").write_text("old")

        from apc.appliers.claude import ClaudeApplier

        applier = ClaudeApplier()
        applier.SKILL_DIR = self.claude_skills
        skills = [{"name": "pdf", "targets": []}]
        count = applier.link_skills(skills, self.source_dir, self._manifest())

        self.assertEqual(count, 1)
        link = self.claude_skills / "pdf"
        self.assertTrue(link.is_symlink())

    def test_link_skills_replaces_broken_symlink(self):
        broken_link = self.claude_skills / "pdf"
        os.symlink("/nonexistent/path", broken_link)

        from apc.appliers.claude import ClaudeApplier

        applier = ClaudeApplier()
        applier.SKILL_DIR = self.claude_skills
        skills = [{"name": "pdf", "targets": []}]
        count = applier.link_skills(skills, self.source_dir, self._manifest())

        self.assertEqual(count, 1)
        self.assertTrue(broken_link.is_symlink())
        self.assertEqual(broken_link.resolve(), (self.source_dir / "pdf").resolve())

    def test_link_skills_skips_missing_source(self):
        from apc.appliers.claude import ClaudeApplier

        applier = ClaudeApplier()
        applier.SKILL_DIR = self.claude_skills
        skills = [{"name": "nonexistent", "targets": []}]
        count = applier.link_skills(skills, self.source_dir, self._manifest())

        self.assertEqual(count, 0)

    def test_link_skills_returns_zero_when_no_skill_dir(self):
        """Appliers without SKILL_DIR (e.g. Gemini) should return 0."""
        from apc.appliers.gemini import GeminiApplier

        applier = GeminiApplier()
        skills = [{"name": "pdf", "targets": []}]
        count = applier.link_skills(skills, self.source_dir, self._manifest("gemini"))

        self.assertEqual(count, 0)

    def test_cursor_replaces_existing_file(self):
        """Cursor replaces an old .mdc file with a symlink."""
        existing = self.cursor_rules / "pdf.mdc"
        existing.write_text("old content")

        from apc.appliers.cursor import CursorApplier

        applier = CursorApplier()
        applier.SKILL_DIR = self.cursor_rules
        skills = [{"name": "pdf", "targets": []}]
        count = applier.link_skills(skills, self.source_dir, self._manifest("cursor"))

        self.assertEqual(count, 1)
        self.assertTrue(existing.is_symlink())


if __name__ == "__main__":
    unittest.main()
