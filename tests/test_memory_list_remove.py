"""Tests for apc memory list (rich tables, #21) and apc memory remove (#48).

Coverage:
  memory list:
    - empty cache → helpful message
    - collected file entries render in "Collected Files" table
    - manual entries render in "Manual Entries" table
    - legacy entries render in "Legacy Entries" table
    - --tool filter: matching entries shown, non-matching filtered out
    - --tool filter: no match → helpful message
    - total count footer
    - long content truncated to 80 chars
    - size display: bytes vs KB

  memory remove:
    - --all: clears cache, prints count
    - --all -y: skips confirmation
    - --all: cancel on prompt keeps cache intact
    - --tool: removes matching entries only
    - --tool: no match → helpful message
    - --tool -y: skips confirmation
    - by ID prefix: removes correct entry
    - by ID prefix: no match → helpful message
    - by ID prefix: ambiguous prefix → lists matches, no removal
    - by ID prefix -y: skips confirmation
    - empty cache → helpful message for all modes
    - interactive mode: valid selection removes entry
    - interactive mode: 'q' cancels
"""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from click.testing import CliRunner

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def cli():
    from main import cli

    return cli


def _raw_file_entry(
    name="CLAUDE.md", tool="claude-code", content="Use TypeScript.", eid="aabbccdd11223344"
):
    return {
        "id": eid,
        "source_tool": tool,
        "source_file": name,
        "label": f"{tool}/{name}",
        "content": content,
        "collected_at": "2026-03-01T00:00:00+00:00",
    }


def _manual_entry(
    text="Always use strict mode",
    category="preference",
    eid="1122334455667788",
):
    return {
        "id": eid,
        "source_tool": "manual",
        "source_file": "memory_add",
        "label": f"Manual [{category}]",
        "category": category,
        "content": text,
        "collected_at": "2026-03-01T00:00:00+00:00",
    }


def _legacy_entry(content="Old rule", category="preference"):
    return {
        "entry_id": "legacy-001",
        "category": category,
        "source": "old-tool",
        "content": content,
    }


# ---------------------------------------------------------------------------
# apc memory list
# ---------------------------------------------------------------------------


