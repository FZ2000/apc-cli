"""Tests for --dry-run on apc collect (#25) and apc sync (#24).

apc collect --dry-run: previews what would be collected without writing.
apc sync --dry-run:    previews file paths per tool without writing.
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from click.testing import CliRunner

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cli():
    from main import cli

    return cli


def _runner():
    return CliRunner()


def _mock_extractor(skills=None, mcp=None, memory=None):
    """Return a MagicMock extractor with canned data."""
    ext = MagicMock()
    ext.extract_skills.return_value = skills or []
    ext.extract_mcp_servers.return_value = mcp or []
    ext.extract_memory.return_value = memory or []
    return ext


# ---------------------------------------------------------------------------
# apc collect --dry-run (#25)
# ---------------------------------------------------------------------------


class TestCollectDryRun(unittest.TestCase):
    """collect --dry-run must preview without touching the cache."""

    def _invoke(self, skills=None, mcp=None, memory=None, extra_args=None):
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            cache_dir = td / ".apc" / "cache"
            extractor = _mock_extractor(
                skills=skills or [{"name": "pdf", "source_tool": "claude-code", "body": "# PDF"}],
                mcp=mcp
                or [{"name": "test-mcp", "source_tool": "cursor", "command": "npx", "args": []}],
                memory=memory or [],
            )
            args = ["collect", "--dry-run", "--yes"] + (extra_args or [])
            with (
                patch("collect.detect_installed_tools", return_value=["claude-code"]),
                patch("collect.get_extractor", return_value=extractor),
                patch("cache.get_cache_dir", return_value=cache_dir),
            ):
                result = _runner().invoke(_cli(), args)
            return result, cache_dir

    def test_dry_run_flag_accepted(self):
        result, _ = self._invoke()
        assert result.exit_code == 0, result.output

    def test_dry_run_shows_cache_paths(self):
        result, _ = self._invoke()
        # Paths may wrap across lines in rich output; check for filename substrings
        flat = result.output.replace("\n", " ")
        assert "skills.j" in flat  # skills.json (may wrap)
        assert "mcp.json" in flat
        assert "memory.j" in flat  # memory.json (may wrap)

    def test_dry_run_shows_skill_count(self):
        result, _ = self._invoke(
            skills=[
                {"name": "pdf", "source_tool": "claude-code", "body": "# PDF"},
                {"name": "sk", "source_tool": "claude-code", "body": "# SK"},
            ]
        )
        assert "2 skills" in result.output

    def test_dry_run_shows_mcp_count(self):
        result, _ = self._invoke(
            mcp=[
                {"name": "mcp-a", "source_tool": "cursor", "command": "npx", "args": []},
                {"name": "mcp-b", "source_tool": "cursor", "command": "npx", "args": []},
                {"name": "mcp-c", "source_tool": "cursor", "command": "npx", "args": []},
            ]
        )
        assert "3 MCP" in result.output

    def test_dry_run_lists_skill_names(self):
        result, _ = self._invoke(
            skills=[{"name": "pdf", "source_tool": "claude-code", "body": "# PDF"}]
        )
        assert "pdf" in result.output

    def test_dry_run_does_not_write_cache(self):
        """Cache files must NOT be created when --dry-run is used."""
        result, cache_dir = self._invoke()
        assert result.exit_code == 0, result.output
        assert not (cache_dir / "skills.json").exists(), "skills.json written in dry-run"
        assert not (cache_dir / "mcp.json").exists(), "mcp.json written in dry-run"
        assert not (cache_dir / "memory.json").exists(), "memory.json written in dry-run"

    def test_dry_run_no_files_written_message(self):
        result, _ = self._invoke(skills=[], mcp=[], memory=[])
        assert "No files written" in result.output or "dry-run" in result.output.lower()

    def test_dry_run_memory_entries_listed(self):
        mem = [{"source_tool": "claude-code", "source_file": "CLAUDE.md", "content": "Some rule"}]
        result, _ = self._invoke(memory=mem)
        assert "claude-code" in result.output or "CLAUDE.md" in result.output


# ---------------------------------------------------------------------------
# apc sync --dry-run (#24)
# ---------------------------------------------------------------------------


class TestSyncDryRun(unittest.TestCase):
    """sync --dry-run must preview file paths per tool without writing."""

    def _invoke_sync_dry(self, tools="cursor"):
        mock_bundle = {
            "skills": [{"name": "pdf", "source_tool": "claude-code", "body": "# PDF"}],
            "mcp_servers": [{"name": "test-mcp", "command": "npx", "args": []}],
            "memory": [],
        }
        with (
            patch("main.load_local_bundle", return_value=mock_bundle),
            patch("main.count_installed_skills", return_value=1),
            patch("main.resolve_target_tools", return_value=[tools]),
        ):
            return _runner().invoke(_cli(), ["sync", "--dry-run", "--yes"])

    def test_dry_run_flag_accepted(self):
        result = self._invoke_sync_dry()
        assert result.exit_code == 0, result.output

    def test_dry_run_shows_no_files_written(self):
        result = self._invoke_sync_dry()
        assert "No files written" in result.output or "dry-run" in result.output.lower()

    def test_dry_run_shows_tool_name(self):
        result = self._invoke_sync_dry(tools="cursor")
        assert "cursor" in result.output

    def test_dry_run_does_not_call_sync_all(self):
        """sync_all must not be called in dry-run mode."""
        mock_bundle = {
            "skills": [{"name": "pdf", "source_tool": "claude-code", "body": "# PDF"}],
            "mcp_servers": [],
            "memory": [],
        }
        with (
            patch("main.load_local_bundle", return_value=mock_bundle),
            patch("main.count_installed_skills", return_value=1),
            patch("main.resolve_target_tools", return_value=["cursor"]),
            patch("main.sync_all") as mock_sync,
        ):
            _runner().invoke(_cli(), ["sync", "--dry-run", "--yes"])

        mock_sync.assert_not_called()
