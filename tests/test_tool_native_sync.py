"""Unit tests for tool-native skill sync (issue #71).

Covers:
- GeminiApplier.SKILL_DIR → ~/.gemini/skills/
- WindsurfApplier: sync_skills_dir(), apply_installed_skill(), unsync_skills()
- CopilotApplier: sync_skills_dir(), apply_installed_skill(), unsync_skills()
- BaseApplier: apply_installed_skill() no-op, unsync_skills() dir-symlink removal
- manifest.py: record_tool_sync(), sync_method property
- install._propagate_to_synced_tools(): hits all synced tools unconditionally
- apc unsync command: single tool, --all, --yes
"""

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

# Ensure src/ is importable
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_skills_dir(tmp_path: Path, *skill_names: str) -> Path:
    """Create ~/.apc/skills/<name>/SKILL.md for each skill_name."""
    skills_dir = tmp_path / ".apc" / "skills"
    for name in skill_names:
        skill_dir = skills_dir / name
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(f"# {name}\nSkill content.", encoding="utf-8")
    return skills_dir


# ---------------------------------------------------------------------------
# Gemini: SKILL_DIR
# ---------------------------------------------------------------------------


class TestGeminiSkillDir(unittest.TestCase):
    def test_skill_dir_is_gemini_skills(self, tmp_path=None):
        from appliers.gemini import GeminiApplier

        applier = GeminiApplier()
        assert applier.SKILL_DIR == Path.home() / ".gemini" / "skills"

    def test_skill_dir_monkeypatched_home(self):
        """SKILL_DIR resolves relative to HOME at call time."""
        import importlib

        import appliers.gemini as gemini_mod

        with patch.dict(os.environ, {"HOME": "/fakehome"}):
            importlib.reload(gemini_mod)
            applier = gemini_mod.GeminiApplier()
            assert applier.SKILL_DIR == Path("/fakehome/.gemini/skills")

        importlib.reload(gemini_mod)  # restore


# ---------------------------------------------------------------------------
# BaseApplier: apply_installed_skill & unsync_skills
# ---------------------------------------------------------------------------


class TestBaseApplierDefaults(unittest.TestCase):
    """Test default implementations on a concrete dir-symlink applier (Claude)."""

    def test_apply_installed_skill_returns_false(self):
        """Dir-symlink tools return False — symlink already propagates."""
        from appliers.claude import ClaudeApplier

        applier = ClaudeApplier()
        result = applier.apply_installed_skill("some-skill")
        assert result is False

    def test_unsync_skills_removes_symlink_and_recreates_dir(self, tmp_path=None):
        import tempfile

        from appliers.claude import ClaudeApplier

        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            skill_dir = td / ".claude" / "skills"
            apc_skills = td / ".apc" / "skills"
            apc_skills.mkdir(parents=True)

            # Create the symlink as sync would
            skill_dir.parent.mkdir(parents=True)
            os.symlink(apc_skills, skill_dir)
            assert skill_dir.is_symlink()

            with patch(
                "appliers.claude.ClaudeApplier.SKILL_DIR",
                new_callable=lambda: property(lambda self: skill_dir),
            ):
                applier = ClaudeApplier()
                result = applier.unsync_skills()

            assert result is True
            assert not skill_dir.is_symlink()
            assert skill_dir.is_dir()

    def test_unsync_skills_returns_false_when_no_symlink(self, tmp_path=None):
        import tempfile

        from appliers.claude import ClaudeApplier

        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            skill_dir = td / ".claude" / "skills"
            skill_dir.mkdir(parents=True)  # real dir, not a symlink

            with patch(
                "appliers.claude.ClaudeApplier.SKILL_DIR",
                new_callable=lambda: property(lambda self: skill_dir),
            ):
                applier = ClaudeApplier()
                result = applier.unsync_skills()

            assert result is False

    def test_unsync_skills_returns_false_when_skill_dir_is_none(self):
        from appliers.windsurf import WindsurfApplier

        applier = WindsurfApplier()
        # Windsurf overrides unsync_skills, but test None guard via copilot-like stub
        from appliers.base import BaseApplier

        class NullSkillDirApplier(BaseApplier):
            TOOL_NAME = "null-tool"
            SKILL_DIR = None
            MEMORY_SCHEMA = ""

            @property
            def MEMORY_ALLOWED_BASE(self):
                return Path("/tmp")

            def apply_skills(self, skills, manifest):
                return 0

            def apply_mcp_servers(self, servers, secrets, manifest, override=False):
                return 0

        applier = NullSkillDirApplier()
        assert applier.unsync_skills() is False