class TestMemoryList:
    def test_empty_cache_shows_message(self, runner, cli):
        with patch("memory.load_memory", return_value=[]):
            result = runner.invoke(cli, ["memory", "list"])
        assert result.exit_code == 0
        assert "No memory entries" in result.output

    def test_collected_files_table_shown(self, runner, cli):
        entries = [_raw_file_entry()]
        with patch("memory.load_memory", return_value=entries):
            result = runner.invoke(cli, ["memory", "list"])
        assert result.exit_code == 0
        assert "Collected Files" in result.output
        assert "claude-code" in result.output
        assert "CLAUDE.md" in result.output

    def test_manual_entries_table_shown(self, runner, cli):
        entries = [_manual_entry()]
        with patch("memory.load_memory", return_value=entries):
            result = runner.invoke(cli, ["memory", "list"])
        assert result.exit_code == 0
        assert "Manual Entries" in result.output
        assert "preference" in result.output
        assert "strict mode" in result.output

    def test_legacy_entries_table_shown(self, runner, cli):
        entries = [_legacy_entry()]
        with patch("memory.load_memory", return_value=entries):
            result = runner.invoke(cli, ["memory", "list"])
        assert result.exit_code == 0
        assert "Legacy Entries" in result.output
        assert "Old rule" in result.output

    def test_all_three_tables_shown_together(self, runner, cli):
        entries = [_raw_file_entry(), _manual_entry(), _legacy_entry()]
        with patch("memory.load_memory", return_value=entries):
            result = runner.invoke(cli, ["memory", "list"])
        assert result.exit_code == 0
        assert "Collected Files" in result.output
        assert "Manual Entries" in result.output
        assert "Legacy Entries" in result.output

    def test_total_count_shown(self, runner, cli):
        entries = [_raw_file_entry(), _manual_entry()]
        with patch("memory.load_memory", return_value=entries):
            result = runner.invoke(cli, ["memory", "list"])
        assert result.exit_code == 0
        assert "2 total entries" in result.output

    def test_tool_filter_shows_matching(self, runner, cli):
        entries = [
            _raw_file_entry(tool="claude-code", eid="aaaaaaaabbbbbbbb"),
            _raw_file_entry(tool="cursor", name="rules.md", eid="ccccccccdddddddd"),
        ]
        with patch("memory.load_memory", return_value=entries):
            result = runner.invoke(cli, ["memory", "list", "--tool", "claude-code"])
        assert result.exit_code == 0
        assert "claude-code" in result.output
        assert "rules.md" not in result.output

    def test_tool_filter_no_match_shows_message(self, runner, cli):
        entries = [_raw_file_entry(tool="claude-code")]
        with patch("memory.load_memory", return_value=entries):
            result = runner.invoke(cli, ["memory", "list", "--tool", "cursor"])
        assert result.exit_code == 0
        assert "No memory entries for tool 'cursor'" in result.output

    def test_content_preview_truncated_at_80_chars(self, runner, cli):
        long_text = "A" * 100
        entries = [_manual_entry(text=long_text)]
        with patch("memory.load_memory", return_value=entries):
            result = runner.invoke(cli, ["memory", "list"])
        assert result.exit_code == 0
        # Content should be truncated — ellipsis present, not the full 100 chars
        assert "A" * 81 not in result.output

    def test_size_shown_in_bytes(self, runner, cli):
        entries = [_raw_file_entry(content="Hi")]
        with patch("memory.load_memory", return_value=entries):
            result = runner.invoke(cli, ["memory", "list"])
        assert result.exit_code == 0
        assert " B" in result.output

    def test_size_shown_in_kb(self, runner, cli):
        entries = [_raw_file_entry(content="x" * 2000)]
        with patch("memory.load_memory", return_value=entries):
            result = runner.invoke(cli, ["memory", "list"])
        assert result.exit_code == 0
        assert "KB" in result.output

    def test_id_prefix_shown(self, runner, cli):
        entries = [_raw_file_entry(eid="deadbeef12345678")]
        with patch("memory.load_memory", return_value=entries):
            result = runner.invoke(cli, ["memory", "list"])
        assert result.exit_code == 0
        assert "deadbeef" in result.output  # first 8 chars of ID


# ---------------------------------------------------------------------------
# apc memory remove — empty cache
# ---------------------------------------------------------------------------


class TestMemoryRemoveEmptyCache:
    def test_all_empty(self, runner, cli):
        with patch("memory.load_memory", return_value=[]):
            result = runner.invoke(cli, ["memory", "remove", "--all", "-y"])
        assert result.exit_code == 0
        assert "No memory entries" in result.output

    def test_tool_empty(self, runner, cli):
        with patch("memory.load_memory", return_value=[]):
            result = runner.invoke(cli, ["memory", "remove", "--tool", "cursor", "-y"])
        assert result.exit_code == 0
        assert "No memory entries" in result.output

    def test_id_empty(self, runner, cli):
        with patch("memory.load_memory", return_value=[]):
            result = runner.invoke(cli, ["memory", "remove", "abc123", "-y"])
        assert result.exit_code == 0
        assert "No memory entries" in result.output


# ---------------------------------------------------------------------------
# apc memory remove --all
# ---------------------------------------------------------------------------


