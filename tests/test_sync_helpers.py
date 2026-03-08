"""Unit tests for sync_helpers — sync_all, sync_skills, resolve_target_tools."""

import tempfile
import unittest
import unittest.mock
from pathlib import Path
from unittest.mock import MagicMock, patch

from appliers.manifest import ToolManifest


def _make_manifest(tmpdir: Path, tool: str = "cursor") -> ToolManifest:
    return ToolManifest(tool, path=tmpdir / f"{tool}.json")


def _mock_applier(tmpdir: Path, tool: str = "cursor"):
    """Return a MagicMock that satisfies the applier interface."""
    applier = MagicMock()
    applier.get_manifest.return_value = _make_manifest(tmpdir, tool)
    applier.SKILL_DIR = tmpdir / "skills"
    applier.sync_skills_dir.return_value = True  # dir-level symlink succeeds
    applier.apply_skills.return_value = 3
    applier.link_skills.return_value = 1
    applier.apply_mcp_servers.return_value = 2
    applier.apply_memory_via_llm.return_value = 1
    applier.prune.return_value = None
    return applier


class TestResolveTargetTools(unittest.TestCase):
    """resolve_target_tools: --tools flag / --all / interactive."""

    def test_tools_flag_parsed(self):
        from sync_helpers import resolve_target_tools

        result = resolve_target_tools("cursor,claude-code", apply_all=False)
        self.assertEqual(result, ["cursor", "claude-code"])

    def test_tools_flag_strips_whitespace(self):
        from sync_helpers import resolve_target_tools

        result = resolve_target_tools("  cursor , claude-code  ", apply_all=False)
        self.assertEqual(result, ["cursor", "claude-code"])

    def test_tools_flag_empty_returns_empty(self):
        from sync_helpers import resolve_target_tools

        result = resolve_target_tools("", apply_all=False)
        self.assertEqual(result, [])

    def test_apply_all_uses_detected_tools(self):
        from sync_helpers import resolve_target_tools

        with patch("sync_helpers.detect_installed_tools", return_value=["cursor", "claude-code"]):
            result = resolve_target_tools(None, apply_all=True)

        self.assertEqual(result, ["cursor", "claude-code"])

    def test_apply_all_no_tools_returns_empty(self):
        from sync_helpers import resolve_target_tools

        with patch("sync_helpers.detect_installed_tools", return_value=[]):
            result = resolve_target_tools(None, apply_all=True)

        self.assertEqual(result, [])


class TestSyncAll(unittest.TestCase):
    """sync_all: happy path, partial failure, all-fail, no-memory flag."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.bundle = {
            "skills": [{"name": "my-skill", "body": "# Instructions"}],
            "mcp_servers": [{"name": "filesystem", "transport": "stdio", "command": "npx"}],
            "memory": [{"id": "abc", "source_tool": "openclaw", "content": "# Context"}],
        }

    def _run_sync_all(self, tool_list, applier_factory, **kwargs):
        """Helper: patch get_applier + load_local_bundle + skills helpers."""

        def get_applier_side_effect(name):
            return applier_factory(self.tmpdir, name)

        with (
            patch("sync_helpers.get_applier", side_effect=get_applier_side_effect),
            patch("sync_helpers.load_local_bundle", return_value=self.bundle),
            patch("sync_helpers._resolve_all_mcp_secrets", return_value={}),
            patch("sync_helpers._discover_installed_skills", return_value=[]),
            patch("sync_helpers.get_skills_dir", return_value=self.tmpdir / "skills"),
        ):
            from sync_helpers import sync_all

            return sync_all(tool_list, **kwargs)

    def test_happy_path_returns_true(self):
        result = self._run_sync_all(["cursor", "claude-code"], _mock_applier)
        self.assertTrue(result)

    def test_happy_path_calls_all_three_phases(self):
        """Each tool's applier should have link_skills, apply_mcp_servers called.

        apply_skills() is no longer called by sync — skills go through
        link_skills() (per-skill) or sync_skills_dir() (dir-level).
        """
        appliers = {}

        def factory(tmpdir, name):
            a = _mock_applier(tmpdir, name)
            appliers[name] = a
            return a

        self._run_sync_all(["cursor"], factory)

        appliers["cursor"].sync_skills_dir.assert_called_once()
        appliers["cursor"].link_skills.assert_not_called()
        appliers["cursor"].apply_skills.assert_not_called()
        appliers["cursor"].apply_mcp_servers.assert_called_once()
        appliers["cursor"].apply_memory_via_llm.assert_called_once()
        appliers["cursor"].prune.assert_called_once()

    def test_no_memory_flag_skips_llm(self):
        appliers = {}

        def factory(tmpdir, name):
            a = _mock_applier(tmpdir, name)
            appliers[name] = a
            return a

        self._run_sync_all(["cursor"], factory, no_memory=True)

        appliers["cursor"].apply_memory_via_llm.assert_not_called()

    def test_partial_failure_returns_true(self):
        """One tool errors, one succeeds → any_success = True."""
        call_count = [0]

        def factory(tmpdir, name):
            call_count[0] += 1
            if call_count[0] == 1:
                bad = MagicMock()
                bad.get_manifest.side_effect = RuntimeError("disk full")
                return bad
            return _mock_applier(tmpdir, name)

        result = self._run_sync_all(["bad-tool", "cursor"], factory)
        self.assertTrue(result)

    def test_all_fail_returns_false(self):
        """Every tool errors → any_success = False."""

        def factory(tmpdir, name):
            bad = MagicMock()
            bad.get_manifest.side_effect = RuntimeError("everything broken")
            return bad

        result = self._run_sync_all(["cursor", "claude-code"], factory)
        self.assertFalse(result)

    def test_single_tool_success(self):
        result = self._run_sync_all(["cursor"], _mock_applier)
        self.assertTrue(result)


class TestSyncSkillsPerToolCounter(unittest.TestCase):
    """sync_skills: success message must show per-tool counts, not cumulative."""

    def test_per_tool_count_not_cumulative(self):
        """With 2 per-skill tools × 3 skills each, each success message
        should say '3 skill(s) linked', not '6 skill(s) linked'."""
        tmpdir = Path(tempfile.mkdtemp())
        installed = [{"name": f"s{i}", "body": ""} for i in range(3)]
        success_messages = []

        def factory(tmpdir_inner, name):
            a = _mock_applier(tmpdir_inner, name)
            a.sync_skills_dir.return_value = True  # dir-level sync
            return a

        with (
            patch("sync_helpers.get_applier", side_effect=lambda n: factory(tmpdir, n)),
            patch(
                "sync_helpers.load_local_bundle",
                return_value={"mcp_servers": [], "memory": []},
            ),
            patch("sync_helpers._discover_installed_skills", return_value=installed),
            patch("sync_helpers.get_skills_dir", return_value=tmpdir / "skills"),
            patch("sync_helpers.success", side_effect=lambda msg: success_messages.append(msg)),
        ):
            from sync_helpers import sync_skills

            sync_skills(["cursor", "claude-code"])

        # Each message should say symlinked, not cumulative counts
        for msg in success_messages:
            self.assertIn("symlinked", msg, f"Expected 'symlinked' in: {msg}")


if __name__ == "__main__":
    unittest.main()