# ---------------------------------------------------------------------------
# manifest: record_tool_sync & sync_method
# ---------------------------------------------------------------------------


class TestManifestToolSync(unittest.TestCase):
    def setUp(self):
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        self._home = Path(self._tmp.name)
        self._patcher = patch("appliers.manifest.Path.home", return_value=self._home)
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()
        self._tmp.cleanup()

    def test_sync_method_is_none_before_record(self):
        from appliers.manifest import ToolManifest

        m = ToolManifest("test-tool")
        assert m.sync_method is None

    def test_record_dir_symlink_sets_sync_method(self):
        from appliers.manifest import ToolManifest

        m = ToolManifest("test-tool")
        m.record_dir_sync("/fake/skill_dir", "/fake/target")
        assert m.sync_method == "dir-symlink"

    def test_record_tool_sync_injection(self):
        from appliers.manifest import ToolManifest

        m = ToolManifest("windsurf")
        m.record_tool_sync("injection")
        assert m.sync_method == "injection"

    def test_record_tool_sync_per_file_symlink(self):
        from appliers.manifest import ToolManifest

        m = ToolManifest("github-copilot")
        m.record_tool_sync("per-file-symlink")
        assert m.sync_method == "per-file-symlink"

    def test_sync_method_persists_after_save_reload(self):
        from appliers.manifest import ToolManifest

        m = ToolManifest("github-copilot")
        m.record_tool_sync("per-file-symlink")
        m.save()

        m2 = ToolManifest("github-copilot")
        assert m2.sync_method == "per-file-symlink"


# ---------------------------------------------------------------------------
# WindsurfApplier: injection into global_rules.md
# ---------------------------------------------------------------------------