class TestMemoryRemoveAll:
    def test_all_clears_cache(self, runner, cli):
        entries = [_raw_file_entry(), _manual_entry()]
        saved = []
        with (
            patch("memory.load_memory", return_value=entries),
            patch("memory.save_memory", side_effect=lambda x: saved.append(x)),
        ):
            result = runner.invoke(cli, ["memory", "remove", "--all", "-y"])
        assert result.exit_code == 0
        assert saved and saved[-1] == []

    def test_all_reports_count(self, runner, cli):
        entries = [_raw_file_entry(), _manual_entry()]
        with (
            patch("memory.load_memory", return_value=entries),
            patch("memory.save_memory"),
        ):
            result = runner.invoke(cli, ["memory", "remove", "--all", "-y"])
        assert "Removed 2" in result.output

    def test_all_cancel_keeps_cache(self, runner, cli):
        entries = [_raw_file_entry()]
        saved = []
        with (
            patch("memory.load_memory", return_value=entries),
            patch("memory.save_memory", side_effect=lambda x: saved.append(x)),
        ):
            result = runner.invoke(cli, ["memory", "remove", "--all"], input="n\n")
        assert result.exit_code == 0
        assert "Cancelled" in result.output
        assert not saved  # save_memory must NOT have been called

    def test_all_confirm_y_proceeds(self, runner, cli):
        entries = [_raw_file_entry()]
        saved = []
        with (
            patch("memory.load_memory", return_value=entries),
            patch("memory.save_memory", side_effect=lambda x: saved.append(x)),
        ):
            result = runner.invoke(cli, ["memory", "remove", "--all"], input="y\n")
        assert result.exit_code == 0
        assert saved and saved[-1] == []


# ---------------------------------------------------------------------------
# apc memory remove --tool
# ---------------------------------------------------------------------------


class TestMemoryRemoveTool:
    def test_removes_matching_tool_entries(self, runner, cli):
        entries = [
            _raw_file_entry(tool="claude-code", eid="aaaa000011111111"),
            _raw_file_entry(tool="cursor", name="rules.md", eid="bbbb000022222222"),
        ]
        saved = []
        with (
            patch("memory.load_memory", return_value=entries),
            patch("memory.save_memory", side_effect=lambda x: saved.append(x)),
        ):
            result = runner.invoke(cli, ["memory", "remove", "--tool", "claude-code", "-y"])
        assert result.exit_code == 0
        assert saved
        remaining = saved[-1]
        assert all(e["source_tool"] != "claude-code" for e in remaining)
        assert any(e["source_tool"] == "cursor" for e in remaining)

    def test_reports_removal_count(self, runner, cli):
        entries = [
            _raw_file_entry(tool="openclaw", eid="cccc000033333333"),
            _raw_file_entry(tool="openclaw", name="STYLE.md", eid="dddd000044444444"),
        ]
        with (
            patch("memory.load_memory", return_value=entries),
            patch("memory.save_memory"),
        ):
            result = runner.invoke(cli, ["memory", "remove", "--tool", "openclaw", "-y"])
        assert "Removed 2" in result.output
        assert "openclaw" in result.output

    def test_no_match_shows_message(self, runner, cli):
        entries = [_raw_file_entry(tool="claude-code")]
        with (
            patch("memory.load_memory", return_value=entries),
            patch("memory.save_memory"),
        ):
            result = runner.invoke(cli, ["memory", "remove", "--tool", "gemini-cli", "-y"])
        assert result.exit_code == 0
        assert "No entries found for tool 'gemini-cli'" in result.output

    def test_cancel_keeps_cache(self, runner, cli):
        entries = [_raw_file_entry(tool="cursor")]
        saved = []
        with (
            patch("memory.load_memory", return_value=entries),
            patch("memory.save_memory", side_effect=lambda x: saved.append(x)),
        ):
            result = runner.invoke(cli, ["memory", "remove", "--tool", "cursor"], input="n\n")
        assert "Cancelled" in result.output
        assert not saved


# ---------------------------------------------------------------------------
# apc memory remove <entry_id>
# ---------------------------------------------------------------------------