class TestWindsurfSyncSkillsDir(unittest.TestCase):
    def setUp(self):
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        self.home = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _make_applier(self):
        from appliers.windsurf import WindsurfApplier

        return WindsurfApplier()

    def _rules_path(self):
        return self.home / ".codeium" / "windsurf" / "memories" / "global_rules.md"

    def test_sync_creates_global_rules_with_apc_block(self):
        _make_skills_dir(self.home, "pdf", "frontend-design")

        with (
            patch("appliers.windsurf._windsurf_global_rules", return_value=self._rules_path()),
            patch("skills.get_skills_dir", return_value=self.home / ".apc" / "skills"),
        ):
            applier = self._make_applier()
            result = applier.sync_skills_dir()

        assert result is True
        content = self._rules_path().read_text()
        assert "<!-- apc-skills-start -->" in content
        assert "<!-- apc-skills-end -->" in content
        assert "## APC Skills" in content
        assert "pdf" in content
        assert "frontend-design" in content

    def test_sync_appends_to_existing_rules(self):
        self._rules_path().parent.mkdir(parents=True, exist_ok=True)
        self._rules_path().write_text("# My Global Rules\n\nBe concise.", encoding="utf-8")
        _make_skills_dir(self.home, "pdf")

        with (
            patch("appliers.windsurf._windsurf_global_rules", return_value=self._rules_path()),
            patch("skills.get_skills_dir", return_value=self.home / ".apc" / "skills"),
        ):
            applier = self._make_applier()
            applier.sync_skills_dir()

        content = self._rules_path().read_text()
        assert "# My Global Rules" in content
        assert "Be concise." in content
        assert "<!-- apc-skills-start -->" in content

    def test_sync_replaces_existing_apc_block(self):
        _make_skills_dir(self.home, "pdf")
        self._rules_path().parent.mkdir(parents=True, exist_ok=True)
        self._rules_path().write_text(
            "# Rules\n\n<!-- apc-skills-start -->\n## APC Skills\n- **old-skill**\n<!-- apc-skills-end -->\n",
            encoding="utf-8",
        )

        with (
            patch("appliers.windsurf._windsurf_global_rules", return_value=self._rules_path()),
            patch("skills.get_skills_dir", return_value=self.home / ".apc" / "skills"),
        ):
            applier = self._make_applier()
            applier.sync_skills_dir()

        content = self._rules_path().read_text()
        assert "old-skill" not in content
        assert "pdf" in content
        # Only one start marker
        assert content.count("<!-- apc-skills-start -->") == 1

    def test_apply_installed_skill_regenerates_block(self):
        _make_skills_dir(self.home, "pdf")

        with (
            patch("appliers.windsurf._windsurf_global_rules", return_value=self._rules_path()),
            patch("skills.get_skills_dir", return_value=self.home / ".apc" / "skills"),
        ):
            applier = self._make_applier()
            applier.sync_skills_dir()  # initial sync
            # Add a second skill after initial sync
            _make_skills_dir(self.home, "frontend-design")
            result = applier.apply_installed_skill("frontend-design")

        assert result is True
        content = self._rules_path().read_text()
        assert "pdf" in content
        assert "frontend-design" in content

    def test_unsync_removes_apc_block(self):
        _make_skills_dir(self.home, "pdf")

        with (
            patch("appliers.windsurf._windsurf_global_rules", return_value=self._rules_path()),
            patch("skills.get_skills_dir", return_value=self.home / ".apc" / "skills"),
        ):
            applier = self._make_applier()
            applier.sync_skills_dir()
            result = applier.unsync_skills()

        assert result is True
        content = self._rules_path().read_text()
        assert "<!-- apc-skills-start -->" not in content
        assert "<!-- apc-skills-end -->" not in content
        assert "## APC Skills" not in content

    def test_unsync_preserves_surrounding_content(self):
        self._rules_path().parent.mkdir(parents=True, exist_ok=True)
        self._rules_path().write_text("# Rules\n\nBe concise.", encoding="utf-8")
        _make_skills_dir(self.home, "pdf")

        with (
            patch("appliers.windsurf._windsurf_global_rules", return_value=self._rules_path()),
            patch("skills.get_skills_dir", return_value=self.home / ".apc" / "skills"),
        ):
            applier = self._make_applier()
            applier.sync_skills_dir()
            applier.unsync_skills()

        content = self._rules_path().read_text()
        assert "# Rules" in content
        assert "Be concise." in content

    def test_unsync_returns_false_when_no_block(self):
        self._rules_path().parent.mkdir(parents=True, exist_ok=True)
        self._rules_path().write_text("# Rules\n\nBe concise.", encoding="utf-8")

        with patch("appliers.windsurf._windsurf_global_rules", return_value=self._rules_path()):
            applier = self._make_applier()
            result = applier.unsync_skills()

        assert result is False

    def test_unsync_returns_false_when_no_file(self):
        with patch("appliers.windsurf._windsurf_global_rules", return_value=self._rules_path()):
            applier = self._make_applier()
            result = applier.unsync_skills()

        assert result is False

    def test_sync_empty_skills_dir(self):
        """Sync with no skills still writes a valid (empty) block."""
        skills_dir = self.home / ".apc" / "skills"
        skills_dir.mkdir(parents=True)

        with (
            patch("appliers.windsurf._windsurf_global_rules", return_value=self._rules_path()),
            patch("skills.get_skills_dir", return_value=skills_dir),
        ):
            applier = self._make_applier()
            result = applier.sync_skills_dir()

        assert result is True
        content = self._rules_path().read_text()
        assert "<!-- apc-skills-start -->" in content


# ---------------------------------------------------------------------------
# CopilotApplier: per-file symlinks
# ---------------------------------------------------------------------------


class TestCopilotSyncSkillsDir(unittest.TestCase):
    def setUp(self):
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        self.home = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _make_applier(self):
        from appliers.copilot import CopilotApplier

        applier = CopilotApplier()
        # Override the global instructions dir to use tmp home
        applier._global_instructions_dir = lambda: self.home / ".github" / "instructions"
        return applier

    def test_sync_creates_per_skill_symlinks(self):
        _make_skills_dir(self.home, "pdf", "frontend-design")
        instr_dir = self.home / ".github" / "instructions"

        with patch("skills.get_skills_dir", return_value=self.home / ".apc" / "skills"):
            applier = self._make_applier()
            result = applier.sync_skills_dir()

        assert result is True
        assert (instr_dir / "pdf.instructions.md").is_symlink()
        assert (instr_dir / "frontend-design.instructions.md").is_symlink()

    def test_sync_symlink_points_to_skill_md(self):
        _make_skills_dir(self.home, "pdf")
        instr_dir = self.home / ".github" / "instructions"

        with patch("skills.get_skills_dir", return_value=self.home / ".apc" / "skills"):
            applier = self._make_applier()
            applier.sync_skills_dir()

        link = instr_dir / "pdf.instructions.md"
        target = Path(os.readlink(link))
        assert target == (self.home / ".apc" / "skills" / "pdf" / "SKILL.md").resolve()

    def test_sync_empty_skills_dir(self):
        """Sync with no skills creates an empty instructions dir, returns True."""
        skills_dir = self.home / ".apc" / "skills"
        skills_dir.mkdir(parents=True)
        instr_dir = self.home / ".github" / "instructions"

        with patch("skills.get_skills_dir", return_value=skills_dir):
            applier = self._make_applier()
            result = applier.sync_skills_dir()

        assert result is True
        assert instr_dir.is_dir()

    def test_sync_missing_skill_md_skipped(self):
        """A skill dir without SKILL.md is silently skipped."""
        skills_dir = self.home / ".apc" / "skills"
        (skills_dir / "incomplete-skill").mkdir(parents=True)
        # No SKILL.md inside

        instr_dir = self.home / ".github" / "instructions"
        with patch("skills.get_skills_dir", return_value=skills_dir):
            applier = self._make_applier()
            applier.sync_skills_dir()

        assert not list(instr_dir.glob("*.instructions.md"))

    def test_apply_installed_skill_creates_one_symlink(self):
        _make_skills_dir(self.home, "pdf")

        with patch("skills.get_skills_dir", return_value=self.home / ".apc" / "skills"):
            applier = self._make_applier()
            result = applier.apply_installed_skill("pdf")

        instr_dir = self.home / ".github" / "instructions"
        assert result is True
        assert (instr_dir / "pdf.instructions.md").is_symlink()

    def test_apply_installed_skill_returns_false_when_skill_missing(self):
        skills_dir = self.home / ".apc" / "skills"
        skills_dir.mkdir(parents=True)

        with patch("skills.get_skills_dir", return_value=skills_dir):
            applier = self._make_applier()
            result = applier.apply_installed_skill("nonexistent")

        assert result is False

    def test_apply_installed_skill_overwrites_existing_link(self):
        """Re-applying an existing skill replaces the symlink cleanly."""
        _make_skills_dir(self.home, "pdf")
        instr_dir = self.home / ".github" / "instructions"
        instr_dir.mkdir(parents=True)
        stale = instr_dir / "pdf.instructions.md"
        stale.write_text("stale", encoding="utf-8")

        with patch("skills.get_skills_dir", return_value=self.home / ".apc" / "skills"):
            applier = self._make_applier()
            applier.apply_installed_skill("pdf")

        assert stale.is_symlink()

    def test_unsync_removes_all_instruction_symlinks(self):
        _make_skills_dir(self.home, "pdf", "frontend-design")

        with patch("skills.get_skills_dir", return_value=self.home / ".apc" / "skills"):
            applier = self._make_applier()
            applier.sync_skills_dir()
            result = applier.unsync_skills()

        instr_dir = self.home / ".github" / "instructions"
        assert result is True
        assert list(instr_dir.glob("*.instructions.md")) == []

    def test_unsync_only_removes_symlinks_not_real_files(self):
        """unsync_skills only removes symlinks; real .instructions.md files are untouched."""
        instr_dir = self.home / ".github" / "instructions"
        instr_dir.mkdir(parents=True)
        real_file = instr_dir / "manual.instructions.md"
        real_file.write_text("# Manual instructions", encoding="utf-8")

        _make_skills_dir(self.home, "pdf")
        with patch("skills.get_skills_dir", return_value=self.home / ".apc" / "skills"):
            applier = self._make_applier()
            applier.sync_skills_dir()
            applier.unsync_skills()

        assert real_file.exists()
        assert not real_file.is_symlink()

    def test_unsync_returns_false_when_nothing_to_remove(self):
        instr_dir = self.home / ".github" / "instructions"
        instr_dir.mkdir(parents=True)

        applier = self._make_applier()
        result = applier.unsync_skills()

        assert result is False

    def test_unsync_returns_false_when_dir_missing(self):
        applier = self._make_applier()
        result = applier.unsync_skills()

        assert result is False