class TestMemoryRemoveById:
    def test_removes_by_id_prefix(self, runner, cli):
        entries = [
            _raw_file_entry(eid="aabbccdd11223344"),
            _raw_file_entry(tool="cursor", name="rules.md", eid="eeff00001122ffee"),
        ]
        saved = []
        with (
            patch("memory.load_memory", return_value=entries),
            patch("memory.save_memory", side_effect=lambda x: saved.append(x)),
        ):
            result = runner.invoke(cli, ["memory", "remove", "aabbccdd", "-y"])
        assert result.exit_code == 0
        assert saved
        remaining = saved[-1]
        assert len(remaining) == 1
        assert remaining[0]["id"] == "eeff00001122ffee"

    def test_no_match_shows_message(self, runner, cli):
        entries = [_raw_file_entry(eid="aabbccdd11223344")]
        with (
            patch("memory.load_memory", return_value=entries),
            patch("memory.save_memory"),
        ):
            result = runner.invoke(cli, ["memory", "remove", "ffffff", "-y"])
        assert "No entry found" in result.output

    def test_ambiguous_prefix_lists_matches(self, runner, cli):
        entries = [
            _raw_file_entry(eid="aabbccdd00000001"),
            _raw_file_entry(tool="cursor", eid="aabbccdd00000002"),
        ]
        with (
            patch("memory.load_memory", return_value=entries),
            patch("memory.save_memory"),
        ):
            result = runner.invoke(cli, ["memory", "remove", "aabbccdd", "-y"])
        assert "Ambiguous" in result.output or "2 entries match" in result.output

    def test_ambiguous_does_not_remove(self, runner, cli):
        entries = [
            _raw_file_entry(eid="aabbccdd00000001"),
            _raw_file_entry(tool="cursor", eid="aabbccdd00000002"),
        ]
        saved = []
        with (
            patch("memory.load_memory", return_value=entries),
            patch("memory.save_memory", side_effect=lambda x: saved.append(x)),
        ):
            runner.invoke(cli, ["memory", "remove", "aabbccdd", "-y"])
        assert not saved

    def test_cancel_by_id_keeps_cache(self, runner, cli):
        entries = [_raw_file_entry(eid="aabbccdd11223344")]
        saved = []
        with (
            patch("memory.load_memory", return_value=entries),
            patch("memory.save_memory", side_effect=lambda x: saved.append(x)),
        ):
            result = runner.invoke(cli, ["memory", "remove", "aabbccdd"], input="n\n")
        assert "Cancelled" in result.output
        assert not saved

    def test_reports_removal_success(self, runner, cli):
        entries = [_raw_file_entry(eid="aabbccdd11223344")]
        with (
            patch("memory.load_memory", return_value=entries),
            patch("memory.save_memory"),
        ):
            result = runner.invoke(cli, ["memory", "remove", "aabbccdd", "-y"])
        assert "Removed entry" in result.output


# ---------------------------------------------------------------------------
# apc memory remove — interactive mode (no args)
# ---------------------------------------------------------------------------


class TestMemoryRemoveInteractive:
    def test_interactive_valid_selection_removes(self, runner, cli):
        entries = [
            _raw_file_entry(eid="aabbccdd11223344"),
            _raw_file_entry(tool="cursor", name="rules.md", eid="eeff00001122ffee"),
        ]
        saved = []
        with (
            patch("memory.load_memory", return_value=entries),
            patch("memory.save_memory", side_effect=lambda x: saved.append(x)),
        ):
            # Select entry 1, then confirm
            result = runner.invoke(cli, ["memory", "remove"], input="1\ny\n")
        assert result.exit_code == 0
        assert saved
        assert len(saved[-1]) == 1

    def test_interactive_q_cancels(self, runner, cli):
        entries = [_raw_file_entry()]
        saved = []
        with (
            patch("memory.load_memory", return_value=entries),
            patch("memory.save_memory", side_effect=lambda x: saved.append(x)),
        ):
            result = runner.invoke(cli, ["memory", "remove"], input="q\n")
        assert "Cancelled" in result.output
        assert not saved

    def test_interactive_out_of_range(self, runner, cli):
        entries = [_raw_file_entry()]
        saved = []
        with (
            patch("memory.load_memory", return_value=entries),
            patch("memory.save_memory", side_effect=lambda x: saved.append(x)),
        ):
            result = runner.invoke(cli, ["memory", "remove"], input="99\n")
        assert "Invalid" in result.output or result.exit_code == 0
        assert not saved

    def test_interactive_shows_table(self, runner, cli):
        entries = [_raw_file_entry(tool="claude-code")]
        with (
            patch("memory.load_memory", return_value=entries),
            patch("memory.save_memory"),
        ):
            result = runner.invoke(cli, ["memory", "remove"], input="q\n")
        assert "claude-code" in result.output