# ---------------------------------------------------------------------------
# install._propagate_to_synced_tools: hits ALL synced tools
# ---------------------------------------------------------------------------


class TestPropagateToSyncedTools(unittest.TestCase):
    def test_calls_apply_installed_skill_for_all_synced(self):
        """_propagate_to_synced_tools calls apply_installed_skill for each synced tool."""
        from install import _propagate_to_synced_tools

        mock_windsurf = MagicMock()
        mock_copilot = MagicMock()
        mock_cursor = MagicMock()

        not_synced_manifest = MagicMock()
        not_synced_manifest.is_first_sync = True

        synced_manifest = MagicMock()
        synced_manifest.is_first_sync = False

        def fake_manifest(name):
            return not_synced_manifest if name == "claude-code" else synced_manifest

        def fake_get_applier(name):
            return {
                "windsurf": mock_windsurf,
                "github-copilot": mock_copilot,
                "cursor": mock_cursor,
            }[name]

        # ToolManifest is lazily imported inside _propagate_to_synced_tools —
        # patch at the source module, not on install.
        with (
            patch(
                "install.detect_installed_tools",
                return_value=["windsurf", "github-copilot", "cursor", "claude-code"],
            ),
            patch("appliers.manifest.ToolManifest", side_effect=fake_manifest),
            patch("install.get_applier", side_effect=fake_get_applier),
        ):
            _propagate_to_synced_tools("new-skill")

        mock_windsurf.apply_installed_skill.assert_called_once_with("new-skill")
        mock_copilot.apply_installed_skill.assert_called_once_with("new-skill")
        mock_cursor.apply_installed_skill.assert_called_once_with("new-skill")

    def test_skips_unsynced_tools(self):
        """Tools with is_first_sync=True are skipped entirely."""
        from install import _propagate_to_synced_tools

        not_synced = MagicMock()
        not_synced.is_first_sync = True

        with (
            patch("install.detect_installed_tools", return_value=["cursor"]),
            patch("appliers.manifest.ToolManifest", return_value=not_synced),
            patch("install.get_applier") as mock_get,
        ):
            _propagate_to_synced_tools("some-skill")

        mock_get.assert_not_called()

    def test_exception_in_applier_does_not_abort(self):
        """An error in one applier does not prevent others from running."""
        from install import _propagate_to_synced_tools

        mock_ok = MagicMock()
        mock_bad = MagicMock()
        mock_bad.apply_installed_skill.side_effect = RuntimeError("boom")

        synced = MagicMock()
        synced.is_first_sync = False

        def fake_get_applier(name):
            return mock_bad if name == "windsurf" else mock_ok

        with (
            patch("install.detect_installed_tools", return_value=["windsurf", "cursor"]),
            patch("appliers.manifest.ToolManifest", return_value=synced),
            patch("install.get_applier", side_effect=fake_get_applier),
        ):
            # Should not raise
            _propagate_to_synced_tools("some-skill")

        mock_ok.apply_installed_skill.assert_called_once_with("some-skill")


# ---------------------------------------------------------------------------
# apc unsync command (CLI)
# ---------------------------------------------------------------------------


class TestUnsyncCommand(unittest.TestCase):
    def setUp(self):
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        self.home = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _runner(self):
        from click.testing import CliRunner

        return CliRunner()

    def _cli(self):
        from unsync import unsync

        return unsync

    def test_unsync_single_tool(self):
        mock_applier = MagicMock()
        mock_applier.unsync_skills.return_value = True
        mock_applier.get_manifest.return_value = MagicMock(_data={}, save=MagicMock())

        synced_manifest = MagicMock()
        synced_manifest.is_first_sync = False

        with (
            patch("unsync.detect_installed_tools", return_value=["cursor", "windsurf"]),
            patch("unsync.ToolManifest", return_value=synced_manifest),
            patch("unsync.get_applier", return_value=mock_applier),
        ):
            result = self._runner().invoke(self._cli(), ["cursor", "--yes"])

        assert result.exit_code == 0, result.output
        assert "unsynced" in result.output or "nothing to undo" in result.output

    def test_unsync_all(self):
        mock_applier = MagicMock()
        mock_applier.unsync_skills.return_value = True
        mock_applier.get_manifest.return_value = MagicMock(_data={}, save=MagicMock())

        synced = MagicMock()
        synced.is_first_sync = False

        with (
            patch("unsync.detect_installed_tools", return_value=["cursor", "windsurf"]),
            patch("unsync.ToolManifest", return_value=synced),
            patch("unsync.get_applier", return_value=mock_applier),
        ):
            result = self._runner().invoke(self._cli(), ["--all", "--yes"])

        assert result.exit_code == 0, result.output

    def test_unsync_skips_unsynced_tools(self):
        not_synced = MagicMock()
        not_synced.is_first_sync = True

        with (
            patch("unsync.detect_installed_tools", return_value=["cursor"]),
            patch("unsync.ToolManifest", return_value=not_synced),
            patch("unsync.get_applier") as mock_get,
        ):
            result = self._runner().invoke(self._cli(), ["cursor", "--yes"])

        assert result.exit_code == 0
        mock_get.assert_not_called()

    def test_unsync_no_args_exits_nonzero(self):
        result = self._runner().invoke(self._cli(), [])
        assert result.exit_code != 0

    def test_unsync_nothing_to_undo_message(self):
        mock_applier = MagicMock()
        mock_applier.unsync_skills.return_value = False  # nothing undone
        mock_applier.get_manifest.return_value = MagicMock(_data={}, save=MagicMock())

        synced = MagicMock()
        synced.is_first_sync = False

        with (
            patch("unsync.detect_installed_tools", return_value=["cursor"]),
            patch("unsync.ToolManifest", return_value=synced),
            patch("unsync.get_applier", return_value=mock_applier),
        ):
            result = self._runner().invoke(self._cli(), ["cursor", "--yes"])

        assert result.exit_code == 0
        assert "nothing to undo" in result.output

    def test_unsync_clears_dir_sync_from_manifest(self):
        mock_applier = MagicMock()
        mock_applier.unsync_skills.return_value = True
        manifest_data = {"dir_sync": {"sync_method": "dir-symlink", "synced_at": "2026-03-08"}}
        mock_manifest = MagicMock(_data=manifest_data, save=MagicMock())
        mock_applier.get_manifest.return_value = mock_manifest

        synced = MagicMock()
        synced.is_first_sync = False

        with (
            patch("unsync.detect_installed_tools", return_value=["cursor"]),
            patch("unsync.ToolManifest", return_value=synced),
            patch("unsync.get_applier", return_value=mock_applier),
        ):
            self._runner().invoke(self._cli(), ["cursor", "--yes"])

        assert "dir_sync" not in manifest_data
        mock_manifest.save.assert_called_once()


# ---------------------------------------------------------------------------
# apc install: --target flag removed
# ---------------------------------------------------------------------------


class TestInstallNoTargetFlag(unittest.TestCase):
    def _runner(self):
        from click.testing import CliRunner

        return CliRunner()

    def _cli(self):
        from install import install

        return install

    def test_target_flag_rejected(self):
        result = self._runner().invoke(self._cli(), ["owner/repo", "--target", "cursor"])
        assert result.exit_code != 0
        assert "no such option" in result.output.lower() or "Error" in result.output

    def test_short_t_flag_rejected(self):
        result = self._runner().invoke(self._cli(), ["owner/repo", "-t", "cursor"])
        assert result.exit_code != 0


if __name__ == "__main__":
    unittest.main()
